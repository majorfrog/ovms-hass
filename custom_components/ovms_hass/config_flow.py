"""Config flow for OVMS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .api import OVMSApiClient, OVMSAuthenticationError, OVMSConnectionError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_hass"
DEFAULT_HOST = "api.openvehicles.com"
DEFAULT_PORT = 6869
DEFAULT_SCAN_INTERVAL = 300
CONF_VEHICLE_ID = "vehicle_id"
CONF_VEHICLE_PASSWORD = "vehicle_password"


class OVMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OVMSOptionsFlowHandler()


    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle import from configuration.yaml.

        Args:
            import_data: Data from YAML configuration

        Returns:
            Configuration flow result
        """
        vehicle_id = import_data.get(CONF_VEHICLE_ID, import_data.get(CONF_HOST, DEFAULT_HOST))
        _LOGGER.info("Importing OVMS configuration for vehicle %s", vehicle_id)

        # Check if entry already exists for this vehicle
        await self.async_set_unique_id(vehicle_id)
        self._abort_if_unique_id_configured()

        # Simply create the config entry without validation
        # Validation will happen during async_setup_entry
        return self.async_create_entry(
            title=f"OVMS {vehicle_id}",
            data=import_data,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a user-initiated config flow.

        Args:
            user_input: User input from the configuration form

        Returns:
            Configuration flow result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Basic validation
            host = user_input.get(CONF_HOST, DEFAULT_HOST)
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            vehicle_id = user_input.get(CONF_VEHICLE_ID)

            # Validate required fields
            if not host or not username or not password:
                errors["base"] = "missing_credentials"
            else:
                # Try to connect to validate credentials
                try:
                    api_client = OVMSApiClient(
                        host=host,
                        username=username,
                        password=password,
                        port=port,
                        use_https=True,
                    )
                    await api_client.connect()

                    # If vehicle_id not provided, try to get first vehicle from list
                    if not vehicle_id:
                        try:
                            vehicles = await api_client.list_vehicles()
                            if vehicles:
                                vehicle_id = vehicles[0].id
                                user_input[CONF_VEHICLE_ID] = vehicle_id
                        except Exception as err:
                            _LOGGER.debug("Could not list vehicles: %s", err)

                    await api_client.disconnect()

                    # Set unique ID based on vehicle_id or host:username
                    unique_id = vehicle_id if vehicle_id else f"{host}:{username}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    title = f"OVMS {vehicle_id}" if vehicle_id else f"OVMS ({host})"
                    return self.async_create_entry(
                        title=title,
                        data=user_input,
                    )
                except OVMSAuthenticationError:
                    errors["base"] = "invalid_auth"
                except OVMSConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception as err:
                    _LOGGER.exception("Unexpected error during config flow: %s", err)
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Optional(CONF_VEHICLE_ID): cv.string,
                    vol.Optional(CONF_VEHICLE_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )


class OVMSOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle OVMS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            self.config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                }
            ),
        )
