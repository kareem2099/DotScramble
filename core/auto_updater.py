import os
import sys
import requests
import subprocess
import threading
import stat
import time
from pathlib import Path
from tkinter import messagebox, Toplevel, Label, ttk

# Import settings and paths
from config import APP_VERSION, UPDATE_CONFIG, DIRS

class AutoUpdater:
    def __init__(self, root_window):
        self.root = root_window
        self.repo_owner = UPDATE_CONFIG['repo_owner']
        self.repo_name = UPDATE_CONFIG['repo_name']

        # Determine current program path (target)
        self.is_frozen = getattr(sys, 'frozen', False)
        self.current_exe = sys.executable if self.is_frozen else sys.argv[0]
        self.current_dir = os.path.dirname(os.path.abspath(self.current_exe))

        # Passive update variables
        self.update_ready = False
        self.ready_file_path = None
        self.on_update_ready_callback = None

        # Use temp directory from AppData (safe and hidden)
        self.temp_dir = DIRS['temp']

    def check_for_updates(self, silent=False):
        """Regular check (shows popup)"""
        if not self._check_environment(silent): return
        threading.Thread(target=self._check_logic_interactive, args=(silent,), daemon=True).start()

    def check_for_updates_silently(self, callback_func):
        """Silent check (shows button only)"""
        if not self._check_environment(True): return
        self.on_update_ready_callback = callback_func
        threading.Thread(target=self._check_logic_silent, daemon=True).start()

    def _check_environment(self, silent):
        """Ensure we're not in development mode"""
        if not self.is_frozen and not os.getenv('FORCE_UPDATE_TEST'):
            if not silent:
                messagebox.showinfo("Dev Mode", "Cannot update from source code.")
            return False
        return True

    # --- Logic 1: Silent (Passive) ---
    def _check_logic_silent(self):
        try:
            self._cleanup_old_files()  # Cleanup before starting

            latest_version, download_url = self._get_latest_release_info()
            if not latest_version: return

            if latest_version != APP_VERSION and download_url:
                # Download in background without GUI
                self._download_file(download_url, gui=False)

        except Exception as e:
            print(f"Silent check failed: {e}")

    # --- Logic 2: Interactive (Active) ---
    def _check_logic_interactive(self, silent):
        try:
            self._cleanup_old_files()

            latest_version, download_url = self._get_latest_release_info()
            if not latest_version:
                if not silent: self._show_error("Could not connect.")
                return

            if latest_version != APP_VERSION:
                if download_url:
                    self.root.after(0, lambda: self._prompt_user(latest_version, download_url))
                else:
                    if not silent: self._show_error("No compatible file found.")
            else:
                if not silent:
                    self.root.after(0, lambda: messagebox.showinfo("Up to date", "You are using the latest version ✅"))

        except Exception as e:
            if not silent: self._show_error(f"Error: {e}")

    # --- Shared Helpers ---
    def _get_latest_release_info(self):
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        response = requests.get(api_url, timeout=5)
        if response.status_code != 200: return None, None

        data = response.json()
        version = data['tag_name']

        assets = data.get('assets', [])
        url = self._get_asset_url(assets)
        return version, url

    def _get_asset_url(self, assets):
        target = "DotScramble-windows.exe" if sys.platform == "win32" else \
                 "DotScramble-macos" if sys.platform == "darwin" else "DotScramble-linux"

        for asset in assets:
            if asset['name'] == target:
                return asset['browser_download_url']
        return None

    def _download_file(self, url, gui=False):
        try:
            filename = f"update_{int(time.time())}.exe" if sys.platform == "win32" else f"update_{int(time.time())}.bin"
            new_filepath = self.temp_dir / filename

            if gui:
                self._start_download_gui(url, new_filepath)
            else:
                # Silent download
                response = requests.get(url, stream=True)
                with open(new_filepath, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=4096):
                        file.write(chunk)

                # Notify download completion
                self.ready_file_path = new_filepath
                self.update_ready = True
                if self.on_update_ready_callback:
                    self.on_update_ready_callback()

        except Exception as e:
            if gui:
                self._show_error(str(e))
            else:
                print(f"Download error: {e}")

    def apply_pending_update(self):
        """Apply the ready update"""
        if self.ready_file_path and self.ready_file_path.exists():
            self._apply_update(self.ready_file_path)

    # --- GUI Helpers ---
    def _prompt_user(self, version, url):
        msg = f"New update {version} available! Install now?"
        if messagebox.askyesno("Update", msg):
            # Use GUI download here
            self._download_file(url, gui=True)

    def _start_download_gui(self, url, target_path):
        self.dl_window = Toplevel(self.root)
        self.dl_window.title("Updating...")
        self.dl_window.geometry("300x120")
        # (Centering code as before...)

        Label(self.dl_window, text="Downloading update...", pady=10).pack()
        self.progress = ttk.Progressbar(self.dl_window, length=250, mode="determinate")
        self.progress.pack(pady=5)

        threading.Thread(target=self._download_chunked_gui, args=(url, target_path), daemon=True).start()

    def _download_chunked_gui(self, url, target_path):
        try:
            response = requests.get(url, stream=True)
            total = int(response.headers.get('content-length', 0))
            with open(target_path, 'wb') as f:
                dl = 0
                for chunk in response.iter_content(4096):
                    f.write(chunk)
                    dl += len(chunk)
                    if total:
                        self.root.after(0, lambda v=(dl/total)*100: self.progress.configure(value=v))

            self.root.after(0, lambda: self._apply_update(target_path))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.dl_window.destroy()

    # --- Applying Logic ---
    def _apply_update(self, new_filepath):
        if hasattr(self, 'dl_window') and self.dl_window:
            self.dl_window.destroy()

        if sys.platform == "win32":
            self._windows_update(new_filepath)
        else:
            self._unix_update(new_filepath)

    def _windows_update(self, new_filepath):
        # Batch script goes in temp too
        batch = self.temp_dir / "updater.bat"
        target = self.current_exe

        # Use absolute paths to avoid issues
        script = f"""
@echo off
timeout /t 2 /nobreak > NUL
move /y "{new_filepath}" "{target}"
start "" "{target}"
del "%~f0"
        """
        with open(batch, "w") as f: f.write(script)

        subprocess.Popen([str(batch)], shell=True)
        self.root.quit()
        sys.exit()

    def _unix_update(self, new_filepath):
        st = os.stat(new_filepath)
        os.chmod(new_filepath, st.st_mode | stat.S_IEXEC)
        try:
            os.replace(new_filepath, self.current_exe)
            os.execv(self.current_exe, sys.argv)
        except OSError as e:
            messagebox.showerror("Error", str(e))

    def _cleanup_old_files(self):
        try:
            for f in self.temp_dir.glob("update_*.exe"):
                try: f.unlink()
                except: pass
        except: pass

    def _show_error(self, msg):
        self.root.after(0, lambda: messagebox.showerror("Error", msg))
