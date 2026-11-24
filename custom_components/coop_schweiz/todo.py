"""To-do list entity for one Coop shopping list."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import voluptuous as vol
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    CoopApiError,
    CoopAuthError,
    CoopItem,
    CoopNotFoundError,
    CoopProduct,
    get_product,
)
from .const import DATA_PRODUCTS, DOMAIN, SERVICE_ADD_PRODUCT
from .coordinator import CoopConfigEntry, CoopCoordinator
from .util import MAX_QUANTITY, format_summary, parse_summary

# Writes go through the coordinator's client one at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CoopConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the to-do list of a config entry."""
    async_add_entities([CoopTodoList(entry.runtime_data, entry)])
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_ADD_PRODUCT,
        {
            vol.Required("code"): cv.string,
            vol.Optional("quantity", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=MAX_QUANTITY)
            ),
        },
        "async_add_product",
    )


def _summary(item: CoopItem) -> str:
    return format_summary(item.name, item.quantity)


class CoopTodoList(CoordinatorEntity[CoopCoordinator], TodoListEntity):
    """Represents the Coop shopping list as a to-do list."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: CoopCoordinator, entry: CoopConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_list"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the products of the list."""
        return [
            TodoItem(
                uid=item.id,
                summary=_summary(item),
                status=(
                    TodoItemStatus.COMPLETED
                    if item.checked
                    else TodoItemStatus.NEEDS_ACTION
                ),
            )
            for item in self.coordinator.data or []
        ]

    @asynccontextmanager
    async def _writing(self) -> AsyncIterator[None]:
        """Translate client errors and refresh the list afterwards."""
        try:
            yield
        except CoopAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except CoopNotFoundError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="item_gone"
            ) from err
        except CoopApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            # Reload right away (async_request_refresh would debounce and
            # delay the display of quick successive changes).
            await self.coordinator.async_refresh()

    async def _async_put_back(self, existing: CoopItem, quantity: int) -> None:
        """Add to a product that already exists instead of duplicating it.

        Open on the list: raise the quantity (and clear a check mark that
        may have been set in the app since the last refresh). Checked or only
        in the app's history: put it back on the list with the given quantity.
        """
        client = self.coordinator.client
        if existing.active and not existing.checked:
            await client.update_item(
                self.coordinator.list_id,
                existing.id,
                quantity=existing.quantity + quantity,
                checked=False,
            )
        else:
            await client.update_item(
                self.coordinator.list_id,
                existing.id,
                quantity=quantity,
                checked=False,
                reactivate=True,
            )

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a product by name ("2x Milk" sets the quantity).

        A product of that name that is already known (on the list or in the
        app's history) is re-used, so that products from the Coop catalogue
        stay catalogue products. Otherwise a free-text product is created.
        """
        name, quantity = parse_summary(item.summary)
        if not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="empty_name"
            )
        existing = self.coordinator.find_existing(name=name)
        async with self._writing():
            if existing:
                await self._async_put_back(existing, quantity)
            else:
                await self.coordinator.client.add_item(
                    self.coordinator.list_id, name, quantity
                )

    async def async_add_product(self, code: str, quantity: int = 1) -> None:
        """Add a product of the Coop catalogue by its product number."""
        code = code.strip()
        existing = self.coordinator.find_existing(code=code)
        product: CoopProduct | None = None
        if not existing:
            product = self.hass.data.get(DOMAIN, {}).get(DATA_PRODUCTS, {}).get(code)
        async with self._writing():
            if existing:
                await self._async_put_back(existing, quantity)
                return
            if product is None:
                product = await get_product(
                    async_get_clientsession(self.hass), code, self.hass.config.language
                )
            if product is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="product_not_found",
                    translation_placeholders={"code": code},
                )
            await self.coordinator.client.add_product(
                self.coordinator.list_id, product, quantity
            )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Rename, change the quantity of, or check/uncheck a product."""
        current = next(
            (it for it in self.coordinator.data or [] if it.id == item.uid), None
        )
        if current is None:
            await self.coordinator.async_refresh()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="item_gone"
            )
        name: str | None = None
        quantity: int | None = None
        checked: bool | None = None
        # Only parse the text when the user really changed it. Otherwise a
        # product named "6 x Eggs" would be renamed just by checking it.
        if item.summary is not None and item.summary != _summary(current):
            new_name, new_quantity = parse_summary(item.summary)
            if not new_name:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="empty_name"
                )
            if new_name != current.name:
                if current.catalog:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN,
                        translation_key="catalog_rename",
                    )
                name = new_name
            if new_quantity != current.quantity:
                quantity = new_quantity
        if item.status is not None:
            is_checked = item.status == TodoItemStatus.COMPLETED
            if is_checked != current.checked:
                checked = is_checked
        if name is None and quantity is None and checked is None:
            return
        async with self._writing():
            await self.coordinator.client.update_item(
                self.coordinator.list_id,
                current.id,
                name=name,
                quantity=quantity,
                checked=checked,
            )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete products."""
        async with self._writing():
            await self.coordinator.client.delete_items(
                self.coordinator.list_id, uids
            )
