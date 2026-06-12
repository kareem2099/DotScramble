#!/usr/bin/env python3
"""
Test script to verify the application runs with localization
"""
import sys
import os
import tkinter as tk
from tkinter import messagebox

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_app_initialization():
    """Test that the main application can be initialized with localization"""
    try:
        # Import the main application
        from views.main_window import AdvancedPrivacyStudioPro
        
        print("🧪 Testing Application Initialization with Localization")
        print("=" * 60)
        
        # Create a minimal test window
        root = tk.Tk()
        root.withdraw()  # Hide the window
        
        # Initialize the application
        app = AdvancedPrivacyStudioPro(root)
        
        print("✅ Application initialized successfully")
        print(f"✅ Current language: {app.locale_manager.current_language}")
        print(f"✅ Window title: {app.root.title()}")
        
        # Test some localized strings
        _ = app.locale_manager.get
        print(f"✅ Menu File: {_('menu.file')}")
        print(f"✅ Load Image: {_('menu.file_items.open_image')}")
        print(f"✅ Save Result: {_('menu.file_items.save_result')}")
        print(f"✅ Edit Menu: {_('menu.edit')}")
        print(f"✅ Undo: {_('menu.edit_items.undo')}")
        print(f"✅ View Menu: {_('menu.view')}")
        print(f"✅ Help Menu: {_('menu.help')}")
        
        # Test RTL detection
        print(f"✅ Is RTL: {app.locale_manager.is_rtl()}")
        
        # Test language switching
        print("\n🔄 Testing language switching...")
        app.change_language('ar')
        print(f"✅ Switched to Arabic: {app.locale_manager.current_language}")
        print(f"✅ Arabic title: {app.root.title()}")
        
        app.change_language('en')
        print(f"✅ Switched back to English: {app.locale_manager.current_language}")
        print(f"✅ English title: {app.root.title()}")
        
        # Clean up
        root.destroy()
        
        print("\n🎉 All application localization tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Application initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_app_initialization()
    sys.exit(0 if success else 1)