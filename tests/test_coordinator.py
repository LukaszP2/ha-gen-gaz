"""Tests for GenGazCoordinator."""

from __future__ import annotations

import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.gen_gaz.api import GenGazAuthError, GenGazConnectionError
from custom_components.gen_gaz.const import CONF_CUSTOMER_ID, CONF_PASSWORD
from custom_components.gen_gaz.coordinator import GenGazCoordinator


class TestGenGazCoordinator(unittest.IsolatedAsyncioTestCase):
    """Test suite for GenGazCoordinator."""

    def setUp(self) -> None:
        """Set up coordinator test."""
        self.hass = MagicMock()
        self.entry = MagicMock()
        self.entry.data = {
            CONF_CUSTOMER_ID: "12345",
            CONF_PASSWORD: "secret_pass",
        }

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    async def test_coordinator_init(self, mock_session: MagicMock) -> None:
        """Test coordinator initialization with default scan interval."""
        coord = GenGazCoordinator(self.hass, self.entry)
        self.assertEqual(coord.customer_id, "12345")
        self.assertEqual(coord.update_interval, datetime.timedelta(minutes=240))

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    async def test_coordinator_init_custom_scan_interval(self, mock_session: MagicMock) -> None:
        """Test coordinator initialization with custom scan interval from options."""
        self.entry.options = {"scan_interval": 120}
        coord = GenGazCoordinator(self.hass, self.entry)
        self.assertEqual(coord.update_interval, datetime.timedelta(minutes=120))

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    async def test_update_data_auth_failure_raises_config_entry_auth_failed(
        self, mock_session: MagicMock
    ) -> None:
        """Test authentication failure raises ConfigEntryAuthFailed."""
        coord = GenGazCoordinator(self.hass, self.entry)
        coord.api.login = AsyncMock(side_effect=GenGazAuthError("Auth failed"))

        with self.assertRaises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    async def test_update_data_customer_exists_false_raises_config_entry_auth_failed(
        self, mock_session: MagicMock
    ) -> None:
        """Test customerExists False raises ConfigEntryAuthFailed."""
        coord = GenGazCoordinator(self.hass, self.entry)
        coord.api.login = AsyncMock(return_value={"customerExists": False})

        with self.assertRaises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    async def test_update_data_connection_error_raises_update_failed(
        self, mock_session: MagicMock
    ) -> None:
        """Test connection error raises UpdateFailed."""
        coord = GenGazCoordinator(self.hass, self.entry)
        coord.api.login = AsyncMock(side_effect=GenGazConnectionError("Network timeout"))

        with self.assertRaises(UpdateFailed):
            await coord._async_update_data()

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    @patch("custom_components.gen_gaz.coordinator.import_reading_statistics")
    async def test_update_data_success(
        self, mock_import_stats: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test successful update data with multiple contracts and meters."""
        coord = GenGazCoordinator(self.hass, self.entry)
        coord.api.login = AsyncMock(return_value={"customerExists": True})
        coord.api.get_contracts = AsyncMock(
            return_value=[
                {"contractNumber": "UM/123", "ppg": "PPG1"},
                {"contractNumber": "UM/456", "ppg": "PPG2"},
            ]
        )

        async def mock_get_current_account(contract_number: str) -> dict:
            if contract_number == "UM/123":
                return {
                    "contract": {"contractNumber": "UM/123", "saldo": 120.50},
                    "invoices": [{"invoiceNumber": "INV/1", "amount": 100.0}],
                }
            return {
                "contract": {"contractNumber": "UM/456", "saldo": 80.00},
                "invoices": [{"invoiceNumber": "INV/2", "amount": 150.0}],
            }

        async def mock_get_advance_plan(contract_number: str) -> dict:
            if contract_number == "UM/123":
                return {
                    "advances": [
                        {"estimatedUsageInM3": 10, "estimatedUsageInKwh": 110}
                    ]
                }
            return {
                "advances": [
                    {"estimatedUsageInM3": 20, "estimatedUsageInKwh": 220}
                ]
            }

        async def mock_get_readings(contract_number: str) -> list:
            if contract_number == "UM/123":
                return [
                    {
                        "deviceNumber": "MET1",
                        "readingValue": 100,
                        "readingDate": "2024-01-01T00:00:00",
                    }
                ]
            return [
                {
                    "deviceNumber": "MET2",
                    "readingValue": 200,
                    "readingDate": "2024-01-01T00:00:00",
                }
            ]

        coord.api.get_current_account = AsyncMock(side_effect=mock_get_current_account)
        coord.api.get_advance_plan = AsyncMock(side_effect=mock_get_advance_plan)
        coord.api.get_readings = AsyncMock(side_effect=mock_get_readings)
        coord.api.get_unread_messages = AsyncMock(return_value=2)

        data = await coord._async_update_data()
        self.assertIn("contracts", data)
        self.assertEqual(len(data["contracts"]), 2)
        self.assertIn("UM/123", data["contracts"])
        self.assertIn("UM/456", data["contracts"])

        # Check structure for both contracts
        c1 = data["contracts"]["UM/123"]
        self.assertEqual(c1["contract"]["contractNumber"], "UM/123")
        self.assertEqual(c1["contract"]["saldo"], 120.50)
        self.assertEqual(c1["readings"][0]["deviceNumber"], "MET1")

        c2 = data["contracts"]["UM/456"]
        self.assertEqual(c2["contract"]["contractNumber"], "UM/456")
        self.assertEqual(c2["contract"]["saldo"], 80.00)
        self.assertEqual(c2["readings"][0]["deviceNumber"], "MET2")

        self.assertEqual(data["unread"], 2)
        # Statistics imported for both contracts/meters
        self.assertEqual(mock_import_stats.call_count, 2)
