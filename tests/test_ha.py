"""Tests of the Home Assistant side (config flow, coordinator, to-do entity).

Skipped when pytest-homeassistant-custom-component is not installed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.exceptions import (  # noqa: E402
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.coop_schweiz.api import (  # noqa: E402
    CoopApiError,
    CoopAuthError,
    CoopItem,
    CoopNotFoundError,
    CoopProduct,
)
from custom_components.coop_schweiz.const import (  # noqa: E402
    CONF_LIST_ID,
    CONF_LIST_NAME,
    CONF_REDIRECT_URL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

pytestmark = pytest.mark.asyncio

PKG = "custom_components.coop_schweiz"
REDIRECT = "https://api.coop.ch/x/redirect?language=de&code=OC-1"
LISTS = [{"id": "L1", "name": "Einkaufszettel"}, {"id": "L2", "name": "Ferien"}]
ITEMS = [
    CoopItem(id="A", name="Milch", quantity=2, checked=False, catalog=False),
    CoopItem(id="B", name="6 x Eier", quantity=1, checked=False, catalog=False),
    CoopItem(
        id="C", name="Apfelsaft", quantity=1, checked=True, catalog=True, code="111"
    ),
    CoopItem(
        id="H",
        name="Bio Vollmilch",
        quantity=1,
        checked=False,
        catalog=True,
        code="6554381",
        active=False,
    ),
]


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield


def _client(**overrides) -> MagicMock:
    client = MagicMock()
    client.refresh_token = "rt-new"
    client.get_lists = AsyncMock(return_value=LISTS)
    client.get_items = AsyncMock(return_value=list(ITEMS))
    client.add_item = AsyncMock(return_value="NEW")
    client.update_item = AsyncMock()
    client.delete_items = AsyncMock()
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


@pytest.fixture
def flow_client():
    client = _client()
    with (
        patch(f"{PKG}.config_flow.exchange_code", AsyncMock(return_value=("rt", "id"))),
        patch(f"{PKG}.config_flow.CoopClient", return_value=client),
        patch(f"{PKG}.async_setup_entry", AsyncMock(return_value=True)),
    ):
        yield client


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Coop Schweiz: Einkaufszettel",
        unique_id="L1",
        data={
            CONF_REFRESH_TOKEN: "rt-old",
            CONF_LIST_ID: "L1",
            CONF_LIST_NAME: "Einkaufszettel",
        },
    )


async def _setup(hass, client) -> tuple[MockConfigEntry, str]:
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(f"{PKG}.coordinator.CoopClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "todo", DOMAIN, f"{entry.entry_id}_list"
    )
    return entry, entity_id


# --- config flow ----------------------------------------------------------


async def test_user_flow_creates_entry(hass, flow_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert "login.supercard.ch" in result["description_placeholders"]["auth_url"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REDIRECT_URL: REDIRECT}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "list"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LIST_ID: "L2"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Coop Schweiz: Ferien"
    assert result["data"] == {
        CONF_REFRESH_TOKEN: "rt-new",
        CONF_LIST_ID: "L2",
        CONF_LIST_NAME: "Ferien",
    }


@pytest.mark.parametrize(
    ("pasted", "exchange", "error"),
    [
        ("https://login.supercard.ch/cas/login", None, "invalid_code"),
        ("https://x/redirect?code=OC-1&state=foreign", None, "wrong_state"),
        (REDIRECT, CoopAuthError("rejected"), "auth"),
        (REDIRECT, CoopApiError("HTTP 500"), "api_error"),
        (REDIRECT, RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(hass, flow_client, pasted, exchange, error):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(
        f"{PKG}.config_flow.exchange_code",
        AsyncMock(side_effect=exchange, return_value=("rt", "id")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REDIRECT_URL: pasted}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_aborts_for_configured_list(hass, flow_client):
    _entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REDIRECT_URL: REDIRECT}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LIST_ID: "L1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_token(hass, flow_client):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REDIRECT_URL: REDIRECT}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_REFRESH_TOKEN] == "rt-new"
    assert entry.data[CONF_LIST_ID] == "L1"


async def test_reauth_with_other_account_aborts(hass, flow_client):
    flow_client.get_lists.return_value = [{"id": "OTHER", "name": "x"}]
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REDIRECT_URL: REDIRECT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_REFRESH_TOKEN] == "rt-old"


# --- setup and entity -----------------------------------------------------


async def test_setup_creates_todo_entity(hass):
    entry, entity_id = await _setup(hass, _client())
    assert entry.state is ConfigEntryState.LOADED
    assert entity_id
    assert hass.states.get(entity_id).state == "2"  # two unchecked products

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_expired_sign_in_starts_reauth(hass):
    client = _client(get_items=AsyncMock(side_effect=CoopAuthError("rejected")))
    entry, _ = await _setup(hass, client)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_backend_error_retries_setup(hass):
    client = _client(get_items=AsyncMock(side_effect=CoopApiError("HTTP 503")))
    entry, _ = await _setup(hass, client)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def _call(hass, service, entity_id, **data):
    await hass.services.async_call(
        "todo", service, data, target={"entity_id": entity_id}, blocking=True
    )


async def test_add_item_parses_quantity(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    await _call(hass, "add_item", entity_id, item="3x Brot")
    client.add_item.assert_awaited_once_with("L1", "Brot", 3)


async def test_checking_does_not_rename(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    await _call(hass, "update_item", entity_id, item="6 x Eier", status="completed")
    client.update_item.assert_awaited_once_with(
        "L1", "B", name=None, quantity=None, checked=True
    )


async def test_rename_and_quantity_change(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    await _call(hass, "update_item", entity_id, item="2× Milch", rename="3x Vollmilch")
    client.update_item.assert_awaited_once_with(
        "L1", "A", name="Vollmilch", quantity=3, checked=None
    )


async def test_catalog_product_cannot_be_renamed(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "update_item", entity_id, item="Apfelsaft", rename="Cola")
    client.update_item.assert_not_awaited()

    await _call(hass, "update_item", entity_id, item="Apfelsaft", rename="2x Apfelsaft")
    client.update_item.assert_awaited_once_with(
        "L1", "C", name=None, quantity=2, checked=None
    )


async def test_remove_item(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    await _call(hass, "remove_item", entity_id, item=["2× Milch"])
    client.delete_items.assert_awaited_once_with("L1", ["A"])


@pytest.mark.parametrize(
    "error", [CoopApiError("HTTP 500"), CoopNotFoundError("gone"), CoopAuthError("x")]
)
async def test_write_errors_become_home_assistant_errors(hass, error):
    client = _client(update_item=AsyncMock(side_effect=error))
    _, entity_id = await _setup(hass, client)
    refreshes = client.get_items.await_count
    with pytest.raises(HomeAssistantError):
        await _call(hass, "update_item", entity_id, item="2× Milch", status="completed")
    await hass.async_block_till_done()
    assert client.get_items.await_count > refreshes  # list reloaded after the error


async def test_diagnostics_contain_no_names(hass):
    from custom_components.coop_schweiz.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry, _ = await _setup(hass, _client())
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["products"] == 3 and data["checked"] == 1
    assert "Milch" not in str(data) and "rt-old" not in str(data)


# --- history, re-use of known products, catalogue products ----------------


async def test_inactive_products_are_hidden(hass):
    _, entity_id = await _setup(hass, _client())
    result = await hass.services.async_call(
        "todo",
        "get_items",
        {},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    names = [item["summary"] for item in result[entity_id]["items"]]
    assert "Bio Vollmilch" not in names
    assert hass.states.get(entity_id).state == "2"


async def test_adding_a_known_name_reuses_the_product(hass):
    client = _client()
    _, entity_id = await _setup(hass, client)
    # in the app's history: back on the list instead of a free-text duplicate
    await _call(hass, "add_item", entity_id, item="2x bio vollmilch")
    client.update_item.assert_awaited_once_with(
        "L1", "H", quantity=2, checked=False, reactivate=True
    )
    client.update_item.reset_mock()
    # checked off: back on the list
    await _call(hass, "add_item", entity_id, item="Apfelsaft")
    client.update_item.assert_awaited_once_with(
        "L1", "C", quantity=1, checked=False, reactivate=True
    )
    client.update_item.reset_mock()
    # already open: raise the quantity
    await _call(hass, "add_item", entity_id, item="Milch")
    client.update_item.assert_awaited_once_with("L1", "A", quantity=3, checked=False)
    client.add_item.assert_not_awaited()


async def test_add_product_service(hass):
    client = _client(add_product=AsyncMock(return_value="NEW"))
    _, entity_id = await _setup(hass, client)
    product = CoopProduct(code="4389992", name="Vollmilch", image="i", category_id=3)
    target = {"entity_id": entity_id}
    with patch(f"{PKG}.todo.get_product", AsyncMock(return_value=product)) as lookup:
        await hass.services.async_call(
            DOMAIN, "add_product", {"code": "4389992", "quantity": 2}, target=target, blocking=True
        )
        lookup.assert_awaited_once()
        client.add_product.assert_awaited_once_with("L1", product, 2)

        # known product number: re-used, no lookup, no new document
        lookup.reset_mock()
        await hass.services.async_call(
            DOMAIN, "add_product", {"code": "6554381"}, target=target, blocking=True
        )
        lookup.assert_not_awaited()
        client.update_item.assert_awaited_once_with(
            "L1", "H", quantity=1, checked=False, reactivate=True
        )

    with patch(f"{PKG}.todo.get_product", AsyncMock(return_value=None)):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "add_product", {"code": "000"}, target=target, blocking=True
            )


async def test_search_command(hass, hass_ws_client):
    await _setup(hass, _client())
    product = CoopProduct(code="1", name="Milch", image="i", category_id=3, content="1 l")
    ws = await hass_ws_client(hass)
    with patch(f"{PKG}.search_products", AsyncMock(return_value=[product])) as search:
        await ws.send_json({"id": 1, "type": f"{DOMAIN}/search", "query": " Milch "})
        answer = await ws.receive_json()
        assert answer["success"]
        assert answer["result"]["products"] == [
            {"code": "1", "name": "Milch", "image": "i", "category_id": 3, "content": "1 l"}
        ]
        await ws.send_json({"id": 2, "type": f"{DOMAIN}/search", "query": "milch"})
        assert (await ws.receive_json())["success"]
        search.assert_awaited_once()  # the second answer came from the cache


async def test_reuse_prefers_open_then_checked_then_history(hass):
    items = [
        CoopItem(
            id="H1", name="Butter", quantity=1, checked=False, catalog=True, code="5", active=False
        ),
        CoopItem(id="C1", name="Butter", quantity=1, checked=True, catalog=False),
        CoopItem(id="O1", name="butter", quantity=2, checked=False, catalog=False),
    ]
    client = _client(get_items=AsyncMock(return_value=items))
    _, entity_id = await _setup(hass, client)
    await _call(hass, "add_item", entity_id, item="Butter")
    client.update_item.assert_awaited_once_with("L1", "O1", quantity=3, checked=False)
    client.add_item.assert_not_awaited()


async def test_reuse_prefers_catalogue_product_among_equals(hass):
    items = [
        CoopItem(id="F", name="Butter", quantity=1, checked=True, catalog=False),
        CoopItem(id="K", name="Butter", quantity=1, checked=True, catalog=True, code="5"),
    ]
    client = _client(get_items=AsyncMock(return_value=items))
    _, entity_id = await _setup(hass, client)
    await _call(hass, "add_item", entity_id, item="Butter")
    client.update_item.assert_awaited_once_with(
        "L1", "K", quantity=1, checked=False, reactivate=True
    )


async def test_add_product_known_on_list(hass):
    items = [
        CoopItem(id="O", name="Cola", quantity=2, checked=False, catalog=True, code="222"),
        CoopItem(id="C", name="Apfelsaft", quantity=4, checked=True, catalog=True, code="111"),
    ]
    client = _client(get_items=AsyncMock(return_value=items), add_product=AsyncMock())
    _, entity_id = await _setup(hass, client)
    target = {"entity_id": entity_id}
    await hass.services.async_call(
        DOMAIN, "add_product", {"code": "222", "quantity": 3}, target=target, blocking=True
    )
    client.update_item.assert_awaited_once_with("L1", "O", quantity=5, checked=False)
    client.update_item.reset_mock()
    await hass.services.async_call(
        DOMAIN, "add_product", {"code": "111"}, target=target, blocking=True
    )
    client.update_item.assert_awaited_once_with(
        "L1", "C", quantity=1, checked=False, reactivate=True
    )
    client.add_product.assert_not_awaited()
