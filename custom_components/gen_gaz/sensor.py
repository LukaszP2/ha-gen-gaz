from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_ANALYTICS, DOMAIN
from .coordinator import GenGazCoordinator


def _contract(data: dict[str, Any]) -> dict[str, Any]:
    val = data.get("contract")
    if isinstance(val, dict):
        return val
    return (data.get("current") or {}).get("contract") or {}


def _invoices(data: dict[str, Any]) -> list[dict[str, Any]]:
    value = (data.get("current") or {}).get("invoices") or []
    return value if isinstance(value, list) else []


def _payments(data: dict[str, Any]) -> list[dict[str, Any]]:
    value = (data.get("current") or {}).get("payments") or []
    return value if isinstance(value, list) else []


def _advances(data: dict[str, Any]) -> list[dict[str, Any]]:
    value = (data.get("advance") or {}).get("advances") or []
    return value if isinstance(value, list) else []


def _readings(data: dict[str, Any]) -> list[dict[str, Any]]:
    value = data.get("readings") or []
    return sorted(
        [r for r in value if r.get("readingValue") is not None and r.get("readingDate")],
        key=lambda x: str(x.get("readingDate", "")),
        reverse=True,
    )


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _plan_factor(advances: list[dict[str, Any]]) -> float | None:
    m3 = sum(float(a.get("estimatedUsageInM3") or 0) for a in advances)
    kwh = sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances)
    return (kwh / m3) if m3 > 0 else None


def _history(data: dict[str, Any]) -> list[dict[str, Any]]:
    readings = _readings(data)
    factor = _plan_factor(_advances(data)) or 10.0
    result = []
    for newer, older in itertools.pairwise(readings):
        if newer.get("deviceNumber") != older.get("deviceNumber"):
            continue
        try:
            new_v = float(newer["readingValue"])
            old_v = float(older["readingValue"])
        except (KeyError, TypeError, ValueError):
            continue

        consumption = new_v - old_v
        d1, d0 = _dt(newer.get("readingDate")), _dt(older.get("readingDate"))
        days = (d1 - d0).days if d1 and d0 else None
        if consumption < 0:
            continue
        result.append({
            "from": older.get("readingDate"),
            "to": newer.get("readingDate"),
            "meter": newer.get("deviceNumber"),
            "reading_from_m3": old_v,
            "reading_to_m3": new_v,
            "consumption_m3": round(consumption, 3),
            "estimated_kwh": round(consumption * factor, 1),
            "kwh_per_m3": round(factor, 4),
            "days": days,
            "m3_per_day": round(consumption / days, 3) if days and days > 0 else None,
            "kwh_per_day": round(consumption * factor / days, 1) if days and days > 0 else None,
        })
    return result


def _invoice_rows(invoices: list[dict[str, Any]]) -> list[tuple[datetime, float, dict[str, Any]]]:
    rows = []
    for inv in invoices:
        dt = _dt(inv.get("issued"))
        if not dt:
            continue
        try:
            amount = float(inv.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        rows.append((dt, amount, inv))
    return sorted(rows, key=lambda x: x[0], reverse=True)


def _period_cost(invoices: list[dict[str, Any]], start: datetime, end: datetime) -> float:
    return round(sum(amount for dt, amount, _ in _invoice_rows(invoices) if start <= dt < end), 2)


def _history_window(history: list[dict[str, Any]], months: int = 12) -> list[dict[str, Any]] | None:
    if not history:
        return None
    end = _dt(history[0]["to"])
    if not end:
        return None
    start = end - timedelta(days=months * 30.4375)
    result = []
    for h in history:
        dt_to = _dt(h.get("to"))
        if dt_to is not None and start <= dt_to <= end:
            result.append(h)
    return result


def _actual_consumption(history: list[dict[str, Any]], months: int = 12) -> dict[str, Any] | None:
    rows = _history_window(history, months)
    if not rows:
        return None
    return {
        "m3": round(sum(x["consumption_m3"] for x in rows), 3),
        "kwh": round(sum(x["estimated_kwh"] for x in rows), 1),
        "from": min(x["from"] for x in rows),
        "to": max(x["to"] for x in rows),
        "intervals": len(rows),
    }


def _plan_totals(advances: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pln": round(sum(float(a.get("advanceAmount") or 0) for a in advances), 2),
        "m3": round(sum(float(a.get("estimatedUsageInM3") or 0) for a in advances), 3),
        "kwh": round(sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances), 1),
    }


SENSOR_DESCRIPTIONS: list[tuple[str, str, str, str | None, SensorDeviceClass | None, SensorStateClass | None, bool]] = [
    # (key, fallback_name, suffix, unit, device_class, state_class, enabled_by_default)
    ("balance", "Saldo", "balance", "PLN", SensorDeviceClass.MONETARY, None, True),
    ("amount_to_pay", "Do zapłaty", "amount_to_pay", "PLN", SensorDeviceClass.MONETARY, None, True),
    ("last_invoice", "Ostatnia faktura", "last_invoice", "PLN", SensorDeviceClass.MONETARY, None, True),
    ("unread", "Nieprzeczytane wiadomości", "unread_messages", None, None, None, True),
    ("tariff", "Taryfa", "tariff", None, None, None, True),
    ("contract", "Numer umowy", "contract", None, None, None, True),
    ("meter_reading", "Stan licznika gazu", "meter_reading", "m³", SensorDeviceClass.GAS, SensorStateClass.TOTAL_INCREASING, True),
    ("meter_number", "Numer licznika gazu", "meter_number", None, None, None, True),
    ("previous_reading", "Poprzedni odczyt gazu", "previous_reading", "m³", SensorDeviceClass.GAS, None, True),
    ("consumption_since_reading", "Zużycie od poprzedniego odczytu (m³)", "consumption_since_reading", "m³", SensorDeviceClass.GAS, SensorStateClass.MEASUREMENT, True),
    ("consumption_since_reading_kwh", "Zużycie od poprzedniego odczytu (kWh)", "consumption_since_reading_kwh", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, True),
    ("conversion_factor", "Przelicznik m³ → kWh", "conversion_factor", "kWh/m³", None, None, True),
    ("next_advance", "Najbliższa zaliczka", "next_advance", "PLN", SensorDeviceClass.MONETARY, None, True),
    ("next_advance_m3", "Najbliższa zaliczka — m³", "next_advance_m3", "m³", SensorDeviceClass.GAS, None, True),
    ("next_advance_kwh", "Najbliższa zaliczka — kWh", "next_advance_kwh", "kWh", SensorDeviceClass.ENERGY, None, True),
    ("advance_plan_total", "Plan zaliczkowy — suma", "advance_plan_total", "PLN", SensorDeviceClass.MONETARY, None, True),
    ("advance_plan_m3", "Plan zaliczkowy — m³", "advance_plan_m3", "m³", SensorDeviceClass.GAS, None, True),
    ("advance_plan_kwh", "Plan zaliczkowy — kWh", "advance_plan_kwh", "kWh", SensorDeviceClass.ENERGY, None, True),
    # Secondary / advanced analytical sensors disabled by default
    ("history_total_m3", "Historia zużycia gazu (m³)", "history_total_m3", "m³", SensorDeviceClass.GAS, SensorStateClass.TOTAL, False),
    ("history_total_kwh", "Historia zużycia gazu (kWh)", "history_total_kwh", "kWh", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, False),
    ("actual_invoice_cost_6m", "Koszt faktur — 6 mies.", "actual_invoice_cost_6m", "PLN", SensorDeviceClass.MONETARY, None, False),
    ("actual_invoice_cost_12m", "Koszt faktur — 12 mies.", "actual_invoice_cost_12m", "PLN", SensorDeviceClass.MONETARY, None, False),
    ("actual_consumption_12m_m3", "Rzeczywiste zużycie — 12 mies.", "actual_consumption_12m_m3", "m³", SensorDeviceClass.GAS, None, False),
    ("actual_consumption_12m_kwh", "Rzeczywiste zużycie — 12 mies. (kWh)", "actual_consumption_12m_kwh", "kWh", SensorDeviceClass.ENERGY, None, False),
    ("actual_cost_per_m3", "Rzeczywisty koszt gazu (m³)", "actual_cost_per_m3", "PLN/m³", None, None, False),
    ("actual_cost_per_kwh", "Rzeczywisty koszt gazu (kWh)", "actual_cost_per_kwh", "PLN/kWh", None, None, False),
    ("plan_cost_per_m3", "Plan — koszt m³", "plan_cost_per_m3", "PLN/m³", None, None, False),
    ("plan_cost_per_kwh", "Plan — koszt kWh", "plan_cost_per_kwh", "PLN/kWh", None, None, False),
    ("actual_vs_plan_6m", "Rzeczywiste 6M vs plan 6M", "actual_vs_plan_6m", "PLN", SensorDeviceClass.MONETARY, None, False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up G.EN. Gaz sensor entities from a config entry."""
    coordinator: GenGazCoordinator = getattr(entry, "runtime_data", None) or hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    contracts = data.get("contracts")

    contract_numbers: list[str] = []
    if isinstance(contracts, dict):
        contract_numbers = list(contracts.keys())
    elif isinstance(contracts, list):
        contract_numbers = [
            c.get("contractNumber")
            for c in contracts
            if isinstance(c, dict) and c.get("contractNumber")
        ]
    elif data.get("current") or data.get("contract"):
        c_num = (data.get("contract") or data.get("current", {}).get("contract", {})).get("contractNumber")
        if c_num:
            contract_numbers = [c_num]

    is_single_contract = len(contract_numbers) <= 1
    entities: list[SensorEntity] = []

    # Account-level entities (parent device: G.EN. Gaz Energia ({customer_id}))
    for key, name, suffix, unit, dev_class, state_class, enabled in SENSOR_DESCRIPTIONS:
        if key == "unread":
            entities.append(
                GenGazSensor(
                    coordinator,
                    key=key,
                    name=name,
                    suffix=suffix,
                    unit=unit,
                    device_class=dev_class,
                    state_class=state_class,
                    enabled_by_default=enabled,
                    is_account_level=True,
                )
            )

    # When multiple contracts exist, provide total balance on account parent device
    if not is_single_contract:
        entities.append(
            GenGazSensor(
                coordinator,
                key="total_balance",
                name="Łączne saldo",
                suffix="total_balance",
                unit="PLN",
                device_class=SensorDeviceClass.MONETARY,
                state_class=None,
                enabled_by_default=True,
                is_account_level=True,
            )
        )

    # Contract-specific entities
    contract_descriptions = [
        desc for desc in SENSOR_DESCRIPTIONS if desc[0] != "unread"
    ]

    enable_analytics = bool(entry.options.get(CONF_ENABLE_ANALYTICS, False))

    if contract_numbers:
        for c_num in contract_numbers:
            for key, name, suffix, unit, dev_class, state_class, enabled in contract_descriptions:
                entities.append(
                    GenGazSensor(
                        coordinator,
                        key=key,
                        name=name,
                        suffix=suffix,
                        unit=unit,
                        device_class=dev_class,
                        state_class=state_class,
                        enabled_by_default=enabled or enable_analytics,
                        contract_number=c_num,
                        is_single_contract=is_single_contract,
                        is_account_level=False,
                    )
                )
    else:
        for key, name, suffix, unit, dev_class, state_class, enabled in contract_descriptions:
            entities.append(
                GenGazSensor(
                    coordinator,
                    key=key,
                    name=name,
                    suffix=suffix,
                    unit=unit,
                    device_class=dev_class,
                    state_class=state_class,
                    enabled_by_default=enabled or enable_analytics,
                    contract_number=None,
                    is_single_contract=True,
                    is_account_level=False,
                )
            )

    async_add_entities(entities)


class GenGazSensor(CoordinatorEntity[GenGazCoordinator], SensorEntity):
    """Representation of a G.EN. Gaz Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GenGazCoordinator,
        key: str,
        name: str,
        suffix: str,
        unit: str | None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        enabled_by_default: bool = True,
        contract_number: str | None = None,
        is_single_contract: bool | None = None,
        is_account_level: bool = False,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_registry_enabled_default = enabled_by_default
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class

        if key in ("unread", "total_balance"):
            is_account_level = True

        data = coordinator.data or {}
        contracts = data.get("contracts")
        contract_keys: list[str] = []
        if isinstance(contracts, dict):
            contract_keys = list(contracts.keys())
        elif isinstance(contracts, list):
            contract_keys = [
                c.get("contractNumber")
                for c in contracts
                if isinstance(c, dict) and c.get("contractNumber")
            ]
        elif data.get("current") or data.get("contract"):
            c_num = (data.get("contract") or data.get("current", {}).get("contract", {})).get("contractNumber")
            if c_num:
                contract_keys = [c_num]

        if is_single_contract is None:
            is_single_contract = len(contract_keys) <= 1

        if not is_account_level and contract_number is None and contract_keys:
            contract_number = contract_keys[0]

        self._contract_number = contract_number
        self._is_account_level = is_account_level
        self._is_single_contract = is_single_contract

        if is_account_level or is_single_contract or not contract_number:
            self._attr_unique_id = f"{coordinator.customer_id}_{suffix}"
        else:
            self._attr_unique_id = f"{coordinator.customer_id}_{contract_number}_{suffix}"

        if is_account_level or not contract_number:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.customer_id)},
                name=f"G.EN. Gaz Energia ({coordinator.customer_id})",
                manufacturer="G.EN. Gaz Energia",
                model="eBOK",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{coordinator.customer_id}_{contract_number}")},
                name=f"G.EN. Gaz - Umowa {contract_number}",
                manufacturer="G.EN. Gaz Energia",
                model="eBOK",
                via_device=(DOMAIN, coordinator.customer_id),
            )

    def _get_contract_data(self) -> dict[str, Any]:
        """Return data for this sensor's contract."""
        data = self.coordinator.data or {}
        contracts = data.get("contracts")
        if isinstance(contracts, dict):
            if self._contract_number and self._contract_number in contracts:
                return contracts[self._contract_number]
            if contracts:
                return next(iter(contracts.values()))
            return {}
        # Backward compatibility if data is formatted in older structure
        return data

    @property
    def native_value(self) -> Any:
        """Return native value of the sensor."""
        data = self.coordinator.data or {}
        if self._key == "unread":
            return data.get("unread", 0)

        if self._key == "total_balance":
            contracts = data.get("contracts")
            if isinstance(contracts, dict):
                total = 0.0
                for cd in contracts.values():
                    s = _contract(cd).get("saldo")
                    if s is None:
                        s = (cd.get("current") or {}).get("saldo")
                    if s is not None:
                        try:
                            total += float(s)
                        except (TypeError, ValueError):
                            pass
                return round(total, 2)
            val = _contract(data).get("saldo")
            if val is not None:
                return val
            return (data.get("current") or {}).get("saldo")

        c_data = self._get_contract_data()
        contract = _contract(c_data)
        invoices = _invoices(c_data)
        payments = _payments(c_data)
        advances = _advances(c_data)
        readings = _readings(c_data)
        history = _history(c_data)
        factor = _plan_factor(advances)
        actual12 = _actual_consumption(history, 12)
        plan = _plan_totals(advances)
        rows = _invoice_rows(invoices)

        if self._key == "balance":
            val = contract.get("saldo")
            if val is not None:
                return val
            return (c_data.get("current") or {}).get("saldo")
        if self._key == "amount_to_pay":
            return round(sum(float(p.get("amountToPay") or 0) for p in payments if not p.get("isPaid")), 2)
        if self._key == "last_invoice":
            return invoices[0].get("amount") if invoices else None
        if self._key == "tariff":
            return contract.get("tariffGroup")
        if self._key == "contract":
            return self._contract_number or contract.get("contractNumber")
        if self._key == "meter_reading":
            return readings[0].get("readingValue") if readings else None
        if self._key == "meter_number":
            return readings[0].get("deviceNumber") if readings else None
        if self._key == "previous_reading":
            return readings[1].get("readingValue") if len(readings) > 1 else None
        if self._key == "consumption_since_reading":
            return history[0]["consumption_m3"] if history else None
        if self._key == "consumption_since_reading_kwh":
            return history[0]["estimated_kwh"] if history else None
        if self._key == "conversion_factor":
            return round(factor, 4) if factor else None
        if self._key == "history_total_m3":
            return round(sum(x["consumption_m3"] for x in history), 3) if history else None
        if self._key == "history_total_kwh":
            return round(sum(x["estimated_kwh"] for x in history), 1) if history else None
        if self._key == "actual_invoice_cost_6m":
            if not rows:
                return None
            end = rows[0][0]
            return _period_cost(invoices, end - timedelta(days=182), end + timedelta(days=1))
        if self._key == "actual_invoice_cost_12m":
            if not rows:
                return None
            end = rows[0][0]
            return _period_cost(invoices, end - timedelta(days=365), end + timedelta(days=1))
        if self._key == "actual_consumption_12m_m3":
            return actual12["m3"] if actual12 else None
        if self._key == "actual_consumption_12m_kwh":
            return actual12["kwh"] if actual12 else None
        if self._key == "actual_cost_per_m3":
            cost = self._actual_cost_12m(invoices, rows)
            return round(cost / actual12["m3"], 2) if cost is not None and actual12 and actual12["m3"] else None
        if self._key == "actual_cost_per_kwh":
            cost = self._actual_cost_12m(invoices, rows)
            return round(cost / actual12["kwh"], 4) if cost is not None and actual12 and actual12["kwh"] else None
        if self._key == "plan_cost_per_m3":
            return round(plan["pln"] / plan["m3"], 2) if plan["m3"] else None
        if self._key == "plan_cost_per_kwh":
            return round(plan["pln"] / plan["kwh"], 4) if plan["kwh"] else None
        if self._key == "actual_vs_plan_6m":
            actual = self._actual_cost_6m(invoices, rows)
            return round(actual - plan["pln"], 2) if actual is not None else None
        if self._key == "next_advance":
            return advances[0].get("advanceAmount") if advances else None
        if self._key == "next_advance_m3":
            return advances[0].get("estimatedUsageInM3") if advances else None
        if self._key == "next_advance_kwh":
            return advances[0].get("estimatedUsageInKwh") if advances else None
        if self._key == "advance_plan_total":
            return plan["pln"]
        if self._key == "advance_plan_m3":
            return plan["m3"]
        if self._key == "advance_plan_kwh":
            return plan["kwh"]
        return None

    def _actual_cost_6m(self, invoices: list[dict[str, Any]], rows: list[tuple[datetime, float, dict[str, Any]]]) -> float | None:
        if not rows:
            return None
        end = rows[0][0]
        return _period_cost(invoices, end - timedelta(days=182), end + timedelta(days=1))

    def _actual_cost_12m(self, invoices: list[dict[str, Any]], rows: list[tuple[datetime, float, dict[str, Any]]]) -> float | None:
        if not rows:
            return None
        end = rows[0][0]
        return _period_cost(invoices, end - timedelta(days=365), end + timedelta(days=1))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return scalar summary attributes without bloating recorder database."""
        data = self.coordinator.data or {}
        if self._key == "total_balance":
            contracts = data.get("contracts") or {}
            return {
                "contracts_count": len(contracts),
                "contract_numbers": list(contracts.keys()) if isinstance(contracts, dict) else [],
            }
        if self._key == "unread":
            return None

        c_data = self._get_contract_data()
        contract = _contract(c_data)
        invoices = _invoices(c_data)
        advances = _advances(c_data)
        readings = _readings(c_data)
        factor = _plan_factor(advances)
        plan = _plan_totals(advances)

        if self._key == "contract":
            return {
                "ppg": contract.get("ppg"),
                "delivery_address": contract.get("deliveryAddress"),
                "type": contract.get("typeOfContract"),
                "active": contract.get("isActive"),
            }
        if self._key == "last_invoice" and invoices:
            i = invoices[0]
            return {
                "invoice_number": i.get("invoiceNumber"),
                "issued": i.get("issued"),
                "payment_deadline": i.get("paymentDeadline"),
                "is_paid": i.get("isPaid"),
            }
        if self._key in {
            "next_advance",
            "next_advance_m3",
            "next_advance_kwh",
            "advance_plan_total",
            "advance_plan_m3",
            "advance_plan_kwh",
            "plan_cost_per_m3",
            "plan_cost_per_kwh",
            "actual_vs_plan_6m",
        }:
            return {
                "months": len(advances),
                "plan_total_pln": plan["pln"],
                "plan_total_m3": plan["m3"],
                "plan_total_kwh": plan["kwh"],
            }
        if self._key in {
            "meter_reading",
            "meter_number",
            "previous_reading",
            "consumption_since_reading",
            "consumption_since_reading_kwh",
            "history_total_m3",
            "history_total_kwh",
            "conversion_factor",
        }:
            attrs: dict[str, Any] = {
                "reading_date": readings[0].get("readingDate") if readings else None,
                "device_number": readings[0].get("deviceNumber") if readings else None,
                "previous_reading_date": readings[1].get("readingDate") if len(readings) > 1 else None,
                "history_count": len(readings),
            }
            if factor:
                attrs["conversion_kwh_per_m3"] = round(factor, 4)
            return attrs
        if self._key.startswith("actual_"):
            attrs = {"invoice_count": len(invoices)}
            if factor:
                attrs["conversion_kwh_per_m3"] = round(factor, 4)
            return attrs
        return None
