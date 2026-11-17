"""One run: read Telegram -> process queued EANs -> rebuild feed.xml.

Started by GitHub Actions every few minutes (see .github/workflows/run.yml).
"""
import html
import re
import traceback
from datetime import datetime, timedelta, timezone

from . import ean as eanlib
from . import feed, images, research, telegram
from .config import (DEFAULT_DIM, DOCS, MAX_PER_RUN, PAGES_BASE, SUPPLIER_PREFIX,
                     TELEGRAM_ALLOWED_CHAT_ID)
from .store import (categories, load_products, load_tg_state, now, save_products,
                    save_tg_state)

FEED_URL = f"{PAGES_BASE}/feed.xml"

HELP = f"""Бот магазина Play with me для Pigu.

Как добавить товар:
• пришлите EAN (можно сразу много, через пробел или с новой строки)
• или фото штрихкода
• или .txt/.csv файл со списком EAN

Товары обрабатываются в течение ~5–15 минут, потом придёт отчёт.

Команды:
/status — сводка
/list — все товары
/info EAN — подробно о товаре
/set EAN weight 0.45 — вес, кг (также length / height / width в метрах)
/set EAN category 10669 — сменить категорию Pigu (тексты перепишутся)
/set EAN manufacturer Название | Адрес | e-mail
/set EAN rep Название | Адрес | e-mail — представитель в ЕС
/redo EAN — найти товар заново
/delete EAN — удалить товар из фида
Фото с подписью EAN — добавить своё фото к товару.

Ссылка на фид для PMP:
{FEED_URL}"""

PKG_FIELDS = {"weight": "weight", "вес": "weight", "length": "length", "длина": "length",
              "height": "height", "высота": "height", "width": "width", "ширина": "width"}


# ---------------------------------------------------------------- Telegram

def handle_updates(state, products):
    if not telegram.enabled():
        print("TELEGRAM_BOT_TOKEN not set — skipping Telegram")
        return
    updates = telegram.get_updates(state.get("offset", 0))
    for u in updates:
        state["offset"] = u["update_id"] + 1
        msg = u.get("message")
        if not msg:
            continue
        chat = msg["chat"]["id"]
        owner = TELEGRAM_ALLOWED_CHAT_ID or state.get("owner")
        if not owner:
            state["owner"] = chat
            owner = chat
            telegram.send(chat, "Вы назначены владельцем бота.\n\n" + HELP)
            continue
        if str(chat) != str(owner):
            telegram.send(chat, "Это частный бот.")
            continue
        try:
            handle_message(msg, chat, products)
        except Exception as e:
            traceback.print_exc()
            telegram.send(chat, f"Ошибка при обработке сообщения: {e}")


def queue(products, codes, chat, mode="queued"):
    added, existed = [], []
    for c in codes:
        if c in products and mode == "queued" and products[c].get("status") != "disabled":
            existed.append(c)
            continue
        p = products.get(c, {"ean": c, "created": now(), "images": []})
        p.update({"ean": c, "status": mode, "supplier_code": p.get("supplier_code") or SUPPLIER_PREFIX + c,
                  "updated": now()})
        products[c] = p
        added.append(c)
    waiting = sum(1 for p in products.values() if p.get("status") in ("queued", "rewrite"))
    out = []
    if added:
        out.append(f"Принято в обработку: {len(added)}. Всего в очереди: {waiting}.")
    if existed:
        out.append("Уже есть: " + ", ".join(existed) + "\n(чтобы найти заново — /redo EAN)")
    return "\n".join(out)


def handle_message(msg, chat, products):
    text = (msg.get("text") or msg.get("caption") or "").strip()

    if msg.get("photo"):
        raw = telegram.download(msg["photo"][-1]["file_id"])
        codes, _ = eanlib.find(text)
        if codes and codes[0] in products:  # own photo for an existing product
            p = products[codes[0]]
            p["images"] = images.save_upload(codes[0], raw, p.get("images", []))
            p["updated"] = now()
            telegram.send(chat, f"Фото добавлено к {codes[0]} (всего фото: {len(p['images'])}).")
            return
        found = decode_barcodes(raw)
        if not found:
            telegram.send(chat, "Не смог прочитать штрихкод на фото. Пришлите EAN цифрами "
                                "или фото поближе и ровнее.")
            return
        telegram.send(chat, "Штрихкод: " + ", ".join(found) + "\n" + queue(products, found, chat))
        return

    if msg.get("document"):
        doc = msg["document"]
        name = (doc.get("file_name") or "").lower()
        if name.endswith((".txt", ".csv")) or (doc.get("mime_type") or "").startswith("text/"):
            raw = telegram.download(doc["file_id"]).decode("utf-8", "ignore")
            ok, bad = eanlib.find(raw)
            reply = queue(products, ok, chat) if ok else "В файле не найдено EAN."
            if bad:
                reply += f"\nНекорректные коды ({len(bad)}): " + ", ".join(bad[:30])
            telegram.send(chat, reply)
        else:
            telegram.send(chat, "Пришлите список EAN в .txt или .csv файле.")
        return

    if text.startswith("/"):
        return command(text, chat, products)

    ok, bad = eanlib.find(text)
    if not ok and not bad:
        telegram.send(chat, "Пришлите EAN товара (11–13 цифр). /help — справка.")
        return
    reply = queue(products, ok, chat) if ok else ""
    if bad:
        reply += "\nНекорректный EAN (не сходится контрольная цифра): " + ", ".join(bad)
    telegram.send(chat, reply.strip())


def decode_barcodes(raw):
    try:
        import io

        from PIL import Image
        from pyzbar.pyzbar import decode
    except Exception as e:
        print("pyzbar not available:", e)
        return []
    im = Image.open(io.BytesIO(raw))
    codes = []
    for variant in (im, im.convert("L"), im.rotate(90, expand=True)):
        for d in decode(variant):
            c = eanlib.normalize(d.data.decode("ascii", "ignore"))
            if eanlib.valid(c) and c not in codes:
                codes.append(c)
        if codes:
            break
    return codes


def command(text, chat, products):
    parts = text.split(maxsplit=3)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        return telegram.send(chat, HELP)
    if cmd == "/feed":
        return telegram.send(chat, FEED_URL)
    if cmd == "/status":
        return telegram.send(chat, status_text(products))
    if cmd == "/list":
        if not products:
            return telegram.send(chat, "Товаров пока нет.")
        lines = [f"{icon(p)} {e} — {short_title(p)}" for e, p in sorted(products.items())]
        return telegram.send(chat, "\n".join(lines))

    code = eanlib.normalize(arg) if arg else ""
    if cmd in ("/info", "/redo", "/delete", "/set") and code not in products:
        return telegram.send(chat, f"Товар {code or '(EAN не указан)'} не найден. /list — список.")

    if cmd == "/info":
        return telegram.send(chat, report(products[code], full=True))
    if cmd == "/redo":
        return telegram.send(chat, queue(products, [code], chat, mode="queued_redo").replace(
            "Принято в обработку", "Будет найден заново"))
    if cmd == "/delete":
        products[code]["status"] = "disabled"
        products[code]["updated"] = now()
        return telegram.send(chat, f"{code} убран из фида. Вернуть: /redo {code}")
    if cmd == "/set":
        if len(parts) < 4:
            return telegram.send(chat, "Формат: /set EAN поле значение. /help — примеры.")
        return telegram.send(chat, set_field(products[code], parts[2].lower(), parts[3].strip()))
    telegram.send(chat, "Неизвестная команда. /help — справка.")


def set_field(p, field, value):
    p["updated"] = now()
    if field in PKG_FIELDS:
        try:
            v = float(value.replace(",", "."))
        except ValueError:
            return "Нужно число, например 0.35"
        if v <= 0:
            return "Значение должно быть больше 0."
        key = PKG_FIELDS[field]
        p.setdefault("package", {})[key] = v
        p["defaults_used"] = [d for d in p.get("defaults_used", []) if d != key]
        refresh_issues(p)
        return f"{p['ean']}: {key} = {v}"
    if field in ("category", "категория"):
        if value not in categories():
            return "Нет такой категории Pigu. ID можно найти в таблице Categories_fields_and_values."
        p["category_id"] = value
        p["status"] = "rewrite"
        return f"Категория изменена на {feed.category_name(value)}. Тексты и атрибуты обновятся в следующем запуске."
    if field in ("manufacturer", "производитель", "rep", "представитель"):
        bits = [b.strip() for b in value.split("|")]
        bits += [None] * (3 - len(bits))
        key = "manufacturer" if field in ("manufacturer", "производитель") else "representative"
        p[key] = {"name": bits[0], "address": bits[1], "email": bits[2]}
        refresh_issues(p)
        return f"{p['ean']}: {key} сохранён."
    if field in ("supplier", "sku", "артикул"):
        p["supplier_code"] = value
        return f"{p['ean']}: артикул = {value}"
    return "Поле не поддерживается: weight, length, height, width, category, manufacturer, rep, sku"


# ---------------------------------------------------------------- processing

def process_queue(products, chat):
    todo = [e for e, p in products.items() if p.get("status") in ("queued", "queued_redo", "rewrite")]
    for code in todo[:MAX_PER_RUN]:
        p = products[code]
        try:
            if p["status"] in ("queued", "queued_redo"):
                full_process(p)
            else:
                rewrite(p)
        except Exception as e:
            traceback.print_exc()
            p["status"] = "error"
            p["issues"] = [f"Ошибка: {e}"]
        p["updated"] = now()
        save_products(products)  # keep progress even if the job is killed later
        telegram.send(chat, report(p))
    left = len(todo) - min(len(todo), MAX_PER_RUN)
    if left:
        telegram.send(chat, f"В очереди ещё {left} — продолжу в следующем запуске.")


def full_process(p):
    code = p["ean"]
    facts = research.research(code)
    p["facts"] = facts
    p["sources"] = facts.get("sources", [])
    if not facts.get("found"):
        p["status"] = "not_found"
        p["issues"] = [facts.get("notes") or "Товар с таким EAN не найден в интернете."]
        return
    p["category_id"] = facts.get("category_id")
    pk = facts.get("package") or {}
    p["package"], p["defaults_used"] = {}, []
    for key, src in (("weight", "weight_kg"), ("length", "length_m"), ("height", "height_m"), ("width", "width_m")):
        v = pk.get(src)
        if isinstance(v, (int, float)) and v > 0:
            p["package"][key] = round(float(v), 3)
        else:
            p["package"][key] = DEFAULT_DIM
            p["defaults_used"].append(key)
    p["manufacturer"] = facts.get("manufacturer") or {}
    p["representative"] = facts.get("eu_representative") or {}
    if facts.get("model"):
        p["manufacturer_code"] = facts["model"]
    images.delete(code)
    p["images"], p["image_errors"] = images.process(code, facts.get("image_urls") or [])
    if p.get("category_id"):
        rewrite(p)
    else:
        p["status"] = "needs_attention"
        refresh_issues(p)


def rewrite(p):
    w = research.write(p.get("facts") or {}, p["category_id"])
    p["titles"], p["descriptions"], p["properties"] = w["titles"], w["descriptions"], w["properties"]
    refresh_issues(p)


def refresh_issues(p):
    issues = []
    if p.get("status") in ("not_found", "error", "disabled"):
        return
    blocking = feed.problems(p)
    issues += blocking
    if p.get("defaults_used"):
        issues.append("размеры/вес по умолчанию 0.1: " + ", ".join(p["defaults_used"]))
    m = p.get("manufacturer") or {}
    if not all(m.get(k) for k in ("name", "address", "email")):
        issues.append("неполные данные производителя (нужны для активации)")
    miss = research.missing_mandatory(p.get("properties") or [], p.get("category_id"))
    if miss:
        issues.append("не заполнены обязательные атрибуты: " + ", ".join(miss))
    if len(p.get("images") or []) == 1:
        issues.append("только 1 фото")
    if (p.get("facts") or {}).get("confidence") == "low":
        issues.append("низкая уверенность, что найден именно этот товар — проверьте")
    p["issues"] = issues
    p["status"] = "needs_attention" if blocking else ("ready" if not issues else "ready_warn")


# ---------------------------------------------------------------- reporting

def icon(p):
    return {"ready": "✅", "ready_warn": "🟡", "needs_attention": "⚠️", "not_found": "❓",
            "error": "❌", "disabled": "🚫"}.get(p.get("status"), "⏳")


def short_title(p):
    t = p.get("titles") or {}
    return (t.get("ee") or t.get("en") or (p.get("facts") or {}).get("product_name_en") or "—")[:70]


def report(p, full=False):
    code = p["ean"]
    lines = [f"{icon(p)} {code} — {short_title(p)}"]
    st = p.get("status")
    if st == "not_found":
        lines.append("Не найден. " + "; ".join(p.get("issues") or []))
        lines.append(f"Если знаете название — пришлите его, или /delete {code}")
        return "\n".join(lines)
    if st == "error":
        lines.append("; ".join(p.get("issues") or []))
        lines.append(f"Попробовать снова: /redo {code}")
        return "\n".join(lines)
    if p.get("category_id") and str(p["category_id"]) in categories():
        lines.append(f"Категория: {feed.category_name(p['category_id'])} ({p['category_id']})")
    pk = p.get("package") or {}
    lines.append(f"Фото: {len(p.get('images') or [])} | Вес {pk.get('weight')} кг | "
                 f"{pk.get('length')}×{pk.get('width')}×{pk.get('height')} м")
    if st in ("ready", "ready_warn"):
        lines.append("В фиде ✔")
    if p.get("issues"):
        lines.append("Проверить:\n• " + "\n• ".join(p["issues"]))
    if p.get("defaults_used"):
        lines.append(f"Пример: /set {code} weight 0.45")
    if full:
        m = p.get("manufacturer") or {}
        r = p.get("representative") or {}
        lines.append(f"Производитель: {m.get('name')} | {m.get('address')} | {m.get('email')}")
        lines.append(f"Представитель ЕС: {r.get('name')} | {r.get('address')} | {r.get('email')}")
        for pr in p.get("properties") or []:
            lines.append(f"  {pr['id']}: {', '.join(pr['values'])}")
        lines += ["Фото:"] + [f"  {u}" for u in p.get("images") or []]
        if p.get("sources"):
            lines += ["Источники:"] + [f"  {u}" for u in p["sources"][:5]]
    return "\n".join(lines)


def status_text(products):
    c = {}
    for p in products.values():
        c[p.get("status")] = c.get(p.get("status"), 0) + 1
    return (f"В фиде: {c.get('ready', 0) + c.get('ready_warn', 0)} "
            f"(из них с замечаниями: {c.get('ready_warn', 0)})\n"
            f"Требуют внимания (не в фиде): {c.get('needs_attention', 0)}\n"
            f"Не найдены: {c.get('not_found', 0)} | Ошибки: {c.get('error', 0)} | Удалены: {c.get('disabled', 0)}\n"
            f"В очереди: {c.get('queued', 0) + c.get('queued_redo', 0) + c.get('rewrite', 0)}\n\n"
            f"Фид: {FEED_URL}")


def write_index(products, included):
    rows = []
    for e, p in sorted(products.items()):
        rows.append(f"<tr><td>{icon(p)}</td><td>{e}</td><td>{html.escape(short_title(p))}</td>"
                    f"<td>{html.escape('; '.join(p.get('issues') or []))}</td></tr>")
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Play with me — Pigu feed</title>
<style>body{{font:14px system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #ddd;padding:6px;vertical-align:top}}</style>
</head><body><h1>Play with me — Pigu feed</h1>
<p>Feed: <a href="feed.xml">{FEED_URL}</a> · products in feed: {len(included)} · updated {now()}</p>
<table>{''.join(rows)}</table></body></html>"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")


def heartbeat(state):
    """GitHub disables scheduled workflows after 60 days without commits."""
    last = state.get("heartbeat")
    t = datetime.now(timezone.utc)
    if not last or t - datetime.fromisoformat(last.replace("Z", "+00:00")) > timedelta(days=20):
        state["heartbeat"] = now()


def main():
    state = load_tg_state()
    products = load_products()
    chat = TELEGRAM_ALLOWED_CHAT_ID or state.get("owner")
    try:
        handle_updates(state, products)
    finally:
        save_tg_state(state)  # never re-process the same Telegram messages
        save_products(products)
    chat = TELEGRAM_ALLOWED_CHAT_ID or state.get("owner") or chat
    process_queue(products, chat)
    included, skipped = feed.build(products)
    write_index(products, included)
    heartbeat(state)
    save_tg_state(state)
    save_products(products)
    print(f"feed: {len(included)} products, skipped {len(skipped)}")


if __name__ == "__main__":
    main()
