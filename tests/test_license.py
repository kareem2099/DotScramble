"""
License behaviour that has bitten users: a week without opening the app, a changed CPU count,
deactivating to move Pro to another computer. No network: the server is a fake.
"""
import base64
import io
import json
import os
import time
import urllib.error

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from src.managers import license_manager as lm
from src.managers.license_manager import LicenseManager

SIGNER = Ed25519PrivateKey.generate()


class DB:
    def __init__(self, **settings):
        self.settings = dict(settings)

    def save_setting(self, key, value, setting_type="general"):
        self.settings[key] = value
        return True

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)


def token(mid=None, exp_in=7 * 86400):
    payload = json.dumps({"uid": "u", "mid": mid or LicenseManager.generate_machine_id(), "tier": "max",
                          "name": "Tester", "iat": int(time.time()), "exp": int(time.time()) + exp_in}).encode()
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return f"{b64(payload)}.{b64(SIGNER.sign(payload))}"


def http_error(code, message="nope"):
    body = io.BytesIO(json.dumps({"error": {"message": message}}).encode())
    return urllib.error.HTTPError("https://core.test", code, message, {}, body)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """The app's key is replaced by the test signer, and background threads are recorded, not run."""
    public = SIGNER.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setattr(lm, "_ED25519_PUBLIC_KEY_B64", base64.b64encode(public).decode())
    renewals = []
    monkeypatch.setattr(LicenseManager, "_schedule_background_recheck",
                        lambda self, renew_now=False: renewals.append(renew_now))
    return renewals


def server(monkeypatch, reply):
    """Route the manager's requests to `reply(url, body)`; returns the list of calls."""
    calls = []

    def post(self, url, api_key, body, *, method="POST", timeout=12):
        calls.append((url.rsplit("/", 1)[-1], method, body))
        result = reply(url, body)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(LicenseManager, "_post", post)
    return calls


def test_a_valid_token_means_pro_without_waiting_for_the_network(offline):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    assert manager.is_max_activated
    assert offline == [False]


def test_a_week_away_renews_instead_of_logging_out(offline, monkeypatch):
    db = DB(dotsuite_api_key="k", license_token=token(exp_in=-60), last_license_check_time=time.time() - 8 * 86400)
    manager = LicenseManager(db)
    assert not manager.is_max_activated
    assert db.settings["dotsuite_api_key"] == "k"          # kept, so the renewal can use it
    assert offline == [True]                               # renewal asked for straight away

    changes = []
    manager.on_change = changes.append
    server(monkeypatch, lambda url, body: {"license_token": token()})
    assert manager._silent_recheck() == "ok"
    assert manager.is_max_activated and changes == [True]


def test_offline_renewal_keeps_the_key_and_tries_again(offline, monkeypatch):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(exp_in=-60)))
    server(monkeypatch, lambda url, body: OSError("network unreachable"))
    assert manager._silent_recheck() == "retry"
    assert manager.api_key == "k"


@pytest.mark.parametrize("code", [401, 403])
def test_an_explicit_rejection_ends_pro(offline, monkeypatch, code):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    changes = []
    manager.on_change = changes.append
    server(monkeypatch, lambda url, body: http_error(code))
    assert manager._silent_recheck() == "revoked"
    assert not manager.is_max_activated and manager.api_key == "" and changes == [False]


def test_a_token_that_runs_out_while_open_turns_pro_off_but_keeps_the_key(offline):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(exp_in=1), last_license_check_time=time.time()))
    changes = []
    manager.on_change = changes.append
    time.sleep(1.1)
    manager._expire_if_due()
    assert not manager.is_max_activated and manager.api_key == "k" and changes == [False]


def test_the_machine_id_does_not_change_with_the_cpu_count(monkeypatch):
    before, legacy_before = LicenseManager.generate_machine_id(), LicenseManager.legacy_machine_id()
    monkeypatch.setattr(os, "cpu_count", lambda: 3)
    assert LicenseManager.generate_machine_id() == before
    assert LicenseManager.legacy_machine_id() != legacy_before


def test_a_token_from_the_old_fingerprint_works_and_moves_to_the_new_id(offline, monkeypatch):
    legacy = LicenseManager.legacy_machine_id()
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(mid=legacy), last_license_check_time=time.time()))
    assert manager.is_max_activated
    assert offline == [True]                              # renewed at once under the new ID
    calls = server(monkeypatch, lambda url, body: {"license_token": token()})
    manager._silent_recheck()
    body = calls[0][2]
    assert body["machine_id"] == LicenseManager.generate_machine_id()
    assert body["previous_machine_id"] == legacy
    assert body["device_name"]


def test_a_token_for_another_machine_without_a_key_is_cleared(offline):
    db = DB(license_token=token(mid="0" * 32))
    manager = LicenseManager(db)
    assert not manager.is_max_activated and db.settings["license_token"] == "" and offline == []


def test_activation_sends_the_identity_and_stores_the_token(offline, monkeypatch):
    db = DB()
    manager = LicenseManager(db)
    calls = server(monkeypatch, lambda url, body: {"license_token": token(), "name": "Kareem"})
    ok, message = manager.verify_and_activate("  ds_prod_key  ")
    assert ok and "Kareem" in message and manager.is_max_activated
    assert db.settings["dotsuite_api_key"] == "ds_prod_key"
    assert calls[0][0] == "activate" and calls[0][2]["machine_id"] == LicenseManager.generate_machine_id()


def test_activation_shows_the_servers_reason(offline, monkeypatch):
    manager = LicenseManager(DB())
    server(monkeypatch, lambda url, body: http_error(409, "Activation limit reached"))
    ok, message = manager.verify_and_activate("ds_prod_key")
    assert not ok and "409" in message and "Activation limit reached" in message


def test_deactivate_frees_the_slot_then_forgets_the_license(offline, monkeypatch):
    db = DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time())
    manager = LicenseManager(db)
    calls = server(monkeypatch, lambda url, body: {})
    assert manager.deactivate() == (True, "")
    assert calls[0][:2] == ("deactivate", "DELETE")
    assert calls[0][2]["previous_machine_id"] == LicenseManager.legacy_machine_id()
    assert not manager.is_max_activated and db.settings["dotsuite_api_key"] == ""


def test_deactivate_offline_changes_nothing_so_it_can_be_retried(offline, monkeypatch):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    server(monkeypatch, lambda url, body: OSError("network unreachable"))
    ok, message = manager.deactivate()
    assert not ok and "Could not reach" in message
    assert manager.is_max_activated and manager.api_key == "k"


def test_deactivate_with_a_key_already_revoked_still_forgets_it(offline, monkeypatch):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    server(monkeypatch, lambda url, body: http_error(401))
    assert manager.deactivate() == (True, "")
    assert not manager.is_max_activated


def test_the_settings_database_is_private(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permissions")
    from src.managers.database_manager import DatabaseManager
    db = DatabaseManager(str(tmp_path / "settings.db"))
    assert os.stat(db.db_path).st_mode & 0o777 == 0o600


# ── Pro usage counts (reported with the check; numbers only) ────────────────

class Clock:
    def __init__(self, day):
        self.day = day

    def __call__(self):
        return self.day


def test_usage_counts_per_day_and_forgets_only_what_was_sent():
    from datetime import date
    from core.pro_usage import ProUsage
    clock = Clock(date(2026, 10, 27))
    usage = ProUsage(DB(), today=clock)
    usage.add("pro_saves")
    clock.day = date(2026, 10, 28)
    usage.add("pro_saves", 2)
    usage.add("batch_images", 10)
    usage.add("not_a_kind")
    report = usage.pending()
    assert [r["day"] for r in report] == ["2026-10-27", "2026-10-28"]
    assert report[1]["pro_saves"] == 2 and report[1]["batch_images"] == 10
    usage.add("pro_saves")                   # counted while the report was on its way
    usage.sent(report)
    assert usage.pending() == [{"day": "2026-10-28", "pro_saves": 1, "batch_images": 0,
                                "metadata_cleaned": 0, "ai_runs": 0}]


def test_usage_keeps_at_most_sixty_days():
    from datetime import date, timedelta
    from core.pro_usage import ProUsage
    clock = Clock(date(2026, 1, 1))
    usage = ProUsage(DB(), today=clock)
    for i in range(70):
        clock.day = date(2026, 1, 1) + timedelta(days=i)
        usage.add("ai_runs")
    assert len(usage.pending()) == 60


def test_the_check_reports_usage_and_clears_it(offline, monkeypatch):
    from core.pro_usage import ProUsage
    db = DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time())
    manager = LicenseManager(db)
    manager.usage, manager.app_version = ProUsage(db), "1.6.0"
    manager.usage.add("pro_saves", 3)
    calls = server(monkeypatch, lambda url, body: {"license_token": token()})
    assert manager._silent_recheck() == "ok"
    body = calls[0][2]
    assert body["app_version"] == "1.6.0" and body["usage"][0]["pro_saves"] == 3
    assert manager.usage.pending() == []


def test_counts_the_server_refuses_never_block_the_license(offline, monkeypatch):
    from core.pro_usage import ProUsage
    db = DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time())
    manager = LicenseManager(db)
    manager.usage = ProUsage(db)
    manager.usage.add("ai_runs")
    calls = server(monkeypatch, lambda url, body: http_error(400, "usage day is out of range")
                   if "usage" in body else {"license_token": token()})
    assert manager._silent_recheck() == "ok"
    assert len(calls) == 2 and "usage" not in calls[1][2]
    assert manager.usage.pending() == []


def test_counts_are_dropped_when_the_license_ends(offline, monkeypatch):
    from core.pro_usage import ProUsage
    db = DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time())
    manager = LicenseManager(db)
    manager.usage = ProUsage(db)
    manager.usage.add("pro_saves")
    server(monkeypatch, lambda url, body: {})
    assert manager.deactivate() == (True, "")
    assert manager.usage.pending() == []


# ── License & devices ────────────────────────────────────────────────────────

class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_devices_reads_the_accounts_list(offline, monkeypatch):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    seen = {}

    def fake_urlopen(req, timeout=10):
        seen["url"], seen["auth"], seen["method"] = req.full_url, req.get_header("Authorization"), req.get_method()
        return _Response(json.dumps({"limit": 2, "devices": [{"machine_id": "abc", "name": "Linux · desk"}]}).encode())

    monkeypatch.setattr(lm.urllib.request, "urlopen", fake_urlopen)
    ok, data = manager.devices()
    assert ok and data["limit"] == 2 and data["devices"][0]["name"] == "Linux · desk"
    assert seen["url"].endswith("/v1/license/devices") and seen["auth"] == "Bearer k" and seen["method"] == "GET"


def test_devices_without_a_license_or_network_says_why(offline, monkeypatch):
    assert LicenseManager(DB()).devices() == (False, "not activated")
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    monkeypatch.setattr(lm.urllib.request, "urlopen", lambda req, timeout=10: (_ for _ in ()).throw(OSError("offline")))
    ok, reason = manager.devices()
    assert not ok and "offline" in reason


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("lang", ["en", "ar", "fa", "es", "ru", "de", "tr"])
@pytest.mark.parametrize("pro", [True, False])
def test_license_window_has_text_in_every_language(qapp, offline, lang, pro):
    from PySide6.QtWidgets import QLabel, QPushButton
    from gui.license_dialog import LicenseDialog
    from src.managers.localization_manager import get_locale_manager
    db = DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()) if pro else DB()
    manager = LicenseManager(db)
    manager.devices = lambda: (True, {"limit": 2, "devices": [
        {"machine_id": LicenseManager.generate_machine_id(), "name": "Linux · this", "activated_at": "2026-10-29T12:00:00Z",
         "last_seen_at": "2026-10-29T12:45:00Z"},
        {"machine_id": "f" * 32, "name": None, "activated_at": None, "last_seen_at": None}]})
    get_locale_manager().set_language(lang)
    try:
        dlg = LicenseDialog(None, license_manager=manager, on_deactivate=lambda: None)
        if pro:
            dlg._show_devices(*manager.devices())       # what the worker thread delivers
        texts = [w.text() for w in dlg.findChildren(QLabel) + dlg.findChildren(QPushButton)]
        assert not [t for t in texts if t.startswith(("ui.", "menu."))], texts
        assert any(LicenseManager.generate_machine_id() in t for t in texts)
        if pro:
            assert any("2" in t for t in texts if t == dlg.count_label.text())
        dlg.deleteLater()
    finally:
        get_locale_manager().set_language("en")


@pytest.mark.parametrize("lang", ["en", "ar", "fa", "es", "ru", "de", "tr"])
@pytest.mark.parametrize("left", [2, 1, 0])
def test_removals_left_is_explained_in_every_language(qapp, offline, lang, left):
    from PySide6.QtWidgets import QLabel
    from gui.license_dialog import LicenseDialog
    from src.managers.localization_manager import get_locale_manager
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    get_locale_manager().set_language(lang)
    try:
        dlg = LicenseDialog(None, license_manager=manager)
        dlg._show_devices(True, {"limit": 2, "devices": [], "self_removals_left": left,
                                 "self_removals_reset_at": "2026-11-20T10:00:00Z" if left == 0 else None})
        texts = [w.text() for w in dlg.findChildren(QLabel)]
        assert not [t for t in texts if t.startswith("ui.")], texts
        if left == 0:
            assert any("support@dotsuite.dev" in t and "2026-11-20" in t for t in texts)
        dlg.deleteLater()
    finally:
        get_locale_manager().set_language("en")


def test_a_refused_deactivation_keeps_the_license(offline, monkeypatch):
    manager = LicenseManager(DB(dotsuite_api_key="k", license_token=token(), last_license_check_time=time.time()))
    server(monkeypatch, lambda url, body: http_error(409, "You can remove 2 devices yourself every 30 days"))
    ok, message = manager.deactivate()
    assert not ok and "409" in message and "30 days" in message
    assert manager.is_max_activated and manager.api_key == "k"
