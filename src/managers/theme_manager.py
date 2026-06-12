import json
import os
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Tuple, Optional

# Import database manager for theme persistence
try:
    from .database_manager import get_db_manager
except ImportError:
    get_db_manager = None

class ThemeManager:
    """
    Enhanced Theme Manager with validation, accessibility checking, and preview support.
    Manages application themes loaded from JSON configuration.
    """
    
    # Required color keys for theme validation
    REQUIRED_COLORS = [
        'bg_dark', 'bg_medium', 'bg_light',
        'accent_cyan', 'accent_green', 'accent_red', 'accent_orange', 'accent_purple', 'accent_pink',
        'text_primary', 'text_secondary', 'text_disabled',
        'canvas_bg', 'border_color', 'hover_color', 'selection_bg',
        'success_color', 'error_color', 'warning_color'
    ]
    
    def __init__(self, root, theme_file="src/assets/themes.json", default_theme="midnight"):
        """
        Initialize the ThemeManager.
        
        Args:
            root: Tkinter root window
            theme_file: Path to themes JSON file
            default_theme: Default theme key to use
        """
        self.root = root
        self.themes = {}
        self.current_theme = default_theme
        self.theme_file = theme_file
        self.validation_warnings = []
        
        self.load_themes(theme_file)
        
    def load_themes(self, file_path: str) -> bool:
        """
        Load themes from JSON file with multiple fallback paths.
        
        Args:
            file_path: Primary path to themes file
            
        Returns:
            bool: True if themes loaded successfully, False otherwise
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
        """
        Validate a theme structure and colors.
        
        Args:
            key: Theme identifier
            theme_data: Theme configuration dictionary
            
        Returns:
            bool: True if theme is valid
        """
        # Check required fields
        if 'name' not in theme_data:
            self.validation_warnings.append(f"Theme '{key}' missing 'name' field")
            return False
        
        if 'colors' not in theme_data:
            self.validation_warnings.append(f"Theme '{key}' missing 'colors' field")
            return False
        
        colors = theme_data['colors']
        
        # Check for required color keys
        missing_colors = [c for c in self.REQUIRED_COLORS if c not in colors]
        if missing_colors:
            self.validation_warnings.append(
                f"Theme '{key}' missing colors: {', '.join(missing_colors)}"
            )
            return False
        
        # Validate color format
        for color_key, color_value in colors.items():
            if not self._is_valid_hex_color(color_value):
                self.validation_warnings.append(
                    f"Theme '{key}' has invalid color '{color_key}': {color_value}"
                )
                return False
        
        # Check contrast (warnings only, don't reject)
        self._check_contrast(key, colors)
        
        return True
    
    def _is_valid_hex_color(self, color: str) -> bool:
        """
        Validate hex color format.
        
        Args:
            color: Color string to validate
            
        Returns:
            bool: True if valid hex color
        """
        if not isinstance(color, str):
            return False
        
        if not color.startswith('#'):
            return False
        
        if len(color) not in [4, 7]:  # #RGB or #RRGGBB
            return False
        
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
    
    def _check_contrast(self, theme_key: str, colors: Dict[str, str]) -> None:
        """
        Check color contrast ratios for accessibility (WCAG AA standard).
        
        Args:
            theme_key: Theme identifier
            colors: Color dictionary
        """
        # Check important text/background combinations
        combinations = [
            ('text_primary', 'bg_dark'),
            ('text_primary', 'bg_medium'),
            ('text_secondary', 'bg_medium'),
        ]
        
        for fg_key, bg_key in combinations:
            if fg_key in colors and bg_key in colors:
                ratio = self._calculate_contrast_ratio(colors[fg_key], colors[bg_key])
                if ratio < 4.5:  # WCAG AA standard for normal text
                    self.validation_warnings.append(
                        f"Theme '{theme_key}': Low contrast ({ratio:.2f}:1) between {fg_key} and {bg_key}"
                    )
    
    def _calculate_contrast_ratio(self, color1: str, color2: str) -> float:
        """
        Calculate WCAG contrast ratio between two colors.
        
        Args:
            color1: First hex color
            color2: Second hex color
            
        Returns:
            float: Contrast ratio (1-21)
        """
        def get_luminance(hex_color: str) -> float:
            """Calculate relative luminance of a color."""
            # Remove # and convert to RGB
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = ''.join([c*2 for c in hex_color])
            
            r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
            
            # Apply gamma correction
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
        """Create a minimal fallback theme."""
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

    def apply_theme(self, theme_key: str, app_instance) -> bool:
        """
        Apply theme colors to the entire application.
        
        Args:
            theme_key: Key of theme to apply
            app_instance: Application instance to theme
            
        Returns:
            bool: True if theme applied successfully
        """
        if theme_key not in self.themes:
            print(f"❌ Theme '{theme_key}' not found")
            return False
        
        self.current_theme = theme_key
        colors = self.themes[theme_key]["colors"]
        
        # Update application colors
        app_instance.colors = colors
        
        # Update root window
        self.root.configure(bg=colors['bg_dark'])
        
        # Recursively update all widgets
        self._update_widget_colors(self.root, colors)
        
        # Update canvas if present
        if hasattr(app_instance, 'canvas'):
            app_instance.canvas.configure(
                bg=colors['canvas_bg'],
                highlightbackground=colors['border_color'],
                highlightthickness=1
            )
        
        # Trigger app-specific theme update if method exists
        if hasattr(app_instance, 'on_theme_changed'):
            app_instance.on_theme_changed(colors)
        
        # Save theme preference to database
        self._save_theme_preference(theme_key)
        
        print(f"🎨 Theme applied: {self.themes[theme_key]['name']}")
        return True
    
    def _save_theme_preference(self, theme_key: str) -> None:
        """Save the current theme preference to database."""
        if get_db_manager:
            try:
                db = get_db_manager()
                if db:
                    db.save_last_used_theme(theme_key)
                    print(f"💾 Theme preference saved: {theme_key}")
            except Exception as e:
                print(f"⚠️  Failed to save theme preference: {e}")

    def _update_widget_colors(self, widget, colors: Dict[str, str]) -> None:
        """
        Recursively update widget colors based on widget type.
        
        Args:
            widget: Tkinter widget to update
            colors: Color dictionary
        """
        try:
            w_type = widget.winfo_class()
            
            # Map widget types to color schemes
            if w_type == 'Frame':
                widget.configure(bg=colors['bg_medium'])
                
            elif w_type == 'Label':
                widget.configure(
                    bg=colors['bg_medium'],
                    fg=colors['text_primary']
                )
                
            elif w_type == 'Button':
                # Detect button type by text content
                text = str(widget.cget('text')).lower()
                
                if any(word in text for word in ['reset', 'clear', 'delete', 'remove']):
                    widget.configure(bg=colors['accent_red'], fg='white', activebackground=colors['error_color'])
                elif any(word in text for word in ['apply', 'save', 'ok', 'submit']):
                    widget.configure(bg=colors['accent_cyan'], fg='black', activebackground=colors['hover_color'])
                elif any(word in text for word in ['cancel', 'close']):
                    widget.configure(bg=colors['bg_light'], fg=colors['text_primary'])
                else:
                    widget.configure(
                        bg=colors['bg_light'],
                        fg=colors['text_primary'],
                        activebackground=colors['hover_color'],
                        activeforeground=colors['text_primary']
                    )
            
            elif w_type == 'Radiobutton':
                widget.configure(
                    bg=colors['bg_medium'],
                    fg=colors['text_primary'],
                    selectcolor=colors['bg_dark'],
                    activebackground=colors['hover_color'],
                    activeforeground=colors['text_primary']
                )
            
            elif w_type == 'Checkbutton':
                widget.configure(
                    bg=colors['bg_medium'],
                    fg=colors['text_primary'],
                    selectcolor=colors['bg_dark'],
                    activebackground=colors['hover_color'],
                    activeforeground=colors['text_primary']
                )
                
            elif w_type == 'Scale':
                widget.configure(
                    bg=colors['bg_medium'],
                    fg=colors['text_primary'],
                    troughcolor=colors['bg_dark'],
                    activebackground=colors['accent_cyan'],
                    highlightbackground=colors['border_color']
                )
                
            elif w_type == 'Entry':
                widget.configure(
                    bg=colors['bg_dark'],
                    fg=colors['text_primary'],
                    insertbackground=colors['text_primary'],
                    selectbackground=colors['selection_bg'],
                    selectforeground=colors['text_primary'],
                    disabledbackground=colors['bg_light'],
                    disabledforeground=colors['text_disabled']
                )
            
            elif w_type == 'Text':
                widget.configure(
                    bg=colors['bg_dark'],
                    fg=colors['text_primary'],
                    insertbackground=colors['text_primary'],
                    selectbackground=colors['selection_bg'],
                    selectforeground=colors['text_primary']
                )
            
            elif w_type == 'Listbox':
                widget.configure(
                    bg=colors['bg_dark'],
                    fg=colors['text_primary'],
                    selectbackground=colors['selection_bg'],
                    selectforeground=colors['text_primary']
                )
            
            elif w_type in ['Menu', 'Menubutton']:
                widget.configure(
                    bg=colors['bg_medium'],
                    fg=colors['text_primary'],
                    activebackground=colors['hover_color'],
                    activeforeground=colors['text_primary']
                )
            
            elif w_type == 'Canvas':
                widget.configure(
                    bg=colors['canvas_bg'],
                    highlightbackground=colors['border_color']
                )

        except tk.TclError:
            # Some widgets don't support certain options
            pass
        except Exception as e:
            print(f"⚠️  Error updating {w_type}: {e}")
            
        # Recurse for children
        try:
            for child in widget.winfo_children():
                self._update_widget_colors(child, colors)
        except Exception:
            pass

    def get_theme_names(self) -> List[Tuple[str, str]]:
        """
        Get list of available themes.
        
        Returns:
            List of (display_name, theme_key) tuples
        """
        return [(v['name'], k) for k, v in self.themes.items()]
    
    def get_theme_info(self, theme_key: str) -> Optional[Dict]:
        """
        Get detailed information about a theme.
        
        Args:
            theme_key: Theme identifier
            
        Returns:
            Dictionary with theme metadata or None
        """
        if theme_key not in self.themes:
            return None
        
        theme = self.themes[theme_key]
        return {
            'name': theme['name'],
            'author': theme.get('author', 'Unknown'),
            'description': theme.get('description', 'No description'),
            'colors': theme['colors']
        }
    
    def preview_theme(self, theme_key: str) -> Optional[tk.Toplevel]:
        """
        Show a preview window for a theme.
        
        Args:
            theme_key: Theme to preview
            
        Returns:
            Preview window or None if theme not found
        """
        if theme_key not in self.themes:
            return None
        
        theme = self.themes[theme_key]
        colors = theme['colors']
        
        # Create preview window
        preview = tk.Toplevel(self.root)
        preview.title(f"Theme Preview: {theme['name']}")
        preview.geometry("400x500")
        preview.configure(bg=colors['bg_dark'])
        
        # Theme info
        info_frame = tk.Frame(preview, bg=colors['bg_medium'], padx=10, pady=10)
        info_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(
            info_frame,
            text=theme['name'],
            font=('Arial', 14, 'bold'),
            bg=colors['bg_medium'],
            fg=colors['text_primary']
        ).pack(anchor='w')
        
        tk.Label(
            info_frame,
            text=f"Author: {theme.get('author', 'Unknown')}",
            bg=colors['bg_medium'],
            fg=colors['text_secondary']
        ).pack(anchor='w')
        
        tk.Label(
            info_frame,
            text=theme.get('description', ''),
            bg=colors['bg_medium'],
            fg=colors['text_secondary'],
            wraplength=360
        ).pack(anchor='w', pady=(5, 0))
        
        # Color swatches
        swatch_frame = tk.Frame(preview, bg=colors['bg_dark'])
        swatch_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Display color groups
        color_groups = [
            ("Backgrounds", ['bg_dark', 'bg_medium', 'bg_light']),
            ("Accents", ['accent_cyan', 'accent_green', 'accent_red', 'accent_orange', 'accent_purple', 'accent_pink']),
            ("Text", ['text_primary', 'text_secondary', 'text_disabled']),
            ("UI", ['border_color', 'hover_color', 'selection_bg']),
            ("Status", ['success_color', 'error_color', 'warning_color'])
        ]
        
        for group_name, color_keys in color_groups:
            group_frame = tk.LabelFrame(
                swatch_frame,
                text=group_name,
                bg=colors['bg_medium'],
                fg=colors['text_primary'],
                font=('Arial', 10, 'bold')
            )
            group_frame.pack(fill='x', pady=5)
            
            colors_frame = tk.Frame(group_frame, bg=colors['bg_medium'])
            colors_frame.pack(padx=5, pady=5)
            
            for i, color_key in enumerate(color_keys):
                if color_key in colors:
                    color_box = tk.Frame(
                        colors_frame,
                        bg=colors[color_key],
                        width=40,
                        height=40,
                        relief='solid',
                        borderwidth=1
                    )
                    color_box.grid(row=0, column=i, padx=2, pady=2)
                    
                    tk.Label(
                        colors_frame,
                        text=color_key.replace('_', ' ').title(),
                        bg=colors['bg_medium'],
                        fg=colors['text_secondary'],
                        font=('Arial', 7)
                    ).grid(row=1, column=i)
        
        return preview
    
    def export_theme(self, theme_key: str, filepath: str) -> bool:
        """
        Export a single theme to a JSON file.
        
        Args:
            theme_key: Theme to export
            filepath: Destination file path
            
        Returns:
            bool: True if export successful
        """
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
        """
        Import theme(s) from a JSON file.
        
        Args:
            filepath: Path to theme file
            
        Returns:
            bool: True if import successful
        """
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
        """Get the current theme key."""
        return self.current_theme
    
    def get_current_colors(self) -> Dict[str, str]:
        """Get colors for current theme."""
        if self.current_theme in self.themes:
            return self.themes[self.current_theme]['colors']
        return {}