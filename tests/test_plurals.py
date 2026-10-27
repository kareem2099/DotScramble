"""
CLDR plural rules and plural-aware LocalizationManager.get().

Sets `current_language` directly instead of calling set_language(), so the
tests never write a language preference into the user's settings database.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.managers.localization_manager import (  # noqa: E402
    PLURAL_FORMS, LocalizationManager, plural_category,
)

LOCALES = os.path.join(os.path.dirname(__file__), "..", "src", "assets", "locales")


@pytest.mark.parametrize("n, expected", [
    (0, "zero"), (1, "one"), (2, "two"),
    (3, "few"), (10, "few"), (103, "few"),
    (11, "many"), (99, "many"), (111, "many"),
    (100, "other"), (101, "other"), (102, "other"), (1000, "other"),
])
def test_arabic_rules(n, expected):
    assert plural_category("ar", n) == expected


@pytest.mark.parametrize("n, expected", [
    (1, "one"), (21, "one"), (101, "one"),
    (2, "few"), (4, "few"), (22, "few"), (34, "few"),
    (0, "many"), (5, "many"), (11, "many"), (12, "many"), (14, "many"), (25, "many"), (111, "many"),
])
def test_russian_rules(n, expected):
    assert plural_category("ru", n) == expected


@pytest.mark.parametrize("lang", ["en", "de", "tr"])
def test_one_other_languages(lang):
    assert plural_category(lang, 1) == "one"
    assert [plural_category(lang, n) for n in (0, 2, 5, 21)] == ["other"] * 4


def test_spanish_and_persian_specials():
    assert plural_category("es", 1) == "one"
    assert plural_category("es", 2) == "other"
    assert plural_category("es", 1_000_000) == "many"   # "1 000 000 de archivos"
    assert plural_category("fa", 0) == "one"            # CLDR: i = 0 or n = 1
    assert plural_category("fa", 2) == "other"


def test_bad_counts_fall_back_to_other():
    assert plural_category("ar", None) == "other"
    assert plural_category("ar", "abc") == "other"
    assert plural_category("xx", 1) == "other"


@pytest.fixture
def manager():
    return LocalizationManager()


@pytest.mark.parametrize("lang, n, expected", [
    ("en", 1, "Added 1 file"), ("en", 3, "Added 3 files"),
    ("ar", 0, "لم تتم إضافة أي ملف"), ("ar", 1, "تمت إضافة ملف واحد"), ("ar", 2, "تمت إضافة ملفين"),
    ("ar", 3, "تمت إضافة 3 ملفات"), ("ar", 11, "تمت إضافة 11 ملفًا"), ("ar", 100, "تمت إضافة 100 ملف"),
    ("ru", 1, "Добавлен 1 файл"), ("ru", 3, "Добавлено 3 файла"), ("ru", 5, "Добавлено 5 файлов"),
    ("ru", 21, "Добавлен 21 файл"),
    ("de", 1, "1 Datei hinzugefügt"), ("de", 2, "2 Dateien hinzugefügt"),
    ("tr", 4, "4 dosya eklendi"),
])
def test_get_picks_the_right_form(manager, lang, n, expected):
    manager.current_language = lang
    assert manager.get("batch.added", count=n) == expected


def test_plural_without_count_uses_other(manager):
    manager.current_language = "en"
    assert manager.get("batch.added") == "Added {count} files"


def test_missing_key_falls_back_to_english_rules(manager):
    manager.current_language = "ru"
    manager.translations["ru"] = {}          # nothing translated
    assert manager.get("batch.added", count=1) == "Added 1 file"


def test_namespace_is_not_returned_as_text(manager):
    manager.current_language = "en"
    assert manager.get("batch") == "batch"


def _plural_entries():
    def walk(d, p=""):
        for k, v in d.items():
            key = f"{p}.{k}" if p else k
            if isinstance(v, dict) and set(v) <= set(PLURAL_FORMS):
                yield key, v
            elif isinstance(v, dict):
                yield from walk(v, key)
    for name in sorted(os.listdir(LOCALES)):
        if name.endswith(".json") and name != "languages.json":
            data = json.load(open(os.path.join(LOCALES, name), encoding="utf-8"))
            for key, forms in walk(data):
                yield name[:-5], key, forms


@pytest.mark.parametrize("lang, key, forms", list(_plural_entries()))
def test_every_plural_entry_covers_its_language(lang, key, forms):
    """Each plural entry has a form for every category an integer can hit in that language."""
    needed = {plural_category(lang, n) for n in range(0, 1200)}
    assert needed <= set(forms), f"{lang} {key}: missing forms {sorted(needed - set(forms))}"
    for text in forms.values():
        assert not re.search(r"\(s\)|\(\w+\)$", text), f"{lang} {key}: placeholder plural left in {text!r}"
