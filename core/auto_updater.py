import os
import sys
import requests
import subprocess
import threading
import stat
import time
import base64
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox
from PySide6.QtCore import QTimer, Qt

from src.config import APP_VERSION, UPDATE_CONFIG, DIRS

# Cryptographic update verification public key to prevent MITM and repo hijacking
_UPDATE_PUBLIC_KEY_B64 = "DQ0zJAi1S0c+NUhOP3050au9k5/fYwLU45ayTZIFVuI=" # The release signer public key

class AutoUpdater:
    def __init__(self, root_window):
        self.root = root_window  # In PySide6, this is the main window widget
        self.repo_owner = UPDATE_CONFIG['repo_owner']
        self.repo_name = UPDATE_CONFIG['repo_name']
        self.is_frozen = getattr(sys, 'frozen', False)
        self.current_exe = sys.executable if self.is_frozen else sys.argv[0]
        self.current_dir = os.path.dirname(os.path.abspath(self.current_exe))
        self.update_ready = False
        self.ready_file_path = None
        self.on_update_ready_callback = None
        self.temp_dir = DIRS['temp']

    def check_for_updates(self, silent=False):
        if not self._check_environment(silent): return
        threading.Thread(target=self._check_logic_interactive, args=(silent,), daemon=True).start()

    def check_for_updates_silently(self, callback_func):
        if not self._check_environment(True): return
        self.on_update_ready_callback = callback_func
        threading.Thread(target=self._check_logic_silent, daemon=True).start()

    def _check_environment(self, silent):
        if not self.is_frozen and not os.getenv('FORCE_UPDATE_TEST'):
            if not silent:
                QTimer.singleShot(0, lambda: QMessageBox.information(self.root, "Dev Mode", "Cannot update from source code."))
            return False
        return True

    def _check_logic_silent(self):
        try:
            self._cleanup_old_files()
            latest_version, download_url, signature = self._get_latest_release_info()
            if latest_version and latest_version != APP_VERSION and download_url:
                self._download_file(download_url, signature, gui=False)
        except Exception as e:
            print(f"Silent check failed: {e}")

    def _check_logic_interactive(self, silent):
        try:
            self._cleanup_old_files()
            latest_version, download_url, signature = self._get_latest_release_info()
            if not latest_version:
                if not silent: self._show_error("Could not connect.")
                return

            if latest_version != APP_VERSION:
                if download_url:
                    QTimer.singleShot(0, lambda: self._prompt_user(latest_version, download_url, signature))
                else:
                    if not silent: self._show_error("No compatible file found.")
            else:
                if not silent:
                    QTimer.singleShot(0, lambda: QMessageBox.information(self.root, "Up to date", "You are using the latest version ✅"))
        except Exception as e:
            if not silent: self._show_error(f"Error: {e}")

    def _get_latest_release_info(self):
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        response = requests.get(api_url, timeout=5)
        if response.status_code != 200: return None, None, None

        data = response.json()
        # Strip leading 'v' so 'v1.3.0' compares equal to '1.3.0'
        version = data['tag_name'].lstrip('v')
        
        # Read the signature from release body e.g. [SIG: base64_signature]
        body = data.get('body', '')
        signature = None
        if "[SIG:" in body:
            try: signature = body.split("[SIG:")[1].split("]")[0].strip()
            except: pass

        assets = data.get('assets', [])
        url = self._get_asset_url(assets)
        return version, url, signature

    def _get_asset_url(self, assets):
        if sys.platform == "win32":
            targets = ["DotScramble-windows.exe", "DotScramble-Windows-x86_64.exe"]
        elif sys.platform == "darwin":
            targets = ["DotScramble-macos", "DotScramble-macOS.dmg"]
        else:  # Linux: prefer AppImage, fall back to .deb
            targets = ["DotScramble-Linux-x86_64.AppImage", "DotScramble-Linux-x86_64.deb", "DotScramble-linux"]
        asset_map = {a['name']: a['browser_download_url'] for a in assets}
        for t in targets:
            if t in asset_map:
                return asset_map[t]
        return None

    def _verify_binary_signature(self, file_path: Path, signature_b64: str) -> bool:
        """Verify the cryptographic Ed25519 signature of the update binary before executing it"""
        if not signature_b64:
            print("[Security Alert] Update dropped: No digital signature provided.")
            return False
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            with open(file_path, "rb") as f:
                binary_data = f.read()
            sig_bytes = base64.b64decode(signature_b64)
            pub_raw   = base64.b64decode(_UPDATE_PUBLIC_KEY_B64)
            public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
            public_key.verify(sig_bytes, binary_data)
            return True
        except Exception as e:
            print(f"[Security Alert] Cryptographic signature check failed! Target drop. Error: {e}")
            return False

    def _download_file(self, url, signature, gui=False):
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            allowed_domains = ['github.com', 'objects.githubusercontent.com', 'api.github.com']
            domain = parsed_url.netloc.lower()
            if not any(domain == d or domain.endswith('.' + d) for d in allowed_domains):
                raise ValueError(f"Unauthorized download host: {domain}")

            filename = f"update_{int(time.time())}.exe" if sys.platform == "win32" else f"update_{int(time.time())}.bin"
            new_filepath = self.temp_dir / filename

            if gui:
                QTimer.singleShot(0, lambda: self._start_download_gui(url, new_filepath, signature))
            else:
                response = requests.get(url, stream=True)
                with open(new_filepath, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=4096): file.write(chunk)

                if self._verify_binary_signature(new_filepath, signature):
                    self.ready_file_path = new_filepath
                    self.update_ready = True
                    if self.on_update_ready_callback:
                        QTimer.singleShot(0, self.on_update_ready_callback)
                else:
                    try: new_filepath.unlink()
                    except: pass

        except Exception as e:
            if gui:
                self._show_error(str(e))
            else:
                print(f"Download error: {e}")
            raise e

    def apply_pending_update(self):
        if self.ready_file_path and self.ready_file_path.exists():
            self._apply_update(self.ready_file_path)

    def _prompt_user(self, version, url, signature):
        msg = f"New update {version} available! Install now?"
        reply = QMessageBox.question(
            self.root, "Update", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            threading.Thread(target=self._download_file, args=(url, signature, True), daemon=True).start()

    def _start_download_gui(self, url, target_path, signature):
        self.dl_window = QDialog(self.root)
        self.dl_window.setWindowTitle("Updating...")
        self.dl_window.setFixedSize(300, 120)
        
        layout = QVBoxLayout(self.dl_window)
        lbl = QLabel("Downloading update...")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        
        self.dl_window.show()
        threading.Thread(target=self._download_chunked_gui, args=(url, target_path, signature), daemon=True).start()

    def _download_chunked_gui(self, url, target_path, signature):
        try:
            from urllib.parse import urlparse
            if not any(urlparse(url).netloc.lower().endswith(d) for d in ['github.com', 'githubusercontent.com']):
                raise ValueError("Unauthorized host")

            response = requests.get(url, stream=True)
            total = int(response.headers.get('content-length', 0))
            with open(target_path, 'wb') as f:
                dl = 0
                for chunk in response.iter_content(4096):
                    f.write(chunk)
                    dl += len(chunk)
                    if total:
                        pct = int((dl/total)*100)
                        QTimer.singleShot(0, lambda p=pct: self.progress.setValue(p))

            if self._verify_binary_signature(target_path, signature):
                QTimer.singleShot(0, lambda: self._apply_update(target_path))
            else:
                try: target_path.unlink()
                except: pass
                QTimer.singleShot(0, lambda: QMessageBox.critical(self.root, "Security Error", "Signature verification failed! Update aborted."))
                QTimer.singleShot(0, self._close_download_window)
        except Exception as e:
            QTimer.singleShot(0, lambda: QMessageBox.critical(self.root, "Error", str(e)))
            QTimer.singleShot(0, self._close_download_window)

    def _close_download_window(self):
        if hasattr(self, 'dl_window') and self.dl_window:
            self.dl_window.close()
            self.dl_window.deleteLater()
            self.dl_window = None

    def _apply_update(self, new_filepath):
        self._close_download_window()
        if not new_filepath or not os.path.exists(new_filepath): return

        if os.path.getsize(new_filepath) < 1024 * 1024:
            try: os.unlink(new_filepath)
            except: pass
            QMessageBox.critical(self.root, "Security Error", "Downloaded file is invalid.")
            return

        if sys.platform == "win32": self._windows_update(new_filepath)
        else: self._unix_update(new_filepath)

    def _windows_update(self, new_filepath):
        batch = self.temp_dir / "updater.bat"
        target = self.current_exe
        script = f"""
@echo off
timeout /t 2 /nobreak > NUL
move /y "{new_filepath}" "{target}"
start "" "{target}"
del "%~f0"
        """
        with open(batch, "w") as f: f.write(script)
        subprocess.Popen([str(batch)], shell=True)
        QApplication.quit()
        sys.exit()

    def _unix_update(self, new_filepath):
        st = os.stat(new_filepath)
        os.chmod(new_filepath, st.st_mode | stat.S_IEXEC)
        try:
            os.replace(new_filepath, self.current_exe)
            os.execv(self.current_exe, sys.argv)
        except OSError as e:
            QMessageBox.critical(self.root, "Error", str(e))

    def _cleanup_old_files(self):
        try:
            for f in self.temp_dir.glob("update_*.exe"):
                try: f.unlink()
                except: pass
            for f in self.temp_dir.glob("update_*.bin"):
                try: f.unlink()
                except: pass
        except: pass

    def _show_error(self, msg):
        QTimer.singleShot(0, lambda: QMessageBox.critical(self.root, "Error", msg))
