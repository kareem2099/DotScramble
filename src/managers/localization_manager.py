"""
Smart Localization Manager with Arabic Text Shaping Support
Fixes disconnected Arabic letters in Tkinter
"""
import json
import os
import locale
import logging
from typing import Dict, List, Optional, Any

# Import Arabic text shaping libraries
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False
    print("⚠️ Arabic support libraries not found. Run: pip install arabic-reshaper python-bidi")

# Import database manager
from src.managers.database_manager import get_db_manager

# Setup logger
logger = logging.getLogger(__name__)

class LocalizationManager:
    def __init__(self, app_root: str = None, default_language: str = "en"):
        # Set correct path (src/assets/locales)
        if app_root is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # src/
            self.assets_dir = os.path.join(base_dir, "assets", "locales")
        else:
            self.assets_dir = os.path.join(app_root, "assets", "locales")

        self.default_language = default_language
        self.current_language = default_language
        self.translations = {}
        self.language_info = {}
        self.rtl_languages = set()

        # Connect to database
        self.db = get_db_manager()

        # Load Data
        self._load_language_metadata()
        self._load_translations()
        
        # Restore saved language from database (or use system language)
        saved_lang = None
        if self.db:
            saved_lang = self.db.get_setting('language')
        
        if saved_lang:
            self.set_language(saved_lang)
        else:
            self.set_language(self._detect_system_language())

    def _load_language_metadata(self) -> None:
        """Load languages.json from src/assets/locales"""
        languages_file = os.path.join(self.assets_dir, "languages.json")
        
        # Default fallback
        default_data = {
            "en": {"name": "English", "native": "English", "rtl": False},
            "ar": {"name": "Arabic", "native": "العربية", "rtl": True}
        }

        try:
            if os.path.exists(languages_file):
                with open(languages_file, 'r', encoding='utf-8') as f:
                    self.language_info = json.load(f)
            else:
                # Create if not exists
                os.makedirs(self.assets_dir, exist_ok=True)
                with open(languages_file, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, indent=4)
                self.language_info = default_data
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            self.language_info = default_data
            
        self.rtl_languages = {c for c, i in self.language_info.items() if i.get('rtl', False)}

    def _load_translations(self) -> None:
        """Load all translation files"""
        if not os.path.exists(self.assets_dir): return

        for lang_code in self.language_info.keys():
            # Support both structure: locales/en.json OR locales/en/translations.json
            # We will use simple: locales/en.json
            file_path = os.path.join(self.assets_dir, f"{lang_code}.json")
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading {lang_code}: {e}")

    def set_language(self, language_code: str) -> bool:
        if language_code not in self.language_info:
            return False
        
        self.current_language = language_code
        
        # Save language to database
        if self.db:
            self.db.save_setting('language', language_code)
            
        return True

    def _get_nested_value(self, data: Dict, key_path: str) -> Any:
        """Helper to traverse nested dictionary using dot notation"""
        keys = key_path.split('.')
        value = data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return None

    def _fix_text_rendering(self, text: str) -> str:
        """Helper to reshape Arabic text for correct display"""
        if not ARABIC_SUPPORT:
            # Fallback: at least set proper text direction for RTL languages
            if self.is_rtl():
                # Add Right-to-Left Mark (U+200F) at the beginning
                return f"\u200F{text}"
            return text
            
        # If current language is Arabic (or any RTL language), apply the fix
        if self.is_rtl():
            try:
                reshaped_text = arabic_reshaper.reshape(text)
                bidi_text = get_display(reshaped_text)
                return bidi_text
            except:
                # Fallback to RTL mark if reshaping fails
                return f"\u200F{text}"
        return text

    def get(self, key: str, **kwargs) -> str:
        """Get translated text handling nested keys and Arabic reshaping"""
        # 1. Try current language
        lang_data = self.translations.get(self.current_language, {})
        text = self._get_nested_value(lang_data, key)

        # 2. Fallback to default (English)
        if text is None:
            text = self._get_nested_value(self.translations.get(self.default_language, {}), key)

        # 3. Return key if not found
        if text is None:
            return key

        # 4. Format string (Apply variables FIRST)
        final_text = str(text)
        if kwargs:
            try: final_text = final_text.format(**kwargs)
            except: pass
            
        # 5. Fix Rendering (Reshape Arabic AFTER formatting)
        return self._fix_text_rendering(final_text)

    def is_rtl(self) -> bool:
        return self.current_language in self.rtl_languages
    
    def get_language_list(self) -> List[Dict[str, str]]:
        """Get list of supported languages."""
        return [
            {
                'code': code,
                'name': info['name'],
                'native_name': info['native']
            }
            for code, info in self.language_info.items()
        ]
        
    def _detect_system_language(self) -> str:
        try:
            sys_lang = locale.getdefaultlocale()[0]
            if sys_lang:
                code = sys_lang.split('_')[0].lower()
                if code in self.language_info:
                    return code
        except: pass
        return self.default_language

# Global Instance
_locale_manager = None

def get_locale_manager():
    global _locale_manager
    if _locale_manager is None:
        _locale_manager = LocalizationManager()
    return _locale_manager