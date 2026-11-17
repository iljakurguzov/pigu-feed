import json
from datetime import datetime, timezone

from .config import CATEGORIES_FILE, PRODUCTS_FILE, TELEGRAM_STATE


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def load_products():
    return _load(PRODUCTS_FILE, {})


def save_products(p):
    _save(PRODUCTS_FILE, p)


def load_tg_state():
    return _load(TELEGRAM_STATE, {"offset": 0, "owner": None, "heartbeat": None})


def save_tg_state(s):
    _save(TELEGRAM_STATE, s)


_cats = None


def categories():
    global _cats
    if _cats is None:
        _cats = _load(CATEGORIES_FILE, {})
    return _cats
