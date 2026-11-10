from __future__ import annotations

from typing import Any

import aiohttp
from aiohttp import ClientSession

BASE_URL = "https://ebok.gen.com.pl/api"


class GenGazApiError(Exception):
    """Base exception for G.EN. Gaz API errors."""


class GenGazAuthError(GenGazApiError):
    """Raised when authentication fails."""


class GenGazConnectionError(GenGazApiError):
    """Raised when communication with G.EN. Gaz fails."""


class GenGazApi:
    """Client for G.EN. Gaz Energia eBOK API."""

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        """Initialize the API client."""
        self._session = session
        self._username = username
        self._password = password

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute a request to the API with retry on 502/503/504."""
        timeout = aiohttp.ClientTimeout(total=30)
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                async with self._session.request(
                    method, f"{BASE_URL}{path}", timeout=timeout, **kwargs
                ) as response:
                    if response.status in (401, 403):
                        raise GenGazAuthError(f"Błąd uwierzytelnienia (HTTP {response.status})")
                    if response.status in (502, 503, 504):
                        if attempt < max_attempts - 1:
                            continue
                        raise GenGazConnectionError(
                            f"Błąd połączenia z eBOK G.EN. (HTTP {response.status})"
                        )
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except aiohttp.ClientResponseError as err:
                if err.status in (401, 403):
                    raise GenGazAuthError(f"Błąd uwierzytelnienia: {err}") from err
                if err.status in (502, 503, 504):
                    if attempt < max_attempts - 1:
                        continue
                    raise GenGazConnectionError(
                        f"Błąd połączenia z eBOK G.EN. (HTTP {err.status}): {err.message}"
                    ) from err
                raise GenGazApiError(f"Błąd odpowiedzi API ({err.status}): {err.message}") from err
            except (TimeoutError, aiohttp.ClientError) as err:
                raise GenGazConnectionError(f"Błąd połączenia z eBOK G.EN.: {err}") from err
            except GenGazApiError:
                raise
            except Exception as err:
                raise GenGazApiError(f"Nieoczekiwany błąd API: {err}") from err

    async def login(self) -> dict[str, Any]:
        """Log in to eBOK and verify credentials."""
        data = await self._request(
            "POST",
            "/account/login",
            json={"customerId": self._username, "password": self._password},
        )
        if isinstance(data, dict) and not data.get("customerExists", True):
            raise GenGazAuthError("Nieprawidłowy identyfikator klienta lub hasło")
        return data if isinstance(data, dict) else {}

    async def get_contracts(self) -> list[dict[str, Any]]:
        """Retrieve list of contracts."""
        data = await self._request("GET", "/contract/getContractList")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("contracts", "contractList", "items", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    async def get_current_account(self, contract_number: str) -> dict[str, Any]:
        """Retrieve current account details for given contract."""
        data = await self._request(
            "GET",
            "/currentAccount/getCurrentAccount",
            params={"contractNumber": contract_number},
        )
        return data if isinstance(data, dict) else {}

    async def get_unread_messages(self) -> int:
        """Retrieve unread message count."""
        data = await self._request("GET", "/messages/getunreadmessagescount")
        if isinstance(data, int):
            return data
        if isinstance(data, dict):
            for key in ("count", "unreadCount", "unreadMessagesCount", "value"):
                if isinstance(data.get(key), (int, float)):
                    return int(data[key])
        return 0

    async def get_advance_plan(self, contract_number: str) -> dict[str, Any]:
        """Retrieve advance payment plan."""
        data = await self._request(
            "GET",
            "/advance/getAdvancePlan",
            params={"contractNumber": contract_number},
        )
        return data if isinstance(data, dict) else {"advances": []}

    async def get_readings(self, contract_number: str) -> list[dict[str, Any]]:
        """Retrieve meter readings for given contract."""
        data = await self._request(
            "GET",
            "/reading/getreadings",
            params={"contractNumber": contract_number},
        )
        return data if isinstance(data, list) else []

    async def get_header_info(self) -> dict[str, Any]:
        """Retrieve header information."""
        data = await self._request("GET", "/info/getheaderinfo")
        return data if isinstance(data, dict) else {}

    async def get_footer_links(self) -> Any:
        """Retrieve footer links."""
        return await self._request("GET", "/link/getfooterlinklist")

    async def update_advance_plan(
        self, contract_number: str, payload: dict[str, Any]
    ) -> None:
        """Update advance payment plan."""
        await self._request(
            "PUT",
            "/advance/updateAdvancePlan",
            params={"contractNumber": contract_number},
            json=payload,
        )
