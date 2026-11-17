import requests

from .config import TELEGRAM_TOKEN

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"


def enabled():
    return bool(TELEGRAM_TOKEN)


def call(method, **params):
    r = requests.post(f"{API}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def get_updates(offset):
    return call("getUpdates", offset=offset, timeout=0,
                allowed_updates=["message"])


def send(chat_id, text):
    if not enabled() or not chat_id:
        print("[tg]", text)
        return
    # Telegram limit is 4096 chars
    for i in range(0, len(text), 4000):
        try:
            call("sendMessage", chat_id=chat_id, text=text[i:i + 4000],
                 disable_web_page_preview=True)
        except Exception as e:  # never break the run because of a message
            print("send failed:", e)


def download(file_id):
    info = call("getFile", file_id=file_id)
    r = requests.get(f"{FILE_API}/{info['file_path']}", timeout=120)
    r.raise_for_status()
    return r.content
