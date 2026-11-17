"""Download product photos and turn them into Pigu-compliant JPEGs.

Pigu: JPG/PNG, min 1000x1000, HTTPS, no redirects, first image on white bg.
We pad every photo onto a white square canvas (1000–2000 px) and host it on
GitHub Pages, so the final URL is always a direct HTTPS link.
"""
import hashlib
import io

import requests
from PIL import Image, ImageOps

from .config import IMG_DIR, MAX_IMAGES, PAGES_BASE

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
}
MIN_SOURCE_SIDE = 500   # smaller pictures are too blurry once upscaled
MIN_OUT, MAX_OUT = 1000, 2000


def _fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    if len(r.content) > 40 * 1024 * 1024:
        raise ValueError("image too large")
    return r.content


def _to_pigu(raw):
    im = Image.open(io.BytesIO(raw))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("RGB")
    w, h = im.size
    if max(w, h) < MIN_SOURCE_SIDE:
        raise ValueError(f"too small ({w}x{h})")
    side = max(w, h)
    if side > MAX_OUT:
        scale = MAX_OUT / side
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        w, h = im.size
        side = MAX_OUT
    elif side < MIN_OUT:
        scale = MIN_OUT / side
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        w, h = im.size
        side = MIN_OUT
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


def process(ean, urls, existing=None):
    """Download urls, save as docs/img/<ean>-N.jpg. Returns (public_urls, errors)."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    result = list(existing or [])
    seen = set()
    errors = []
    n = len(result)
    for url in urls:
        if len(result) >= MAX_IMAGES:
            break
        try:
            jpg = _to_pigu(_fetch(url))
        except Exception as e:
            errors.append(f"{url[:80]} — {e}")
            continue
        digest = hashlib.md5(jpg).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        n += 1
        name = f"{ean}-{n}.jpg"
        (IMG_DIR / name).write_bytes(jpg)
        result.append(f"{PAGES_BASE}/img/{name}")
    return result, errors


def save_upload(ean, raw, existing):
    """Owner sent a photo in Telegram: add it as an extra product image."""
    jpg = _to_pigu(raw)
    n = len(existing) + 1
    name = f"{ean}-{n}.jpg"
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    (IMG_DIR / name).write_bytes(jpg)
    return existing + [f"{PAGES_BASE}/img/{name}"]


def delete(ean):
    for f in IMG_DIR.glob(f"{ean}-*.jpg"):
        f.unlink()
