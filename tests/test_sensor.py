"""Tests for G.EN. Gaz sensor platform."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.gen_gaz.const import DOMAIN
from custom_components.gen_gaz.sensor import (
    SENSOR_DESCRIPTIONS,
    GenGazSensor,
    async_setup_entry,
)


class TestGenGazSensor(unittest.IsolatedAsyncioTestCase):
    """Test suite for GenGazSensor."""

    def setUp(self) -> None:
        """Set up test environment with 2 contracts and 2 meters."""
        self.coordinator = MagicMock()
        self.coordinator.customer_id = "12345"
        self.coordinator.data = {
            "contracts": {
                "UM/123": {
                    "contract": {
                        "contractNumber": "UM/123",
                        "saldo": 50.0,
                        "tariffGroup": "W-3.6",
                        "ppg": "PPG123",
                        "deliveryAddress": "Testowa 1",
                        "isActive": True,
                    },
                    "current": {
                        "contract": {
                            "contractNumber": "UM/123",
                            "saldo": 50.0,
                            "tariffGroup": "W-3.6",
                            "ppg": "PPG123",
                            "deliveryAddress": "Testowa 1",
                            "isActive": True,
                        },
                        "invoices": [
                            {"invoiceNumber": "F/001", "amount": 100.0, "issued": "2024-01-10T00:00:00Z", "isPaid": True}
                        ],
                        "payments": [
                            {"amountToPay": 100.0, "isPaid": False}
                        ],
                    },
                    "advance": {
                        "advances": [
                            {
                                "advanceAmount": 150.0,
                                "estimatedUsageInM3": 20,
                                "estimatedUsageInKwh": 220,
                            }
                        ]
                    },
                    "readings": [
                        {
                            "readingValue": 120.5,
                            "deviceNumber": "MET1",
                            "readingDate": "2024-02-01T00:00:00Z",
                        },
                        {
                            "readingValue": 100.0,
                            "deviceNumber": "MET1",
                            "readingDate": "2024-01-01T00:00:00Z",
                        },
                    ],
                },
                "UM/456": {
                    "contract": {
                        "contractNumber": "UM/456",
                        "saldo": 75.0,
                        "tariffGroup": "W-1.1",
                        "ppg": "PPG456",
                        "deliveryAddress": "Testowa 2",
                        "isActive": True,
                    },
                    "current": {
                        "contract": {
                            "contractNumber": "UM/456",
                            "saldo": 75.0,
                            "tariffGroup": "W-1.1",
                            "ppg": "PPG456",
                            "deliveryAddress": "Testowa 2",
                            "isActive": True,
                        },
                        "invoices": [
                            {"invoiceNumber": "F/002", "amount": 200.0, "issued": "2024-01-15T00:00:00Z", "isPaid": True}
                        ],
                        "payments": [
                            {"amountToPay": 200.0, "isPaid": False}
                        ],
                    },
                    "advance": {
                        "advances": [
                            {
                                "advanceAmount": 250.0,
                                "estimatedUsageInM3": 30,
                                "estimatedUsageInKwh": 330,
                            }
                        ]
                    },
                    "readings": [
                        {
                            "readingValue": 250.0,
                            "deviceNumber": "MET2",
                            "readingDate": "2024-02-01T00:00:00Z",
                        },
                        {
                            "readingValue": 200.0,
                            "deviceNumber": "MET2",
                            "readingDate": "2024-01-01T00:00:00Z",
                        },
                    ],
                },
            },
            "unread": 1,
        }

    def test_sensors_initialization(self) -> None:
        """Test sensors correctly set unique_id, device_info, and classes."""
        for key, name, suffix, unit, dev_class, state_class, enabled in SENSOR_DESCRIPTIONS:
            if key == "unread":
                sensor = GenGazSensor(
                    self.coordinator,
                    key,
                    name,
                    suffix,
                    unit,
                    dev_class,
                    state_class,
                    enabled,
                    is_account_level=True,
                )
                self.assertTrue(sensor.has_entity_name)
                self.assertEqual(sensor.translation_key, key)
                self.assertEqual(sensor.unique_id, f"12345_{suffix}")
                self.assertEqual(
                    sensor.device_info["identifiers"],
                    {(DOMAIN, "12345")},
                )
            else:
                sensor = GenGazSensor(
                    self.coordinator,
                    key,
                    name,
                    suffix,
                    unit,
                    dev_class,
                    state_class,
                    enabled,
                    contract_number="UM/123",
                    is_single_contract=False,
                )
                self.assertTrue(sensor.has_entity_name)
                self.assertEqual(sensor.translation_key, key)
                self.assertEqual(sensor.entity_registry_enabled_default, enabled)
                # unique_id includes contract number in multi-contract mode
                self.assertEqual(sensor.unique_id, f"12345_UM/123_{suffix}")
                # device info points to contract sub-device
                self.assertEqual(
                    sensor.device_info["identifiers"],
                    {(DOMAIN, "12345_UM/123")},
                )
                self.assertEqual(sensor.device_info["via_device"], (DOMAIN, "12345"))
                self.assertEqual(sensor.device_info["name"], "G.EN. Gaz - Umowa UM/123")

            if dev_class is not None:
                self.assertEqual(sensor.device_class, dev_class)
            if state_class is not None:
                self.assertEqual(sensor.state_class, state_class)

    def test_sensor_values(self) -> None:
        """Test specific sensor native values for multiple contracts and meters."""
        # Contract 1 (UM/123, MET1)
        s_balance1 = GenGazSensor(
            self.coordinator, "balance", "Saldo", "balance", "PLN",
            SensorDeviceClass.MONETARY, contract_number="UM/123", is_single_contract=False
        )
        self.assertEqual(s_balance1.native_value, 50.0)

        s_meter1 = GenGazSensor(
            self.coordinator, "meter_reading", "Stan licznika gazu", "meter_reading", "m³",
            SensorDeviceClass.GAS, SensorStateClass.TOTAL_INCREASING,
            contract_number="UM/123", is_single_contract=False
        )
        self.assertEqual(s_meter1.native_value, 120.5)

        s_meter_no1 = GenGazSensor(
            self.coordinator, "meter_number", "Numer licznika gazu", "meter_number", None,
            contract_number="UM/123", is_single_contract=False
        )
        self.assertEqual(s_meter_no1.native_value, "MET1")

        s_cons1 = GenGazSensor(
            self.coordinator, "consumption_since_reading", "Zużycie", "consumption_since_reading", "m³",
            SensorDeviceClass.GAS, SensorStateClass.MEASUREMENT,
            contract_number="UM/123", is_single_contract=False
        )
        self.assertEqual(s_cons1.native_value, 20.5)

        # Contract 2 (UM/456, MET2)
        s_balance2 = GenGazSensor(
            self.coordinator, "balance", "Saldo", "balance", "PLN",
            SensorDeviceClass.MONETARY, contract_number="UM/456", is_single_contract=False
        )
        self.assertEqual(s_balance2.native_value, 75.0)

        s_meter2 = GenGazSensor(
            self.coordinator, "meter_reading", "Stan licznika gazu", "meter_reading", "m³",
            SensorDeviceClass.GAS, SensorStateClass.TOTAL_INCREASING,
            contract_number="UM/456", is_single_contract=False
        )
        self.assertEqual(s_meter2.native_value, 250.0)

        s_meter_no2 = GenGazSensor(
            self.coordinator, "meter_number", "Numer licznika gazu", "meter_number", None,
            contract_number="UM/456", is_single_contract=False
        )
        self.assertEqual(s_meter_no2.native_value, "MET2")

        s_cons2 = GenGazSensor(
            self.coordinator, "consumption_since_reading", "Zużycie", "consumption_since_reading", "m³",
            SensorDeviceClass.GAS, SensorStateClass.MEASUREMENT,
            contract_number="UM/456", is_single_contract=False
        )
        self.assertEqual(s_cons2.native_value, 50.0)

        # Account-level total balance and unread messages
        s_unread = GenGazSensor(
            self.coordinator, "unread", "Nieprzeczytane", "unread_messages", None, is_account_level=True
        )
        self.assertEqual(s_unread.native_value, 1)

        s_total = GenGazSensor(
            self.coordinator, "total_balance", "Łączne saldo", "total_balance", "PLN",
            SensorDeviceClass.MONETARY, is_account_level=True
        )
        self.assertEqual(s_total.native_value, 125.0)

    def test_extra_state_attributes_do_not_contain_huge_history(self) -> None:
        """Test that extra_state_attributes do not leak full history lists into recorder."""
        s_meter = GenGazSensor(
            self.coordinator, "meter_reading", "Stan licznika gazu", "meter_reading", "m³",
            SensorDeviceClass.GAS, SensorStateClass.TOTAL_INCREASING,
            contract_number="UM/123", is_single_contract=False
        )
        attrs = s_meter.extra_state_attributes
        self.assertIsNotNone(attrs)
        assert attrs is not None
        self.assertNotIn("history", attrs)
        self.assertNotIn("consumption_intervals", attrs)
        self.assertEqual(attrs.get("history_count"), 2)

    async def test_async_setup_entry_multiple_contracts(self) -> None:
        """Test async_setup_entry creates entities for both contracts and account."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.runtime_data = self.coordinator
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # Verify entities are created for both contracts
        um123_entities = [e for e in entities if getattr(e, "_contract_number", None) == "UM/123"]
        um456_entities = [e for e in entities if getattr(e, "_contract_number", None) == "UM/456"]
        self.assertTrue(len(um123_entities) > 0, "No entities created for contract UM/123")
        self.assertTrue(len(um456_entities) > 0, "No entities created for contract UM/456")
        self.assertEqual(len(um123_entities), len(um456_entities))

        # Check unique IDs for both contracts
        self.assertTrue(any(e.unique_id == "12345_UM/123_balance" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_UM/456_balance" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_UM/123_meter_reading" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_UM/456_meter_reading" for e in entities))

        # Check account-level entities
        self.assertTrue(any(e.unique_id == "12345_unread_messages" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_total_balance" for e in entities))

        # Verify device hierarchy (via_device)
        sample_um123 = next(e for e in entities if e.unique_id == "12345_UM/123_balance")
        self.assertEqual(sample_um123.device_info["via_device"], (DOMAIN, "12345"))
        self.assertEqual(sample_um123.device_info["identifiers"], {(DOMAIN, "12345_UM/123")})

        sample_account = next(e for e in entities if e.unique_id == "12345_unread_messages")
        self.assertEqual(sample_account.device_info["identifiers"], {(DOMAIN, "12345")})

    async def test_async_setup_entry_single_contract_backward_compatibility(self) -> None:
        """Test single contract retains legacy unique_ids without contract prefix."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "single_entry"

        single_coord = MagicMock()
        single_coord.customer_id = "12345"
        single_coord.data = {
            "contracts": {
                "UM/123": self.coordinator.data["contracts"]["UM/123"]
            },
            "unread": 1,
        }
        entry.runtime_data = single_coord
        async_add_entities = MagicMock()

        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # In single contract mode, unique_id must not include contract number
        self.assertTrue(any(e.unique_id == "12345_balance" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_meter_reading" for e in entities))
        self.assertTrue(any(e.unique_id == "12345_unread_messages" for e in entities))
        self.assertEqual(len(entities), len(SENSOR_DESCRIPTIONS))
