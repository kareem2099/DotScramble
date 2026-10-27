"""Minimum-supported-version gate (core/version_gate.py). No network: _open_checked is faked."""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import core.version_gate as vg  # noqa: E402
from core.auto_updater import UpdateError  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── Policy decisions ────────────────────────────────────────────────────────

@pytest.mark.parametrize("current, minimum, blocked", [
    ("1.4.1", "1.5.0", True),
    ("1.5.0", "1.5.0", False),
    ("1.5.1", "1.5.0", False),
    ("2.0.0", "1.9.9", False),
    ("1.5", "1.5.1", True),
    ("v1.4.0", "v1.5.0", True),
])
def test_blocking_minimum(current, minimum, blocked):
    result = vg.blocking_minimum(current, {"min_supported_version": minimum})
    assert (result == minimum) is blocked


@pytest.mark.parametrize("policy", [
    None, {}, [], "1.5.0", {"min_supported_version": 5}, {"min_supported_version": "abc"},
    {"min_supported_version": "1.5.0-beta"}, {"other": "9.9.9"},
])
def test_unusable_policies_never_block(policy):
    assert vg.blocking_minimum("0.0.1", policy) is None


def test_unparseable_current_version_never_blocks():
    assert vg.blocking_minimum("dev", {"min_supported_version": "9.9.9"}) is None


def test_gate_applies_only_to_packaged_builds_or_when_forced():
    assert vg.gate_applies(frozen=True, environ={}) is True
    assert vg.gate_applies(frozen=False, environ={}) is False
    assert vg.gate_applies(frozen=False, environ={vg.FORCE_ENV: "1"}) is True


def test_policy_file_in_repo_is_valid_and_blocks_nothing_yet():
    root = os.path.join(os.path.dirname(__file__), "..")
    policy = json.load(open(os.path.join(root, "version_policy.json"), encoding="utf-8"))
    assert vg.required_minimum(policy)
    from version_info import VERSION
    assert vg.blocking_minimum(VERSION, policy) is None, "the shipped version must not block itself"


# ── Fetching (faked network) ────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, body: bytes):
        self.raw = io.BytesIO(body)
        self.raw.read = lambda n, decode_content=True, _r=self.raw.read: _r(n)
        self.closed = False

    def close(self):
        self.closed = True


def _serve(monkeypatch, body=None, error=None):
    seen = {}

    def fake_open(url, timeout):
        seen["url"] = url
        if error:
            raise error
        seen["response"] = _FakeResponse(body)
        return seen["response"]
    monkeypatch.setattr(vg, "_open_checked", fake_open)
    return seen


def test_fetch_reads_the_policy_from_the_main_branch(monkeypatch):
    seen = _serve(monkeypatch, json.dumps({"min_supported_version": "1.5.0"}).encode())
    assert vg.fetch_policy() == {"min_supported_version": "1.5.0"}
    assert seen["url"].startswith("https://raw.githubusercontent.com/") and seen["url"].endswith("/main/version_policy.json")
    assert seen["response"].closed


@pytest.mark.parametrize("body, error", [
    (None, ConnectionError("offline")),
    (None, UpdateError("Download failed: HTTP 404")),   # before the file is pushed
    (b"not json", None),
    (b"{" + b" " * vg.MAX_POLICY_BYTES + b"}", None),
])
def test_fetch_failures_return_none(monkeypatch, body, error):
    _serve(monkeypatch, body, error)
    assert vg.fetch_policy() is None


# ── UI ──────────────────────────────────────────────────────────────────────

def test_dialog_download_opens_release_page_and_closing_quits(app, monkeypatch):
    opened, quits = [], []
    monkeypatch.setattr(vg.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString())))
    monkeypatch.setattr(vg.QApplication, "quit", staticmethod(lambda: quits.append(True)))
    dlg = vg.UpdateRequiredDialog(None, "1.4.1", "1.5.0")
    dlg.download_btn.click()
    assert opened == [vg.RELEASES_URL]
    assert not quits                       # downloading keeps the screen up
    dlg.reject()
    assert quits == [True]                 # Quit / closing the window leaves the app


def test_gate_shows_the_dialog_when_blocked(app, monkeypatch):
    shown = []
    monkeypatch.setattr(vg, "fetch_policy", lambda: {"min_supported_version": "9.9.9"})
    monkeypatch.setattr(vg.UpdateRequiredDialog, "exec", lambda self: shown.append(self.windowTitle()))
    window = QWidget()
    gate = vg.VersionGate(window, "1.5.0")
    gate._worker()                          # what start() runs on its thread
    app.processEvents()
    assert len(shown) == 1


def test_gate_stays_quiet_when_allowed_or_offline(app, monkeypatch):
    shown = []
    monkeypatch.setattr(vg.UpdateRequiredDialog, "exec", lambda self: shown.append(True))
    for policy in ({"min_supported_version": "1.0.0"}, None):
        monkeypatch.setattr(vg, "fetch_policy", lambda p=policy: p)
        vg.VersionGate(QWidget(), "1.5.0")._worker()
        app.processEvents()
    assert shown == []
