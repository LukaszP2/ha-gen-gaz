"""Tests for G.EN. Gaz config flow."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.gen_gaz.api import GenGazAuthError, GenGazConnectionError
from custom_components.gen_gaz.config_flow import (
    GenGazConfigFlow,
    GenGazOptionsFlowHandler,
)
from custom_components.gen_gaz.const import (
    CONF_CUSTOMER_ID,
    CONF_ENABLE_ANALYTICS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)


class TestGenGazConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Test suite for GenGazConfigFlow."""

    async def test_step_user_show_form(self) -> None:
        """Test user step shows form when input is None."""
        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        result = await flow.async_step_user(user_input=None)

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {})

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_user_invalid_auth(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test user step sets error on invalid auth."""
        mock_login.side_effect = GenGazAuthError("Invalid credentials")

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        result = await flow.async_step_user(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "wrong"}
        )

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["errors"], {"base": "invalid_auth"})

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_user_cannot_connect(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test user step sets error on connection failure."""
        mock_login.side_effect = GenGazConnectionError("Network timeout")

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        result = await flow.async_step_user(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "pass"}
        )

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["errors"], {"base": "cannot_connect"})

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_user_success(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test successful entry creation."""
        mock_login.return_value = {"customerExists": True, "customerId": "12345"}

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        result = await flow.async_step_user(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "valid"}
        )

        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertIn("12345", result["title"])
        self.assertEqual(result["data"][CONF_CUSTOMER_ID], "12345")
        self.assertEqual(result["data"][CONF_PASSWORD], "valid")

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_reauth_confirm_success(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test reauth flow success."""
        mock_login.return_value = {"customerExists": True}

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old"}
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        # Step reauth
        res = await flow.async_step_reauth({})
        self.assertEqual(res["type"], FlowResultType.FORM)
        self.assertEqual(res["step_id"], "reauth_confirm")

        # Step reauth confirm with new password
        confirm_res = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new_pass"})
        self.assertEqual(confirm_res["type"], FlowResultType.ABORT)
        self.assertEqual(confirm_res["reason"], "reauth_successful")

    async def test_step_reconfigure_show_form(self) -> None:
        """Test reconfigure step shows form with current customer_id."""
        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old"}
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        result = await flow.async_step_reconfigure(user_input=None)
        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "reconfigure")
        self.assertEqual(result["errors"], {})
        self.assertEqual(result["description_placeholders"], {"customer_id": "12345"})

    async def test_step_reconfigure_missing_entry(self) -> None:
        """Test reconfigure aborts when entry is not found."""
        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        flow.context = {"entry_id": "nonexistent"}
        flow.hass.config_entries.async_get_entry.return_value = None

        result = await flow.async_step_reconfigure(user_input=None)
        self.assertEqual(result["type"], FlowResultType.ABORT)
        self.assertEqual(result["reason"], "reconfigure_entry_not_found")

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_reconfigure_success(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test successful reconfiguration of customer_id and password."""
        mock_login.return_value = {"customerExists": True}

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old_password"}
        mock_entry.unique_id = "12345"
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        result = await flow.async_step_reconfigure(
            user_input={CONF_CUSTOMER_ID: "67890", CONF_PASSWORD: "new_password"}
        )

        self.assertEqual(result["type"], FlowResultType.ABORT)
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(mock_entry.data[CONF_CUSTOMER_ID], "67890")
        self.assertEqual(mock_entry.data[CONF_PASSWORD], "new_password")
        self.assertEqual(mock_entry.unique_id, "67890")

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_reconfigure_invalid_auth(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test reconfigure sets error on invalid auth exception."""
        mock_login.side_effect = GenGazAuthError("Invalid credentials")

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old"}
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        result = await flow.async_step_reconfigure(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "wrong_pass"}
        )

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "reconfigure")
        self.assertEqual(result["errors"], {"base": "invalid_auth"})

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_reconfigure_customer_not_exists(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test reconfigure sets error when customerExists is false."""
        mock_login.return_value = {"customerExists": False}

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old"}
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        result = await flow.async_step_reconfigure(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "wrong_pass"}
        )

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "reconfigure")
        self.assertEqual(result["errors"], {"base": "invalid_auth"})

    @patch("custom_components.gen_gaz.config_flow.async_get_clientsession")
    @patch("custom_components.gen_gaz.config_flow.GenGazApi.login")
    async def test_step_reconfigure_connection_error(
        self, mock_login: AsyncMock, mock_session: MagicMock
    ) -> None:
        """Test reconfigure sets error on connection error."""
        mock_login.side_effect = GenGazConnectionError("Timeout")

        flow = GenGazConfigFlow()
        flow.hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "old"}
        flow.context = {"entry_id": "test_entry"}
        flow.hass.config_entries.async_get_entry.return_value = mock_entry

        result = await flow.async_step_reconfigure(
            user_input={CONF_CUSTOMER_ID: "12345", CONF_PASSWORD: "pass"}
        )

        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "reconfigure")
        self.assertEqual(result["errors"], {"base": "cannot_connect"})


class TestGenGazOptionsFlow(unittest.IsolatedAsyncioTestCase):
    """Test suite for GenGazOptionsFlowHandler."""

    async def test_options_flow_show_form_default(self) -> None:
        """Test options flow shows form with default scan interval."""
        mock_entry = MagicMock()
        mock_entry.options = {}
        flow = GenGazOptionsFlowHandler(mock_entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init(user_input=None)
        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "init")

    async def test_options_flow_show_form_existing_interval(self) -> None:
        """Test options flow shows form with existing configured interval."""
        mock_entry = MagicMock()
        mock_entry.options = {CONF_SCAN_INTERVAL: 120, CONF_ENABLE_ANALYTICS: True}
        flow = GenGazOptionsFlowHandler(mock_entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init(user_input=None)
        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "init")

    async def test_options_flow_submit(self) -> None:
        """Test options flow creates entry on submit."""
        mock_entry = MagicMock()
        mock_entry.options = {
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
            CONF_ENABLE_ANALYTICS: False,
        }
        flow = GenGazOptionsFlowHandler(mock_entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init(
            user_input={CONF_SCAN_INTERVAL: 180, CONF_ENABLE_ANALYTICS: True}
        )
        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertEqual(result["data"][CONF_SCAN_INTERVAL], 180)
        self.assertTrue(result["data"][CONF_ENABLE_ANALYTICS])

    async def test_async_get_options_flow(self) -> None:
        """Test async_get_options_flow returns GenGazOptionsFlowHandler."""
        mock_entry = MagicMock()
        options_flow = GenGazConfigFlow.async_get_options_flow(mock_entry)
        self.assertIsInstance(options_flow, GenGazOptionsFlowHandler)
        self.assertEqual(options_flow.config_entry, mock_entry)
