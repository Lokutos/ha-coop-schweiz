"""DataUpdateCoordinator: keeps the products of one list up to date."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CoopApiError, CoopAuthError, CoopClient, CoopItem
from .const import (
    CONF_LIST_ID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    MAX_BACKOFF_SECONDS,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

type CoopConfigEntry = ConfigEntry[CoopCoordinator]


class CoopCoordinator(DataUpdateCoordinator[list[CoopItem]]):
    """Polls the shopping list and stores rotated refresh tokens.

    `data` holds the products that are on the list. `history` holds the
    products the app keeps only as history; they are re-activated instead of
    creating duplicates when the same product is added again.
    """

    config_entry: CoopConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CoopConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,  # appears in log lines: no list name here
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.list_id: str = entry.data[CONF_LIST_ID]
        self.history: list[CoopItem] = []
        self._failures = 0
        self.client = CoopClient(
            async_get_clientsession(hass),
            entry.data[CONF_REFRESH_TOKEN],
            language=hass.config.language,
            on_token_update=self._async_store_token,
        )

    async def _async_update_data(self) -> list[CoopItem]:
        try:
            items = await self.client.get_items(self.list_id)
        except CoopAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CoopApiError as err:
            # Back off while the backend is failing, so that a broken
            # installation does not keep hammering the servers.
            self._failures += 1
            self.update_interval = timedelta(
                seconds=min(
                    SCAN_INTERVAL_SECONDS * 2 ** min(self._failures, 6),
                    MAX_BACKOFF_SECONDS,
                )
            )
            raise UpdateFailed(str(err)) from err
        if self._failures:
            self._failures = 0
            self.update_interval = timedelta(seconds=SCAN_INTERVAL_SECONDS)
        self.history = [item for item in items if not item.active]
        return [item for item in items if item.active]

    def find_existing(self, *, code: str = "", name: str = "") -> CoopItem | None:
        """Find a product by product number or by name (list first, then history)."""
        if code:
            matches = [
                item for item in (*(self.data or []), *self.history) if item.code == code
            ]
        else:
            wanted = name.casefold()
            matches = [
                item
                for item in (*(self.data or []), *self.history)
                if item.name.casefold() == wanted
            ]
        # Prefer what is open on the list, then checked, then history;
        # catalogue products first among equals.
        matches.sort(
            key=lambda item: (not item.active, item.checked, not item.catalog)
        )
        return matches[0] if matches else None

    @callback
    def _async_store_token(self, refresh_token: str) -> None:
        """Persist a rotated refresh token right away."""
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_REFRESH_TOKEN: refresh_token},
        )
