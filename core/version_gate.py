"""
Minimum-supported-version gate.

version_policy.json on the repo's main branch says which versions may still run:

    {"min_supported_version": "1.5.0"}

A packaged copy older than that shows a blocking "update required" screen. Its only
actions are opening the latest release page — a fresh download, never an in-place
update — or quitting. To retire old versions, bump the number in that file: no new
release is needed.

The policy is fetched off the UI thread. If GitHub can't be reached or the file is
missing / malformed, the app runs normally, so offline use is never blocked.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading

from PySide6.QtCore import QObject, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.auto_updater import _open_checked, is_newer, parse_version
from src.config import UPDATE_CONFIG

logger = logging.getLogger(__name__)

_OWNER, _REPO = UPDATE_CONFIG['repo_owner'], UPDATE_CONFIG['repo_name']
POLICY_URL = f"https://raw.githubusercontent.com/{_OWNER}/{_REPO}/main/version_policy.json"
RELEASES_URL = f"https://github.com/{_OWNER}/{_REPO}/releases/latest"
MAX_POLICY_BYTES = 4096
# Runs only in packaged builds; set to 1 to try it from source.
FORCE_ENV = "DOTSCRAMBLE_VERSION_GATE"


def _t(key, **kwargs):
    from src.managers.localization_manager import get_locale_manager
    return get_locale_manager().get(key, **kwargs)


# ── Pure helpers (no Qt, unit-tested) ───────────────────────────────────────

def required_minimum(policy) -> str | None:
    """The minimum version a policy demands, or None if it is unusable."""
    if not isinstance(policy, dict):
        return None
    minimum = policy.get("min_supported_version")
    return minimum if isinstance(minimum, str) and parse_version(minimum) else None


def blocking_minimum(current_version, policy) -> str | None:
    """The minimum version when *current_version* is below it, else None (allowed)."""
    minimum = required_minimum(policy)
    if minimum and parse_version(current_version) and is_newer(minimum, current_version):
        return minimum
    return None


def fetch_policy(timeout=5):
    """version_policy.json as a dict, or None when it can't be fetched or read."""
    try:
        response = _open_checked(POLICY_URL, timeout)
        try:
            body = response.raw.read(MAX_POLICY_BYTES + 1, decode_content=True)
        finally:
            response.close()
        if len(body) > MAX_POLICY_BYTES:
            logger.warning("version_policy.json is larger than %d bytes; ignored", MAX_POLICY_BYTES)
            return None
        return json.loads(body.decode("utf-8"))
    except Exception as e:  # offline, 404 before the file exists, bad JSON…: never block on it
        logger.info("Version policy not checked: %s", e)
        return None


def gate_applies(frozen=None, environ=None) -> bool:
    environ = os.environ if environ is None else environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    return bool(frozen) or environ.get(FORCE_ENV) == "1"


# ── Qt ──────────────────────────────────────────────────────────────────────

class UpdateRequiredDialog(QDialog):
    """Blocking screen: download the latest release or quit. Closing it quits too."""

    def __init__(self, parent, current_version, minimum):
        super().__init__(parent)
        self.setWindowTitle(_t("ui.version_gate.title"))
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)

        title = QLabel(_t("ui.version_gate.title"))
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        message = QLabel(_t("ui.version_gate.message", current=current_version, minimum=minimum))
        message.setProperty("role", "caption")
        message.setWordWrap(True)
        layout.addWidget(message)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        quit_btn = QPushButton(_t("ui.version_gate.quit"))
        quit_btn.setProperty("variant", "ghost")
        quit_btn.clicked.connect(self.reject)
        self.download_btn = QPushButton(_t("ui.version_gate.download"))
        self.download_btn.setProperty("variant", "primary")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._open_download_page)
        buttons.addWidget(quit_btn)
        buttons.addWidget(self.download_btn)
        layout.addLayout(buttons)

    def _open_download_page(self):
        QDesktopServices.openUrl(QUrl(RELEASES_URL))

    def done(self, result):
        super().done(result)
        QApplication.quit()  # there is no way past this screen except a newer version


class VersionGate(QObject):
    """Checks the policy in the background and shows UpdateRequiredDialog if needed."""

    _blocked = Signal(str)  # the minimum supported version

    def __init__(self, window, current_version):
        super().__init__(window)
        self.window = window
        self.current_version = current_version
        self._blocked.connect(self._on_blocked, Qt.ConnectionType.QueuedConnection)

    def start(self):
        if gate_applies():
            threading.Thread(target=self._worker, daemon=True, name="version-gate").start()

    def _worker(self):
        minimum = blocking_minimum(self.current_version, fetch_policy())
        if minimum:
            self._blocked.emit(minimum)

    def _on_blocked(self, minimum):
        logger.warning("DotScramble %s is below the minimum supported %s", self.current_version, minimum)
        UpdateRequiredDialog(self.window, self.current_version, minimum).exec()
