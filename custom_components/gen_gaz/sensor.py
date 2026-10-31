from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GenGazCoordinator


def _contract(data):
    return ((data.get("current") or {}).get("contract") or {})


def _invoices(data):
    value = ((data.get("current") or {}).get("invoices") or [])
    return value if isinstance(value, list) else []


def _payments(data):
    value = ((data.get("current") or {}).get("payments") or [])
    return value if isinstance(value, list) else []


def _advances(data):
    value = ((data.get("advance") or {}).get("advances") or [])
    return value if isinstance(value, list) else []


def _readings(data):
    value = data.get("readings") or []
    return sorted(
        [r for r in value if r.get("readingValue") is not None and r.get("readingDate")],
        key=lambda x: x.get("readingDate", ""),
        reverse=True,
    )


def _dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _plan_factor(advances):
    m3 = sum(float(a.get("estimatedUsageInM3") or 0) for a in advances)
    kwh = sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances)
    return (kwh / m3) if m3 > 0 else None


def _history(data):
    readings = _readings(data)
    factor = _plan_factor(_advances(data)) or 10.0
    result = []
    for newer, older in zip(readings, readings[1:]):
        if newer.get("deviceNumber") != older.get("deviceNumber"):
            continue
        new_v = float(newer["readingValue"])
        old_v = float(older["readingValue"])
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


def _invoice_rows(invoices):
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


def _period_cost(invoices, start, end):
    return round(sum(amount for dt, amount, _ in _invoice_rows(invoices) if start <= dt < end), 2)


def _history_window(history, months=12):
    if not history:
        return None
    end = _dt(history[0]["to"])
    if not end:
        return None
    start = end - timedelta(days=months * 30.4375)
    rows = [h for h in history if _dt(h["to"]) and _dt(h["to"]) > start and _dt(h["from"]) and _dt(h["from"]) <= end]
    # Use intervals whose end falls in the requested window. This avoids inventing daily values.
    rows = [h for h in history if _dt(h["to"]) and start <= _dt(h["to"]) <= end]
    return rows


def _actual_consumption(history, months=12):
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


def _plan_totals(advances):
    return {
        "pln": round(sum(float(a.get("advanceAmount") or 0) for a in advances), 2),
        "m3": round(sum(float(a.get("estimatedUsageInM3") or 0) for a in advances), 3),
        "kwh": round(sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances), 1),
    }


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    keys = [
        ("balance", "Saldo", "balance", "PLN"),
        ("amount_to_pay", "Do zapłaty", "amount_to_pay", "PLN"),
        ("last_invoice", "Ostatnia faktura", "last_invoice", "PLN"),
        ("unread", "Nieprzeczytane wiadomości", "unread_messages", None),
        ("tariff", "Taryfa", "tariff", None),
        ("contract", "Numer umowy", "contract", None),
        ("meter_reading", "Stan licznika gazu", "meter_reading", "m³"),
        ("meter_number", "Numer licznika gazu", "meter_number", None),
        ("previous_reading", "Poprzedni odczyt gazu", "previous_reading", "m³"),
        ("consumption_since_reading", "Zużycie od poprzedniego odczytu", "consumption_since_reading", "m³"),
        ("consumption_since_reading_kwh", "Zużycie od poprzedniego odczytu", "consumption_since_reading_kwh", "kWh"),
        ("conversion_factor", "Przelicznik m³ → kWh", "conversion_factor", "kWh/m³"),
        ("history_total_m3", "Historia zużycia gazu", "history_total_m3", "m³"),
        ("history_total_kwh", "Historia zużycia gazu", "history_total_kwh", "kWh"),
        ("actual_invoice_cost_6m", "Koszt faktur — 6 mies.", "actual_invoice_cost_6m", "PLN"),
        ("actual_invoice_cost_12m", "Koszt faktur — 12 mies.", "actual_invoice_cost_12m", "PLN"),
        ("actual_consumption_12m_m3", "Rzeczywiste zużycie — 12 mies.", "actual_consumption_12m_m3", "m³"),
        ("actual_consumption_12m_kwh", "Rzeczywiste zużycie — 12 mies.", "actual_consumption_12m_kwh", "kWh"),
        ("actual_cost_per_m3", "Rzeczywisty koszt gazu", "actual_cost_per_m3", "PLN/m³"),
        ("actual_cost_per_kwh", "Rzeczywisty koszt gazu", "actual_cost_per_kwh", "PLN/kWh"),
        ("plan_cost_per_m3", "Plan — koszt m³", "plan_cost_per_m3", "PLN/m³"),
        ("plan_cost_per_kwh", "Plan — koszt kWh", "plan_cost_per_kwh", "PLN/kWh"),
        ("actual_vs_plan_6m", "Rzeczywiste 6M vs plan 6M", "actual_vs_plan_6m", "PLN"),
        ("next_advance", "Najbliższa zaliczka", "next_advance", "PLN"),
        ("next_advance_m3", "Najbliższa zaliczka — m³", "next_advance_m3", "m³"),
        ("next_advance_kwh", "Najbliższa zaliczka — kWh", "next_advance_kwh", "kWh"),
        ("advance_plan_total", "Plan zaliczkowy — suma", "advance_plan_total", "PLN"),
        ("advance_plan_m3", "Plan zaliczkowy — m³", "advance_plan_m3", "m³"),
        ("advance_plan_kwh", "Plan zaliczkowy — kWh", "advance_plan_kwh", "kWh"),
    ]
    async_add_entities([GenGazSensor(coordinator, *args) for args in keys])


class GenGazSensor(CoordinatorEntity[GenGazCoordinator], SensorEntity):
    def __init__(self, coordinator, key: str, name: str, suffix: str, unit: str | None):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "gen_gaz")},
            "name": "G.EN. Gaz Energia",
            "manufacturer": "G.EN. Gaz Energia",
        }
        if key == "meter_reading":
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_state_class = "total_increasing"

    @property
    def native_value(self):
        data = self.coordinator.data
        contract = _contract(data)
        invoices = _invoices(data)
        payments = _payments(data)
        advances = _advances(data)
        readings = _readings(data)
        history = _history(data)
        factor = _plan_factor(advances)
        actual12 = _actual_consumption(history, 12)
        plan = _plan_totals(advances)
        rows = _invoice_rows(invoices)

        if self._key == "balance": return contract.get("saldo")
        if self._key == "amount_to_pay": return round(sum(float(p.get("amountToPay") or 0) for p in payments if not p.get("isPaid")), 2)
        if self._key == "last_invoice": return invoices[0].get("amount") if invoices else None
        if self._key == "unread": return data.get("unread", 0)
        if self._key == "tariff": return contract.get("tariffGroup")
        if self._key == "contract": return contract.get("contractNumber")
        if self._key == "meter_reading": return readings[0].get("readingValue") if readings else None
        if self._key == "meter_number": return readings[0].get("deviceNumber") if readings else None
        if self._key == "previous_reading": return readings[1].get("readingValue") if len(readings) > 1 else None
        if self._key == "consumption_since_reading": return history[0]["consumption_m3"] if history else None
        if self._key == "consumption_since_reading_kwh": return history[0]["estimated_kwh"] if history else None
        if self._key == "conversion_factor": return round(factor, 4) if factor else None
        if self._key == "history_total_m3": return round(sum(x["consumption_m3"] for x in history), 3)
        if self._key == "history_total_kwh": return round(sum(x["estimated_kwh"] for x in history), 1)
        if self._key == "actual_invoice_cost_6m":
            if not rows: return None
            end = rows[0][0]
            return _period_cost(invoices, end - timedelta(days=182), end + timedelta(days=1))
        if self._key == "actual_invoice_cost_12m":
            if not rows: return None
            end = rows[0][0]
            return _period_cost(invoices, end - timedelta(days=365), end + timedelta(days=1))
        if self._key == "actual_consumption_12m_m3": return actual12["m3"] if actual12 else None
        if self._key == "actual_consumption_12m_kwh": return actual12["kwh"] if actual12 else None
        if self._key == "actual_cost_per_m3":
            cost = self._actual_cost_12m(invoices, rows)
            return round(cost / actual12["m3"], 2) if cost is not None and actual12 and actual12["m3"] else None
        if self._key == "actual_cost_per_kwh":
            cost = self._actual_cost_12m(invoices, rows)
            return round(cost / actual12["kwh"], 4) if cost is not None and actual12 and actual12["kwh"] else None
        if self._key == "plan_cost_per_m3": return round(plan["pln"] / plan["m3"], 2) if plan["m3"] else None
        if self._key == "plan_cost_per_kwh": return round(plan["pln"] / plan["kwh"], 4) if plan["kwh"] else None
        if self._key == "actual_vs_plan_6m":
            actual = self._actual_cost_6m(invoices, rows)
            return round(actual - plan["pln"], 2) if actual is not None else None
        if self._key == "next_advance": return advances[0].get("advanceAmount") if advances else None
        if self._key == "next_advance_m3": return advances[0].get("estimatedUsageInM3") if advances else None
        if self._key == "next_advance_kwh": return advances[0].get("estimatedUsageInKwh") if advances else None
        if self._key == "advance_plan_total": return plan["pln"]
        if self._key == "advance_plan_m3": return plan["m3"]
        if self._key == "advance_plan_kwh": return plan["kwh"]
        return None

    def _actual_cost_6m(self, invoices, rows):
        if not rows: return None
        end = rows[0][0]
        return _period_cost(invoices, end - timedelta(days=182), end + timedelta(days=1))

    def _actual_cost_12m(self, invoices, rows):
        if not rows: return None
        end = rows[0][0]
        return _period_cost(invoices, end - timedelta(days=365), end + timedelta(days=1))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        contract = _contract(data)
        invoices = _invoices(data)
        advances = _advances(data)
        readings = _readings(data)
        history = _history(data)
        plan = _plan_totals(advances)
        factor = _plan_factor(advances)
        actual12 = _actual_consumption(history, 12)

        if self._key == "contract":
            return {"ppg": contract.get("ppg"), "delivery_address": contract.get("deliveryAddress"), "type": contract.get("typeOfContract"), "active": contract.get("isActive")}
        if self._key == "last_invoice" and invoices:
            i = invoices[0]
            return {"invoice_number": i.get("invoiceNumber"), "issued": i.get("issued"), "payment_deadline": i.get("paymentDeadline"), "is_paid": i.get("isPaid")}
        if self._key in {"next_advance", "next_advance_m3", "next_advance_kwh", "advance_plan_total", "advance_plan_m3", "advance_plan_kwh", "plan_cost_per_m3", "plan_cost_per_kwh", "actual_vs_plan_6m"}:
            return {"months": len(advances), "plan_total_pln": plan["pln"], "plan_total_m3": plan["m3"], "plan_total_kwh": plan["kwh"], "plan": advances}
        if self._key in {"meter_reading", "meter_number", "previous_reading", "consumption_since_reading", "consumption_since_reading_kwh", "history_total_m3", "history_total_kwh", "conversion_factor"}:
            return {"reading_date": readings[0].get("readingDate") if readings else None, "device_number": readings[0].get("deviceNumber") if readings else None, "previous_reading_date": readings[1].get("readingDate") if len(readings) > 1 else None, "conversion_kwh_per_m3": round(factor, 4) if factor else None, "history_count": len(readings), "history": readings, "consumption_intervals": history}
        if self._key.startswith("actual_"):
            attrs = {"invoice_count": len(invoices), "invoices": invoices, "history_12m": actual12}
            if factor: attrs["conversion_kwh_per_m3"] = round(factor, 4)
            return attrs
        return None
