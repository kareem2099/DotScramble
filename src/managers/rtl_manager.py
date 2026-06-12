"""
RTL (Right-to-Left) Layout Manager for DotScramble

This module handles all RTL layout concerns including:
- Grid weight configuration
- Widget positioning and mirroring
- Menu bar visibility fixes
- Layout state management
- Debug utilities for troubleshooting
"""

import tkinter as tk
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class RTLManager:
    """Comprehensive RTL layout management system"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.is_rtl = False
        self.previous_rtl_state = False
        self.layout_state = {}
        
        # Panel configuration
        self.panel_config = {
            'control_panel': {
                'min_width': 350,
                'weight': 0,  # Fixed width
                'sticky': 'ns'
            },
            'canvas_panel': {
                'min_width': 400,
                'weight': 1,  # Expandable
                'sticky': 'nsew'
            }
        }
    
    def set_rtl_state(self, rtl: bool) -> None:
        """Set RTL state and trigger layout updates if changed"""
        if rtl == self.is_rtl:
            return  # No change needed
            
        self.previous_rtl_state = self.is_rtl
        self.is_rtl = rtl
        
        logger.info(f"RTL state changed: {self.previous_rtl_state} → {self.is_rtl}")
        
        # Store current layout state before changes
        self._capture_layout_state()
        
        # Apply RTL layout changes
        self._apply_rtl_layout()
        
        # Update UI text and widget properties
        self._update_ui_for_rtl()
        
        # Fix menu bar visibility issues
        self._fix_menu_bar_visibility()
        
        # Validate layout after changes
        self._validate_layout_state()
    
    def _capture_layout_state(self) -> None:
        """Capture current layout state for debugging"""
        try:
            if hasattr(self.app, 'main_container') and self.app.main_container:
                container = self.app.main_container
                
                # Capture grid configuration
                self.layout_state['grid_config'] = {
                    'col_0_weight': container.grid_columnconfigure(0).get('weight', 0),
                    'col_1_weight': container.grid_columnconfigure(1).get('weight', 0),
                    'col_0_minsize': container.grid_columnconfigure(0).get('minsize', 0),
                    'col_1_minsize': container.grid_columnconfigure(1).get('minsize', 0)
                }
                
                # Capture panel positions
                if hasattr(self.app, 'left_panel') and hasattr(self.app, 'right_panel'):
                    self.layout_state['panel_positions'] = {
                        'left_panel': self._get_panel_grid_info(self.app.left_panel),
                        'right_panel': self._get_panel_grid_info(self.app.right_panel)
                    }
        except Exception as e:
            logger.warning(f"Could not capture layout state: {e}")
    
    def _get_panel_grid_info(self, panel) -> Dict[str, Any]:
        """Get grid information for a panel"""
        try:
            grid_info = panel.grid_info()
            return {
                'row': grid_info.get('row', 0),
                'column': grid_info.get('column', 0),
                'sticky': grid_info.get('sticky', ''),
                'padx': grid_info.get('padx', 0),
                'pady': grid_info.get('pady', 0)
            }
        except:
            return {}
    
    def _apply_rtl_layout(self) -> None:
        """Apply RTL layout by moving panels to new grid columns directly."""
        try:
            if not hasattr(self.app, 'main_container') or not self.app.main_container:
                logger.warning("Main container not found, cannot apply RTL layout")
                return

            container = self.app.main_container

            # Temporarily freeze container geometry propagation.
            # Without this, grid_columnconfigure() calls propagate a new
            # minimum-size request up to root → X11 grants a different
            # window height (979 → 1012px) → status bar slides off-screen.
            container.grid_propagate(False)
            try:
                self._configure_grid_weights(container)
                self._reposition_panels(container)
            finally:
                container.grid_propagate(True)

            logger.info("RTL layout applied successfully")

        except Exception as e:
            logger.error(f"Error applying RTL layout: {e}")


    def _configure_grid_weights(self, container) -> None:
        """Configure grid column weights based on RTL state.

        NOTE: Do NOT set minsize here — minsize propagates up to the root
        window and causes it to grow by ~33px on X11, pushing the status
        bar below the visible screen area in maximized windows.
        left_panel already enforces its own size via grid_propagate(False).
        """
        container.grid_columnconfigure(0, weight=0, minsize=0)
        container.grid_columnconfigure(1, weight=0, minsize=0)

        if self.is_rtl:
            # RTL: Canvas LEFT (col 0, expandable) | Controls RIGHT (col 1, fixed)
            container.grid_columnconfigure(0, weight=1)
            container.grid_columnconfigure(1, weight=0)
        else:
            # LTR: Controls LEFT (col 0, fixed) | Canvas RIGHT (col 1, expandable)
            container.grid_columnconfigure(0, weight=0)
            container.grid_columnconfigure(1, weight=1)


    def _reposition_panels(self, container) -> None:
        """Move panels to correct columns for current RTL state.

        Calls grid() directly on already-managed widgets — Tkinter supports
        updating a widget's grid options without grid_forget first.
        No pack_forget is done so inner content never flickers.
        """
        try:
            if not hasattr(self.app, 'left_panel') or not hasattr(self.app, 'right_panel'):
                logger.warning("Panels not found, cannot reposition")
                return

            if self.is_rtl:
                control_col, canvas_col = 1, 0
                control_padx, canvas_padx = (15, 0), (0, 15)
            else:
                control_col, canvas_col = 0, 1
                control_padx, canvas_padx = (0, 15), (15, 0)

            # Move control panel (left_panel) to new column — no grid_forget needed
            self.app.left_panel.grid(
                row=0,
                column=control_col,
                sticky=self.panel_config['control_panel']['sticky'],
                padx=control_padx,
            )

            # Move canvas panel (right_panel) to new column — no grid_forget needed
            self.app.right_panel.grid(
                row=0,
                column=canvas_col,
                sticky=self.panel_config['canvas_panel']['sticky'],
                padx=canvas_padx,
            )

            logger.debug(f"Panels repositioned: RTL={self.is_rtl}")

        except Exception as e:
            logger.error(f"Error repositioning panels: {e}")
            raise

    

    
    def _update_ui_for_rtl(self) -> None:
        """Update UI text and widget properties for RTL layout"""
        try:
            # Update UI text (translation)
            self.app.update_ui_text()
            self.app.update_input_field_direction()
            
            # Apply full mirroring to all widgets
            self._apply_full_mirroring()
            
            # Update button references if they exist
            if hasattr(self.app, 'update_button_references'):
                self.app.update_button_references()
                
        except Exception as e:
            logger.warning(f"Error updating UI for RTL: {e}")
    
    def _apply_full_mirroring(self) -> None:
        """Apply full mirroring to all widgets for RTL layout"""
        try:
            # Get text direction properties
            anchor = self._get_text_anchor("w")
            justify = self._get_text_justify("left")
            
            # Update the Status Bar
            if hasattr(self.app, 'status_label') and self.app.status_label is not None:
                if self.app.status_label.winfo_exists():
                    self.app.status_label.config(anchor=anchor, justify=justify)
            
            # Update all Labels, Radiobuttons, and Checkbuttons in the Left Panel
            if hasattr(self.app, 'left_panel') and self.app.left_panel:
                for widget in self.app.left_panel.winfo_children():
                    if isinstance(widget, tk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, (tk.Label, tk.Radiobutton, tk.Checkbutton)):
                                child.config(anchor=anchor)
            
            # Update all Labels, Radiobuttons, and Checkbuttons in the Right Panel
            if hasattr(self.app, 'right_panel') and self.app.right_panel:
                for widget in self.app.right_panel.winfo_children():
                    if isinstance(widget, tk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, (tk.Label, tk.Radiobutton, tk.Checkbutton)):
                                child.config(anchor=anchor)
            
            # Force Canvas Update for RTL
            if self.app.original_image is not None:
                self.app.root.after(100, lambda: self.app.display_image(
                    self.app.processed_image if self.app.processed_image is not None else self.app.original_image
                ))
                
        except Exception as e:
            logger.warning(f"Error applying full mirroring: {e}")
    
    def _fix_menu_bar_visibility(self) -> None:
        """Ensure menu bar is visible after layout changes"""
        try:
            if not hasattr(self.app, 'menubar') or not self.app.menubar:
                logger.warning("Menu bar not found")
                return

            # Simply re-assign the menubar — safe, no geometry thrashing.
            # Do NOT use root.config(menu='') then restore — that triggers a full
            # pack geometry recalculation which collapses the status bar.
            self.app.root.config(menu=self.app.menubar)

            logger.debug("Menu bar visibility fixed")

        except Exception as e:
            logger.warning(f"Could not fix menu bar: {e}")
    
    def _validate_layout_state(self) -> None:
        """Validate that layout state is correct after RTL changes"""
        try:
            if not hasattr(self.app, 'main_container') or not self.app.main_container:
                logger.warning("Layout validation failed: main container missing")
                return
            
            container = self.app.main_container
            
            # Check grid weights
            col0_weight = container.grid_columnconfigure(0).get('weight', 0)
            col1_weight = container.grid_columnconfigure(1).get('weight', 0)
            
            if self.is_rtl:
                expected_col0 = 1  # Canvas should expand
                expected_col1 = 0  # Controls should be fixed
            else:
                expected_col0 = 0  # Controls should be fixed
                expected_col1 = 1  # Canvas should expand
            
            if col0_weight != expected_col0 or col1_weight != expected_col1:
                logger.warning(f"Layout validation failed: weights {col0_weight},{col1_weight} != expected {expected_col0},{expected_col1}")
                # Attempt to fix by reapplying layout
                self._apply_rtl_layout()
            else:
                logger.debug("Layout validation passed")
                
        except Exception as e:
            logger.warning(f"Layout validation error: {e}")
    
    def _get_text_anchor(self, default="w") -> str:
        """Return appropriate text anchor based on RTL state."""
        if not self.is_rtl:
            return default
        # Flip anchors for RTL
        anchor_map = {
            "w": "e", "e": "w",
            "nw": "ne", "ne": "nw",
            "sw": "se", "se": "sw",
            "n": "n", "s": "s", "center": "center"
        }
        return anchor_map.get(default, default)
    
    def _get_text_justify(self, default="left") -> str:
        """Return appropriate text justification based on RTL state."""
        if not self.is_rtl:
            return default
        # Flip justification for RTL
        justify_map = {"left": "right", "right": "left", "center": "center"}
        return justify_map.get(default, default)
    
    def debug_layout_state(self) -> None:
        """Print current layout state for debugging."""
        try:
            print(f"\n{'='*60}")
            print(f"RTL State: {self.is_rtl}")
            print(f"Previous RTL State: {self.previous_rtl_state}")
            
            if hasattr(self.app, 'main_container') and self.app.main_container:
                col0_weight = self.app.main_container.grid_columnconfigure(0).get('weight', 0)
                col1_weight = self.app.main_container.grid_columnconfigure(1).get('weight', 0)
                col0_minsize = self.app.main_container.grid_columnconfigure(0).get('minsize', 0)
                col1_minsize = self.app.main_container.grid_columnconfigure(1).get('minsize', 0)
                print(f"Grid Weights: col0={col0_weight}, col1={col1_weight}")
                print(f"Grid Min Sizes: col0={col0_minsize}, col1={col1_minsize}")
            
            if hasattr(self.app, 'left_panel') and self.app.left_panel:
                grid_info = self.app.left_panel.grid_info()
                print(f"Left Panel: column={grid_info.get('column')}, width={self.app.left_panel.winfo_width()}")
            
            if hasattr(self.app, 'right_panel') and self.app.right_panel:
                grid_info = self.app.right_panel.grid_info()
                print(f"Right Panel: column={grid_info.get('column')}, width={self.app.right_panel.winfo_width()}")
            
            print(f"{'='*60}\n")
            
        except Exception as e:
            logger.error(f"Debug failed: {e}")
    
    def get_layout_summary(self) -> Dict[str, Any]:
        """Get a summary of current layout state"""
        summary = {
            'rtl_enabled': self.is_rtl,
            'panel_config': self.panel_config.copy(),
            'layout_state': self.layout_state.copy()
        }
        
        try:
            if hasattr(self.app, 'main_container') and self.app.main_container:
                container = self.app.main_container
                summary['grid_config'] = {
                    'col_0_weight': container.grid_columnconfigure(0).get('weight', 0),
                    'col_1_weight': container.grid_columnconfigure(1).get('weight', 0),
                    'col_0_minsize': container.grid_columnconfigure(0).get('minsize', 0),
                    'col_1_minsize': container.grid_columnconfigure(1).get('minsize', 0)
                }
        except:
            pass
        
        return summary


# Global instance for easy access
_rtl_manager = None


def get_rtl_manager(app_instance=None):
    """Get the global RTL manager instance"""
    global _rtl_manager
    if _rtl_manager is None and app_instance:
        _rtl_manager = RTLManager(app_instance)
    return _rtl_manager