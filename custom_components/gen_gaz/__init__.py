from __future__ import annotations

from datetime import date
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .coordinator import GenGazCoordinator

_LOGGER = logging.getLogger(DOMAIN)
PLATFORMS = [Platform.SENSOR]
SERVICE_UPDATE_ADVANCE_PLAN = "update_advance_plan"


def _get_coordinator(hass: HomeAssistant) -> GenGazCoordinator:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise vol.Invalid("Brak skonfigurowanego G.EN. Gaz")
    return next(iter(entries.values()))


async def _async_update_advance_plan(call: ServiceCall) -> None:
    coordinator = _get_coordinator(call.hass)
    data = coordinator.data or {}
    contracts = data.get("contracts") or []
    contract = contracts[0].get("contractNumber") if contracts else None
    if not contract:
        raise vol.Invalid("Nie znaleziono numeru umowy")

    advances = []
    for i in range(1, 7):
        key = f"advance_{i}"
        value = call.data.get(key)
        if value is not None:
            advances.append({"advanceNewAmount": float(value)})

    payload: dict[str, Any] = {
        "reason": str(call.data["reason"]).strip(),
        "reading": {
            "readingValue": int(call.data["reading_value"]),
            "readingDate": call.data["reading_date"].isoformat(),
        },
        "isBlankFormRequired": bool(call.data.get("is_blank_form_required", False)),
        "advances": advances,
    }
    await coordinator.api.update_advance_plan(contract, payload)
    await coordinator.async_request_refresh()


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("reason"): vol.All(cv.string, vol.Length(min=1, max=250)),
        vol.Required("reading_value"): vol.Coerce(int),
        vol.Required("reading_date"): cv.date,
        vol.Optional("is_blank_form_required", default=False): cv.boolean,
        vol.Optional("advance_1"): vol.Coerce(float),
        vol.Optional("advance_2"): vol.Coerce(float),
        vol.Optional("advance_3"): vol.Coerce(float),
        vol.Optional("advance_4"): vol.Coerce(float),
        vol.Optional("advance_5"): vol.Coerce(float),
        vol.Optional("advance_6"): vol.Coerce(float),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GenGazCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN):
        hass.services.async_register(
            DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN, _async_update_advance_plan, SERVICE_SCHEMA
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN)
    return unloaded
