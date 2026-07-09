"""
RTL (Right-to-Left) Layout Manager for DotScramble (PySide6 version)

This module handles native Qt RTL layout direction changes when the locale language changes.
"""

import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

class RTLManager:
    """Comprehensive RTL layout management system using PySide6 native directions"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.is_rtl = False
        self.previous_rtl_state = False
        
    def set_rtl_state(self, rtl: bool) -> None:
        """Set RTL state and trigger layout updates if changed"""
        if rtl == self.is_rtl:
            return  # No change needed
            
        self.previous_rtl_state = self.is_rtl
        self.is_rtl = rtl
        
        logger.info(f"RTL state changed: {self.previous_rtl_state} → {self.is_rtl}")
        
        # Apply layout direction to the Qt application
        app = QApplication.instance()
        if app:
            if rtl:
                app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            else:
                app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        
        # Update UI text (translation)
        if hasattr(self.app, 'update_ui_text'):
            self.app.update_ui_text()
            
        # Re-display canvas image if present to refresh orientation
        if hasattr(self.app, 'canvas') and self.app.canvas:
            if hasattr(self.app, 'processed_image') and self.app.processed_image is not None:
                self.app.display_image(self.app.processed_image)
            elif hasattr(self.app, 'original_image') and self.app.original_image is not None:
                self.app.display_image(self.app.original_image)
            else:
                self.app.canvas.update()

    def get_layout_summary(self) -> dict:
        """Get a summary of current layout state"""
        return {
            'rtl_enabled': self.is_rtl,
            'previous_rtl_state': self.previous_rtl_state
        }


# Global instance for easy access
_rtl_manager = None


def get_rtl_manager(app_instance=None):
    """Get the global RTL manager instance"""
    global _rtl_manager
    if _rtl_manager is None and app_instance:
        _rtl_manager = RTLManager(app_instance)
    elif _rtl_manager is not None and app_instance:
        _rtl_manager.app = app_instance
    return _rtl_manager