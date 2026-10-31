from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GenGazApi
from .const import CONF_CUSTOMER_ID, CONF_PASSWORD, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_CUSTOMER_ID): str,
    vol.Required(CONF_PASSWORD): str,
})


class GenGazConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            api = GenGazApi(
                async_get_clientsession(self.hass),
                user_input[CONF_CUSTOMER_ID].strip(),
                user_input[CONF_PASSWORD],
            )
            try:
                result = await api.login()
                if not result.get("customerExists"):
                    errors["base"] = "invalid_auth"
                else:
                    customer_id = str(
                        result.get("customerId") or user_input[CONF_CUSTOMER_ID]
                    )
                    await self.async_set_unique_id(customer_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="G.EN. Gaz Energia",
                        data={
                            CONF_CUSTOMER_ID: user_input[CONF_CUSTOMER_ID].strip(),
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
