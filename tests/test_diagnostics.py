"""Tests for diagnostics platform."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from custom_components.gen_gaz.const import CONF_CUSTOMER_ID, CONF_PASSWORD
from custom_components.gen_gaz.diagnostics import async_get_config_entry_diagnostics


class TestGenGazDiagnostics(unittest.IsolatedAsyncioTestCase):
    """Test suite for diagnostics."""

    async def test_diagnostics_redaction(self) -> None:
        """Test diagnostics redact sensitive information."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_CUSTOMER_ID: "12345",
            CONF_PASSWORD: "super_secret_password",
        }

        coordinator = MagicMock()
        coordinator.data = {
            "current": {
                "contract": {
                    "contractNumber": "UM/123",
                    "deliveryAddress": "Sekretna 10",
                    "ppg": "PPG_SECRET",
                }
            }
        }
        entry.runtime_data = coordinator

        diag = await async_get_config_entry_diagnostics(hass, entry)
        self.assertIn("entry", diag)
        self.assertIn("data", diag)

        # Sensitive data should be redacted
        self.assertEqual(diag["entry"][CONF_PASSWORD], "**REDACTED**")
        self.assertEqual(diag["entry"][CONF_CUSTOMER_ID], "**REDACTED**")
        contract = diag["data"]["current"]["contract"]
        self.assertEqual(contract["deliveryAddress"], "**REDACTED**")
        self.assertEqual(contract["ppg"], "**REDACTED**")
        self.assertEqual(contract["contractNumber"], "UM/123")

    async def test_diagnostics_redaction_multi_contract(self) -> None:
        """Test diagnostics redact sensitive information across multiple contracts."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_CUSTOMER_ID: "12345",
            CONF_PASSWORD: "super_secret_password",
        }

        coordinator = MagicMock()
        coordinator.data = {
            "contracts": {
                "UM/123": {
                    "contract": {
                        "contractNumber": "UM/123",
                        "deliveryAddress": "Sekretna 10",
                        "ppg": "PPG_1",
                    }
                },
                "UM/456": {
                    "contract": {
                        "contractNumber": "UM/456",
                        "deliveryAddress": "Sekretna 20",
                        "ppg": "PPG_2",
                    }
                },
            }
        }
        entry.runtime_data = coordinator

        diag = await async_get_config_entry_diagnostics(hass, entry)
        c1 = diag["data"]["contracts"]["UM/123"]["contract"]
        c2 = diag["data"]["contracts"]["UM/456"]["contract"]
        self.assertEqual(c1["deliveryAddress"], "**REDACTED**")
        self.assertEqual(c1["ppg"], "**REDACTED**")
        self.assertEqual(c2["deliveryAddress"], "**REDACTED**")
        self.assertEqual(c2["ppg"], "**REDACTED**")
        self.assertEqual(c1["contractNumber"], "UM/123")
        self.assertEqual(c2["contractNumber"], "UM/456")
