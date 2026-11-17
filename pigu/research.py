"""Find product data by EAN and write Pigu listing texts with Claude.

Step 1 (research): Claude + web search -> facts, photo URLs, Pigu category.
Step 2 (write):    Claude -> titles/descriptions in 6 languages + category
                   attributes, restricted to Pigu's allowed values.
"""
import json
import re

import anthropic

from .config import ANTHROPIC_API_KEY, LANGS, MODEL
from .store import categories

_client = None


def client():
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY secret is not set")
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
    return _client


def _category_list():
    lines = [f"{cid} | {c['top_en']} > {c['title_en']}" for cid, c in categories().items()]
    return "\n".join(lines)


def _extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _text(resp):
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


RESEARCH_SYSTEM = """You research products for a marketplace listing (Pigu / Kaup24 / PHH Group, Baltic states).
The seller gives you an EAN/GTIN barcode. Use web search to identify the EXACT product with this barcode.
Search the barcode number itself first, then brand + model to collect details.

Rules:
- Never guess. If you cannot confirm which product has this barcode, return "found": false.
- Package dimensions/weight: only if a source states them (packaged/box size preferred). Convert to metres and kg. Otherwise null.
- image_urls: up to 8 DIRECT image file URLs (ending .jpg/.jpeg/.png/.webp or clearly an image CDN URL) of this exact product, largest available,
  prefer the manufacturer or big retailers; first one should be the product on a white/neutral background. No logos, no banners.
- Manufacturer: legal name, postal address, contact e-mail as published by the brand (EU GPSR "manufacturer" info). null if not found.
- EU representative: only if the manufacturer is outside the EU and a source names an EU importer/representative; otherwise null.
- category_id: choose the single most specific matching id from the Pigu category list below.

Answer with ONE JSON object in a ```json block and nothing after it:
{
 "found": true|false,
 "confidence": "high"|"medium"|"low",
 "product_name_en": str, "brand": str|null, "model": str|null,
 "manufacturer": {"name": str|null, "address": str|null, "email": str|null},
 "eu_representative": {"name": str|null, "address": str|null, "email": str|null},
 "facts_en": [str, ...],            // concrete features, contents, materials, sizes, batteries etc.
 "age_from": number|null, "material": str|null, "country_of_origin": str|null, "colour": str|null,
 "package": {"weight_kg": number|null, "length_m": number|null, "height_m": number|null, "width_m": number|null},
 "image_urls": [str, ...],
 "category_id": str,
 "sources": [str, ...],
 "notes": str|null
}

Pigu categories (id | top category > category):
"""


def research(ean):
    system = [{"type": "text", "text": RESEARCH_SYSTEM + _category_list(),
               "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": f"EAN: {ean}"}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]
    for _ in range(4):  # server-side tool loop may pause
        resp = client().messages.create(model=MODEL, max_tokens=8000, system=system,
                                        tools=tools, messages=messages)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    data = _extract_json(_text(resp))
    if str(data.get("category_id")) not in categories():
        data["category_id"] = None
    return data


WRITE_SYSTEM = """You write marketplace listings for the shop "Play with me" on Pigu.lt / 220.lv / Kaup24.ee / Hobbyhall.fi.
Write natural, accurate, sales-friendly text based ONLY on the facts given. Do not invent features, certifications or numbers.

Output ONE JSON object in a ```json block:
{
 "titles": {"lt": str, "lv": str, "ee": str, "fi": str, "ru": str, "en": str},
 "descriptions": {"lt": str, "lv": str, "ee": str, "fi": str, "ru": str, "en": str},
 "properties": [{"id": str, "values": [str, ...]}, ...]
}

Titles: "Brand + product type + model/key feature", max ~120 characters, no ALL CAPS, no emojis, no prices.
Descriptions: HTML using ONLY <p>, <br>, <b>, <strong>, <i>, <em>, <ul>, <ol>, <li>, <h2>, <h3>.
  No HTML entities (&nbsp; etc.), no links, no images, no inline styles. A short intro paragraph + a <ul> of key features
  (+ age recommendation and safety warning for toys if the facts mention them).
Properties: use the category fields given below. "id" = the field's Lithuanian title EXACTLY as given.
  If the field has allowed values, every value MUST be copied exactly from that list; otherwise write the value in Lithuanian
  (numbers as plain numbers, no units unless needed). Fill every mandatory field you can support with the facts;
  skip fields you cannot support. Brand name fields: the brand as written by the manufacturer.
"""


def write(facts, category_id):
    cat = categories()[str(category_id)]
    fields = []
    for f in cat["fields"]:
        line = {"id": f["title_lt"], "en": f["title_en"], "mandatory": f["mandatory"], "type": f["type"]}
        if f.get("values_lt"):
            line["allowed_values"] = f["values_lt"]
        fields.append(line)
    user = (f"Category: {cat['top_en']} > {cat['title_en']}\n\n"
            f"Category fields:\n{json.dumps(fields, ensure_ascii=False)}\n\n"
            f"Product facts:\n{json.dumps(facts, ensure_ascii=False)}")
    resp = client().messages.create(model=MODEL, max_tokens=12000,
                                    system=WRITE_SYSTEM,
                                    messages=[{"role": "user", "content": user}])
    data = _extract_json(_text(resp))
    data["properties"] = clean_properties(data.get("properties", []), cat)
    for k in ("titles", "descriptions"):
        data[k] = {lang: (data.get(k) or {}).get(lang, "").strip() for lang in LANGS}
    return data


def clean_properties(props, cat):
    """Keep only known fields; force list values to Pigu's allowed spelling."""
    by_title = {f["title_lt"].lower(): f for f in cat["fields"]}
    out = []
    for p in props:
        f = by_title.get(str(p.get("id", "")).strip().lower())
        if not f:
            continue
        values = [str(v).strip() for v in (p.get("values") or []) if str(v).strip()]
        allowed = f.get("values_lt")
        if allowed:
            lookup = {a.lower(): a for a in allowed}
            values = [lookup[v.lower()] for v in values if v.lower() in lookup]
        if values:
            out.append({"id": f["title_lt"], "values": values})
    return out


def missing_mandatory(props, category_id):
    cat = categories().get(str(category_id))
    if not cat:
        return []
    have = {p["id"].lower() for p in props}
    return [f["title_en"] for f in cat["fields"] if f["mandatory"] and f["title_lt"].lower() not in have]
