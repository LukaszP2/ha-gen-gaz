from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import GenGazApiError, GenGazConnectionError
from .const import DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN
from .coordinator import GenGazCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


def _get_coordinator_and_contract(
    hass: HomeAssistant, requested_contract: str | None
) -> tuple[GenGazCoordinator, str | None]:
    """Retrieve the coordinator instance and resolved contract."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Brak skonfigurowanej integracji G.EN. Gaz")

    if requested_contract:
        for entry in entries:
            coordinator = getattr(entry, "runtime_data", None) or hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if coordinator is not None and coordinator.data:
                contracts = coordinator.data.get("contracts")
                if isinstance(contracts, dict) and requested_contract in contracts:
                    return coordinator, requested_contract
                if isinstance(contracts, list) and any(
                    isinstance(c, dict) and c.get("contractNumber") == requested_contract for c in contracts
                ):
                    return coordinator, requested_contract

    for entry in entries:
        coordinator = getattr(entry, "runtime_data", None) or hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if coordinator is not None:
            data = coordinator.data or {}
            contracts = data.get("contracts") or {}
            resolved_contract = requested_contract
            if not resolved_contract:
                if isinstance(contracts, dict) and contracts:
                    resolved_contract = next(iter(contracts.keys()))
                elif isinstance(contracts, list) and contracts:
                    resolved_contract = contracts[0].get("contractNumber")
            return coordinator, resolved_contract

    raise ServiceValidationError("Brak skonfigurowanej integracji G.EN. Gaz")


def _get_coordinator(hass: HomeAssistant) -> GenGazCoordinator:
    """Retrieve the coordinator instance."""
    coordinator, _ = _get_coordinator_and_contract(hass, None)
    return coordinator


async def _async_update_advance_plan(call: ServiceCall) -> None:
    """Handle the service call to update advance payment plan."""
    coordinator, contract = _get_coordinator_and_contract(
        call.hass, call.data.get("contract_number")
    )
    if not contract:
        raise ServiceValidationError("Nie znaleziono numeru umowy")

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

    try:
        await coordinator.api.update_advance_plan(contract, payload)
        await coordinator.async_request_refresh()
    except (GenGazApiError, GenGazConnectionError) as err:
        raise HomeAssistantError(f"Błąd aktualizacji planu zaliczek: {err}") from err


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("contract_number"): cv.string,
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
    """Set up G.EN. Gaz from a config entry."""
    coordinator = GenGazCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_ADVANCE_PLAN,
            _async_update_advance_plan,
            SERVICE_SCHEMA,
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    active_entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and getattr(e, "runtime_data", None) is not None
    ]
    if not active_entries and hass.services.has_service(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN):
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_ADVANCE_PLAN)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry on options update."""
    await hass.config_entries.async_reload(entry.entry_id)
