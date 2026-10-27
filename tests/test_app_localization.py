#!/usr/bin/env python3
"""
Test script to verify the application runs with localization (PySide6 version)
"""
import sys
import os
from PySide6.QtWidgets import QApplication

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_app_initialization():
    """Test that the main application can be initialized with localization"""
    # Initialize QApplication if it doesn't exist
    app = QApplication.instance() or QApplication([])

    from src.views.main_window import AdvancedPrivacyStudioPro
    
    print("🧪 Testing Application Initialization with Localization")
    print("=" * 60)
    
    # Initialize the application
    win = AdvancedPrivacyStudioPro()
    
    print("✅ Application initialized successfully")
    print(f"✅ Current language: {win.locale_manager.current_language}")
    print(f"✅ Window title: {win.windowTitle()}")
    
    # Test some localized strings
    _ = win.locale_manager.get
    print(f"✅ Menu File: {_('menu.file')}")
    print(f"✅ Load Image: {_('menu.file_items.open_image')}")
    print(f"✅ Save Result: {_('menu.file_items.save_result')}")
    print(f"✅ Edit Menu: {_('menu.edit')}")
    print(f"✅ Undo: {_('menu.edit_items.undo')}")
    print(f"✅ View Menu: {_('menu.view')}")
    print(f"✅ Help Menu: {_('menu.help')}")
    
    # Test RTL detection
    print(f"✅ Is RTL: {win.locale_manager.is_rtl()}")
    
    # Test language switching
    print("\n🔄 Testing language switching...")
    win.change_language('ar')
    print(f"✅ Switched to Arabic: {win.locale_manager.current_language}")
    print(f"✅ Arabic title: {win.windowTitle()}")
    assert win.locale_manager.current_language == 'ar'
    
    win.change_language('en')
    print(f"✅ Switched back to English: {win.locale_manager.current_language}")
    print(f"✅ English title: {win.windowTitle()}")
    assert win.locale_manager.current_language == 'en'
    
    # Clean up
    win.close()
    print("\n🎉 All application localization tests passed!")
    return True

if __name__ == "__main__":
    success = test_app_initialization()
    sys.exit(0 if success else 1)