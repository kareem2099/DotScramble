"""
Smart Localization Manager with Arabic Text Shaping Support
Fixes disconnected Arabic letters in Tkinter
"""
import json
import os
import locale
import logging
from typing import Dict, List, Optional, Any



# Import database manager
from src.managers.database_manager import get_db_manager

# Setup logger
logger = logging.getLogger(__name__)


# ── Plurals ──────────────────────────────────────────────────────────────────
# A translation can be a dict of CLDR plural forms instead of a string:
#     "added": {"one": "Added {count} file", "other": "Added {count} files"}
# get(key, count=n) then picks the form for n in the current language.
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")


def _plural_ar(n: int) -> str:
    if n == 0: return "zero"
    if n == 1: return "one"
    if n == 2: return "two"
    if 3 <= n % 100 <= 10: return "few"
    if 11 <= n % 100 <= 99: return "many"
    return "other"


def _plural_ru(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11: return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14: return "few"
    return "many"


def _plural_one_other(n: int) -> str:
    return "one" if n == 1 else "other"


def _plural_es(n: int) -> str:
    # CLDR: "many" for exact millions ("1 000 000 de archivos")
    if n == 1: return "one"
    if n != 0 and n % 1_000_000 == 0: return "many"
    return "other"


def _plural_fa(n: int) -> str:
    return "one" if n in (0, 1) else "other"


# CLDR cardinal rules for whole numbers (counts are never fractional here)
_PLURAL_RULES = {
    "ar": _plural_ar,
    "ru": _plural_ru,
    "es": _plural_es,
    "fa": _plural_fa,
    "en": _plural_one_other,
    "de": _plural_one_other,
    "tr": _plural_one_other,
}


def plural_category(language: str, n) -> str:
    """CLDR plural category of `n` in `language` ('other' for unknown languages)."""
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return "other"
    return _PLURAL_RULES.get(language, lambda _n: "other")(n)


def _is_plural_entry(value) -> bool:
    return isinstance(value, dict) and bool(value) and set(value) <= set(PLURAL_FORMS)


def _pick_plural(forms: dict, language: str, count) -> str:
    form = plural_category(language, count)
    return forms.get(form) or forms.get("other") or next(iter(forms.values()))


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
        return text  # Qt6 handles bidi + shaping internally

    def get(self, key: str, **kwargs) -> str:
        """
        Get translated text for a dotted key, formatted with kwargs.
        Plural entries pick their form from kwargs['count'] (CLDR rules).
        """
        # 1. Try current language
        language = self.current_language
        text = self._get_nested_value(self.translations.get(language, {}), key)

        # 2. Fallback to default (English)
        if text is None:
            language = self.default_language
            text = self._get_nested_value(self.translations.get(language, {}), key)

        # 3. Plural entry → the form for this count, in the language the text came from
        if _is_plural_entry(text):
            text = _pick_plural(text, language, kwargs.get("count"))

        # 4. Return key if not found (or a namespace was requested)
        if text is None or isinstance(text, dict):
            return key

        # 5. Format string (Apply variables FIRST)
        final_text = str(text)
        if kwargs:
            try: final_text = final_text.format(**kwargs)
            except: pass

        # 6. Fix Rendering (Reshape Arabic AFTER formatting)
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
            sys_lang = locale.getlocale()[0] or os.environ.get('LANG', '')
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