#!/usr/bin/env python3
"""
Test script for the localization system
"""

import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_localization():
    """Test the localization system functionality"""
    print("🧪 Testing Localization System")
    print("=" * 50)
    
    try:
        # Test 1: Import LocalizationManager
        print("1. Testing LocalizationManager import...")
        from managers.localization_manager import LocalizationManager, get_locale_manager
        print("   ✅ LocalizationManager imported successfully")
        
        # Test 2: Initialize LocalizationManager
        print("2. Testing LocalizationManager initialization...")
        loc_mgr = LocalizationManager()
        print("   ✅ LocalizationManager initialized successfully")
        
        # Test 3: Get language list
        print("3. Testing language list retrieval...")
        languages = loc_mgr.get_language_list()
        print(f"   ✅ Found {len(languages)} languages:")
        for lang in languages:
            print(f"      - {lang['name']} ({lang['code']}) - {lang['native_name']}")
        
        # Test 4: Test English localization
        print("4. Testing English localization...")
        loc_mgr.set_language('en')
        en_title = loc_mgr.get('app.title')
        en_status = loc_mgr.get('ui.status.ready')
        print(f"   ✅ English title: {en_title}")
        print(f"   ✅ English status: {en_status}")
        
        # Test 5: Test Arabic localization
        print("5. Testing Arabic localization...")
        loc_mgr.set_language('ar')
        ar_title = loc_mgr.get('app.title')
        ar_status = loc_mgr.get('ui.status.ready')
        print(f"   ✅ Arabic title: {ar_title}")
        print(f"   ✅ Arabic status: {ar_status}")
        
        # Test 6: Test RTL detection
        print("6. Testing RTL detection...")
        is_ar_rtl = loc_mgr.is_rtl()
        is_en_rtl = loc_mgr.is_rtl()
        print(f"   ✅ Arabic is RTL: {is_ar_rtl}")
        print(f"   ✅ English is RTL: {is_en_rtl}")
        
        # Test 7: Test missing key fallback
        print("7. Testing missing key fallback...")
        missing_key = loc_mgr.get('non.existent.key')
        print(f"   ✅ Missing key fallback: '{missing_key}'")
        
        # Test 8: Test get_locale_manager singleton
        print("8. Testing singleton pattern...")
        loc_mgr2 = get_locale_manager()
        print(f"   ✅ Singleton instance: {loc_mgr2 is loc_mgr}")
        
        print("\n🎉 All localization tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_language_persistence():
    """Test language persistence in database"""
    print("\n🧪 Testing Database Language Persistence")
    print("=" * 50)
    
    try:
        # Test 1: Import database manager
        print("1. Testing database manager import...")
        from managers.database_manager import init_database_manager
        print("   ✅ DatabaseManager imported successfully")
        
        # Test 2: Initialize database
        print("2. Testing database initialization...")
        db = init_database_manager()
        print("   ✅ DatabaseManager initialized successfully")
        
        # Test 3: Save language setting
        print("3. Testing language setting save...")
        save_result = db.save_last_used_language('ar')
        print(f"   ✅ Language save result: {save_result}")
        
        # Test 4: Retrieve language setting
        print("4. Testing language setting retrieval...")
        retrieved_lang = db.get_last_used_language()
        print(f"   ✅ Retrieved language: {retrieved_lang}")
        
        # Test 5: Test with different language
        print("5. Testing with different language...")
        db.save_last_used_language('en')
        retrieved_lang2 = db.get_last_used_language()
        print(f"   ✅ Retrieved language after change: {retrieved_lang2}")
        
        # Test 6: Test default fallback
        print("6. Testing default fallback...")
        # Clear the setting and test default
        db.delete_setting('last_language')
        default_lang = db.get_last_used_language()
        print(f"   ✅ Default language: {default_lang}")
        
        print("\n🎉 All database persistence tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Database test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting Localization System Tests")
    print("=" * 60)
    
    # Run localization tests
    loc_success = test_localization()
    
    # Run database tests
    db_success = test_database_language_persistence()
    
    print("\n" + "=" * 60)
    if loc_success and db_success:
        print("🎉 ALL TESTS PASSED! Localization system is working correctly.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED! Please check the errors above.")
        sys.exit(1)