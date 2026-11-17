"""Build docs/feed.xml in the exact tag order of the Pigu (PMP) XML template."""
from xml.etree import ElementTree

from .config import FEED_FILE
from .store import categories

TITLE_TAGS = [("lt", "title"), ("ru", "title-ru"), ("lv", "title-lv"),
              ("ee", "title-ee"), ("fi", "title-fi"), ("en", "title-en")]
DESC_TAGS = [("lt", "long-description"), ("ru", "long-description-ru"), ("lv", "long-description-lv"),
             ("ee", "long-description-ee"), ("fi", "long-description-fi"), ("en", "long-description-en")]


def cdata(s):
    s = "" if s is None else str(s)
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def num(x):
    return f"{float(x):.3f}".rstrip("0").rstrip(".") or "0"


def problems(p):
    """Blocking problems: product cannot go into the feed."""
    out = []
    if not p.get("category_id") or str(p["category_id"]) not in categories():
        out.append("нет категории Pigu")
    if not any((p.get("titles") or {}).values()):
        out.append("нет названия")
    if not any((p.get("descriptions") or {}).values()):
        out.append("нет описания")
    if not p.get("images"):
        out.append("нет фото")
    return out


def category_name(cid):
    c = categories()[str(cid)]
    return f"{c['top_en']} / {c['title_en']}"


def product_xml(p):
    x = ["  <product>",
         f"    <category-id>{p['category_id']}</category-id>",
         f"    <category-name>{cdata(category_name(p['category_id']))}</category-name>"]
    for lang, tag in TITLE_TAGS:
        v = (p.get("titles") or {}).get(lang)
        if v:
            x.append(f"    <{tag}>{cdata(v)}</{tag}>")
    for lang, tag in DESC_TAGS:
        v = (p.get("descriptions") or {}).get(lang)
        if v:
            x.append(f"    <{tag}>{cdata(v)}</{tag}>")
    m = p.get("manufacturer") or {}
    r = p.get("representative") or {}
    for tag, val in (("manufacturer-name", m.get("name")), ("manufacturer-address", m.get("address")),
                     ("manufacturer-email", m.get("email")), ("representative-name", r.get("name")),
                     ("representative-address", r.get("address")), ("representative-email", r.get("email"))):
        if val:
            x.append(f"    <{tag}>{cdata(val)}</{tag}>")
    props = p.get("properties") or []
    if props:
        x.append("    <properties>")
        for pr in props:
            x.append("      <property>")
            x.append(f"        <id>{cdata(pr['id'])}</id>")
            x.append("        <values>")
            for v in pr["values"]:
                x.append(f"          <value>{cdata(v)}</value>")
            x.append("        </values>")
            x.append("      </property>")
        x.append("    </properties>")
    pk = p.get("package") or {}
    x += ["    <colours>", "      <colour>", "        <images>"]
    for url in p["images"]:
        x.append(f"          <image><url>{url}</url></image>")
    x += ["        </images>", "        <modifications>", "          <modification>",
          f"            <weight>{num(pk.get('weight'))}</weight>",
          f"            <length>{num(pk.get('length'))}</length>",
          f"            <height>{num(pk.get('height'))}</height>",
          f"            <width>{num(pk.get('width'))}</width>",
          "            <attributes>",
          "              <barcodes>",
          f"                <barcode>{cdata(p['ean'])}</barcode>",
          "              </barcodes>",
          f"              <supplier-code>{cdata(p['supplier_code'])}</supplier-code>"]
    if p.get("manufacturer_code"):
        x.append(f"              <manufacturer-code>{cdata(p['manufacturer_code'])}</manufacturer-code>")
    x += ["            </attributes>", "          </modification>", "        </modifications>",
          "      </colour>", "    </colours>", "  </product>"]
    return "\n".join(x)


def build(products):
    """Write feed.xml. Returns (included_eans, skipped {ean: problems})."""
    included, skipped = [], {}
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<products>"]
    for ean in sorted(products):
        p = products[ean]
        if p.get("status") in ("queued", "not_found", "error", "disabled"):
            continue
        prob = problems(p)
        if prob:
            skipped[ean] = prob
            continue
        parts.append(product_xml(p))
        included.append(ean)
    parts.append("</products>")
    xml = "\n".join(parts) + "\n"
    ElementTree.fromstring(xml.encode("utf-8"))  # well-formedness check
    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEED_FILE.write_text(xml, encoding="utf-8")
    return included, skipped
