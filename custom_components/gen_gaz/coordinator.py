from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GenGazApi
from .const import CONF_CUSTOMER_ID, CONF_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN
from .statistics import import_reading_statistics

_LOGGER = logging.getLogger(DOMAIN)


class GenGazCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        customer_id = (
            entry.data.get(CONF_CUSTOMER_ID)
            or entry.data.get("customerId")
            or entry.data.get("username")
            or entry.data.get("customer")
        )
        password = entry.data.get(CONF_PASSWORD) or entry.data.get("pass")
        if not customer_id or password is None:
            raise ValueError(
                "Brak danych logowania G.EN. Gaz. "
                "Wpis wymaga customer_id i password."
            )

        self.api = GenGazApi(
            async_get_clientsession(hass),
            str(customer_id),
            str(password),
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            login = await self.api.login()
            if not login.get("customerExists"):
                raise UpdateFailed("Nieprawidłowy identyfikator klienta lub hasło")

            contracts = await self.api.get_contracts()
            current = {}
            advance = {}
            readings = []

            if contracts:
                contract_number = contracts[0].get("contractNumber")
                if contract_number:
                    current = await self.api.get_current_account(contract_number)
                    advance = await self.api.get_advance_plan(contract_number)
                    readings = await self.api.get_readings(contract_number)

            unread = await self.api.get_unread_messages()

            # G.EN. readings have their original measurement dates. Import them into
            # HA long-term statistics so the history is not shifted to the import time.
            kwh_per_m3 = 11.0
            advances = (advance or {}).get("advances") or []
            total_m3 = sum(float(a.get("estimatedUsageInM3") or 0) for a in advances)
            total_kwh = sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances)
            if total_m3 > 0 and total_kwh > 0:
                kwh_per_m3 = total_kwh / total_m3
            import_reading_statistics(self.hass, readings, kwh_per_m3)

            return {
                "login": login,
                "contracts": contracts,
                "current": current,
                "advance": advance,
                "readings": readings,
                "unread": unread,
            }
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.debug("G.EN. API update failed", exc_info=True)
            raise UpdateFailed(f"Błąd komunikacji z eBOK G.EN.: {err}") from err
