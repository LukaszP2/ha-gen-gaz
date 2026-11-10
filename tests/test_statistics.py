"""Tests for statistics handling."""

from __future__ import annotations

import unittest
from datetime import UTC
from unittest.mock import MagicMock, patch

from custom_components.gen_gaz.statistics import (
    _parse_date,
    import_reading_statistics,
)


class TestGenGazStatistics(unittest.TestCase):
    """Test suite for statistics."""

    def test_parse_date_naive(self) -> None:
        """Test parse date attaches UTC to naive string and rounds to the hour."""
        dt = _parse_date("2024-03-15T14:32:15")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.tzinfo, UTC)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.second, 0)
        self.assertEqual(dt.microsecond, 0)
        self.assertEqual(dt.hour, 14)

    def test_parse_date_with_z(self) -> None:
        """Test parse date handles ISO string with Z."""
        dt = _parse_date("2024-03-15T10:15:00Z")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.tzinfo, UTC)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.hour, 10)

    def test_parse_date_invalid(self) -> None:
        """Test parse date returns None on invalid string."""
        self.assertIsNone(_parse_date("not-a-date"))
        self.assertIsNone(_parse_date(12345))

    @patch("custom_components.gen_gaz.statistics.async_add_external_statistics")
    def test_import_reading_statistics_success(self, mock_add_stats: MagicMock) -> None:
        """Test import reading statistics builds valid metadata and statistics."""
        hass = MagicMock()
        readings = [
            {"deviceNumber": "M123", "readingValue": 100, "readingDate": "2024-01-01T12:30:00Z"},
            {"deviceNumber": "M123", "readingValue": 150, "readingDate": "2024-02-01T10:00:00Z"},
        ]

        import_reading_statistics(hass, readings, 11.2)
        self.assertEqual(mock_add_stats.call_count, 2)

        # Check volume metadata
        vol_meta = mock_add_stats.call_args_list[0][0][1]
        self.assertEqual(vol_meta["statistic_id"], "gen_gaz:gas_meter_m123")
        self.assertEqual(vol_meta["unit_of_measurement"], "m³")
        self.assertTrue(vol_meta["has_sum"])
        self.assertFalse(vol_meta["has_mean"])

        # Check energy metadata
        energy_meta = mock_add_stats.call_args_list[1][0][1]
        self.assertEqual(energy_meta["statistic_id"], "gen_gaz:gas_meter_m123_kwh")
        self.assertEqual(energy_meta["unit_of_measurement"], "kWh")
        self.assertTrue(energy_meta["has_sum"])
        self.assertFalse(energy_meta["has_mean"])

        # Check volume data
        vol_stats = mock_add_stats.call_args_list[0][0][2]
        self.assertEqual(len(vol_stats), 2)
        self.assertEqual(vol_stats[0]["start"].minute, 0)
        self.assertEqual(vol_stats[0]["state"], 100)

    @patch("custom_components.gen_gaz.statistics.async_add_external_statistics")
    def test_import_reading_statistics_empty(self, mock_add_stats: MagicMock) -> None:
        """Test import reading statistics does nothing when readings are empty."""
        hass = MagicMock()
        import_reading_statistics(hass, [], 11.0)
        mock_add_stats.assert_not_called()

    @patch("custom_components.gen_gaz.statistics.async_add_external_statistics")
    def test_import_reading_statistics_multiple_meters(self, mock_add_stats: MagicMock) -> None:
        """Test import reading statistics imports LTS for all detected meters."""
        hass = MagicMock()
        readings = [
            {"deviceNumber": "M123", "readingValue": 100, "readingDate": "2024-01-01T12:30:00Z"},
            {"deviceNumber": "M456", "readingValue": 200, "readingDate": "2024-01-01T12:30:00Z"},
        ]

        import_reading_statistics(hass, readings, 11.2)
        # 2 meters * 2 statistics (volume and energy) = 4 calls
        self.assertEqual(mock_add_stats.call_count, 4)
        stat_ids = [call[0][1]["statistic_id"] for call in mock_add_stats.call_args_list]
        self.assertIn("gen_gaz:gas_meter_m123", stat_ids)
        self.assertIn("gen_gaz:gas_meter_m123_kwh", stat_ids)
        self.assertIn("gen_gaz:gas_meter_m456", stat_ids)
        self.assertIn("gen_gaz:gas_meter_m456_kwh", stat_ids)
