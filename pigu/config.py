import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = ROOT / "state"
DOCS = ROOT / "docs"
IMG_DIR = DOCS / "img"

PRODUCTS_FILE = DATA / "products.json"
CATEGORIES_FILE = DATA / "categories.json"
TELEGRAM_STATE = STATE / "telegram.json"
FEED_FILE = DOCS / "feed.xml"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

# Public base URL of GitHub Pages (images + feed)
REPO = os.environ.get("GITHUB_REPOSITORY", "iljakurguzov/pigu-feed")
_owner, _name = REPO.split("/", 1)
PAGES_BASE = os.environ.get("PAGES_BASE", f"https://{_owner.lower()}.github.io/{_name}")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
SUPPLIER_PREFIX = os.environ.get("SUPPLIER_PREFIX", "PWM-")
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "8"))
MAX_IMAGES = 6
DEFAULT_DIM = 0.1  # metres / kg when unknown (agreed with the shop owner)

LANGS = ["lt", "lv", "ee", "fi", "ru", "en"]
