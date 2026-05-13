import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shoppilot.db")

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
