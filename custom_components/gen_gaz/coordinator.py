from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GenGazApi, GenGazApiError, GenGazAuthError, GenGazConnectionError
from .const import (
    CONF_CUSTOMER_ID,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .statistics import import_reading_statistics

_LOGGER = logging.getLogger(__name__)


class GenGazCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from G.EN. Gaz eBOK."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
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

        self.customer_id = str(customer_id)
        self.api = GenGazApi(
            async_get_clientsession(hass),
            self.customer_id,
            str(password),
        )
        options = getattr(entry, "options", None)
        scan_interval = None
        if options and hasattr(options, "get"):
            val = options.get(CONF_SCAN_INTERVAL)
            if isinstance(val, (int, float, str)):
                scan_interval = val

        if scan_interval is None:
            scan_interval = DEFAULT_SCAN_INTERVAL_MINUTES

        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=int(scan_interval)),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from G.EN. Gaz API."""
        try:
            login = await self.api.login()
            if not login.get("customerExists", True):
                raise ConfigEntryAuthFailed("Nieprawidłowy identyfikator klienta lub hasło")

            contracts_list, unread = await asyncio.gather(
                self.api.get_contracts(),
                self.api.get_unread_messages(),
            )

            contracts_data: dict[str, dict[str, Any]] = {}

            async def _fetch_contract_data(
                contract: dict[str, Any]
            ) -> tuple[str, dict[str, Any]]:
                contract_number = str(contract.get("contractNumber") or "")
                current, advance, readings = await asyncio.gather(
                    self.api.get_current_account(contract_number),
                    self.api.get_advance_plan(contract_number),
                    self.api.get_readings(contract_number),
                )
                contract_data = dict(contract)
                if isinstance(current, dict) and isinstance(current.get("contract"), dict):
                    contract_data = {**contract, **current["contract"]}
                return contract_number, {
                    "contract": contract_data,
                    "current": current or {},
                    "advance": advance or {},
                    "readings": readings or [],
                }

            if contracts_list:
                tasks = [
                    _fetch_contract_data(c)
                    for c in contracts_list
                    if isinstance(c, dict) and c.get("contractNumber")
                ]
                if tasks:
                    results = await asyncio.gather(*tasks)
                    for contract_number, c_dict in results:
                        contracts_data[contract_number] = c_dict

            # Import LTS statistics for all meters across all contracts
            for c_dict in contracts_data.values():
                readings = c_dict.get("readings") or []
                if not readings:
                    continue
                advances = (c_dict.get("advance") or {}).get("advances") or []
                kwh_per_m3 = 11.0
                total_m3 = sum(float(a.get("estimatedUsageInM3") or 0) for a in advances)
                total_kwh = sum(float(a.get("estimatedUsageInKwh") or 0) for a in advances)
                if total_m3 > 0 and total_kwh > 0:
                    kwh_per_m3 = total_kwh / total_m3

                import_reading_statistics(self.hass, readings, kwh_per_m3)

            return {
                "contracts": contracts_data,
                "unread": unread,
            }
        except GenGazAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ConfigEntryAuthFailed:
            raise
        except (GenGazConnectionError, GenGazApiError) as err:
            _LOGGER.debug("G.EN. API communication error: %s", err)
            raise UpdateFailed(f"Błąd komunikacji z eBOK G.EN.: {err}") from err
        except Exception as err:
            _LOGGER.debug("G.EN. API unexpected failure", exc_info=True)
            raise UpdateFailed(f"Nieoczekiwany błąd eBOK G.EN.: {err}") from err
