"""Diagnostics: only counts and state, never tokens, ids or product names."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import VERSION
from .coordinator import CoopConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CoopConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    items = coordinator.data or []
    interval = coordinator.update_interval
    return {
        "version": VERSION,
        "last_update_success": coordinator.last_update_success,
        "update_interval_seconds": interval.total_seconds() if interval else None,
        "products": len(items),
        "checked": sum(1 for item in items if item.checked),
        "catalog_products": sum(1 for item in items if item.catalog),
    }
