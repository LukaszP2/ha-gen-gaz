"""Tests for integration setup and unload."""

from __future__ import annotations

import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ServiceValidationError

from custom_components.gen_gaz import (
    SERVICE_UPDATE_ADVANCE_PLAN,
    _async_update_advance_plan,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.gen_gaz.const import DOMAIN


class TestGenGazInit(unittest.IsolatedAsyncioTestCase):
    """Test suite for __init__."""

    @patch("custom_components.gen_gaz.coordinator.async_get_clientsession")
    @patch("custom_components.gen_gaz.GenGazCoordinator.async_config_entry_first_refresh")
    async def test_setup_and_unload_entry(
        self, mock_refresh: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test setup and unload of config entry."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {"customer_id": "12345", "password": "pass"}

        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        hass.services.has_service.return_value = False

        res = await async_setup_entry(hass, entry)
        self.assertTrue(res)
        self.assertTrue(hasattr(entry, "runtime_data"))
        entry.add_update_listener.assert_called_once_with(async_reload_entry)
        entry.async_on_unload.assert_called_once()
        hass.services.async_register.assert_called_once()

        # Unload
        hass.config_entries.async_entries.return_value = []
        hass.services.has_service.return_value = True
        unload_res = await async_unload_entry(hass, entry)
        self.assertTrue(unload_res)
        hass.services.async_remove.assert_called_once_with(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN)

    async def test_async_reload_entry(self) -> None:
        """Test reload entry on options update."""
        hass = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        await async_reload_entry(hass, entry)
        hass.config_entries.async_reload.assert_called_once_with("test_entry")

    async def test_service_update_advance_plan_missing_contract_raises(self) -> None:
        """Test service call raises ServiceValidationError when contract is not found."""
        hass = MagicMock()
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.data = {"contracts": []}
        entry.runtime_data = coordinator
        hass.config_entries.async_entries.return_value = [entry]

        call = MagicMock()
        call.hass = hass
        call.data = {
            "reason": "Test reason",
            "reading_value": 150,
            "reading_date": datetime.date(2024, 1, 1),
        }

        with self.assertRaises(ServiceValidationError):
            await _async_update_advance_plan(call)

    async def test_service_update_advance_plan_success(self) -> None:
        """Test service call succeeds with contract from coordinator."""
        hass = MagicMock()
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.data = {"contracts": [{"contractNumber": "UM/999"}]}
        coordinator.api.update_advance_plan = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entry.runtime_data = coordinator
        hass.config_entries.async_entries.return_value = [entry]

        call = MagicMock()
        call.hass = hass
        call.data = {
            "reason": "Test reason",
            "reading_value": 150,
            "reading_date": datetime.date(2024, 1, 1),
            "advance_1": 120.0,
        }

        await _async_update_advance_plan(call)
        coordinator.api.update_advance_plan.assert_called_once()
        args = coordinator.api.update_advance_plan.call_args[0]
        self.assertEqual(args[0], "UM/999")
        self.assertEqual(args[1]["reason"], "Test reason")
        self.assertEqual(args[1]["reading"]["readingValue"], 150)
        self.assertEqual(args[1]["advances"], [{"advanceNewAmount": 120.0}])

    async def test_service_update_advance_plan_multi_contract_dict(self) -> None:
        """Test service call selects correct contract from contracts dictionary."""
        hass = MagicMock()
        entry = MagicMock()
        coordinator = MagicMock()
        coordinator.data = {
            "contracts": {
                "UM/123": {},
                "UM/456": {},
            }
        }
        coordinator.api.update_advance_plan = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entry.runtime_data = coordinator
        hass.config_entries.async_entries.return_value = [entry]

        call = MagicMock()
        call.hass = hass
        call.data = {
            "contract_number": "UM/456",
            "reason": "Update UM 456",
            "reading_value": 220,
            "reading_date": datetime.date(2024, 2, 1),
            "advance_1": 180.0,
        }

        await _async_update_advance_plan(call)
        coordinator.api.update_advance_plan.assert_called_once()
        args = coordinator.api.update_advance_plan.call_args[0]
        self.assertEqual(args[0], "UM/456")
        self.assertEqual(args[1]["reason"], "Update UM 456")
