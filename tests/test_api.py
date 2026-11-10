"""Tests for GenGazApi."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from custom_components.gen_gaz.api import (
    GenGazApi,
    GenGazAuthError,
    GenGazConnectionError,
)


class TestGenGazApi(unittest.IsolatedAsyncioTestCase):
    """Test suite for GenGazApi."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.session = MagicMock(spec=aiohttp.ClientSession)
        self.api = GenGazApi(self.session, "123456", "secret_pass")

    async def test_login_success(self) -> None:
        """Test successful login."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"customerExists": True, "customerId": "123456"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        self.session.request.return_value = mock_response

        res = await self.api.login()
        self.assertTrue(res.get("customerExists"))

    async def test_login_auth_error_when_customer_exists_false(self) -> None:
        """Test login raising GenGazAuthError when customerExists is False."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"customerExists": False})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        self.session.request.return_value = mock_response

        with self.assertRaises(GenGazAuthError):
            await self.api.login()

    async def test_request_http_401_raises_auth_error(self) -> None:
        """Test HTTP 401 raises GenGazAuthError."""
        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        self.session.request.return_value = mock_response

        with self.assertRaises(GenGazAuthError):
            await self.api.get_contracts()

    async def test_request_connection_error(self) -> None:
        """Test connection failure raises GenGazConnectionError."""
        self.session.request.side_effect = aiohttp.ClientConnectionError("Connection refused")

        with self.assertRaises(GenGazConnectionError):
            await self.api.get_contracts()

    async def test_get_contracts(self) -> None:
        """Test getting contracts."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value=[{"contractNumber": "UM/123"}])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        self.session.request.return_value = mock_response

        contracts = await self.api.get_contracts()
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["contractNumber"], "UM/123")

    async def test_update_advance_plan(self) -> None:
        """Test updating advance plan."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        self.session.request.return_value = mock_response

        await self.api.update_advance_plan("UM/123", {"reason": "test"})
        self.session.request.assert_called_once()

    async def test_request_http_503_retry_success(self) -> None:
        """Test HTTP 503 retries once and succeeds on second attempt."""
        resp_503 = MagicMock()
        resp_503.status = 503
        resp_503.__aenter__ = AsyncMock(return_value=resp_503)
        resp_503.__aexit__ = AsyncMock(return_value=None)

        resp_200 = MagicMock()
        resp_200.status = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.json = AsyncMock(return_value=[{"contractNumber": "UM/123"}])
        resp_200.__aenter__ = AsyncMock(return_value=resp_200)
        resp_200.__aexit__ = AsyncMock(return_value=None)

        self.session.request.side_effect = [resp_503, resp_200]

        contracts = await self.api.get_contracts()
        self.assertEqual(len(contracts), 1)
        self.assertEqual(self.session.request.call_count, 2)

    async def test_request_http_502_retry_failure_raises_connection_error(self) -> None:
        """Test HTTP 502 retries once and raises GenGazConnectionError on second failure."""
        resp_502 = MagicMock()
        resp_502.status = 502
        resp_502.__aenter__ = AsyncMock(return_value=resp_502)
        resp_502.__aexit__ = AsyncMock(return_value=None)

        self.session.request.side_effect = [resp_502, resp_502]

        with self.assertRaises(GenGazConnectionError):
            await self.api.get_contracts()
        self.assertEqual(self.session.request.call_count, 2)

    async def test_request_http_504_retry_failure_raises_connection_error(self) -> None:
        """Test HTTP 504 retries once and raises GenGazConnectionError on second failure."""
        resp_504 = MagicMock()
        resp_504.status = 504
        resp_504.__aenter__ = AsyncMock(return_value=resp_504)
        resp_504.__aexit__ = AsyncMock(return_value=None)

        self.session.request.side_effect = [resp_504, resp_504]

        with self.assertRaises(GenGazConnectionError):
            await self.api.get_contracts()
        self.assertEqual(self.session.request.call_count, 2)
