"""Tests for the API client against a fake HTTP session (no network)."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from coop_schweiz import api, const

LIST = "LIST-1"
SECRET_MARKER = "TOPSECRETTOKEN"


def _jwt(uid: str = "scid-test") -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": uid}).encode())
    return f"h.{payload.decode().rstrip('=')}.s"


class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Answers requests from a handler and records them."""

    def __init__(self, firestore=None, token_status=200, token_body=None):
        self.calls: list[tuple[str, str, dict]] = []
        self.firestore = firestore or (lambda method, url, kwargs: (200, {}))
        self.token_status = token_status
        self.token_body = token_body

    def count(self, part: str) -> int:
        return sum(1 for _, url, _ in self.calls if part in url)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url == const.OIDC_TOKEN:
            body = self.token_body or {"id_token": "id", "refresh_token": "rt"}
            return _Response(self.token_status, body)
        if url == const.TOKEN_BRIDGE:
            return _Response(200, {"token": "custom"})
        if url.startswith(const.FIREBASE_SIGN_IN):
            return _Response(200, {"idToken": _jwt(), "expiresIn": "3600"})
        return _Response(*self.firestore(method, url, kwargs))


def _doc(item_id, name=None, code="", quantity="1", checked=False, **extra):
    data = {
        "checked": {"booleanValue": checked},
        "coopProduct": {
            "mapValue": {
                "fields": {
                    "code": {"stringValue": code},
                    "quantity": {"integerValue": quantity},
                }
            }
        },
    }
    if name is not None:
        data["name"] = {"mapValue": {"fields": name}}
    data.update(extra)
    return {
        "name": f"projects/p/databases/(default)/documents/x/{item_id}",
        "fields": {"data": {"mapValue": {"fields": data}}},
    }


def _names(**langs):
    return {lang: {"stringValue": text} for lang, text in langs.items()}


def run(coro):
    return asyncio.run(coro)


# --- sign-in helpers ------------------------------------------------------


def test_version_matches_manifest():
    manifest = json.loads(
        (Path(api.__file__).parent / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == const.VERSION
    assert manifest["domain"] == const.DOMAIN


def test_authorize_url_and_extract_code():
    url, verifier, state = api.build_authorize_url()
    assert url.startswith(const.OIDC_AUTHORIZE) and state in url
    assert len(verifier) >= 43
    redirect = f"https://api.coop.ch/x/redirect?language=de&code=OC-1&state={state}"
    assert api.extract_code(redirect, state) == "OC-1"
    assert api.extract_code(f"code=OC-2&state={state}", state) == "OC-2"
    assert api.extract_code("  OC-3 ", state) == "OC-3"


@pytest.mark.parametrize(
    "pasted", ["", "   ", "https://login.supercard.ch/cas/login", "two words"]
)
def test_extract_code_rejects_input_without_code(pasted):
    with pytest.raises(api.CoopInvalidCodeError):
        api.extract_code(pasted, "state")


def test_extract_code_rejects_foreign_state():
    with pytest.raises(api.CoopStateError):
        api.extract_code("https://x/redirect?code=OC-1&state=other", "mine")


def test_exchange_code():
    session = FakeSession()
    assert run(api.exchange_code(session, "OC-1", "verifier")) == ("rt", "id")


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (400, {"error": "invalid_grant"}, api.CoopAuthError),
        (400, {"error": "x", "error_description": "INVALID_TICKET"}, api.CoopAuthError),
        (401, {"error": "invalid_client"}, api.CoopApiError),
        (503, {"error": "invalid_grant"}, api.CoopApiError),
        (200, {"access_token": SECRET_MARKER}, api.CoopApiError),
        (500, ValueError("no json"), api.CoopApiError),
    ],
)
def test_token_errors_are_classified_and_never_leak(status, body, error):
    session = FakeSession(token_status=status, token_body=body)
    client = api.CoopClient(session, "rt")
    with pytest.raises(error) as info:
        run(client.get_items(LIST))
    assert type(info.value) is error
    assert SECRET_MARKER not in str(info.value)


def test_rotated_refresh_token_is_reported():
    seen: list[str] = []
    session = FakeSession(
        firestore=lambda m, u, k: (200, {}),
        token_body={"id_token": "id", "refresh_token": "rt-new"},
    )
    client = api.CoopClient(session, "rt-old", on_token_update=seen.append)
    run(client.get_items(LIST))
    assert seen == ["rt-new"] and client.refresh_token == "rt-new"


def test_id_token_of_code_exchange_avoids_second_token_call():
    session = FakeSession()
    client = api.CoopClient(session, "rt", id_token="fresh")
    run(client.get_items(LIST))
    assert session.count(const.OIDC_TOKEN) == 0


def test_concurrent_calls_share_one_sign_in():
    session = FakeSession()
    client = api.CoopClient(session, "rt")

    async def both():
        await asyncio.gather(client.get_items(LIST), client.get_items(LIST))

    run(both())
    assert session.count(const.OIDC_TOKEN) == 1
    assert session.count(const.FIREBASE_SIGN_IN) == 1


# --- reading --------------------------------------------------------------


def test_get_items_parses_paginates_and_skips_stubs():
    pages = {
        "": {
            "documents": [
                _doc("A", _names(de="Milch", fr="Lait"), quantity="2", checked=True),
                _doc("B", _names(de=""), code="1234"),
                {"name": "x/STUB"},
                _doc("C"),
            ],
            "nextPageToken": "p2",
        },
        "p2": {
            "documents": [
                _doc(
                    "D",
                    customProduct={
                        "mapValue": {"fields": {"name": {"stringValue": "Eigenes"}}}
                    },
                ),
                _doc("E", _names(fr="Pain"), quantity="kaputt"),
            ]
        },
    }

    def firestore(method, url, kwargs):
        token = url.split("pageToken=")[1] if "pageToken=" in url else ""
        return 200, pages[token]

    client = api.CoopClient(FakeSession(firestore), "rt")
    items = run(client.get_items(LIST))
    assert [(i.id, i.name, i.quantity, i.checked, i.catalog) for i in items] == [
        ("A", "Milch", 2, True, False),
        ("B", "Coop 1234", 1, False, True),
        ("D", "Eigenes", 1, False, False),
        ("E", "Pain", 1, False, False),
    ]


def test_names_are_normalised_like_the_summary_parser():
    def firestore(method, url, kwargs):
        return 200, {"documents": [_doc("A", _names(de="Milch  Bio 500 g"))]}

    client = api.CoopClient(FakeSession(firestore), "rt")
    assert run(client.get_items(LIST))[0].name == "Milch Bio 500 g"


def test_error_codes_never_carry_free_text():
    assert api._error_code({"error": "invalid_grant"}) == "invalid_grant"
    assert api._error_code({"error": {"message": "INVALID_CUSTOM_TOKEN : x"}}) == (
        "INVALID_CUSTOM_TOKEN"
    )
    assert api._error_code({"error": {"message": "Missing doc projects/p/x/L1"}}) == ""
    assert api._error_code({"error": "some free text"}) == ""


def test_language_preference():
    def firestore(method, url, kwargs):
        return 200, {"documents": [_doc("A", _names(de="Milch", fr="Lait"))]}

    client = api.CoopClient(FakeSession(firestore), "rt", language="fr-CH")
    assert run(client.get_items(LIST))[0].name == "Lait"


def test_firestore_401_is_retried_once_with_a_new_token():
    answers = [(401, {"error": {"status": "UNAUTHENTICATED"}}), (200, {})]
    session = FakeSession(lambda m, u, k: answers.pop(0))
    client = api.CoopClient(session, "rt")
    assert run(client.get_items(LIST)) == []
    assert session.count(const.FIREBASE_SIGN_IN) == 2


def test_firestore_errors_carry_status_only():
    body = {"error": {"status": "PERMISSION_DENIED", "message": f"path {SECRET_MARKER}"}}
    client = api.CoopClient(FakeSession(lambda m, u, k: (403, body)), "rt")
    with pytest.raises(api.CoopApiError) as info:
        run(client.get_items(LIST))
    assert "PERMISSION_DENIED" in str(info.value)
    assert SECRET_MARKER not in str(info.value)


def test_get_lists_reports_query_errors():
    rows = [{"error": {"status": "PERMISSION_DENIED"}}]
    client = api.CoopClient(FakeSession(lambda m, u, k: (200, rows)), "rt")
    with pytest.raises(api.CoopApiError):
        run(client.get_lists())


def test_get_lists():
    doc = {
        "name": "projects/p/databases/(default)/documents/v2_shoppingLists/L1",
        "fields": {
            "data": {"mapValue": {"fields": {"name": {"stringValue": "Einkaufszettel"}}}}
        },
    }
    rows = [{"document": doc}, {"readTime": "x"}]
    client = api.CoopClient(FakeSession(lambda m, u, k: (200, rows)), "rt")
    assert run(client.get_lists()) == [{"id": "L1", "name": "Einkaufszettel"}]


# --- writing --------------------------------------------------------------


def _writes(session):
    return [
        (method, url, kwargs.get("json"))
        for method, url, kwargs in session.calls
        if url.startswith(const.FIRESTORE_BASE)
    ]


def test_add_item_creates_free_text_product_and_touches_list():
    session = FakeSession()
    item_id = run(api.CoopClient(session, "rt").add_item(LIST, "  Brot \n", 3))
    (method, url, doc), (touch_method, touch_url, _) = _writes(session)
    assert method == "POST" and url.endswith(f"documentId={item_id}")
    data = doc["fields"]["data"]["mapValue"]["fields"]
    assert data["name"]["mapValue"]["fields"]["de"] == {"stringValue": "Brot"}
    assert data["coopProduct"]["mapValue"]["fields"]["quantity"] == {"integerValue": "3"}
    assert doc["fields"]["origin"]["mapValue"]["fields"]["createdBy"] == {
        "stringValue": "scid-test"
    }
    assert touch_method == "PATCH" and touch_url.split("?")[0].endswith(LIST)


def test_update_item_uses_mask_and_existence_precondition():
    session = FakeSession()
    client = api.CoopClient(session, "rt")
    run(client.update_item(LIST, "A", quantity=4, checked=True))
    method, url, doc = _writes(session)[0]
    assert method == "PATCH"
    assert "currentDocument.exists=true" in url
    assert "updateMask.fieldPaths=data.coopProduct.quantity" in url
    assert "updateMask.fieldPaths=data.checked" in url
    assert "updateMask.fieldPaths=data.lastCheckedAt" in url
    assert "data.name" not in url
    # like the app: a quantity change marks the product active, and every
    # change carries the product's own modification stamp
    assert "updateMask.fieldPaths=data.status" in url
    assert "updateMask.fieldPaths=activity" in url
    data = doc["fields"]["data"]["mapValue"]["fields"]
    assert set(data) == {"coopProduct", "checked", "lastCheckedAt", "status"}
    activity = doc["fields"]["activity"]["mapValue"]["fields"]
    assert activity["lastModifiedBy"] == {"stringValue": "scid-test"}


def test_update_item_without_changes_sends_nothing():
    session = FakeSession()
    run(api.CoopClient(session, "rt").update_item(LIST, "A"))
    assert session.calls == []


def test_update_of_deleted_item_raises_not_found():
    body = {"error": {"status": "NOT_FOUND"}}
    client = api.CoopClient(FakeSession(lambda m, u, k: (404, body)), "rt")
    with pytest.raises(api.CoopNotFoundError):
        run(client.update_item(LIST, "A", checked=True))


def test_delete_items_ignores_missing_and_touches_once():
    def firestore(method, url, kwargs):
        return (404, {}) if url.endswith("/B") else (200, {})

    session = FakeSession(firestore)
    run(api.CoopClient(session, "rt").delete_items(LIST, ["A", "B", "C"]))
    methods = [method for method, _, _ in _writes(session)]
    assert methods == ["DELETE", "DELETE", "DELETE", "PATCH"]


def test_failing_list_stamp_does_not_fail_the_write():
    def firestore(method, url, kwargs):
        return (403, {}) if method == "PATCH" else (200, {})

    session = FakeSession(firestore)
    assert run(api.CoopClient(session, "rt").add_item(LIST, "Brot"))


def test_empty_name_is_rejected():
    client = api.CoopClient(FakeSession(), "rt")
    with pytest.raises(ValueError):
        run(client.add_item(LIST, "   "))


# --- catalogue products and history ---------------------------------------


def test_inactive_products_are_marked():
    def firestore(method, url, kwargs):
        return 200, {
            "documents": [
                _doc("A", _names(de="Milch"), status={"stringValue": "active"}),
                _doc("B", _names(de="Brie"), code="77", status={"stringValue": "inactive"}),
            ]
        }

    items = run(api.CoopClient(FakeSession(firestore), "rt").get_items(LIST))
    assert [(i.id, i.active, i.code) for i in items] == [("A", True, ""), ("B", False, "77")]


def test_checking_only_does_not_touch_status():
    session = FakeSession()
    run(api.CoopClient(session, "rt").update_item(LIST, "A", checked=True))
    url = _writes(session)[0][1]
    assert "data.status" not in url and "updateMask.fieldPaths=activity" in url


def test_reactivate_puts_product_back_on_the_list():
    session = FakeSession()
    client = api.CoopClient(session, "rt")
    run(client.update_item(LIST, "A", quantity=2, checked=False, reactivate=True))
    _, url, doc = _writes(session)[0]
    data = doc["fields"]["data"]["mapValue"]["fields"]
    assert data["status"] == {"stringValue": "active"}
    assert data["checked"] == {"booleanValue": False}
    assert data["lastCheckedAt"] == {"nullValue": None}
    assert url.count("updateMask.fieldPaths=data.status") == 1


def test_add_product_creates_catalogue_product():
    session = FakeSession()
    product = api.CoopProduct(
        code="6554381", name="Bio Vollmilch", image="https://img/x.jpg", category_id=7
    )
    run(api.CoopClient(session, "rt").add_product(LIST, product, 2))
    data = _writes(session)[0][2]["fields"]["data"]["mapValue"]["fields"]
    assert data["source"] == {"stringValue": "specific-catalog"}
    assert data["productId"] == {"stringValue": "6554381"}
    assert data["categoryId"] == {"integerValue": "7"}
    assert data["status"] == {"stringValue": "active"}
    assert data["name"]["mapValue"]["fields"]["fr"] == {"stringValue": "Bio Vollmilch"}
    assert data["coopProduct"]["mapValue"]["fields"] == {
        "code": {"stringValue": "6554381"},
        "imageUrl": {"stringValue": "https://img/x.jpg"},
        "quantity": {"integerValue": "2"},
    }


def test_free_text_product_keeps_its_source():
    session = FakeSession()
    run(api.CoopClient(session, "rt").add_item(LIST, "Brot"))
    data = _writes(session)[0][2]["fields"]["data"]["mapValue"]["fields"]
    assert data["source"] == {"stringValue": "free-text"}
    assert data["productId"] == {"stringValue": ""}


class SearchSession:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.calls = status, body, []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Response(self.status, self.body)


SEARCH_BODY = {
    "products": [
        {
            "code": "6554381",
            "title": "Bio  Vollmilch",
            "content": "1",
            "contentUnit": "l",
            "matchingWeNeedCategoryId": 7,
            "images": [
                {"url": "https://www.coop.ch/img/produkte/90_90/RGB/6554381_001.jpg"},
                {"url": "//www.coop.ch/img/produkte/310_310/RGB/6554381_001.jpg?_=1"},
            ],
        },
        {"code": "4389992", "title": "Vollmilch", "images": []},
        {"code": "bad code!", "title": "x"},
        {"title": "no code"},
        "garbage",
    ]
}


def test_search_products_parses_results():
    session = SearchSession(body=SEARCH_BODY)
    products = run(api.search_products(session, " bio/milch ", "fr-CH"))
    assert [(p.code, p.name, p.category_id, p.content) for p in products] == [
        ("6554381", "Bio Vollmilch", 7, "1 l"),
        ("4389992", "Vollmilch", 0, ""),
    ]
    assert products[0].image == (
        "https://www.coop.ch/img/produkte/310_310/RGB/6554381_001.jpg?_=1"
    )
    assert products[1].image.endswith("/310_310/RGB/4389992_001.jpg")
    _, url, kwargs = session.calls[0]
    assert url.endswith("/products/search/bio%20milch")
    assert kwargs["params"]["lang"] == "fr"


def test_search_ignores_short_queries_and_reports_errors():
    session = SearchSession(status=500, body={})
    assert run(api.search_products(session, "m")) == []
    assert run(api.search_products(session, "..")) == []
    assert session.calls == []
    with pytest.raises(api.CoopApiError):
        run(api.search_products(session, "milch"))
    assert run(api.search_products(SearchSession(status=404, body={}), "milch")) == []


def test_search_tolerates_unexpected_types():
    body = {"products": [{"code": "1", "title": "Milch", "images": 7}]}
    products = run(api.search_products(SearchSession(body=body), "milch"))
    assert [(p.code, p.name) for p in products] == [("1", "Milch")]
    assert products[0].image.endswith("/310_310/RGB/1_001.jpg")
    assert run(api.search_products(SearchSession(body={"products": 5}), "milch")) == []


def test_get_product_matches_the_exact_code():
    session = SearchSession(body=SEARCH_BODY)
    assert run(api.get_product(session, "4389992")).name == "Vollmilch"
    assert run(api.get_product(session, "999")) is None
    assert run(api.get_product(session, "../evil")) is None
