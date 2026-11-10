"""Tests for translations matching strings.json."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

BASE_DIR = Path("custom_components/gen_gaz")


def get_key_paths(data: dict[str, Any], prefix: str = "") -> set[str]:
    """Recursively collect all dot-separated key paths from a dictionary."""
    paths: set[str] = set()
    for key, value in data.items():
        current_path = f"{prefix}.{key}" if prefix else str(key)
        paths.add(current_path)
        if isinstance(value, dict):
            paths.update(get_key_paths(value, current_path))
    return paths


class TestTranslations(unittest.TestCase):
    """Test suite for translation files."""

    def setUp(self) -> None:
        """Load strings.json and translation files."""
        with open(BASE_DIR / "strings.json", encoding="utf-8") as f:
            self.strings = json.load(f)
        with open(BASE_DIR / "translations" / "en.json", encoding="utf-8") as f:
            self.en = json.load(f)
        with open(BASE_DIR / "translations" / "pl.json", encoding="utf-8") as f:
            self.pl = json.load(f)
        self.strings_keys = get_key_paths(self.strings)

    def test_en_translation_contains_all_strings_keys(self) -> None:
        """Test translations/en.json has all keys defined in strings.json."""
        en_keys = get_key_paths(self.en)
        missing_keys = self.strings_keys - en_keys
        self.assertEqual(
            missing_keys,
            set(),
            f"Missing keys in translations/en.json: {sorted(missing_keys)}",
        )

    def test_pl_translation_contains_all_strings_keys(self) -> None:
        """Test translations/pl.json has all keys defined in strings.json."""
        pl_keys = get_key_paths(self.pl)
        missing_keys = self.strings_keys - pl_keys
        self.assertEqual(
            missing_keys,
            set(),
            f"Missing keys in translations/pl.json: {sorted(missing_keys)}",
        )
