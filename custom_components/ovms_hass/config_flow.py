"""Config flow for OVMS integration."""

from __future__ import annotations

from collections.abc import Mapping
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
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    OVMSAPIError,
    OVMSApiClient,
    OVMSAuthenticationError,
    OVMSConnectionError,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_hass"
DEFAULT_HOST = "api.openvehicles.com"
DEFAULT_PORT = 6869
DEFAULT_SCAN_INTERVAL = 300
CONF_VEHICLE_ID = "vehicle_id"
CONF_VEHICLE_PASSWORD = "vehicle_password"


async def _async_check_login(
    host: str,
    port: int,
    username: str,
    password: str,
    vehicle_id: str | None = None,
) -> str | None:
    """Try a REST login; return None on success or the form error key.

    With vehicle_id, the account must also have that vehicle. Otherwise a
    login to another account would be saved and every poll would fail.
    """
    api_client = OVMSApiClient(
        host=host, port=port, username=username, password=password, use_https=True
    )
    try:
        await api_client.connect()
    except OVMSAuthenticationError:
        return "invalid_auth"
    except OVMSConnectionError:
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error checking the OVMS login")
        return "unknown"
    try:
        if vehicle_id:
            vehicles = await api_client.list_vehicles()
            if vehicle_id not in {vehicle.id for vehicle in vehicles}:
                return "vehicle_not_found"
    except (OVMSConnectionError, OVMSAPIError):
        return "cannot_connect"
    finally:
        await api_client.disconnect()
    return None


def _password_selector() -> TextSelector:
    return TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


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
        _LOGGER.debug("Importing OVMS configuration for vehicle %s", vehicle_id)

        # Check if entry already exists for this vehicle. No `updates`: the
        # entry wins over the deprecated YAML, so a password changed through
        # reauth or reconfigure isn't overwritten by a stale YAML one.
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


    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the server rejects the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new server password (and optionally vehicle password).

        The server password is checked with a real login. The vehicle
        password can't be checked through the REST API; a wrong one shows
        up as failing commands.
        """
        entry = self._get_reauth_entry()
        host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_check_login(
                host,
                entry.data.get(CONF_PORT, DEFAULT_PORT),
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if error:
                errors["base"] = error
            else:
                updates = {CONF_PASSWORD: user_input[CONF_PASSWORD]}
                if user_input.get(CONF_VEHICLE_PASSWORD):
                    updates[CONF_VEHICLE_PASSWORD] = user_input[CONF_VEHICLE_PASSWORD]
                return self.async_update_reload_and_abort(entry, data_updates=updates)

        password = _password_selector()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): password,
                    vol.Optional(CONF_VEHICLE_PASSWORD): password,
                }
            ),
            description_placeholders={
                "username": entry.data[CONF_USERNAME],
                "host": host,
            },
            errors=errors,
        )


    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the server connection of an existing vehicle.

        The vehicle ID is the entry's identity (entity unique IDs are built
        from it), so it can't be changed here; another vehicle is a new
        entry. New settings are only stored after a working login.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_check_login(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                vehicle_id=entry.data.get(CONF_VEHICLE_ID),
            )
            if error:
                errors["base"] = error
            else:
                updates = {
                    key: user_input[key]
                    for key in (CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD)
                }
                if user_input.get(CONF_VEHICLE_PASSWORD):
                    updates[CONF_VEHICLE_PASSWORD] = user_input[CONF_VEHICLE_PASSWORD]
                return self.async_update_reload_and_abort(entry, data_updates=updates)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT): cv.port,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): _password_selector(),
                vol.Optional(CONF_VEHICLE_PASSWORD): _password_selector(),
            }
        )
        # Prefill from the entry (or the rejected input); never the passwords.
        current = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_HOST: current.get(CONF_HOST, DEFAULT_HOST),
                    CONF_PORT: current.get(CONF_PORT, DEFAULT_PORT),
                    CONF_USERNAME: current.get(CONF_USERNAME),
                },
            ),
            description_placeholders={
                "vehicle_id": entry.data.get(CONF_VEHICLE_ID, entry.unique_id or "")
            },
            errors=errors,
        )


class OVMSOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle OVMS options; saving them reloads the entry.

    Replaces an update listener: HA 2026.12 breaks reauth/reconfigure
    (async_update_reload_and_abort) for entries that have one.
    """

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
