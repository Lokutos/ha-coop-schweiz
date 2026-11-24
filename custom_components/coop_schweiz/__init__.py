"""Coop Schweiz shopping list (unofficial) for Home Assistant."""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import CoopApiError, search_products
from .const import (
    CARD_FILE,
    CARD_URL,
    DATA_PRODUCTS,
    DATA_SEARCHES,
    DOMAIN,
    SEARCH_CACHE_SECONDS,
    VERSION,
)
from .coordinator import CoopConfigEntry, CoopCoordinator

PLATFORMS: list[Platform] = [Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_MAX_CACHED = 500


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the product search and the dashboard card."""
    hass.data.setdefault(DOMAIN, {DATA_PRODUCTS: {}, DATA_SEARCHES: {}})
    websocket_api.async_register_command(hass, ws_search)
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card and load it in the frontend."""
    if hass.http is None:
        return
    # Imported here: only needed (and only available) with the HTTP server.
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / "frontend" / CARD_FILE
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), False)]
    )
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/search",
        vol.Required("query"): vol.All(str, vol.Length(max=100)),
    }
)
@websocket_api.async_response
async def ws_search(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Search the Coop catalogue for the dashboard card."""
    query = " ".join(msg["query"].split()).casefold()
    store = hass.data[DOMAIN]
    searches: dict[str, tuple[float, list[dict[str, Any]]]] = store[DATA_SEARCHES]
    cached = searches.get(query)
    if cached and time.monotonic() - cached[0] < SEARCH_CACHE_SECONDS:
        connection.send_result(msg["id"], {"products": cached[1]})
        return
    try:
        products = await search_products(
            async_get_clientsession(hass), query, hass.config.language
        )
    except CoopApiError as err:
        connection.send_error(msg["id"], "search_failed", str(err))
        return
    if len(searches) >= _MAX_CACHED or len(store[DATA_PRODUCTS]) >= _MAX_CACHED * 4:
        searches.clear()
        store[DATA_PRODUCTS].clear()
    for product in products:
        store[DATA_PRODUCTS][product.code] = product
    result = [asdict(product) for product in products]
    searches[query] = (time.monotonic(), result)
    connection.send_result(msg["id"], {"products": result})


async def async_setup_entry(hass: HomeAssistant, entry: CoopConfigEntry) -> bool:
    """Set up a config entry (one shopping list)."""
    coordinator = CoopCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CoopConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
