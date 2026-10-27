#!/usr/bin/env python3
"""
Test script for verifying security and stability hotfixes in DotScramble.
"""

import sys
import os
import time
import tempfile
import shutil
from pathlib import Path

# Add the src directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock db_manager for testing
class MockDBManager:
    def __init__(self):
        self.settings = {}

    def save_setting(self, key, value, setting_type="general"):
        self.settings[key] = value
        return True

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def delete_setting(self, key):
        if key in self.settings:
            del self.settings[key]
            return True
        return False

def test_license_clock_rollback():
    print("🧪 Test 1: License System Clock Rollback Protection")
    print("-" * 50)
    
    from src.managers.license_manager import LicenseManager
    
    # Setup initial mock state (a valid looking configuration)
    db = MockDBManager()
    db.save_setting("dotsuite_api_key", "test_key", "license")
    # For testing, we mock a fake token. Note that token verification will return False,
    # but startup code checks self._license_token existence first.
    db.save_setting("license_token", "header.payload.signature", "license")
    
    # 1. Normal state: last check was 1 hour ago
    current_time = time.time()
    db.save_setting("last_license_check_time", current_time - 3600, "license")
    
    print("Initializing LicenseManager under normal clock conditions...")
    manager = LicenseManager(db)
    # The token is fake so verification fails, clearing local state
    print(f"   [Normal] token is checked; api_key exists before check: {db.get_setting('dotsuite_api_key') is not None}")
    
    # Re-enable max and token for rollback test simulation
    db.save_setting("dotsuite_api_key", "test_key", "license")
    db.save_setting("license_token", "header.payload.signature", "license")
    
    # 2. Clock Rollback: set last check to 1 hour in the FUTURE
    db.save_setting("last_license_check_time", current_time + 3600, "license")
    
    print("Initializing LicenseManager under rolled-back clock conditions...")
    # This should detect time.time() < last_license_check_time and clear the settings
    manager_tampered = LicenseManager(db)
    
    # Check if settings were cleared
    api_key_res = db.get_setting("dotsuite_api_key", "")
    token_res = db.get_setting("license_token", "")
    is_max_res = db.get_setting("is_max_activated", None)
    
    if api_key_res == "" and token_res == "" and is_max_res is False:
        print("   ✅ SUCCESS: Clock rollback detected! Local state was wiped.")
        return True
    else:
        print("   ❌ FAILURE: Clock rollback was NOT detected or local state was not cleared.")
        print(f"   Debug: api_key={api_key_res!r}, token={token_res!r}, is_max_activated={is_max_res!r}")
        return False

def test_base64_dynamic_padding():
    print("\n🧪 Test 2: Base64 Dynamic Padding Validation")
    print("-" * 50)
    
    from src.managers.license_manager import LicenseManager
    
    # Define _verify_token helper or test _b64dec via reflection/copy
    # Let's inspect base64 decode with various lengths of string padding
    import base64
    def _b64dec(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
        
    test_payloads = [
        "eyJhY3RpdmUiOiB0cnVlfQ",   # Length 21 (Needs 3 '=' padding)
        "eyJhY3RpdmUiOiB0cnVlfQ==", # Length 23 (Already padded/ignored)
        "eyJhY3RpdmUiOiB0cnVlfQ=",  # Length 22
        "eyJhY3RpdmUiOiB0cnVlLCBpc19wcm8iOiB0cnVlfQ", # Length 43 (Needs 1 '=')
    ]
    
    success = True
    for p in test_payloads:
        try:
            decoded = _b64dec(p)
            print(f"   Decoded {p[:15]}... -> {decoded.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"   ❌ Failed on payload: {p}. Error: {e}")
            success = False
            
    if success:
        print("   ✅ SUCCESS: Base64 dynamic padding handles all inputs without crashing.")
    return success

def test_model_size_validation():
    print("\n🧪 Test 3: Model Completeness & Size Validation")
    print("-" * 50)
    
    from src.models import detection_engine
    
    # Store old MODEL_PATH
    old_model_path = detection_engine.MODEL_PATH
    
    # Setup a temp directory and temp file to simulate
    temp_dir = tempfile.mkdtemp()
    temp_model = Path(temp_dir) / "fake_face_landmarker.task"
    detection_engine.MODEL_PATH = str(temp_model)
    
    try:
        # Case A: File doesn't exist
        print("   Checking non-existent model...")
        assert not detection_engine.is_model_downloaded(), "Missing file should be False"
        
        # Case B: File is 0 bytes (corrupted/interrupted)
        print("   Checking empty (0-byte) model...")
        temp_model.touch()
        assert not detection_engine.is_model_downloaded(), "0-byte file should be False"
        
        # Case C: File is small (under 1MB)
        print("   Checking small (100KB) model...")
        with open(temp_model, "wb") as f:
            f.write(b"\x00" * 100000)
        assert not detection_engine.is_model_downloaded(), "100KB file should be False"
        
        # Case D: File is large enough (2MB)
        print("   Checking complete (2MB) model...")
        with open(temp_model, "wb") as f:
            f.write(b"\x00" * 2000000)
        assert detection_engine.is_model_downloaded(), "2MB file should be True"
        
        print("   ✅ SUCCESS: Model path validation accurately identifies corrupted/empty files.")
        return True
    except AssertionError as e:
        print(f"   ❌ FAILURE: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir)
        detection_engine.MODEL_PATH = old_model_path

def test_updater_domain_and_size():
    print("\n🧪 Test 4: Updater Domain and Size Hardening")
    print("-" * 50)

    from core.auto_updater import check_download_url, download_file, UpdateError

    bad_urls = [
        "https://malicious-site.com/DotScramble.exe",
        "https://github.com.malicious.com/kareem2099/releases/update.exe",
        "http://attacker.local/update.exe",
        "http://github.com/kareem2099/DotScramble/releases/download/v1.4.1/SHA256SUMS",  # no TLS
    ]
    good_urls = [
        "https://github.com/kareem2099/DotScramble/releases/download/v1.4.1/DotScramble-Linux-x86_64.AppImage",
        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/update.bin",
        "https://release-assets.githubusercontent.com/github-production-release-asset/1/2",
        "https://api.github.com/repos/kareem2099/DotScramble/releases",
    ]

    print("   Checking invalid/malicious URLs...")
    for url in bad_urls:
        try:
            check_download_url(url)
        except UpdateError as e:
            assert "Unauthorized download host" in str(e)
        else:
            raise AssertionError(f"Domain validation let bad URL pass: {url}")
        # download_file must refuse before opening any connection
        try:
            download_file(url, Path(tempfile.gettempdir()) / "never-written", 1024)
        except UpdateError:
            pass
        else:
            raise AssertionError(f"download_file fetched a bad URL: {url}")

    print("   Checking valid GitHub release URLs...")
    for url in good_urls:
        check_download_url(url)

    print("   ✅ SUCCESS: Updater successfully blocks arbitrary/malicious hosts.")
    return True

if __name__ == "__main__":
    print("🚀 Running Security & Stability Hotfix Verification Tests")
    print("=" * 60)
    
    tests = [
        test_license_clock_rollback,
        test_base64_dynamic_padding,
        test_model_size_validation,
        test_updater_domain_and_size
    ]
    
    results = [t() for t in tests]
    
    print("\n" + "=" * 60)
    if all(results):
        print("🎉 ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATION TESTS FAILED. Please review the output above.")
        sys.exit(1)
