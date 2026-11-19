"""Config flow for the PVVX display integration."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector

from .const import (
    CONF_AUTO_UPDATE,
    CONF_BATTERY,
    CONF_BIG_NUMBER,
    CONF_BIG_NUMBER_ENTITY,
    CONF_BRACKET,
    CONF_HAPPY,
    CONF_KEEP_ALIVE,
    CONF_MIN_UPDATE_INTERVAL,
    CONF_PERCENT,
    CONF_PERMANENT,
    CONF_SAD,
    CONF_SMALL_NUMBER,
    CONF_SMALL_NUMBER_ENTITY,
    CONF_UNIT,
    CONF_VALIDITY_PERIOD,
    DEFAULT_MIN_UPDATE_INTERVAL,
    DEFAULT_VALIDITY_PERIOD,
    DOMAIN,
    UNIT_LABELS,
)

_ADDRESS_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class PvvxDisplayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup of a PVVX MiThermometer display."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PvvxDisplayOptionsFlow:
        """Create the device options flow."""
        return PvvxDisplayOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the thermometer's Bluetooth address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not _ADDRESS_PATTERN.fullmatch(address):
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"PVVX MiThermometer {address}",
                    data={CONF_ADDRESS: address},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )


class PvvxDisplayOptionsFlow(OptionsFlow):
    """Configure the display defaults for one thermometer."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage default values and display indicators."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AUTO_UPDATE, default=options.get(CONF_AUTO_UPDATE, True)
                ): cv.boolean,
                vol.Required(
                    CONF_PERMANENT, default=options.get(CONF_PERMANENT, True)
                ): cv.boolean,
                vol.Required(
                    CONF_KEEP_ALIVE, default=options.get(CONF_KEEP_ALIVE, False)
                ): cv.boolean,
                vol.Optional(CONF_BIG_NUMBER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_SMALL_NUMBER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_BIG_NUMBER, default=options.get(CONF_BIG_NUMBER, 0.0)
                ): vol.All(vol.Coerce(float), vol.Range(min=-99.5, max=1999.5)),
                vol.Required(
                    CONF_SMALL_NUMBER, default=options.get(CONF_SMALL_NUMBER, 0)
                ): vol.All(vol.Coerce(float), vol.Range(min=-9, max=99)),
                vol.Required(
                    CONF_MIN_UPDATE_INTERVAL,
                    default=options.get(
                        CONF_MIN_UPDATE_INTERVAL, DEFAULT_MIN_UPDATE_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Required(
                    CONF_VALIDITY_PERIOD,
                    default=options.get(CONF_VALIDITY_PERIOD, DEFAULT_VALIDITY_PERIOD),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_UNIT, default=options.get(CONF_UNIT, "none")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=value, label=label)
                            for value, label in UNIT_LABELS.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_HAPPY, default=options.get(CONF_HAPPY, False)): cv.boolean,
                vol.Required(CONF_SAD, default=options.get(CONF_SAD, False)): cv.boolean,
                vol.Required(
                    CONF_BRACKET, default=options.get(CONF_BRACKET, False)
                ): cv.boolean,
                vol.Required(
                    CONF_PERCENT, default=options.get(CONF_PERCENT, False)
                ): cv.boolean,
                vol.Required(
                    CONF_BATTERY, default=options.get(CONF_BATTERY, False)
                ): cv.boolean,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, options),
        )
