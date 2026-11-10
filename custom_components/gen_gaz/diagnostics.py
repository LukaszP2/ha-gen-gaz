from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DOMAIN
from .coordinator import GenGazCoordinator

TO_REDACT = {
    CONF_PASSWORD,
    "password",
    "deliveryAddress",
    "ppg",
    "customerId",
    "customer_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GenGazCoordinator | None = (
        getattr(entry, "runtime_data", None)
        or hass.data.get(DOMAIN, {}).get(entry.entry_id)
    )
    coord_data = coordinator.data if coordinator else {}

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(coord_data or {}, TO_REDACT),
    }
