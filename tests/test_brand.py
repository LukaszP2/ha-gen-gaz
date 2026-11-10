"""Tests for brand assets."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

BRAND_DIR = Path("custom_components/gen_gaz/brand")


class TestBrandAssets(unittest.TestCase):
    """Test brand assets presence, format, and dimensions."""

    def test_brand_directory_exists(self) -> None:
        """Test that brand directory exists."""
        self.assertTrue(BRAND_DIR.is_dir(), f"Brand directory {BRAND_DIR} not found")

    def test_icon_png(self) -> None:
        """Test icon.png exists, is valid PNG, and is square 256x256 px."""
        icon_path = BRAND_DIR / "icon.png"
        self.assertTrue(icon_path.is_file(), "icon.png does not exist")

        with Image.open(icon_path) as img:
            self.assertEqual(img.format, "PNG", "icon.png must be in PNG format")
            self.assertEqual(img.size, (256, 256), "icon.png must be 256x256 px")
            self.assertEqual(img.width, img.height, "icon.png must be square")

    def test_logo_png(self) -> None:
        """Test logo.png exists, is valid PNG, and has valid dimensions."""
        logo_path = BRAND_DIR / "logo.png"
        self.assertTrue(logo_path.is_file(), "logo.png does not exist")

        with Image.open(logo_path) as img:
            self.assertEqual(img.format, "PNG", "logo.png must be in PNG format")
            self.assertGreater(img.width, 0, "logo.png width must be positive")
            self.assertGreater(img.height, 0, "logo.png height must be positive")
