from __future__ import annotations

from typing import Any
from aiohttp import ClientSession

BASE_URL = "https://ebok.gen.com.pl/api"


class GenGazApi:
    def __init__(self, session: ClientSession, username: str, password: str):
        self._session = session
        self._username = username
        self._password = password

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with self._session.request(
            method, f"{BASE_URL}{path}", timeout=30, **kwargs
        ) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    async def login(self) -> dict[str, Any]:
        return await self._request(
            "POST", "/account/login",
            json={"customerId": self._username, "password": self._password},
        )

    async def get_contracts(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/contract/getContractList")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("contracts", "contractList", "items", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    async def get_current_account(self, contract_number: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/currentAccount/getCurrentAccount",
            params={"contractNumber": contract_number},
        )

    async def get_unread_messages(self) -> int:
        data = await self._request("GET", "/messages/getunreadmessagescount")
        if isinstance(data, int):
            return data
        if isinstance(data, dict):
            for key in ("count", "unreadCount", "unreadMessagesCount", "value"):
                if isinstance(data.get(key), (int, float)):
                    return int(data[key])
        return 0

    async def get_advance_plan(self, contract_number: str) -> dict[str, Any]:
        data = await self._request(
            "GET", "/advance/getAdvancePlan",
            params={"contractNumber": contract_number},
        )
        return data if isinstance(data, dict) else {"advances": []}

    async def get_readings(self, contract_number: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", "/reading/getreadings",
            params={"contractNumber": contract_number},
        )
        return data if isinstance(data, list) else []

    async def get_header_info(self) -> dict[str, Any]:
        return await self._request("GET", "/info/getheaderinfo")

    async def get_footer_links(self) -> Any:
        return await self._request("GET", "/link/getfooterlinklist")

async def _gen_gaz_update_advance_plan(self, contract_number: str, payload: dict[str, Any]) -> None:
    await self._request(
        "PUT",
        "/advance/updateAdvancePlan",
        params={"contractNumber": contract_number},
        json=payload,
    )

GenGazApi.update_advance_plan = _gen_gaz_update_advance_plan
