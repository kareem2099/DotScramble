"""
Auto-update for packaged DotScramble builds.

Flow: GitHub ``/releases/latest`` → pick the asset that matches how this copy
was installed (AppImage, .deb, Arch package, portable tar.gz) → download it
with a size cap → verify it against the release's SHA256SUMS *and* its
detached GPG signature (.asc) made with the pinned FreeRave release key →
install → restart.

Network, hashing and installing run on worker threads. Their results reach
the UI through Qt signals, which Qt queues onto the main thread.
"""
import base64
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from src.config import APP_VERSION, UPDATE_CONFIG, DIRS

logger = logging.getLogger(__name__)

# ── Release trust anchors ───────────────────────────────────────────────────
# FreeRave release signing key (same as public_key.asc; build.py signs every
# artifact with it). Pinned by fingerprint so a hijacked repo can't swap it.
RELEASE_KEY_FINGERPRINT = "0F0467813146DE68272EDC82145D345956DE18D2"
RELEASE_PUBLIC_KEY = """\
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEatt3vRYJKwYBBAHaRw8BAQdAwR3C9s6HNSyNbyrZezTGq70oEGdUIILHmU3C
cARTEuG0IUZyZWVSYXZlIDxrYXJlZW0yMDk5MDdAZ21haWwuY29tPoiWBBMWCgA+
FiEEDwRngTFG3mgnLtyCFF00WVbeGNIFAmrbd70CGwMFCQPCZwAFCwkIBwIGFQoJ
CAsCBBYCAwECHgECF4AACgkQFF00WVbeGNKiBQEAvykcyYV+I4REw/YnHNR75yvS
aFmqD/Z8YOpMs/vqiXMBAOsGNvekPr78zteVFnaWS8MFazfihB3nJKxd0Pe5HeMP
=IJjH
-----END PGP PUBLIC KEY BLOCK-----"""

CHECKSUMS_ASSET = "SHA256SUMS"
SIGNATURE_SUFFIX = ".asc"

# One asset per install kind; build.py only produces x86_64 Linux builds.
ASSET_NAMES = {
    "appimage": "DotScramble-Linux-x86_64.AppImage",
    "deb": "DotScramble-Linux-x86_64.deb",
    "pacman": "DotScramble-Linux-x86_64.pkg.tar.zst",
    "tarball": "DotScramble-Linux-x86_64.tar.gz",
}

# Where the .deb / Arch packages put the binary and its launcher.
SYSTEM_EXECUTABLE = "/usr/share/dotscramble/DotScramble"
SYSTEM_LAUNCHER = "/usr/bin/dotscramble"
PACKAGE_NAME = "dotscramble"

MAX_UPDATE_BYTES = 512 * 1024 * 1024   # releases are ~215 MB today
MIN_UPDATE_BYTES = 1024 * 1024
MAX_SMALL_ASSET_BYTES = 64 * 1024      # SHA256SUMS and .asc files
MAX_REDIRECTS = 5

ALLOWED_HOSTS = ("github.com", "api.github.com")
ALLOWED_HOST_SUFFIXES = (".githubusercontent.com",)  # release-assets., objects.

HTTP_HEADERS = {"User-Agent": f"DotScramble-Updater/{APP_VERSION}"}
STATE_FILE = DIRS['temp'] / "update_state.json"
CACHE_DIR = DIRS['temp'] / "updates"


class UpdateError(Exception):
    """A failure the user should see; the message is already human-readable."""


# ── Pure helpers (no Qt, unit-tested) ───────────────────────────────────────

def parse_version(tag):
    """'v1.4.1' / '1.4' → (1, 4, 1) / (1, 4, 0). Pre-release or junk tags → None."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", (tag or "").strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def is_newer(latest_tag, current_version):
    """True only when *latest_tag* is strictly newer: never offer a downgrade."""
    latest, current = parse_version(latest_tag), parse_version(current_version)
    return bool(latest and current and latest > current)


def _owned_by_pacman():
    return any(Path("/var/lib/pacman/local").glob(f"{PACKAGE_NAME}-[0-9]*"))


def _owned_by_dpkg():
    return Path(f"/var/lib/dpkg/info/{PACKAGE_NAME}.list").exists()


def detect_install_kind(frozen=None, executable=None, environ=None, system=None):
    """
    How this copy was installed, which decides the asset and how to replace it:
    'source', 'appimage', 'deb', 'pacman', 'tarball' or 'unsupported'.
    """
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    environ = os.environ if environ is None else environ
    system = sys.platform if system is None else system

    if not frozen:
        return "source"
    if not system.startswith("linux"):
        return "unsupported"   # only Linux builds are published and signed
    if environ.get("APPIMAGE"):
        # sys.executable lives inside the read-only AppImage mount; $APPIMAGE
        # is the file on disk that has to be replaced.
        return "appimage"
    if os.path.realpath(executable) == SYSTEM_EXECUTABLE:
        if _owned_by_pacman():
            return "pacman"
        if _owned_by_dpkg():
            return "deb"
        return "unsupported"
    return "tarball"


def pick_asset(assets, kind, machine=None):
    """The release asset (GitHub API dict) for this install kind, or None."""
    machine = (machine or platform.machine()).lower()
    if machine not in ("x86_64", "amd64"):
        return None
    wanted = ASSET_NAMES.get(kind)
    for asset in assets or []:
        if asset.get("name") == wanted and asset.get("browser_download_url"):
            return asset
    return None


def find_asset(assets, name):
    for asset in assets or []:
        if asset.get("name") == name and asset.get("browser_download_url"):
            return asset
    return None


def parse_sha256sums(text):
    """`sha256sum` output ('<hex>  <name>' or '<hex> *<name>') → {name: hex}."""
    sums = {}
    for line in (text or "").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(\S.*)", line.strip())
        if match:
            sums[match.group(2).strip()] = match.group(1).lower()
    return sums


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_download_url(url):
    """Only HTTPS to GitHub (and its release CDN) may be fetched."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = host in ALLOWED_HOSTS or any(host.endswith(s) for s in ALLOWED_HOST_SUFFIXES)
    if parsed.scheme != "https" or not allowed:
        raise UpdateError(f"Unauthorized download host: {parsed.scheme}://{host}")


def _dearmor(armored):
    """ASCII-armored OpenPGP block → binary packets (what gpgv --keyring reads)."""
    body = armored.strip().split("\n\n", 1)[1]
    lines = [line.strip() for line in body.splitlines()
             if line.strip() and not line.startswith("-----")]
    if lines and re.fullmatch(r"=[A-Za-z0-9+/]{4}", lines[-1]):
        lines.pop()   # CRC-24 checksum line
    return base64.b64decode("".join(lines))


def verify_signature(file_path, signature_path, gpgv=None):
    """
    Check a detached signature against the pinned release key only.
    Raises UpdateError unless gpgv reports a valid signature by that key.
    """
    gpgv = gpgv or shutil.which("gpgv")
    if not gpgv:
        raise UpdateError("gpgv is not installed, so the update's signature can't be checked.")
    with tempfile.TemporaryDirectory(prefix="dotscramble-gpg-") as home:
        keyring = Path(home) / "release-key.gpg"
        keyring.write_bytes(_dearmor(RELEASE_PUBLIC_KEY))
        try:
            result = subprocess.run(
                [gpgv, "--homedir", home, "--status-fd", "1", "--keyring", str(keyring),
                 str(signature_path), str(file_path)],
                capture_output=True, text=True, timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise UpdateError(f"Signature check could not run: {e}") from e
    valid_by = [line.split()[2:] for line in result.stdout.splitlines()
                if line.startswith("[GNUPG:] VALIDSIG ")]
    if result.returncode != 0 or not any(RELEASE_KEY_FINGERPRINT in fields for fields in valid_by):
        raise UpdateError("The update's GPG signature is not valid for the DotScramble release key.")


def verify_download(file_path, asset_name, sums_text, signature_path, api_digest=None):
    """SHA256SUMS + GitHub's own digest + GPG signature. Raises UpdateError."""
    expected = parse_sha256sums(sums_text).get(asset_name)
    if not expected:
        raise UpdateError(f"{CHECKSUMS_ASSET} has no entry for {asset_name}.")
    actual = sha256_file(file_path)
    if actual != expected:
        raise UpdateError(f"Checksum mismatch for {asset_name}.")
    if api_digest and api_digest.lower() != f"sha256:{actual}":
        raise UpdateError(f"{asset_name} doesn't match the checksum GitHub reports.")
    verify_signature(file_path, signature_path)


def _open_checked(url, timeout):
    """GET *url*, following redirects by hand so every hop is host-checked."""
    for _ in range(MAX_REDIRECTS + 1):
        check_download_url(url)
        response = requests.get(url, stream=True, timeout=timeout,
                                headers=HTTP_HEADERS, allow_redirects=False)
        if response.is_redirect:
            url = urljoin(url, response.headers.get("location", ""))
            response.close()
            continue
        if response.status_code != 200:
            response.close()
            raise UpdateError(f"Download failed: HTTP {response.status_code}")
        return response
    raise UpdateError("Download failed: too many redirects")


def download_file(url, dest, max_bytes, expected_size=None, progress=None, cancelled=None):
    """
    Stream *url* into *dest* (via a .part file), never writing more than
    *max_bytes* and, when GitHub told us the size, exactly *expected_size*.
    """
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    if expected_size and expected_size > max_bytes:
        raise UpdateError("Update file is larger than allowed.")
    try:
        with _open_checked(url, timeout=(10, 60)) as response:
            length = int(response.headers.get("content-length") or 0)
            if length > max_bytes or (expected_size and length and length != expected_size):
                raise UpdateError("Update file has an unexpected size.")
            total = expected_size or length
            written = 0
            with open(part, "wb") as f:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if cancelled and cancelled():
                        raise UpdateError("Download cancelled.")
                    written += len(chunk)
                    if written > max_bytes:
                        raise UpdateError("Update file is larger than allowed.")
                    f.write(chunk)
                    if progress and total:
                        progress(min(100, written * 100 // total))
        if expected_size and written != expected_size:
            raise UpdateError("Download was incomplete.")
        os.replace(part, dest)
    except requests.RequestException as e:
        raise UpdateError(f"Download failed: {e}") from e
    finally:
        part.unlink(missing_ok=True)
    return dest


def fetch_latest_release(owner, repo, timeout=10):
    """The newest published, non-prerelease release from the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        response = requests.get(url, timeout=timeout,
                                headers={**HTTP_HEADERS, "Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise UpdateError(f"Could not reach GitHub: {e}") from e
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise UpdateError("GitHub rate limit reached, try again later.")
    if response.status_code != 200:
        raise UpdateError(f"GitHub returned HTTP {response.status_code}")
    data = response.json()
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise UpdateError("GitHub returned an unexpected response.")
    return data


def extract_tarball_binary(archive, dest, binary_name="DotScramble"):
    """Copy the single top-level executable out of the portable tar.gz."""
    with tarfile.open(archive, "r:gz") as tar:
        member = next((m for m in tar.getmembers()
                       if m.isfile() and m.name in (binary_name, f"./{binary_name}")), None)
        if member is None or member.size > MAX_UPDATE_BYTES:
            raise UpdateError(f"{binary_name} not found in the update archive.")
        with tar.extractfile(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)
    os.chmod(dest, 0o755)


def _replace_file(source, target, extract=None):
    """Atomically swap *target* for *source* (or what *extract* writes)."""
    target = Path(target)
    staged = target.with_name(f".{target.name}.update")
    try:
        if extract:
            extract(source, staged)
        else:
            shutil.copyfile(source, staged)
            os.chmod(staged, 0o755)
        os.replace(staged, target)   # the running process keeps its old inode
    except PermissionError as e:
        raise UpdateError(f"No permission to replace {target}. Download the update manually.") from e
    finally:
        staged.unlink(missing_ok=True)


def install_update(kind, file_path, executable=None, environ=None):
    """
    Put the verified update in place. Returns the command that starts the new
    version. Runs on a worker thread (pkexec waits for the user's password).
    """
    environ = os.environ if environ is None else environ
    executable = executable or sys.executable
    if kind == "appimage":
        target = environ["APPIMAGE"]
        _replace_file(file_path, target)
        return [target]
    if kind == "tarball":
        _replace_file(file_path, executable, extract=extract_tarball_binary)
        return [executable]
    if kind in ("deb", "pacman"):
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise UpdateError("pkexec is not available to install the package.")
        if kind == "deb":
            cmd = [pkexec, "dpkg", "-i", str(file_path)]
        else:
            cmd = [pkexec, "pacman", "-U", "--noconfirm", str(file_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as e:
            raise UpdateError(str(e)) from e
        if result.returncode in (126, 127):
            raise UpdateError("Authorization was cancelled.")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise UpdateError(detail[-1] if detail else f"exit code {result.returncode}")
        launcher = SYSTEM_LAUNCHER if os.path.exists(SYSTEM_LAUNCHER) else SYSTEM_EXECUTABLE
        return [launcher]
    raise UpdateError("This installation can't be updated automatically.")


def restart_environment(environ=None):
    """Env for relaunching ourselves: a fresh PyInstaller bootstrap, original LD path."""
    env = dict(os.environ if environ is None else environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is not None:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


# ── Qt side ─────────────────────────────────────────────────────────────────

class AutoUpdater(QObject):
    """Owns the update flow for the main window; every public method is UI-thread only."""

    updateReady = Signal(bool)            # silent: True for the background check

    _checked = Signal(bool, object, str)  # silent, release dict or None, error
    _progress = Signal(int)
    _downloaded = Signal(bool, str)       # silent, error ("" on success)
    _installed = Signal(object, str)      # restart command, error

    def __init__(self, root_window):
        super().__init__(root_window)
        self.root = root_window
        self.repo_owner = UPDATE_CONFIG['repo_owner']
        self.repo_name = UPDATE_CONFIG['repo_name']
        self.kind = detect_install_kind()
        self.update_ready = False
        self.ready_file_path = None
        self.ready_version = None
        self._release = None
        self._busy = False
        self._cancel = threading.Event()
        self._dialog = None

        self._checked.connect(self._on_checked)
        self._progress.connect(self._on_progress)
        self._downloaded.connect(self._on_downloaded)
        self._installed.connect(self._on_installed)

    @staticmethod
    def _t(key, **kwargs):
        from src.managers.localization_manager import get_locale_manager
        return get_locale_manager().get(key, **kwargs)

    # ── Checking ────────────────────────────────────────────────────────────

    def check_for_updates(self, silent=False):
        """Help → Check for Updates (silent=False) or the startup check."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._check_worker, args=(silent,), daemon=True).start()

    def check_for_updates_silently(self):
        """Startup check: packaged builds only, at most every check_interval_days."""
        if self.kind in ("source", "unsupported") or not self._interval_elapsed():
            return
        self.check_for_updates(silent=True)

    def _interval_elapsed(self):
        days = UPDATE_CONFIG.get('check_interval_days', 0) or 0
        try:
            last = json.loads(STATE_FILE.read_text()).get("last_check", 0)
        except (OSError, ValueError, AttributeError):
            last = 0
        # A downloaded-but-not-installed update is worth re-offering every launch.
        return time.time() - last >= days * 86400 or any(CACHE_DIR.glob("*--*"))

    def _check_worker(self, silent):
        try:
            release = fetch_latest_release(self.repo_owner, self.repo_name)
            try:
                STATE_FILE.write_text(json.dumps({"last_check": time.time()}))
            except OSError:
                pass
            self._checked.emit(silent, release, "")
        except Exception as e:
            self._checked.emit(silent, None, str(e))

    def _on_checked(self, silent, release, error):
        self._busy = False
        if error:
            logger.warning(f"Update check failed: {error}")
            if not silent:
                self._error(self._t("dialogs.info.update_failed", error=error))
            return

        tag = release["tag_name"]
        if not is_newer(tag, APP_VERSION):
            self._cleanup_cache(keep=None)
            if not silent:
                self._info(self._t("dialogs.info.no_updates") + " ✅")
            return

        if self.update_ready and self.ready_version == tag:
            self.updateReady.emit(silent)
            return

        if self.kind == "source":
            if not silent:
                self._info(self._t("dialogs.info.dev_update_available", version=tag))
            return

        asset = pick_asset(release.get("assets"), self.kind)
        if asset is None:
            if not silent:
                self._offer_release_page(release)
            return

        if not silent:
            if QMessageBox.question(
                self.root, self._t("menu.help_items.check_updates"),
                self._t("dialogs.info.update_available", version=tag),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            self._show_progress(self._t("dialogs.info.update_downloading"), cancellable=True)

        self._release = release
        self._busy = True
        self._cancel.clear()
        threading.Thread(target=self._download_worker, args=(release, asset, silent), daemon=True).start()

    def _offer_release_page(self, release):
        url = release.get("html_url") or f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/latest"
        if QMessageBox.question(
            self.root, self._t("menu.help_items.check_updates"),
            self._t("dialogs.info.update_manual", version=release["tag_name"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            import webbrowser
            webbrowser.open(url)

    # ── Downloading & verifying (worker thread) ─────────────────────────────

    def _download_worker(self, release, asset, silent):
        tag, name = release["tag_name"], asset["name"]
        target = CACHE_DIR / f"{tag}--{name}"
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cleanup_cache(keep=target)
            assets = release.get("assets")
            sums_asset = find_asset(assets, CHECKSUMS_ASSET)
            sig_asset = find_asset(assets, name + SIGNATURE_SUFFIX)
            if not sums_asset or not sig_asset:
                raise UpdateError(f"Release {tag} has no {CHECKSUMS_ASSET} or signature for {name}.")

            sums_path = download_file(sums_asset["browser_download_url"], CACHE_DIR / CHECKSUMS_ASSET,
                                      MAX_SMALL_ASSET_BYTES)
            sig_path = download_file(sig_asset["browser_download_url"], CACHE_DIR / (name + SIGNATURE_SUFFIX),
                                     MAX_SMALL_ASSET_BYTES)
            sums_text = sums_path.read_text(errors="replace")

            if target.exists():
                # Downloaded on an earlier launch: re-verify instead of fetching 200 MB again.
                try:
                    verify_download(target, name, sums_text, sig_path, asset.get("digest"))
                except UpdateError:
                    target.unlink(missing_ok=True)

            if not target.exists():
                size = asset.get("size") or None
                if size is not None and size < MIN_UPDATE_BYTES:
                    raise UpdateError("Update file is too small to be valid.")
                download_file(asset["browser_download_url"], target, MAX_UPDATE_BYTES,
                              expected_size=size, progress=self._progress.emit,
                              cancelled=self._cancel.is_set)
                try:
                    verify_download(target, name, sums_text, sig_path, asset.get("digest"))
                except UpdateError:
                    target.unlink(missing_ok=True)
                    raise

            self.ready_file_path = target
            self.ready_version = tag
            self._downloaded.emit(silent, "")
        except Exception as e:
            self._downloaded.emit(silent, str(e) or e.__class__.__name__)

    def _on_progress(self, percent):
        if self._dialog is not None:
            self._dialog.setValue(percent)

    def _on_downloaded(self, silent, error):
        self._busy = False
        self._close_progress()
        if error:
            logger.warning(f"Update download failed: {error}")
            if not silent and not self._cancel.is_set():
                self._error(self._t("dialogs.info.update_failed", error=error))
            return
        self.update_ready = True
        self.updateReady.emit(silent)

    # ── Installing & restarting ─────────────────────────────────────────────

    def apply_pending_update(self):
        """Install the verified download, then restart into the new version."""
        if self._busy or not self.update_ready or not self.ready_file_path \
                or not Path(self.ready_file_path).exists():
            return
        self._busy = True
        self._show_progress(self._t("dialogs.info.update_installing"), cancellable=False)
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        try:
            command = install_update(self.kind, self.ready_file_path)
            self._installed.emit(command, "")
        except Exception as e:
            self._installed.emit(None, str(e) or e.__class__.__name__)

    def _on_installed(self, command, error):
        self._busy = False
        self._close_progress()
        if error:
            logger.error(f"Update install failed: {error}")
            self._error(self._t("dialogs.info.update_install_failed", error=error))
            return

        self.update_ready = False
        self._cleanup_cache(keep=None)
        # Close (saves window state, DB) before the new copy starts.
        if self.root is not None and not self.root.close():
            return
        try:
            subprocess.Popen(command + sys.argv[1:], env=restart_environment(),
                             start_new_session=True, close_fds=True, cwd=str(Path.home()))
        except OSError as e:
            logger.error(f"Restart after update failed: {e}")
        QApplication.quit()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _cleanup_cache(self, keep):
        try:
            for f in CACHE_DIR.glob("*"):
                if f != keep and f.is_file():
                    f.unlink(missing_ok=True)
            # Files from the old updater (one random name per launch)
            for pattern in ("update_*.bin", "update_*.exe"):
                for f in DIRS['temp'].glob(pattern):
                    f.unlink(missing_ok=True)
        except OSError:
            pass

    def _show_progress(self, label, cancellable):
        self._close_progress()
        dialog = QProgressDialog(label, self._t("ui.ai.cancel"), 0, 100, self.root)
        dialog.setWindowTitle(self._t("menu.help_items.check_updates"))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        if cancellable:
            dialog.canceled.connect(self._cancel.set)
        else:
            dialog.setCancelButton(None)
            dialog.setRange(0, 0)   # busy indicator while installing
        dialog.setValue(0)
        dialog.show()
        self._dialog = dialog

    def _close_progress(self):
        dialog, self._dialog = self._dialog, None
        if dialog is not None:
            try:
                dialog.canceled.disconnect()
            except (RuntimeError, TypeError):
                pass
            dialog.close()
            dialog.deleteLater()

    def _info(self, message):
        QMessageBox.information(self.root, self._t("menu.help_items.check_updates"), message)

    def _error(self, message):
        QMessageBox.critical(self.root, self._t("ui.messages.title_error"), message)
