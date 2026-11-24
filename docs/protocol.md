# How the integration talks to the Coop backend

These notes describe the interface as far as the integration uses it. They
were gathered for interoperability with the Coop app (version 1.19.1,
November 2026). Nothing here is official or guaranteed to stay as it is.

## 1. Sign-in: Supercard ID (OpenID Connect)

- Authorization code flow with PKCE (S256).
- Authorize: `https://login.supercard.ch/cas/oidc/authorize` (with `source=app`)
- Token: `https://login.supercard.ch/cas/oidc/token`
- Client `api.coop.ch`, scope `openid coopApp`, fixed redirect address of the
  app (see `const.py`).
- The authorization code is single-use and only valid for a short time.
- The token response contains a `refresh_token` (not observed to rotate; the
  client handles rotation anyway) and an `id_token` (JWT). The `id_token` is
  used as bearer token in step 2.

## 2. Bridge to Firebase

`GET https://www.coop.ch/rest/v2/coopathome/firebase/shoppinglist-token` with
`Authorization: Bearer <id_token>` returns a Firebase custom token.

## 3. Firebase sign-in

`POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken`
with the custom token returns a Firebase ID token (valid for about an hour).
Its `user_id` claim is the user id used in Firestore.

## 4. Firestore

REST API `firestore.googleapis.com/v1`, project of the shopping list.

- **Lists:** `:runQuery` on collection `v2_shoppingLists` with
  `data.owner == uid OR data.participants array-contains uid`, ordered by
  `activity.lastModifiedAt` descending. Other queries are rejected.
- **Products:** subcollection
  `v2_shoppingLists/{listId}/v2_shoppingListProducts` (paged `GET`).
- **Create:** `POST …?documentId=<upper-case UUID>`.
- **Change:** `PATCH` with `updateMask.fieldPaths=…` and
  `currentDocument.exists=true`, so that a product deleted in the meantime is
  not re-created as an incomplete document.
- **Delete:** `DELETE`.
- Every change of a product also writes the product's own `activity`
  (last modified at/by, source), as the app does.
- After every change the list's `activity.lastModifiedAt` is updated so that
  other devices sync.

### Product document (`data`)

| Field | Meaning |
|---|---|
| `name` | Map of names per language (`de`, `fr`, `it`, `en`) |
| `coopProduct` | `code` (catalogue number, empty for free text), `imageUrl`, `quantity` |
| `checked`, `lastCheckedAt` | Checked state and time |
| `source` | `free-text` for typed products, `specific-catalog` for products of the Coop catalogue |
| `productId` | Coop product number for catalogue products, empty for free text |
| `status` | `active`: on the list. `inactive`: kept by the app as history only (quantity 0); not shown by the integration and re-activated when the product is added again |
| `type` | `OTHER` |
| others | `shoppingListId`, `categoryId`, `popularityIndex`, `imageName`, `description`, `brands`, `keywords`, `synonyms` |

Beside `data`, each document has `origin` (created at/by, source) and
`activity` (last modified at/by, source). Products written by this
integration identify themselves in `source` as `homeassistant`.

## 5. Product catalogue

`GET https://www.coop.ch/rest/v2/coopathome/products/search/<term>` with
`currentPage`, `pageSize`, `lang`, `curr=CHF`. No sign-in. Each result has
`code` (product number), `title`, `images` and `matchingWeNeedCategoryId`
(the category used on the list). Searching for a product number returns
that product. The integration searches when the user types in the card
(at least two characters, 0.4 s after the last keystroke) and when
`coop_schweiz.add_product` is called with a product number that is
neither on the list nor in the cache. Answers are cached for 10 minutes.

## Load on the backend

One request every 5 minutes per list (one more for every further 200
products), plus three requests about once an hour to renew the Firebase
token. Every change made in Home Assistant costs one request per changed
product, one for the list's stamp and one reload of the list. The product
search sends at most one request per typing pause in the card and one when
`coop_schweiz.add_product` gets an unknown product number; repeated terms are
answered from the cache for 10 minutes. On errors the polling interval grows
up to one hour. An invalid sign-in stops polling until the user signs in
again.
