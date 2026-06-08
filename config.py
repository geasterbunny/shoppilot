import os
import sys

# Use the OS (Windows) trust store for TLS instead of certifi's bundled CAs.
# This machine sits behind a TLS-inspecting proxy/AV whose root CA is installed
# in the Windows certificate store but NOT in certifi — so httpx/anthropic calls
# fail with CERTIFICATE_VERIFY_FAILED. Injecting truststore early (before any
# HTTP client is constructed) makes every SSL connection trust the OS store.
import truststore

if sys.platform == "win32":
    truststore.inject_into_ssl()

from dotenv import find_dotenv, load_dotenv

ENV_FILE = find_dotenv(usecwd=True)
# override=True so values in .env win over variables already present (possibly
# empty) in the inherited shell environment — e.g. a blank ANTHROPIC_API_KEY
# exported by the parent process would otherwise shadow the real key here.
_loaded = load_dotenv(ENV_FILE, override=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shoppilot.db")

MOCK_ETSY = os.getenv("MOCK_ETSY", "false").strip().lower() in ("1", "true", "yes", "on")
MOCK_PRINTIFY = os.getenv("MOCK_PRINTIFY", "true").strip().lower() in ("1", "true", "yes", "on")
MOCK_POSTIZ = os.getenv("MOCK_POSTIZ", "true").strip().lower() in ("1", "true", "yes", "on")
MOCK_DESIGN = os.getenv("MOCK_DESIGN", "true").strip().lower() in ("1", "true", "yes", "on")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
IDEOGRAM_API_KEY = os.getenv("IDEOGRAM_API_KEY", "")
HF_API_KEY = os.getenv("HF_API_KEY", "")

ETSY_API_KEY = os.getenv("ETSY_API_KEY", "")
# Etsy's developer portal calls this the "Shared Secret". It's a SEPARATE value
# from the keystring (ETSY_API_KEY) — fetch from the eye-reveal in the dashboard.
# Used as the value for the x-api-key header on authenticated v3 API calls.
# Etsy's keystring is only used as the OAuth client_id; live API calls reject it
# in x-api-key with "API key not found or not active, or incorrect shared secret".
ETSY_SHARED_SECRET = os.getenv("ETSY_SHARED_SECRET", "")
ETSY_SHOP_ID = os.getenv("ETSY_SHOP_ID", "")
ETSY_ACCESS_TOKEN = os.getenv("ETSY_ACCESS_TOKEN", "")
ETSY_REFRESH_TOKEN = os.getenv("ETSY_REFRESH_TOKEN", "")
ETSY_REDIRECT_URI = os.getenv(
    "ETSY_REDIRECT_URI", "http://127.0.0.1:8000/auth/etsy/callback"
)

PRINTIFY_API_KEY = os.getenv("PRINTIFY_API_KEY", "")
PRINTIFY_SHOP_ID = os.getenv("PRINTIFY_SHOP_ID", "")

POSTIZ_API_KEY = os.getenv("POSTIZ_API_KEY", "")
POSTIZ_URL = os.getenv("POSTIZ_URL", "")

# Gmail SMTP credentials for post-design notification emails. NOTIFICATION_EMAIL
# is the sending Gmail account (also used as the From address); SMTP_PASSWORD is
# its app password. Both empty by default — notifications are skipped if unset.
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")
# Optional explicit From address; falls back to NOTIFICATION_EMAIL when empty.
SMTP_FROM = os.getenv("SMTP_FROM", "")


def _mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


print(f"[config] .env resolved: {ENV_FILE!r}  (cwd={os.getcwd()})")
print(f"[config] .env loaded:   {_loaded}")
print(f"[config] MOCK_ETSY raw: {os.getenv('MOCK_ETSY')!r}  parsed: {MOCK_ETSY}")
print(f"[config] ETSY_API_KEY:  {_mask(ETSY_API_KEY)}")
