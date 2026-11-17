import re

_CANDIDATE = re.compile(r"(?<!\d)\d{11,14}(?!\d)")


def valid(code: str) -> bool:
    """GTIN check digit (UPC-A 12, EAN-13). Pigu accepts 11–13 digits."""
    if not code.isdigit() or not 11 <= len(code) <= 13:
        return False
    if len(code) == 11:  # some UPCs lose the leading zero
        return True
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize(code: str) -> str:
    code = code.strip()
    if len(code) == 14 and code.startswith("0"):
        code = code[1:]
    return code


def find(text: str):
    """Return (valid, invalid) EAN lists found in free text, de-duplicated, in order."""
    ok, bad = [], []
    for m in _CANDIDATE.findall(text or ""):
        c = normalize(m)
        target = ok if valid(c) else bad
        if c not in target:
            target.append(c)
    return ok, bad
