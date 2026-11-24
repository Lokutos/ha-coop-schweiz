"""Constants for the Coop shopping list integration.

The OIDC and Firebase values below are fixed values of the publicly
distributed Coop app. They are identical for every installation and are not
personal secrets. A Firebase web API key only identifies the project, see
https://firebase.google.com/docs/projects/api-keys.

The only personal credential is the user's refresh token. It is stored in the
config entry, which Home Assistant keeps unencrypted in `.storage` (and
therefore in backups).
"""

DOMAIN = "coop_schweiz"
VERSION = "0.2.3"  # keep in sync with manifest.json

# Supercard ID (CAS / OpenID Connect)
OIDC_AUTHORIZE = "https://login.supercard.ch/cas/oidc/authorize"
OIDC_TOKEN = "https://login.supercard.ch/cas/oidc/token"
CLIENT_ID = "api.coop.ch"
CLIENT_SECRET = "AE2DASE-3e3aws-asFFFF-72we5baequp83aeefKk321"
SCOPE = "openid coopApp"
REDIRECT_URI = (
    "https://api.coop.ch/auth-redirects/api/v1/public/auth-redirects/"
    "post-authorize/redirect?language=de"
)

# Bridge from the Coop backend to a Firebase custom token
TOKEN_BRIDGE = "https://www.coop.ch/rest/v2/coopathome/firebase/shoppinglist-token"

# Firebase / Firestore project of the shopping list
FIREBASE_API_KEY = "AIzaSyC-xCc41xfBqInud6rCYC27OGQqcANk5jg"
FIREBASE_SIGN_IN = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
)
FIRESTORE_BASE = (
    "https://firestore.googleapis.com/v1/projects/"
    "coop-shoppinglist-prod1/databases/(default)/documents"
)

# Product catalogue of the Coop app (no sign-in needed)
PRODUCT_SEARCH = "https://www.coop.ch/rest/v2/coopathome/products/search/{term}"
PRODUCT_IMAGE = "https://www.coop.ch/img/produkte/310_310/RGB/{code}_001.jpg"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_LIST_ID = "list_id"
CONF_LIST_NAME = "list_name"
CONF_REDIRECT_URL = "redirect_url"

SERVICE_ADD_PRODUCT = "add_product"
DATA_PRODUCTS = "products"
DATA_SEARCHES = "searches"
SEARCH_CACHE_SECONDS = 600

# Dashboard card served by the integration
CARD_FILE = "coop-schweiz-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"

SCAN_INTERVAL_SECONDS = 300
MAX_BACKOFF_SECONDS = 3600
