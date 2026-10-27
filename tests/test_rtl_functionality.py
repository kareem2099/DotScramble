#!/usr/bin/env python3
"""
RTL Functionality Test Script for DotScramble (PySide6 version)
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_rtl_functionality():
    """Test RTL layout direction changes natively in PySide6"""
    # Initialize QApplication singleton if it doesn't exist
    app = QApplication.instance() or QApplication([])
    
    from src.views.main_window import AdvancedPrivacyStudioPro
    
    # Initialize the main window
    window = AdvancedPrivacyStudioPro()
    
    # Test 1: Check RTL Manager initialization
    assert hasattr(window, 'rtl_manager'), "RTL Manager should be initialized on the main window"
    assert window.rtl_manager is not None
    
    # Test 2: Toggle RTL State to True
    window.rtl_manager.set_rtl_state(True)
    assert app.layoutDirection() == Qt.LayoutDirection.RightToLeft, "QApplication layout direction should be RightToLeft"
    assert window.rtl_manager.is_rtl is True
    
    # Test 3: Toggle RTL State to False
    window.rtl_manager.set_rtl_state(False)
    assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight, "QApplication layout direction should be LeftToRight"
    assert window.rtl_manager.is_rtl is False
    
    # Test 4: Verify change_language('ar') automatically switches to RTL layout
    window.change_language('ar')
    assert window.rtl_manager.is_rtl is True, "RTL should be active when language is set to Arabic"
    assert app.layoutDirection() == Qt.LayoutDirection.RightToLeft, "QApplication direction should be RightToLeft for Arabic"
    
    # Test 5: Verify change_language('en') automatically switches to LTR layout
    window.change_language('en')
    assert window.rtl_manager.is_rtl is False, "RTL should be disabled when language is set to English"
    assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight, "QApplication direction should be LeftToRight for English"
    
    # Clean up the window
    window.close()

if __name__ == "__main__":
    print("🚀 Running RTL Functionality PySide6 Tests...")
    test_rtl_functionality()
    print("🎉 All RTL functionality tests passed!")