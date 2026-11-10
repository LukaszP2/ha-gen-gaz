from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GenGazApi, GenGazAuthError, GenGazConnectionError
from .const import (
    CONF_CUSTOMER_ID,
    CONF_ENABLE_ANALYTICS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_ANALYTICS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_CUSTOMER_ID): str,
    vol.Required(CONF_PASSWORD): str,
})

STEP_REAUTH_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_PASSWORD): str,
})


class GenGazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for G.EN. Gaz Energia."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            customer_id = user_input[CONF_CUSTOMER_ID].strip()
            password = user_input[CONF_PASSWORD]

            api = GenGazApi(
                async_get_clientsession(self.hass),
                customer_id,
                password,
            )
            try:
                result = await api.login()
                if not result.get("customerExists", True):
                    errors["base"] = "invalid_auth"
                else:
                    await self.async_set_unique_id(customer_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"G.EN. Gaz Energia ({customer_id})",
                        data={
                            CONF_CUSTOMER_ID: customer_id,
                            CONF_PASSWORD: password,
                        },
                    )
            except GenGazAuthError:
                errors["base"] = "invalid_auth"
            except GenGazConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in user step")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle initiation of re-authentication with G.EN. Gaz."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication confirmation step."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry or self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )

        if entry is None:
            return self.async_abort(reason="reauth_failed")

        customer_id = str(
            entry.data.get(CONF_CUSTOMER_ID)
            or entry.data.get("customerId")
            or entry.data.get("username")
            or ""
        )

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            api = GenGazApi(
                async_get_clientsession(self.hass),
                customer_id,
                password,
            )
            try:
                result = await api.login()
                if not result.get("customerExists", True):
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data={
                            **entry.data,
                            CONF_PASSWORD: password,
                        },
                    )
            except GenGazAuthError:
                errors["base"] = "invalid_auth"
            except GenGazConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in reauth step")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={"customer_id": customer_id},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if entry is None:
            entry = self.hass.config_entries.async_get_entry(
                self.context.get("entry_id", "")
            )

        if entry is None:
            return self.async_abort(reason="reconfigure_entry_not_found")

        current_customer_id = str(
            entry.data.get(CONF_CUSTOMER_ID)
            or entry.data.get("customerId")
            or entry.data.get("username")
            or ""
        )

        if user_input is not None:
            customer_id = str(user_input[CONF_CUSTOMER_ID]).strip()
            password = str(user_input[CONF_PASSWORD])

            api = GenGazApi(
                async_get_clientsession(self.hass),
                customer_id,
                password,
            )
            try:
                result = await api.login()
                if not result.get("customerExists", True):
                    errors["base"] = "invalid_auth"
                else:
                    await self.async_set_unique_id(customer_id)
                    self._abort_if_unique_id_configured()
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=customer_id,
                        title=f"G.EN. Gaz Energia ({customer_id})",
                        data_updates={
                            CONF_CUSTOMER_ID: customer_id,
                            CONF_PASSWORD: password,
                        },
                        reason="reconfigure_successful",
                    )
            except GenGazAuthError:
                errors["base"] = "invalid_auth"
            except GenGazConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in reconfigure step")
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_CUSTOMER_ID, default=current_customer_id): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            description_placeholders={"customer_id": current_customer_id},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GenGazOptionsFlowHandler:
        """Create the options flow."""
        return GenGazOptionsFlowHandler(config_entry)


class GenGazOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for G.EN. Gaz."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        if self._entry is not None:
            return self._entry
        return super().config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        current_analytics = self.config_entry.options.get(
            CONF_ENABLE_ANALYTICS, DEFAULT_ENABLE_ANALYTICS
        )

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                    ),
                ),
                vol.Optional(
                    CONF_ENABLE_ANALYTICS,
                    default=current_analytics,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
