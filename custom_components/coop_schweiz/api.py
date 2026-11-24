"""Client for the Coop shopping list (Supercard ID -> Firebase -> Firestore).

This module does not depend on Home Assistant.

Error messages never contain response bodies, tokens, user ids or list ids,
so that they are safe to appear in logs and bug reports.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import aiohttp

from .const import (
    CLIENT_ID,
    CLIENT_SECRET,
    DOMAIN,
    FIREBASE_API_KEY,
    FIREBASE_SIGN_IN,
    FIRESTORE_BASE,
    OIDC_AUTHORIZE,
    OIDC_TOKEN,
    PRODUCT_IMAGE,
    PRODUCT_SEARCH,
    REDIRECT_URI,
    SCOPE,
    TOKEN_BRIDGE,
    VERSION,
)
from .util import clamp_quantity, clean_name

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
LANGUAGES = ("de", "fr", "it", "en")
PAGE_SIZE = 200
MAX_PAGES = 10
TOKEN_MARGIN_SECONDS = 120
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
SOURCE_CATALOG = "specific-catalog"
SEARCH_LIMIT = 12
_CODE = re.compile(r"[A-Za-z0-9_.-]{3,60}")
_UPPER_CODE = re.compile(r"[A-Z0-9_]{3,60}")
_PRODUCT_CODE = re.compile(r"[A-Za-z0-9_-]{1,20}")
# Error codes of the token endpoint that mean "sign in again".
_AUTH_ERROR_CODES = {"invalid_grant", "invalid_ticket", "access_denied"}


class CoopError(Exception):
    """Base class of all errors raised by this module."""


class CoopAuthError(CoopError):
    """The sign-in is no longer valid; the user has to sign in again."""


class CoopApiError(CoopError):
    """The backend answered with an unexpected status or content."""


class CoopConnectionError(CoopApiError):
    """The backend could not be reached (network error or timeout)."""


class CoopNotFoundError(CoopApiError):
    """The addressed item or list does not exist (any more)."""


class CoopInvalidCodeError(CoopError):
    """The pasted address does not contain a usable authorization code."""


class CoopStateError(CoopError):
    """The pasted address belongs to a different sign-in attempt."""


@dataclass(slots=True)
class CoopItem:
    """One product on the shopping list."""

    id: str
    name: str
    quantity: int
    checked: bool
    catalog: bool  # True for products from the Coop catalogue
    code: str = ""  # Coop product number of catalogue products
    active: bool = True  # False: kept by the app as history, not on the list


@dataclass(slots=True)
class CoopProduct:
    """One product of the Coop catalogue (search result)."""

    code: str
    name: str
    image: str = ""
    category_id: int = 0
    content: str = ""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def build_authorize_url() -> tuple[str, str, str]:
    """Return (authorize_url, code_verifier, state) for the sign-in."""
    verifier = _b64url(secrets.token_bytes(40))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_hex(16)
    query = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "source": "app",
    }
    return f"{OIDC_AUTHORIZE}?{urlencode(query)}", verifier, state


def extract_code(pasted: str, expected_state: str | None = None) -> str:
    """Extract the authorization code from the pasted redirect address.

    Accepts the full address (preferred) or the bare code.
    """
    text = (pasted or "").strip()
    if not text:
        raise CoopInvalidCodeError("empty input")
    if "://" not in text and "=" not in text:
        if any(char.isspace() for char in text):
            raise CoopInvalidCodeError("input is neither an address nor a code")
        return text
    parsed = urlparse(text)
    params = parse_qs(parsed.query or parsed.fragment or text)
    if "code" not in params:
        raise CoopInvalidCodeError("address has no code parameter")
    state = params.get("state", [None])[0]
    if expected_state and state and state != expected_state:
        raise CoopStateError("address belongs to another sign-in attempt")
    return params["code"][0]


def _error_code(body: Any) -> str:
    """Return a short machine-readable error code of an error response."""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, str):
        return error if _CODE.fullmatch(error) else ""
    if isinstance(error, dict):
        status = error.get("status")
        if isinstance(status, str) and _CODE.fullmatch(status):
            return status
        message = error.get("message")
        if isinstance(message, str):
            # Identity Toolkit: "CODE" or "CODE : detail". Free text (which
            # could contain document paths) is never passed on.
            head = message.split(":", 1)[0].strip()
            if _UPPER_CODE.fullmatch(head):
                return head
    return ""


def _fields(value: Any) -> dict[str, Any]:
    """Return the fields of a Firestore map value (or of a document)."""
    if not isinstance(value, dict):
        return {}
    if "mapValue" in value:
        value = value["mapValue"]
    fields = value.get("fields") if isinstance(value, dict) else None
    return fields if isinstance(fields, dict) else {}


def _string(value: Any) -> str:
    text = value.get("stringValue") if isinstance(value, dict) else None
    return text.strip() if isinstance(text, str) else ""


def _doc_id(doc: dict[str, Any]) -> str:
    return str(doc.get("name", "")).rsplit("/", 1)[-1]


async def _fetch(
    session: aiohttp.ClientSession, method: str, url: str, **kwargs: Any
) -> tuple[int, Any]:
    """Send a request; return (status, parsed JSON or None)."""
    try:
        async with session.request(
            method, url, timeout=REQUEST_TIMEOUT, **kwargs
        ) as resp:
            status = resp.status
            try:
                body = await resp.json(content_type=None)
            except (ValueError, aiohttp.ClientPayloadError):
                body = None
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CoopConnectionError(
            f"Request failed ({type(err).__name__})"
        ) from err
    return status, body


async def _token_request(
    session: aiohttp.ClientSession, data: dict[str, str]
) -> dict[str, Any]:
    """Call the OIDC token endpoint and classify errors."""
    status, body = await _fetch(session, "POST", OIDC_TOKEN, data=data)
    if status == 200 and isinstance(body, dict) and body.get("id_token"):
        return body
    code = _error_code(body)
    description = ""
    if isinstance(body, dict) and isinstance(body.get("error_description"), str):
        description = body["error_description"]
    if status in (400, 401) and (
        code.lower() in _AUTH_ERROR_CODES or "INVALID_TICKET" in description.upper()
    ):
        raise CoopAuthError(f"Sign-in rejected ({code or 'no error code'})")
    raise CoopApiError(f"Token endpoint: HTTP {status} {code}".strip())


async def exchange_code(
    session: aiohttp.ClientSession, code: str, verifier: str
) -> tuple[str, str]:
    """Exchange the authorization code; return (refresh_token, id_token)."""
    body = await _token_request(
        session,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": verifier,
        },
    )
    refresh_token = body.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CoopApiError("Token endpoint returned no refresh token")
    return refresh_token, body["id_token"]


def _parse_product(raw: Any) -> CoopProduct | None:
    """Convert a search result of the catalogue; None if unusable."""
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip()
    name = clean_name(str(raw.get("title") or raw.get("name") or ""))
    if not _PRODUCT_CODE.fullmatch(code) or not name:
        return None
    image = ""
    images = raw.get("images")
    for entry in images if isinstance(images, list) else []:
        url = entry.get("url") if isinstance(entry, dict) else None
        if isinstance(url, str) and "/310_310/" in url:
            image = url
            break
    if not image:
        image = PRODUCT_IMAGE.format(code=code)
    if image.startswith("//"):
        image = f"https:{image}"
    try:
        category_id = int(raw.get("matchingWeNeedCategoryId") or 0)
    except (TypeError, ValueError):
        category_id = 0
    content = " ".join(
        str(raw.get(key) or "").strip() for key in ("content", "contentUnit")
    ).strip()
    return CoopProduct(
        code=code, name=name, image=image, category_id=category_id, content=content
    )


async def search_products(
    session: aiohttp.ClientSession,
    query: str,
    language: str = "de",
    limit: int = SEARCH_LIMIT,
) -> list[CoopProduct]:
    """Search the Coop catalogue (no sign-in needed)."""
    term = clean_name(query).replace("/", " ").strip()
    # ".." would be normalised away as a path segment: require real text.
    if len(term) < 2 or not any(char.isalnum() for char in term):
        return []
    lang = (language or "de")[:2].lower()
    status, body = await _fetch(
        session,
        "GET",
        PRODUCT_SEARCH.format(term=quote(term, safe="")),
        params={
            "currentPage": "0",
            "pageSize": str(max(1, min(limit, 30))),
            "lang": lang if lang in LANGUAGES else "de",
            "curr": "CHF",
        },
    )
    if status == 404:
        return []
    if status != 200 or not isinstance(body, dict):
        raise CoopApiError(f"Product search: HTTP {status}")
    raw_products = body.get("products")
    products = (
        _parse_product(raw)
        for raw in (raw_products if isinstance(raw_products, list) else [])
    )
    return [product for product in products if product]


async def get_product(
    session: aiohttp.ClientSession, code: str, language: str = "de"
) -> CoopProduct | None:
    """Look up one catalogue product by its product number."""
    code = (code or "").strip()
    if not _PRODUCT_CODE.fullmatch(code):
        return None
    for product in await search_products(session, code, language, limit=5):
        if product.code == code:
            return product
    return None


class CoopClient:
    """Holds the refresh token and talks to Firestore."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        *,
        id_token: str | None = None,
        language: str = "de",
        on_token_update: Callable[[str], None] | None = None,
    ) -> None:
        self._session = session
        self._refresh_token = refresh_token
        self._id_token = id_token  # fresh id_token of the code exchange
        self._on_token_update = on_token_update
        self._lock = asyncio.Lock()
        self._fb_token: str | None = None
        self._fb_expires = 0.0
        self._uid: str | None = None
        language = (language or "de")[:2].lower()
        self._languages = tuple(dict.fromkeys((language, *LANGUAGES)))

    @property
    def refresh_token(self) -> str:
        """Return the current refresh token."""
        return self._refresh_token

    # --- Authentication ---------------------------------------------------

    async def _oidc_id_token(self) -> str:
        if self._id_token:
            id_token, self._id_token = self._id_token, None
            return id_token
        body = await _token_request(
            self._session,
            {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": SCOPE,
            },
        )
        rotated = body.get("refresh_token")
        if isinstance(rotated, str) and rotated and rotated != self._refresh_token:
            self._refresh_token = rotated
            if self._on_token_update:
                self._on_token_update(rotated)
        return body["id_token"]

    async def _ensure_firebase(self) -> str:
        """Return a valid Firebase ID token (cached for about an hour)."""
        async with self._lock:
            if self._fb_token and time.time() < self._fb_expires:
                return self._fb_token
            id_token = await self._oidc_id_token()
            status, body = await _fetch(
                self._session,
                "GET",
                TOKEN_BRIDGE,
                headers={"Authorization": f"Bearer {id_token}"},
            )
            custom = body.get("token") if isinstance(body, dict) else None
            if status != 200 or not isinstance(custom, str) or not custom:
                raise CoopApiError(f"Token bridge: HTTP {status}")
            status, body = await _fetch(
                self._session,
                "POST",
                f"{FIREBASE_SIGN_IN}?key={FIREBASE_API_KEY}",
                json={"token": custom, "returnSecureToken": True},
            )
            token = body.get("idToken") if isinstance(body, dict) else None
            if status != 200 or not isinstance(token, str) or not token:
                raise CoopApiError(
                    f"Firebase sign-in: HTTP {status} {_error_code(body)}".strip()
                )
            uid = self._uid_from_token(token)
            if not uid:
                raise CoopApiError("Firebase sign-in returned no user id")
            try:
                lifetime = int(body.get("expiresIn", 3600))
            except (TypeError, ValueError):
                lifetime = 3600
            self._uid = uid
            self._fb_token = token
            self._fb_expires = time.time() + max(lifetime - TOKEN_MARGIN_SECONDS, 60)
            return token

    @staticmethod
    def _uid_from_token(token: str) -> str | None:
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except (IndexError, ValueError, binascii.Error):
            return None
        uid = claims.get("user_id") or claims.get("sub")
        return uid if isinstance(uid, str) and uid else None

    async def _firestore(
        self, method: str, url: str, what: str, payload: Any = None
    ) -> Any:
        """Send an authenticated Firestore request; retry once on 401."""
        status, body = 0, None
        for attempt in range(2):
            token = await self._ensure_firebase()
            kwargs: dict[str, Any] = {"headers": {"Authorization": f"Bearer {token}"}}
            if payload is not None:
                kwargs["json"] = payload
            status, body = await _fetch(self._session, method, url, **kwargs)
            if status != 401 or attempt:
                break
            self._fb_token = None  # token revoked or clock skew: fetch a new one
        if status == 404:
            raise CoopNotFoundError(f"{what}: not found")
        if status != 200:
            raise CoopApiError(f"{what}: HTTP {status} {_error_code(body)}".strip())
        return body

    # --- Reading ----------------------------------------------------------

    async def get_lists(self) -> list[dict[str, str]]:
        """Return all lists the user owns or participates in."""
        await self._ensure_firebase()
        uid = {"stringValue": self._uid}
        query = {
            "structuredQuery": {
                "from": [{"collectionId": "v2_shoppingLists"}],
                "where": {
                    "compositeFilter": {
                        "op": "OR",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "data.owner"},
                                    "op": "EQUAL",
                                    "value": uid,
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "data.participants"},
                                    "op": "ARRAY_CONTAINS",
                                    "value": uid,
                                }
                            },
                        ],
                    }
                },
                "orderBy": [
                    {
                        "field": {"fieldPath": "activity.lastModifiedAt"},
                        "direction": "DESCENDING",
                    }
                ],
            }
        }
        rows = await self._firestore(
            "POST", f"{FIRESTORE_BASE}:runQuery", "List query", query
        )
        if not isinstance(rows, list):
            raise CoopApiError("List query: unexpected response")
        lists: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if "error" in row:
                raise CoopApiError(f"List query: {_error_code(row)}".strip())
            doc = row.get("document")
            if not isinstance(doc, dict) or not _doc_id(doc):
                continue
            data = _fields(_fields(doc).get("data"))
            lists.append({"id": _doc_id(doc), "name": _string(data.get("name")) or "?"})
        return lists

    async def get_items(self, list_id: str) -> list[CoopItem]:
        """Return all products of a list.

        Includes inactive ones (`active` is False): the app keeps products
        that were removed from the list as history and re-activates them
        when they are added again.
        """
        base = (
            f"{FIRESTORE_BASE}/v2_shoppingLists/{quote(list_id, safe='')}"
            f"/v2_shoppingListProducts?pageSize={PAGE_SIZE}"
        )
        items: list[CoopItem] = []
        page_token = ""
        for _ in range(MAX_PAGES):
            url = f"{base}&pageToken={quote(page_token, safe='')}" if page_token else base
            body = await self._firestore("GET", url, "Loading products")
            if not isinstance(body, dict):
                raise CoopApiError("Loading products: unexpected response")
            for doc in body.get("documents") or []:
                item = self._parse_item(doc)
                if item:
                    items.append(item)
            page_token = body.get("nextPageToken") or ""
            if not page_token:
                break
        else:
            _LOGGER.warning(
                "The list has more than %s products; the rest is not shown",
                PAGE_SIZE * MAX_PAGES,
            )
        return items

    def _parse_item(self, doc: Any) -> CoopItem | None:
        """Convert a Firestore document; return None for unusable documents."""
        if not isinstance(doc, dict):
            return None
        item_id = _doc_id(doc)
        data = _fields(_fields(doc).get("data"))
        if not item_id or not data:
            return None
        product = _fields(data.get("coopProduct"))
        code = _string(product.get("code"))
        names = _fields(data.get("name"))
        name = next(
            (text for lang in self._languages if (text := _string(names.get(lang)))),
            "",
        ) or _string(_fields(data.get("customProduct")).get("name"))
        if not name:
            if not code:
                _LOGGER.debug("Skipping a product without name and product code")
                return None
            name = f"Coop {code}"
        try:
            quantity = clamp_quantity(int(product.get("quantity", {}).get("integerValue", 1)))
        except (AttributeError, TypeError, ValueError):
            quantity = 1
        checked_value = data.get("checked")
        checked = isinstance(checked_value, dict) and checked_value.get("booleanValue") is True
        # Normalised like the summary parser does, so that an unchanged name
        # is recognised as unchanged when the user edits only the quantity.
        return CoopItem(
            id=item_id,
            name=clean_name(name),
            quantity=quantity,
            checked=checked,
            catalog=bool(code),
            code=code,
            active=_string(data.get("status")) != STATUS_INACTIVE,
        )

    # --- Writing ----------------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _source() -> dict[str, Any]:
        return {
            "mapValue": {
                "fields": {
                    "originator": {"stringValue": "coopch"},
                    "platform": {"stringValue": "firebase"},
                    "appVersion": {"stringValue": f"ha-{DOMAIN}-{VERSION}"},
                    "meta": {"stringValue": "homeassistant"},
                }
            }
        }

    def _activity(self) -> dict[str, Any]:
        """Modification stamp of a document, as the app writes it."""
        return {
            "mapValue": {
                "fields": {
                    "lastModifiedAt": {"timestampValue": self._now()},
                    "lastModifiedBy": {"stringValue": self._uid},
                    "source": self._source(),
                }
            }
        }

    def _products_url(self, list_id: str, item_id: str | None = None) -> str:
        url = (
            f"{FIRESTORE_BASE}/v2_shoppingLists/{quote(list_id, safe='')}"
            "/v2_shoppingListProducts"
        )
        return f"{url}/{quote(item_id, safe='')}" if item_id else url

    async def _create_product(
        self,
        list_id: str,
        name: str,
        quantity: int,
        *,
        code: str = "",
        image: str = "",
        category_id: int = 0,
    ) -> str:
        """Create a product document the way the app does; return its id."""
        await self._ensure_firebase()
        item_id = str(uuid.uuid4()).upper()
        names = {lang: {"stringValue": name} for lang in LANGUAGES}
        empty = {lang: {"stringValue": ""} for lang in LANGUAGES}
        doc = {
            "fields": {
                "data": {
                    "mapValue": {
                        "fields": {
                            "name": {"mapValue": {"fields": names}},
                            "checked": {"booleanValue": False},
                            "lastCheckedAt": {"nullValue": None},
                            "shoppingListId": {"stringValue": list_id},
                            "categoryId": {"integerValue": str(category_id)},
                            "coopProduct": {
                                "mapValue": {
                                    "fields": {
                                        "code": {"stringValue": code},
                                        "imageUrl": {"stringValue": image},
                                        "quantity": {
                                            "integerValue": str(clamp_quantity(quantity))
                                        },
                                    }
                                }
                            },
                            "description": {"stringValue": ""},
                            "brands": {"stringValue": ""},
                            "source": {
                                "stringValue": SOURCE_CATALOG if code else "free-text"
                            },
                            "type": {"stringValue": "OTHER"},
                            "status": {"stringValue": STATUS_ACTIVE},
                            "productId": {"stringValue": code},
                            "imageName": {"stringValue": "default"},
                            "popularityIndex": {"integerValue": "999"},
                            "attachmentImage": {"nullValue": None},
                            "keywords": {"mapValue": {"fields": empty}},
                            "synonyms": {"mapValue": {"fields": empty}},
                        }
                    }
                },
                "origin": {
                    "mapValue": {
                        "fields": {
                            "createdAt": {"timestampValue": self._now()},
                            "createdBy": {"stringValue": self._uid},
                            "source": self._source(),
                        }
                    }
                },
                "activity": self._activity(),
            }
        }
        await self._firestore(
            "POST",
            f"{self._products_url(list_id)}?documentId={item_id}",
            "Adding product",
            doc,
        )
        await self.touch_list(list_id)
        return item_id

    async def add_item(self, list_id: str, name: str, quantity: int = 1) -> str:
        """Create a free-text product; return its id."""
        name = clean_name(name)
        if not name:
            raise ValueError("name must not be empty")
        return await self._create_product(list_id, name, quantity)

    async def add_product(
        self, list_id: str, product: CoopProduct, quantity: int = 1
    ) -> str:
        """Create a product of the Coop catalogue; return its id.

        Such products carry the Coop product number, so the app and the
        self-scanner know exactly which product is meant.
        """
        return await self._create_product(
            list_id,
            product.name,
            quantity,
            code=product.code,
            image=product.image,
            category_id=product.category_id,
        )

    async def update_item(
        self,
        list_id: str,
        item_id: str,
        *,
        name: str | None = None,
        quantity: int | None = None,
        checked: bool | None = None,
        reactivate: bool = False,
    ) -> None:
        """Change name, quantity and/or checked state of an existing product.

        `reactivate` puts a product back on the list that the app keeps only
        as history. Raises CoopNotFoundError if the product was deleted in
        the meantime.
        """
        data: dict[str, Any] = {}
        mask: list[str] = []
        if name is not None:
            name = clean_name(name)
            if not name:
                raise ValueError("name must not be empty")
            names = {lang: {"stringValue": name} for lang in LANGUAGES}
            data["name"] = {"mapValue": {"fields": names}}
            mask.append("data.name")
        if quantity is not None:
            data["coopProduct"] = {
                "mapValue": {
                    "fields": {
                        "quantity": {"integerValue": str(clamp_quantity(quantity))}
                    }
                }
            }
            mask.append("data.coopProduct.quantity")
        if checked is not None:
            data["checked"] = {"booleanValue": checked}
            data["lastCheckedAt"] = (
                {"timestampValue": self._now()} if checked else {"nullValue": None}
            )
            mask += ["data.checked", "data.lastCheckedAt"]
        if reactivate or quantity is not None:
            # Like the app: a quantity change also marks the product active.
            data["status"] = {"stringValue": STATUS_ACTIVE}
            mask.append("data.status")
        if not mask:
            return
        await self._ensure_firebase()
        mask.append("activity")
        query = "&".join(f"updateMask.fieldPaths={path}" for path in mask)
        # The precondition prevents creating a stub document when the product
        # was deleted in the app since the last refresh.
        await self._firestore(
            "PATCH",
            f"{self._products_url(list_id, item_id)}?{query}&currentDocument.exists=true",
            "Updating product",
            {
                "fields": {
                    "data": {"mapValue": {"fields": data}},
                    "activity": self._activity(),
                }
            },
        )
        await self.touch_list(list_id)

    async def delete_items(self, list_id: str, item_ids: list[str]) -> None:
        """Delete products; products that are already gone are ignored."""
        try:
            for item_id in item_ids:
                try:
                    await self._firestore(
                        "DELETE",
                        self._products_url(list_id, item_id),
                        "Deleting product",
                    )
                except CoopNotFoundError:
                    continue
        finally:
            await self.touch_list(list_id)

    async def touch_list(self, list_id: str) -> None:
        """Update the list's modification stamp so other devices sync.

        Best effort: the product change itself has already succeeded.
        """
        patch = {
            "fields": {
                "activity": {
                    "mapValue": {
                        "fields": {
                            "lastModifiedAt": {"timestampValue": self._now()},
                            "lastModifiedBy": {"stringValue": self._uid},
                            "source": self._source(),
                        }
                    }
                }
            }
        }
        url = (
            f"{FIRESTORE_BASE}/v2_shoppingLists/{quote(list_id, safe='')}"
            "?updateMask.fieldPaths=activity.lastModifiedAt"
            "&updateMask.fieldPaths=activity.lastModifiedBy"
            "&updateMask.fieldPaths=activity.source"
            "&currentDocument.exists=true"
        )
        try:
            await self._firestore("PATCH", url, "Updating list stamp", patch)
        except CoopError as err:
            _LOGGER.debug("Could not update the list's modification stamp: %s", err)
