"""Config flow: Supercard ID sign-in and choice of the list."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CoopApiError,
    CoopAuthError,
    CoopClient,
    CoopConnectionError,
    CoopInvalidCodeError,
    CoopStateError,
    build_authorize_url,
    exchange_code,
    extract_code,
)
from .const import (
    CONF_LIST_ID,
    CONF_LIST_NAME,
    CONF_REDIRECT_URL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema({vol.Required(CONF_REDIRECT_URL): str})


class CoopConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guides through sign-in and choice of the list."""

    VERSION = 1

    def __init__(self) -> None:
        self._auth_url, self._verifier, self._state = build_authorize_url()
        self._refresh_token: str | None = None
        self._lists: list[dict[str, str]] = []

    async def _async_sign_in(self, pasted: str) -> str | None:
        """Redeem the pasted address; return an error key or None."""
        session = async_get_clientsession(self.hass)
        try:
            code = extract_code(pasted, self._state)
            refresh_token, id_token = await exchange_code(
                session, code, self._verifier
            )
            client = CoopClient(session, refresh_token, id_token=id_token)
            self._lists = await client.get_lists()
            self._refresh_token = client.refresh_token
        except CoopInvalidCodeError:
            return "invalid_code"
        except CoopStateError:
            return "wrong_state"
        except CoopAuthError as err:
            _LOGGER.warning("Coop sign-in failed: %s", err)
            return "auth"
        except CoopConnectionError as err:
            _LOGGER.warning("Coop sign-in failed: %s", err)
            return "cannot_connect"
        except CoopApiError as err:
            _LOGGER.warning("Coop sign-in failed: %s", err)
            return "api_error"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during the Coop sign-in")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: show the sign-in link, take the redirect address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_sign_in(user_input[CONF_REDIRECT_URL])
            if error:
                errors["base"] = error
            elif not self._lists:
                errors["base"] = "no_lists"
            else:
                return await self.async_step_list()
        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            description_placeholders={"auth_url": self._auth_url},
            errors=errors,
        )

    async def async_step_list(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: choose the list."""
        options = {lst["id"]: lst["name"] for lst in self._lists}
        if user_input is not None and user_input[CONF_LIST_ID] in options:
            list_id = user_input[CONF_LIST_ID]
            await self.async_set_unique_id(list_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Coop Schweiz: {options[list_id]}",
                data={
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_LIST_ID: list_id,
                    CONF_LIST_NAME: options[list_id],
                },
            )
        return self.async_show_form(
            step_id="list",
            data_schema=vol.Schema({vol.Required(CONF_LIST_ID): vol.In(options)}),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start the sign-in again after the refresh token became invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in again and replace the stored refresh token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await self._async_sign_in(user_input[CONF_REDIRECT_URL])
            if error:
                errors["base"] = error
            elif entry.data[CONF_LIST_ID] not in {lst["id"] for lst in self._lists}:
                return self.async_abort(reason="wrong_account")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_REFRESH_TOKEN: self._refresh_token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_SCHEMA,
            description_placeholders={"auth_url": self._auth_url},
            errors=errors,
        )
