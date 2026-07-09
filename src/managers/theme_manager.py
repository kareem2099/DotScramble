import json
import os
from typing import Dict, List, Tuple, Optional
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QFrame, QGroupBox, QGridLayout, QPushButton
from PySide6.QtCore import Qt

# Import database manager for theme persistence
try:
    from .database_manager import get_db_manager
except ImportError:
    get_db_manager = None

class ThemeManager:
    """
    Enhanced Theme Manager with validation, accessibility checking, and preview support.
    Manages application themes loaded from JSON configuration and applies them using QSS.
    """
    
    # Required color keys for theme validation
    REQUIRED_COLORS = [
        'bg_dark', 'bg_medium', 'bg_light',
        'accent_cyan', 'accent_green', 'accent_red', 'accent_orange', 'accent_purple', 'accent_pink',
        'text_primary', 'text_secondary', 'text_disabled',
        'canvas_bg', 'border_color', 'hover_color', 'selection_bg',
        'success_color', 'error_color', 'warning_color'
    ]
    
    def get_styled_qss(self, colors: Dict[str, str]) -> str:
        """
        Loads the QSS stylesheet template and replaces all color variables.
        """
        template = ""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        paths_to_try = [
            os.path.join(base_dir, "assets", "themes", "theme_template.qss"),
            os.path.join(os.getcwd(), "assets", "themes", "theme_template.qss"),
            "assets/themes/theme_template.qss"
        ]
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        template = f.read()
                        break
                except Exception as e:
                    print(f"⚠️ Error reading stylesheet template: {e}")
                    
        if not template:
            # Safe basic fallback styling
            template = """
            QWidget { background-color: {bg_dark}; color: {text_primary}; }
            QMainWindow { background-color: {bg_dark}; }
            """
            
        qss_code = template
        for key, value in colors.items():
            qss_code = qss_code.replace(f"{{{key}}}", value)
        return qss_code
    
    def __init__(self, app_instance=None, theme_file="src/assets/themes.json", default_theme="midnight"):
        """
        Initialize the ThemeManager.
        
        Args:
            app_instance: QApplication instance
            theme_file: Path to themes JSON file
            default_theme: Default theme key to use
        """
        self.app_instance = app_instance
        self.themes = {}
        self.current_theme = default_theme
        self.theme_file = theme_file
        self.validation_warnings = []
        
        self.load_themes(theme_file)
        
    def load_themes(self, file_path: str) -> bool:
        """
        Load themes from JSON file with multiple fallback paths.
        """
        paths_to_try = [file_path]
        
        # Add fallback paths
        if not os.path.exists(file_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            paths_to_try.extend([
                os.path.join(base_dir, "assets", "themes", "themes.json"),
                os.path.join(base_dir, "src", "assets", "themes.json"),
                os.path.join(base_dir, "themes.json"),
                os.path.join(os.getcwd(), "themes.json")
            ])
        
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        loaded_themes = json.load(f)
                    
                    # Validate themes
                    self.themes = {}
                    for key, theme_data in loaded_themes.items():
                        if self._validate_theme(key, theme_data):
                            self.themes[key] = theme_data
                    
                    if self.themes:
                        print(f"✅ Loaded {len(self.themes)} theme(s) from: {path}")
                        if self.validation_warnings:
                            print(f"⚠️  {len(self.validation_warnings)} validation warning(s)")
                            for warning in self.validation_warnings[:5]:  # Show first 5
                                print(f"   - {warning}")
                        return True
                        
                except json.JSONDecodeError as e:
                    print(f"❌ JSON parsing error in {path}: {e}")
                except Exception as e:
                    print(f"❌ Error loading themes from {path}: {e}")
        
        # Fallback to default theme
        print("⚠️  Using fallback default theme")
        self._create_fallback_theme()
        return False

    def _validate_theme(self, key: str, theme_data: Dict) -> bool:
        """Validate theme structure and colors."""
        if 'name' not in theme_data:
            self.validation_warnings.append(f"Theme '{key}' missing 'name' field")
            return False
        
        if 'colors' not in theme_data:
            self.validation_warnings.append(f"Theme '{key}' missing 'colors' field")
            return False
        
        colors = theme_data['colors']
        
        missing_colors = [c for c in self.REQUIRED_COLORS if c not in colors]
        if missing_colors:
            self.validation_warnings.append(
                f"Theme '{key}' missing colors: {', '.join(missing_colors)}"
            )
            return False
        
        for color_key, color_value in colors.items():
            if not self._is_valid_hex_color(color_value):
                self.validation_warnings.append(
                    f"Theme '{key}' has invalid color '{color_key}': {color_value}"
                )
                return False
        
        self._check_contrast(key, colors)
        return True
    
    def _is_valid_hex_color(self, color: str) -> bool:
        if not isinstance(color, str):
            return False
        if not color.startswith('#'):
            return False
        if len(color) not in [4, 7]:
            return False
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
    
    def _check_contrast(self, theme_key: str, colors: Dict[str, str]) -> None:
        combinations = [
            ('text_primary', 'bg_dark'),
            ('text_primary', 'bg_medium'),
            ('text_secondary', 'bg_medium'),
        ]
        
        for fg_key, bg_key in combinations:
            if fg_key in colors and bg_key in colors:
                ratio = self._calculate_contrast_ratio(colors[fg_key], colors[bg_key])
                if ratio < 4.5:
                    self.validation_warnings.append(
                        f"Theme '{theme_key}': Low contrast ({ratio:.2f}:1) between {fg_key} and {bg_key}"
                    )
    
    def _calculate_contrast_ratio(self, color1: str, color2: str) -> float:
        def get_luminance(hex_color: str) -> float:
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = ''.join([c*2 for c in hex_color])
            
            r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
            
            def adjust(c):
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            
            r, g, b = adjust(r), adjust(g), adjust(b)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
        
        lum1 = get_luminance(color1)
        lum2 = get_luminance(color2)
        lighter = max(lum1, lum2)
        darker = min(lum1, lum2)
        return (lighter + 0.05) / (darker + 0.05)
    
    def _create_fallback_theme(self) -> None:
        self.themes = {
            "midnight": {
                "name": "🌑 Midnight (Fallback)",
                "author": "System",
                "description": "Fallback default theme",
                "colors": {
                    "bg_dark": "#1e1e1e",
                    "bg_medium": "#252526",
                    "bg_light": "#333333",
                    "accent_cyan": "#00bcd4",
                    "accent_green": "#4caf50",
                    "accent_red": "#f44336",
                    "accent_orange": "#ff9800",
                    "accent_purple": "#9c27b0",
                    "accent_pink": "#e91e63",
                    "text_primary": "#ffffff",
                    "text_secondary": "#cccccc",
                    "text_disabled": "#808080",
                    "canvas_bg": "#1e1e1e",
                    "border_color": "#3e3e3e",
                    "hover_color": "#2d2d2d",
                    "selection_bg": "#264f78",
                    "success_color": "#4caf50",
                    "error_color": "#f44336",
                    "warning_color": "#ff9800"
                }
            }
        }

    def apply_theme(self, theme_key: str, ui_view_or_app) -> bool:
        """
        Apply theme colors to the entire application using QSS.
        
        Args:
            theme_key: Key of theme to apply
            ui_view_or_app: Main window view or QApplication instance
        """
        if theme_key not in self.themes:
            print(f"❌ Theme '{theme_key}' not found")
            return False
        
        self.current_theme = theme_key
        colors = self.themes[theme_key]["colors"]
        
        # Store colors in both app and main window
        if hasattr(ui_view_or_app, 'colors'):
            ui_view_or_app.colors = colors
            
        # Get reference to QApplication
        app = QApplication.instance()
        if not app and self.app_instance:
            app = self.app_instance
            
        # Dynamically generate QSS stylesheet
        qss_code = self.get_styled_qss(colors)
        
        # Apply stylesheet globally
        if app:
            app.setStyleSheet(qss_code)
            
        # If applied to a QWidget / QMainWindow specifically, apply stylesheet there too
        if hasattr(ui_view_or_app, 'setStyleSheet'):
            ui_view_or_app.setStyleSheet(qss_code)
            
        # Trigger specific theme changed callback
        if hasattr(ui_view_or_app, 'on_theme_changed'):
            ui_view_or_app.on_theme_changed(colors)
            
        # Save theme preference to database
        self._save_theme_preference(theme_key)
        
        print(f"🎨 Theme applied: {self.themes[theme_key]['name']}")
        return True
    
    def _save_theme_preference(self, theme_key: str) -> None:
        if get_db_manager:
            try:
                db = get_db_manager()
                if db:
                    db.save_last_used_theme(theme_key)
                    print(f"💾 Theme preference saved: {theme_key}")
            except Exception as e:
                print(f"⚠️  Failed to save theme preference: {e}")

    def get_theme_names(self) -> List[Tuple[str, str]]:
        return [(v['name'], k) for k, v in self.themes.items()]
    
    def get_theme_info(self, theme_key: str) -> Optional[Dict]:
        if theme_key not in self.themes:
            return None
        theme = self.themes[theme_key]
        return {
            'name': theme['name'],
            'author': theme.get('author', 'Unknown'),
            'description': theme.get('description', 'No description'),
            'colors': theme['colors']
        }
    
    def preview_theme(self, theme_key: str) -> Optional[QDialog]:
        """
        Show a preview dialog for a theme.
        """
        if theme_key not in self.themes:
            return None
        
        theme = self.themes[theme_key]
        colors = theme['colors']
        
        dialog = QDialog()
        dialog.setWindowTitle(f"Theme Preview: {theme['name']}")
        dialog.setMinimumSize(400, 500)
        dialog.setStyleSheet(self.get_styled_qss(colors))
        
        layout = QVBoxLayout(dialog)
        
        # Info Group
        info_frame = QFrame()
        info_frame.setStyleSheet(f"background-color: {colors['bg_medium']}; border-radius: 6px; padding: 10px;")
        info_layout = QVBoxLayout(info_frame)
        
        name_lbl = QLabel(theme['name'])
        name_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {colors['text_primary']};")
        info_layout.addWidget(name_lbl)
        
        author_lbl = QLabel(f"Author: {theme.get('author', 'Unknown')}")
        author_lbl.setStyleSheet(f"color: {colors['text_secondary']};")
        info_layout.addWidget(author_lbl)
        
        desc_lbl = QLabel(theme.get('description', ''))
        desc_lbl.setStyleSheet(f"color: {colors['text_secondary']};")
        desc_lbl.setWordWrap(True)
        info_layout.addWidget(desc_lbl)
        
        layout.addWidget(info_frame)
        
        # Swatches layout
        swatch_group = QGroupBox("Color Swatches")
        grid_layout = QGridLayout(swatch_group)
        
        color_keys = [
            ('bg_dark', 0, 0), ('bg_medium', 0, 1), ('bg_light', 0, 2),
            ('accent_cyan', 1, 0), ('accent_green', 1, 1), ('accent_red', 1, 2),
            ('accent_orange', 2, 0), ('accent_purple', 2, 1), ('accent_pink', 2, 2),
            ('text_primary', 3, 0), ('text_secondary', 3, 1), ('text_disabled', 3, 2)
        ]
        
        for key, r, c in color_keys:
            if key in colors:
                cell = QFrame()
                cell.setMinimumSize(50, 50)
                cell.setStyleSheet(f"background-color: {colors[key]}; border: 1px solid {colors['border_color']}; border-radius: 4px;")
                
                label = QLabel(key.replace('_', ' ').title())
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet(f"font-size: 9px; color: {colors['text_secondary']};")
                
                cell_layout = QVBoxLayout(cell)
                cell_layout.addWidget(label)
                
                grid_layout.addWidget(cell, r, c)
                
        layout.addWidget(swatch_group)
        
        # Close Button
        btn = QPushButton("Close")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        
        dialog.exec()
        return dialog
    
    def export_theme(self, theme_key: str, filepath: str) -> bool:
        if theme_key not in self.themes:
            return False
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({theme_key: self.themes[theme_key]}, f, indent=4)
            print(f"✅ Exported theme '{theme_key}' to {filepath}")
            return True
        except Exception as e:
            print(f"❌ Error exporting theme: {e}")
            return False
    
    def import_theme(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                new_themes = json.load(f)
            imported = 0
            for key, theme_data in new_themes.items():
                if self._validate_theme(key, theme_data):
                    self.themes[key] = theme_data
                    imported += 1
            if imported > 0:
                print(f"✅ Imported {imported} theme(s)")
                return True
            else:
                print("❌ No valid themes found in file")
                return False
        except Exception as e:
            print(f"❌ Error importing themes: {e}")
            return False
    
    def get_current_theme_key(self) -> str:
        return self.current_theme
    
    def get_current_colors(self) -> Dict[str, str]:
        if self.current_theme in self.themes:
            return self.themes[self.current_theme]['colors']
        return {}