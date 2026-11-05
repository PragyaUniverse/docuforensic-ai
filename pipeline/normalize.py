"""Value normalization, per docs/CONTRACTS.md section 4."""
from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}

_OCR_DIGIT_MAP = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})

ADDRESS_ABBREV = [
    (r"\bRD\b\.?", "ROAD"),
    (r"\bST\b\.?", "STREET"),
    (r"\bAPT\b\.?", "APARTMENT"),
    (r"\bAPTS\b\.?", "APARTMENTS"),
    (r"\bFLR\b\.?", "FLOOR"),
    (r"\bNR\b\.?", "NEAR"),
    (r"\bOPP\b\.?", "OPPOSITE"),
    (r"\bSEC\b\.?", "SECTOR"),
    (r"\bBLDG\b\.?", "BUILDING"),
    (r"\bNGR\b\.?", "NAGAR"),
    (r"\bH\.?\s?NO\b\.?", "HOUSE NO"),
    (r"\bDIST\b\.?", "DISTRICT"),
    (r"\bAVE\b\.?", "AVENUE"),
]


def norm_money(raw: str) -> str | None:
    """'Rs. 85,400.00' -> '85400.00'. None when no amount can be read."""
    s = raw.replace("₹", " ").replace(" ", " ")
    s = re.sub(r"(?i)\b(rs|inr)\b\.?", " ", s)
    s = s.replace("/-", " ")
    m = re.search(r"\d[\d,\s]*(?:\.\s?\d{1,2})?", s)
    if not m:
        return None
    # Spaces inside a number only come from OCR, and only before a three-digit group.
    token = re.sub(r"\s+(?=\d{3}\b)", "", m.group(0)).split()[0] if " " in m.group(0) else m.group(0)
    token = token.replace(",", "").replace(" ", "")
    try:
        return f"{float(token):.2f}"
    except ValueError:
        return None


def _safe_date(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def norm_date(raw: str) -> str | None:
    """Indian day-first dates, numeric or with month names, to YYYY-MM-DD."""
    s = raw.strip()
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2,4})\b", s)
    if m:
        y = int(m.group(3))
        y += 2000 if y < 50 else (1900 if y < 100 else 0)
        return _safe_date(y, int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([A-Za-z]{3,9})[\s\-/.,]*(\d{2,4})\b", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        y = int(m.group(3))
        y += 2000 if y < 50 else (1900 if y < 100 else 0)
        return _safe_date(y, MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    m = re.search(r"\b([A-Za-z]{3,9})\s*(\d{1,2})(?:st|nd|rd|th)?[\s,]*(\d{4})\b", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def norm_period(raw: str) -> str | None:
    """'March 2026' -> '2026-03'; a date range -> 'start/end'."""
    dates = re.findall(
        r"\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2,4}|\d{1,2}(?:st|nd|rd|th)?[\s\-]*[A-Za-z]{3,9}[\s\-,]*\d{2,4}|\d{4}-\d{2}-\d{2}",
        raw,
    )
    if len(dates) >= 2:
        a, b = norm_date(dates[0]), norm_date(dates[1])
        if a and b:
            return f"{a}/{b}"
    m = re.search(r"\b([A-Za-z]{3,9})[\s\-,']*(\d{2,4})\b", raw)
    if m and m.group(1)[:3].lower() in MONTHS:
        y = int(m.group(2))
        y += 2000 if y < 100 else 0
        return f"{y:04d}-{MONTHS[m.group(1)[:3].lower()]:02d}"
    m = re.search(r"\b(\d{1,2})\s*[-/]\s*(\d{4})\b", raw)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    single = norm_date(raw)
    return single


def norm_name(raw: str) -> str:
    s = re.sub(r"[^\w\s.'-]", " ", raw)
    return re.sub(r"\s+", " ", s).strip().casefold()


def norm_address(raw: str) -> str:
    s = raw.upper().replace("\n", " ")
    for pattern, repl in ADDRESS_ABBREV:
        s = re.sub(pattern, repl, s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.")
    return s


def norm_id(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw).upper()


def norm_number(raw: str) -> str | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
    return m.group(0).replace(",", "") if m else None


def looks_like_money(text: str) -> bool:
    return bool(re.fullmatch(r"(?:(?:rs\.?|inr|₹)\s*)?\d[\d,]*(?:\.\d{1,2})?(?:/-)?", text.strip(), re.IGNORECASE))


def looks_like_date(text: str) -> bool:
    return norm_date(text) is not None and bool(re.search(r"\d", text))


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
