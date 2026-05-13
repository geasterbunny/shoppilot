import os

from dotenv import find_dotenv, load_dotenv

ENV_FILE = find_dotenv(usecwd=True)
_loaded = load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shoppilot.db")

MOCK_ETSY = os.getenv("MOCK_ETSY", "false").strip().lower() in ("1", "true", "yes", "on")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ETSY_API_KEY = os.getenv("ETSY_API_KEY", "")
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
