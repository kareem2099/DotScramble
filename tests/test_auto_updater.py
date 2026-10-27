"""
Unit tests for core/auto_updater.py: version compare, asset choice,
checksum + GPG verification, guarded downloads, install and UI threading.
No test touches the network.
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import auto_updater as au  # noqa: E402
from core.auto_updater import UpdateError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GPG = shutil.which("gpg")
GPGV = shutil.which("gpgv")


def _release_assets(tag="v1.4.1"):
    base = f"https://github.com/kareem2099/DotScramble/releases/download/{tag}/"
    names = list(au.ASSET_NAMES.values())
    names += [n + ".asc" for n in names] + ["SHA256SUMS"]
    return [{"name": n, "browser_download_url": base + n, "size": 2 * 1024 * 1024} for n in names]


# ── Versions ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tag, expected", [
    ("v1.4.1", (1, 4, 1)),
    ("1.4.1", (1, 4, 1)),
    ("v2.0", (2, 0, 0)),
    (" v1.10.3 ", (1, 10, 3)),
    ("v1.5.0-beta.1", None),
    ("latest", None),
    ("", None),
    (None, None),
])
def test_parse_version(tag, expected):
    assert au.parse_version(tag) == expected


@pytest.mark.parametrize("latest, current, newer", [
    ("v1.4.1", "1.4.1", False),     # same version, 'v' prefix ignored
    ("v1.4.0", "1.4.1", False),     # never downgrade
    ("v1.4.2", "1.4.1", True),
    ("v1.10.0", "1.9.9", True),     # numeric, not string, compare
    ("v1.5.0-rc.1", "1.4.1", False),  # pre-releases are not offered
    ("garbage", "1.4.1", False),
])
def test_is_newer(latest, current, newer):
    assert au.is_newer(latest, current) is newer


def test_app_version_is_parseable():
    assert au.parse_version(au.APP_VERSION) is not None


# ── Install kind & asset choice ─────────────────────────────────────────────

def test_detect_install_kind(monkeypatch):
    kind = au.detect_install_kind
    assert kind(frozen=False, executable="/usr/bin/python3", environ={}, system="linux") == "source"
    assert kind(frozen=True, executable="C:/x/DotScramble.exe", environ={}, system="win32") == "unsupported"
    assert kind(frozen=True, executable="/tmp/.mount_X/usr/bin/DotScramble",
                environ={"APPIMAGE": "/home/u/DotScramble.AppImage"}, system="linux") == "appimage"
    assert kind(frozen=True, executable="/home/u/apps/DotScramble", environ={}, system="linux") == "tarball"

    monkeypatch.setattr(au.os.path, "realpath", lambda p: p)
    monkeypatch.setattr(au, "_owned_by_pacman", lambda: True)
    assert kind(frozen=True, executable=au.SYSTEM_EXECUTABLE, environ={}, system="linux") == "pacman"
    monkeypatch.setattr(au, "_owned_by_pacman", lambda: False)
    monkeypatch.setattr(au, "_owned_by_dpkg", lambda: True)
    assert kind(frozen=True, executable=au.SYSTEM_EXECUTABLE, environ={}, system="linux") == "deb"
    monkeypatch.setattr(au, "_owned_by_dpkg", lambda: False)
    assert kind(frozen=True, executable=au.SYSTEM_EXECUTABLE, environ={}, system="linux") == "unsupported"


@pytest.mark.parametrize("kind, name", [
    ("appimage", "DotScramble-Linux-x86_64.AppImage"),
    ("deb", "DotScramble-Linux-x86_64.deb"),
    ("pacman", "DotScramble-Linux-x86_64.pkg.tar.zst"),
    ("tarball", "DotScramble-Linux-x86_64.tar.gz"),
])
def test_pick_asset_per_install_kind(kind, name):
    asset = au.pick_asset(_release_assets(), kind, machine="x86_64")
    assert asset["name"] == name


def test_pick_asset_rejects_other_arch_and_missing():
    assets = _release_assets()
    assert au.pick_asset(assets, "appimage", machine="aarch64") is None
    assert au.pick_asset(assets, "source", machine="x86_64") is None
    assert au.pick_asset(assets, "unsupported", machine="x86_64") is None
    no_appimage = [a for a in assets if a["name"] != au.ASSET_NAMES["appimage"]]
    # Never fall back to a different package type (e.g. a .deb for an AppImage install)
    assert au.pick_asset(no_appimage, "appimage", machine="x86_64") is None


# ── Checksums ───────────────────────────────────────────────────────────────

def test_parse_sha256sums_formats():
    h1, h2, h3 = "a" * 64, "B" * 64, "c" * 64
    text = (f"[SHA-256 Checksums]\n{h1}  DotScramble-Linux-x86_64.deb\n"
            f"{h2} *DotScramble-Linux-x86_64.AppImage\nnot a line\n{h3}  name with space.tar.gz\n")
    assert au.parse_sha256sums(text) == {
        "DotScramble-Linux-x86_64.deb": h1,
        "DotScramble-Linux-x86_64.AppImage": "b" * 64,
        "name with space.tar.gz": h3,
    }


def test_parse_real_release_sha256sums():
    sums_file = ROOT / "release" / "SHA256SUMS"
    if not sums_file.exists():
        pytest.skip("no local release/SHA256SUMS")
    sums = au.parse_sha256sums(sums_file.read_text())
    for kind in ("appimage", "deb", "pacman", "tarball"):
        assert len(sums[au.ASSET_NAMES[kind]]) == 64


def test_verify_download_checksums(tmp_path, monkeypatch):
    signature_checked = []
    monkeypatch.setattr(au, "verify_signature", lambda f, s: signature_checked.append(f))
    f = tmp_path / "pkg.deb"
    f.write_bytes(b"payload")
    good = hashlib.sha256(b"payload").hexdigest()

    au.verify_download(f, "pkg.deb", f"{good}  pkg.deb\n", tmp_path / "sig", f"sha256:{good}")
    assert signature_checked == [f]

    with pytest.raises(UpdateError, match="mismatch"):
        au.verify_download(f, "pkg.deb", f"{'0' * 64}  pkg.deb\n", tmp_path / "sig")
    with pytest.raises(UpdateError, match="no entry"):
        au.verify_download(f, "pkg.deb", f"{good}  other.deb\n", tmp_path / "sig")
    with pytest.raises(UpdateError, match="GitHub"):
        au.verify_download(f, "pkg.deb", f"{good}  pkg.deb\n", tmp_path / "sig", "sha256:" + "0" * 64)
    assert len(signature_checked) == 1   # never reached the signature on a bad hash


# ── GPG ─────────────────────────────────────────────────────────────────────

def test_embedded_key_matches_public_key_file():
    assert au.RELEASE_PUBLIC_KEY.strip() == (ROOT / "public_key.asc").read_text().strip()


@pytest.mark.skipif(not GPG, reason="gpg not installed")
def test_embedded_key_has_pinned_fingerprint(tmp_path):
    keyring = tmp_path / "k.gpg"
    keyring.write_bytes(au._dearmor(au.RELEASE_PUBLIC_KEY))
    out = subprocess.run([GPG, "--homedir", str(tmp_path), "--with-colons", "--show-keys", str(keyring)],
                         capture_output=True, text=True, check=True).stdout
    fingerprints = [line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:")]
    assert fingerprints[0] == au.RELEASE_KEY_FINGERPRINT


def _make_key(home, name):
    home.mkdir(mode=0o700)
    subprocess.run([GPG, "--homedir", str(home), "--batch", "--passphrase", "", "--quick-gen-key",
                    f"{name} <{name}@test.invalid>", "ed25519", "sign", "never"],
                   check=True, capture_output=True)
    out = subprocess.run([GPG, "--homedir", str(home), "--with-colons", "--list-keys"],
                         capture_output=True, text=True, check=True).stdout
    fpr = next(line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:"))
    armored = subprocess.run([GPG, "--homedir", str(home), "--armor", "--export", fpr],
                             capture_output=True, text=True, check=True).stdout
    return fpr, armored


def _sign(home, path):
    subprocess.run([GPG, "--homedir", str(home), "--batch", "--yes", "--detach-sign", "--armor",
                    "--output", str(path) + ".asc", str(path)], check=True, capture_output=True)
    return Path(str(path) + ".asc")


@pytest.mark.skipif(not (GPG and GPGV), reason="gpg/gpgv not installed")
def test_verify_signature_with_pinned_key(tmp_path, monkeypatch):
    release_home, other_home = tmp_path / "release", tmp_path / "other"
    fpr, armored = _make_key(release_home, "release")
    _make_key(other_home, "attacker")
    monkeypatch.setattr(au, "RELEASE_PUBLIC_KEY", armored)
    monkeypatch.setattr(au, "RELEASE_KEY_FINGERPRINT", fpr)

    f = tmp_path / "DotScramble.AppImage"
    f.write_bytes(os.urandom(4096))
    sig = _sign(release_home, f)
    au.verify_signature(f, sig)          # good signature by the pinned key

    f.write_bytes(f.read_bytes() + b"x")  # tampered file
    with pytest.raises(UpdateError, match="signature"):
        au.verify_signature(f, sig)

    g = tmp_path / "evil.AppImage"
    g.write_bytes(b"evil")
    with pytest.raises(UpdateError, match="signature"):
        au.verify_signature(g, _sign(other_home, g))  # signed, but by another key


@pytest.mark.skipif(not GPGV, reason="gpgv not installed")
def test_verify_real_release_signature():
    # The actual v1.4.1 SHA256SUMS + AppImage + .asc built by build.py.
    release = ROOT / "release"
    name = au.ASSET_NAMES["appimage"]
    if not (release / name).exists() or not (release / (name + ".asc")).exists():
        pytest.skip("no local release artifacts")
    packets = subprocess.run(["gpg", "--list-packets", str(release / (name + ".asc"))],
                             capture_output=True, text=True).stdout
    if au.RELEASE_KEY_FINGERPRINT not in packets:
        pytest.skip("local release artifacts were signed by an earlier release key")
    au.verify_download(release / name, name, (release / "SHA256SUMS").read_text(), release / (name + ".asc"))


def test_missing_gpgv_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(au.shutil, "which", lambda name: None)
    with pytest.raises(UpdateError, match="gpgv"):
        au.verify_signature(tmp_path / "f", tmp_path / "f.asc")


# ── Downloads ───────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.is_redirect = status in (301, 302, 307, 308)

    def iter_content(self, chunk_size):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def _fake_get(routes, seen):
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs.get("allow_redirects") is False
        return routes[url]
    return get


GH = "https://github.com/kareem2099/DotScramble/releases/download/v9.9.9/a.bin"
CDN = "https://release-assets.githubusercontent.com/x/a.bin"


def test_download_follows_github_redirect(tmp_path, monkeypatch):
    body = os.urandom(300 * 1024)
    seen, progress = [], []
    monkeypatch.setattr(au.requests, "get", _fake_get({
        GH: FakeResponse(302, headers={"location": CDN}),
        CDN: FakeResponse(200, body, {"content-length": str(len(body))}),
    }, seen))
    dest = au.download_file(GH, tmp_path / "a.bin", 1024 * 1024, expected_size=len(body), progress=progress.append)
    assert dest.read_bytes() == body
    assert seen == [GH, CDN]
    assert progress[-1] == 100
    assert not list(tmp_path.glob("*.part"))


def test_download_rejects_redirect_to_foreign_host(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(au.requests, "get", _fake_get({
        GH: FakeResponse(302, headers={"location": "https://evil.example/a.bin"}),
    }, seen))
    with pytest.raises(UpdateError, match="Unauthorized"):
        au.download_file(GH, tmp_path / "a.bin", 1024)
    assert seen == [GH]   # never connected to the foreign host
    assert not (tmp_path / "a.bin").exists()


@pytest.mark.parametrize("body, headers, max_bytes, expected_size, match", [
    (b"x" * 2048, {"content-length": "2048"}, 1024, None, "size"),        # header over the cap
    (b"x" * 2048, {}, 1024, None, "larger"),                               # stream over the cap
    (b"x" * 100, {"content-length": "100"}, 1024, 200, "size"),           # not what GitHub listed
    (b"x" * 100, {}, 1024, 200, "incomplete"),                            # truncated
    (b"", {}, 1024, 4096, "larger"),                                        # listed size over the cap
])
def test_download_size_limits(tmp_path, monkeypatch, body, headers, max_bytes, expected_size, match):
    monkeypatch.setattr(au.requests, "get", _fake_get({GH: FakeResponse(200, body, headers)}, []))
    with pytest.raises(UpdateError, match=match):
        au.download_file(GH, tmp_path / "a.bin", max_bytes, expected_size=expected_size)
    assert not list(tmp_path.iterdir())


def test_download_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(au.requests, "get", _fake_get({GH: FakeResponse(200, b"x" * 4096)}, []))
    with pytest.raises(UpdateError, match="cancelled"):
        au.download_file(GH, tmp_path / "a.bin", 1 << 20, cancelled=lambda: True)
    assert not list(tmp_path.iterdir())


def test_download_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr(au.requests, "get", _fake_get({GH: FakeResponse(404)}, []))
    with pytest.raises(UpdateError, match="404"):
        au.download_file(GH, tmp_path / "a.bin", 1024)


# ── Installing ──────────────────────────────────────────────────────────────

def test_install_appimage_replaces_appimage_file(tmp_path):
    current = tmp_path / "DotScramble.AppImage"
    current.write_bytes(b"old")
    new = tmp_path / "download.AppImage"
    new.write_bytes(b"new")
    cmd = au.install_update("appimage", new, executable="/tmp/.mount_X/usr/bin/DotScramble",
                            environ={"APPIMAGE": str(current)})
    assert cmd == [str(current)]
    assert current.read_bytes() == b"new"
    assert os.access(current, os.X_OK)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["DotScramble.AppImage", "download.AppImage"]


def _tarball(path, members):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_install_tarball_extracts_binary(tmp_path):
    exe = tmp_path / "DotScramble"
    exe.write_bytes(b"old")
    archive = tmp_path / "u.tar.gz"
    _tarball(archive, {"DotScramble": b"new binary"})
    assert au.install_update("tarball", archive, executable=str(exe)) == [str(exe)]
    assert exe.read_bytes() == b"new binary"
    assert os.access(exe, os.X_OK)


def test_install_tarball_without_binary_keeps_old(tmp_path):
    exe = tmp_path / "DotScramble"
    exe.write_bytes(b"old")
    archive = tmp_path / "u.tar.gz"
    _tarball(archive, {"../DotScramble": b"evil", "README": b"hi"})
    with pytest.raises(UpdateError, match="not found"):
        au.install_update("tarball", archive, executable=str(exe))
    assert exe.read_bytes() == b"old"


@pytest.mark.parametrize("kind, expected", [
    ("deb", ["/usr/bin/pkexec", "dpkg", "-i", "/c/pkg"]),
    ("pacman", ["/usr/bin/pkexec", "pacman", "-U", "--noconfirm", "/c/pkg"]),
])
def test_install_system_package_uses_pkexec(monkeypatch, kind, expected):
    calls = []
    monkeypatch.setattr(au.shutil, "which", lambda name: f"/usr/bin/{name}")

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(au.subprocess, "run", run)
    assert au.install_update(kind, "/c/pkg")[0] in (au.SYSTEM_LAUNCHER, au.SYSTEM_EXECUTABLE)
    assert calls == [expected]

    monkeypatch.setattr(au.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 126, "", ""))
    with pytest.raises(UpdateError, match="cancelled"):
        au.install_update(kind, "/c/pkg")


def test_install_refuses_unsupported_kinds():
    for kind in ("source", "unsupported"):
        with pytest.raises(UpdateError):
            au.install_update(kind, "/c/pkg")


def test_restart_environment():
    env = au.restart_environment({"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/opt/lib", "X": "1"})
    assert env == {"LD_LIBRARY_PATH": "/opt/lib", "PYINSTALLER_RESET_ENVIRONMENT": "1", "X": "1"}
    assert "LD_LIBRARY_PATH" not in au.restart_environment({"LD_LIBRARY_PATH": "/tmp/_MEI123"})


# ── Qt: results land on the UI thread, the UI thread never waits ────────────

@pytest.fixture
def qt_root():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    root = QWidget()
    yield app, root
    root.deleteLater()


def _pump(app, until, timeout=5):
    end = time.monotonic() + timeout
    while not until() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_check_runs_off_the_ui_thread(qt_root, monkeypatch):
    app, root = qt_root
    from PySide6.QtCore import QThread
    main = QThread.currentThread()
    fetch_threads, shown = [], []

    def slow_fetch(owner, repo):
        fetch_threads.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.5)
        return {"tag_name": "v0.0.1", "assets": []}
    monkeypatch.setattr(au, "fetch_latest_release", slow_fetch)
    monkeypatch.setattr(au.QMessageBox, "information",
                        lambda *a: shown.append((QThread.currentThread() is main, a[2])))

    updater = au.AutoUpdater(root)
    started = time.monotonic()
    updater.check_for_updates(silent=False)
    assert time.monotonic() - started < 0.2      # returned without waiting for GitHub
    _pump(app, lambda: shown)
    assert fetch_threads == [False]
    assert shown and shown[0][0] is True          # dialog shown from the UI thread
    assert not updater._busy


def test_check_error_is_reported_on_ui_thread(qt_root, monkeypatch):
    app, root = qt_root
    from PySide6.QtCore import QThread
    main = QThread.currentThread()
    errors = []

    def failing_fetch(owner, repo):
        raise UpdateError("GitHub returned HTTP 500")
    monkeypatch.setattr(au, "fetch_latest_release", failing_fetch)
    monkeypatch.setattr(au.QMessageBox, "critical",
                        lambda *a: errors.append((QThread.currentThread() is main, a[2])))
    au.AutoUpdater(root).check_for_updates(silent=False)
    _pump(app, lambda: errors)
    assert errors and errors[0][0] is True and "500" in errors[0][1]


def test_silent_check_skipped_from_source(qt_root, monkeypatch):
    _, root = qt_root
    monkeypatch.setattr(au, "fetch_latest_release",
                        lambda *a: pytest.fail("source checkouts must not auto-update"))
    updater = au.AutoUpdater(root)
    assert updater.kind == "source"
    updater.check_for_updates_silently()
    assert not updater._busy


def test_download_flow_marks_update_ready(qt_root, monkeypatch, tmp_path):
    app, root = qt_root
    monkeypatch.setattr(au, "CACHE_DIR", tmp_path / "updates")
    payload = os.urandom(2 * 1024 * 1024)
    name = au.ASSET_NAMES["tarball"]
    sums = f"{hashlib.sha256(payload).hexdigest()}  {name}\n".encode()
    files = {name: payload, name + ".asc": b"sig", "SHA256SUMS": sums}

    def fake_download(url, dest, max_bytes, expected_size=None, progress=None, cancelled=None):
        Path(dest).write_bytes(files[url.rsplit("/", 1)[1]])
        return Path(dest)
    monkeypatch.setattr(au, "download_file", fake_download)
    monkeypatch.setattr(au, "verify_signature", lambda f, s: None)

    updater = au.AutoUpdater(root)
    updater.kind = "tarball"
    ready = []
    updater.updateReady.connect(ready.append)
    release = {"tag_name": "v99.0.0", "assets": _release_assets("v99.0.0")}
    asset = au.pick_asset(release["assets"], "tarball", machine="x86_64")
    asset["size"] = len(payload)
    updater._busy = True
    threading.Thread(target=updater._download_worker, args=(release, asset, True)).start()
    _pump(app, lambda: ready)
    assert ready == [True]
    assert updater.update_ready and updater.ready_version == "v99.0.0"
    assert updater.ready_file_path.read_bytes() == payload


def test_tampered_download_is_deleted(qt_root, monkeypatch, tmp_path):
    app, root = qt_root
    monkeypatch.setattr(au, "CACHE_DIR", tmp_path / "updates")
    name = au.ASSET_NAMES["tarball"]
    files = {name: os.urandom(2 * 1024 * 1024), name + ".asc": b"sig",
             "SHA256SUMS": f"{'0' * 64}  {name}\n".encode()}

    def fake_download(url, dest, max_bytes, expected_size=None, progress=None, cancelled=None):
        Path(dest).write_bytes(files[url.rsplit("/", 1)[1]])
        return Path(dest)
    monkeypatch.setattr(au, "download_file", fake_download)
    done = []
    updater = au.AutoUpdater(root)
    updater._downloaded.connect(lambda silent, err: done.append(err))
    release = {"tag_name": "v99.0.0", "assets": _release_assets("v99.0.0")}
    asset = au.pick_asset(release["assets"], "tarball", machine="x86_64")
    threading.Thread(target=updater._download_worker, args=(release, asset, True)).start()
    _pump(app, lambda: done)
    assert "mismatch" in done[0]
    assert not updater.update_ready
    assert not (tmp_path / "updates" / f"v99.0.0--{name}").exists()
