"""Value normalization and comparison shared by contextual and cross-document checks.

Comparisons return a tri-state so benign variation ("Rd." vs "Road", a middle initial,
rounding) never raises a conflict, while real differences do.
"""
from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from config.settings import settings
from models.schemas import Field, TextSource

MONEY_TOLERANCE = Decimal("1.00")


# ---- money
def parse_money(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    text = raw.upper().replace("RS.", " ").replace("RS", " ").replace("INR", " ").replace("₹", " ")
    text = re.sub(r"\b(CR|DR|ONLY|/-)\b", " ", text).replace("/-", " ")
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def money_of(field: Field | None) -> Decimal | None:
    if field is None:
        return None
    return parse_money(field.value_norm) or parse_money(field.value_raw)


_MONEY_SHAPE = re.compile(r"^\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?$|^\d+(?:\.\d{1,2})?$")


def money_well_formed(raw: str | None) -> bool:
    """False for fragments such as '26,4', where a reading was cut short by OCR or layout."""
    if not raw:
        return False
    text = re.sub(r"(?i)^\s*(rs\.?|inr|₹)\s*", "", raw.strip())
    text = re.sub(r"(?i)\s*(cr|dr|/-|only)\s*$", "", text)
    return bool(_MONEY_SHAPE.match(text))


def money_strict(field: Field | None) -> Decimal | None:
    """The amount, or None if the printed reading isn't a complete number.

    A truncated reading can't support an arithmetic conflict: it would report an error in our
    reading as if it were a problem with the document.
    """
    if field is None or not money_well_formed(field.value_raw):
        return None
    return money_of(field)


def fmt_money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


# ---- dates
_DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y",
    "%d/%m/%y", "%d-%m-%y", "%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y", "%d-%b-%y",
)


def _ocr_month(text: str) -> str:
    """OCR commonly reads the letter O in 'Oct' as a zero."""
    return re.sub(r"(?i)(?<![0-9])0ct", "Oct", text)


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = _ocr_month(re.sub(r"\s+", " ", raw.strip()).strip(" .,:"))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def date_of(field: Field | None) -> date | None:
    if field is None:
        return None
    return parse_date(field.value_norm) or parse_date(field.value_raw)


_MONTH_FORMATS = ("%B %Y", "%b %Y", "%B-%Y", "%b-%Y", "%m/%Y", "%m-%Y", "%Y-%m", "%B, %Y", "%b, %Y")


def parse_period(raw: str | None) -> tuple[date, date] | None:
    """'March 2026', 'Mar-2026', '01/03/2026 to 31/03/2026' -> (start, end)."""
    if not raw:
        return None
    text = re.sub(r"\s+", " ", raw.strip()).strip(" .,:")
    parts = re.split(r"\s+(?:to|-|–|—|till|until)\s+|(?<=\d)/(?=\d{4}-)", text, flags=re.IGNORECASE)
    if len(parts) == 2:
        start, end = parse_date(parts[0]), parse_date(parts[1])
        if start and end:
            return start, end
    for fmt in _MONTH_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        last = monthrange(parsed.year, parsed.month)[1]
        return date(parsed.year, parsed.month, 1), date(parsed.year, parsed.month, last)
    single = parse_date(text)
    return (single, single) if single else None


# ---- comparison result
@dataclass
class Comparison:
    same: bool
    score: float  # 0..100
    reason: str
    benign_note: str | None = None


# ---- names
_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "shri", "sri", "smt", "kumari", "prof", "master"}


def name_tokens(raw: str) -> list[str]:
    text = re.sub(r"[^\w\s]", " ", raw.casefold())
    return [t for t in text.split() if t not in _HONORIFICS and not t.isdigit()]


def compare_names(a: str, b: str) -> Comparison:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return Comparison(False, 0.0, "one of the names is empty")
    if sorted(ta) == sorted(tb):
        note = None if ta == tb else "same names in a different order"
        return Comparison(True, 100.0, "same tokens", note)
    if confusable(" ".join(ta), " ".join(tb)):
        return Comparison(True, 99.0, "characters OCR commonly confuses", "could be one OCR misreading")
    ratio = fuzz.token_sort_ratio(" ".join(ta), " ".join(tb))
    # Surnames must agree before an initial or a dropped middle name is treated as benign.
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if _surname_ok(ta, tb) and _tokens_covered(short, long_):
        return Comparison(True, max(ratio, 95.0), "initials or a dropped middle name",
                          "differs only by an initial or an omitted middle name")
    return Comparison(False, ratio, "name tokens differ")


def _surname_ok(ta: list[str], tb: list[str]) -> bool:
    return ta[-1] == tb[-1] or ta[0] == tb[-1] or ta[-1] == tb[0]


def _tokens_covered(short: list[str], long_: list[str]) -> bool:
    remaining = list(long_)
    for tok in short:
        for cand in remaining:
            if tok == cand or (len(tok) == 1 and cand.startswith(tok)) or (
                len(cand) == 1 and tok.startswith(cand)
            ):
                remaining.remove(cand)
                break
        else:
            return False
    return True


# ---- addresses
_ADDRESS_ABBREV = {
    "RD": "ROAD", "ST": "STREET", "STR": "STREET", "LN": "LANE", "AVE": "AVENUE", "APT": "APARTMENT",
    "APTS": "APARTMENTS", "BLDG": "BUILDING", "FLR": "FLOOR", "NGR": "NAGAR", "SEC": "SECTOR",
    "HSG": "HOUSING", "SOC": "SOCIETY", "OPP": "OPPOSITE", "NR": "NEAR", "MKT": "MARKET",
    "BLK": "BLOCK", "CHS": "SOCIETY", "H": "HOUSE", "HNO": "HOUSE NUMBER", "NO": "NUMBER",
    "COLY": "COLONY", "CLNY": "COLONY", "EXTN": "EXTENSION", "EXT": "EXTENSION", "DIST": "DISTRICT",
    "BENGALURU": "BANGALORE", "GURUGRAM": "GURGAON", "MUMBAI": "BOMBAY",
}
_ADDRESS_NOISE = {"NUMBER", "THE", "AT", "POST", "INDIA", "PIN", "PINCODE", "CODE"}


def clean_address(raw: str) -> str:
    """Trims text after the PIN code, and phone numbers, that layout extraction can run into."""
    match = re.search(r"(?<!\d)\d{6}(?!\d)", raw)
    text = raw[: match.end()] if match else raw
    text = re.sub(r"\+?91[ -]?\d{5}[ -]?\d{5}|(?<!\d)[6-9]\d{9}(?!\d)", " ", text)
    return text.strip(" ,;")


def norm_address(raw: str) -> str:
    text = re.sub(r"[^\w\s/-]", " ", clean_address(raw).upper()).replace("-", " ").replace("/", " ")
    tokens: list[str] = []
    for tok in text.split():
        tokens.extend(_ADDRESS_ABBREV.get(tok, tok).split())
    return " ".join(t for t in tokens if t not in _ADDRESS_NOISE)


def compare_addresses(a: str, b: str) -> Comparison:
    na, nb = norm_address(a), norm_address(b)
    if not na or not nb:
        return Comparison(False, 0.0, "one of the addresses is empty")
    if na == nb:
        note = None if a.strip().upper() == b.strip().upper() else "formatting or abbreviations only"
        return Comparison(True, 100.0, "same after normalization", note)
    ta, tb = set(na.split()), set(nb.split())
    num_a = {t for t in ta if any(c.isdigit() for c in t)}
    num_b = {t for t in tb if any(c.isdigit() for c in t)}
    ratio = fuzz.token_sort_ratio(na, nb)
    pin_a = {t for t in num_a if re.fullmatch(r"\d{6}", t)}
    pin_b = {t for t in num_b if re.fullmatch(r"\d{6}", t)}
    if pin_a and pin_b and pin_a != pin_b:
        return Comparison(False, ratio, f"PIN codes differ ({sorted(pin_a)[0]} vs {sorted(pin_b)[0]})")
    house_a, house_b = num_a - pin_a, num_b - pin_b
    if house_a and house_b and house_a != house_b:
        diff = sorted(house_a ^ house_b)
        return Comparison(False, ratio, "house, flat or sector numbers differ: " + ", ".join(diff))
    # One address being a shorter form of the other (no state or PIN) is benign.
    if ta <= tb or tb <= ta:
        return Comparison(True, max(ratio, 95.0), "one is a shorter form of the other",
                          "one version omits city, state or PIN")
    if ratio >= 95:
        return Comparison(True, ratio, "near-identical text", "minor spelling variation")
    only = sorted(ta ^ tb)
    return Comparison(False, ratio, "address words differ: " + ", ".join(only[:6]))


# ---- employers
_EMPLOYER_SUFFIX = {"PVT", "PRIVATE", "LTD", "LIMITED", "LLP", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "THE", "M", "S"}
_EMPLOYER_ABBREV = {"TECH": "TECHNOLOGIES", "TECHNOLOGY": "TECHNOLOGIES", "SOLNS": "SOLUTIONS",
                    "SVCS": "SERVICES", "INTL": "INTERNATIONAL", "MFG": "MANUFACTURING", "IND": "INDUSTRIES"}


def norm_employer(raw: str) -> str:
    text = re.sub(r"[^\w\s]", " ", raw.upper())
    tokens = [_EMPLOYER_ABBREV.get(t, t) for t in text.split()]
    return " ".join(t for t in tokens if t not in _EMPLOYER_SUFFIX)


def compare_employers(a: str, b: str) -> Comparison:
    na, nb = norm_employer(a), norm_employer(b)
    if not na or not nb:
        return Comparison(False, 0.0, "one of the employer names is empty")
    if na == nb:
        note = None if a.strip().upper() == b.strip().upper() else "legal suffix or abbreviation only"
        return Comparison(True, 100.0, "same after normalization", note)
    ratio = fuzz.token_sort_ratio(na, nb)
    if ratio >= 95:
        return Comparison(True, ratio, "near-identical", "minor spelling variation")
    return Comparison(False, ratio, "employer names differ")


# ---- identifiers
def norm_id(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z*]", "", raw).upper()


def compare_ids(a: str, b: str) -> Comparison:
    na, nb = norm_id(a), norm_id(b)
    if na == nb:
        return Comparison(True, 100.0, "identical")
    # Masked forms such as XXXXXXXX1234 or ****1234 compare on their visible tail.
    def visible(value: str) -> str:
        return re.sub(r"^[X*]+", "", value)
    va, vb = visible(na), visible(nb)
    if (va != na or vb != nb) and len(min(va, vb, key=len)) >= 3 and (va.endswith(vb) or vb.endswith(va)):
        return Comparison(True, 95.0, "masked number agrees on visible digits",
                          "one version is masked; only the visible digits were compared")
    return Comparison(False, fuzz.ratio(na, nb), "numbers differ")


_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    if not number.isdigit():
        return False
    check = 0
    for i, ch in enumerate(reversed(number)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(ch)]]
    return check == 0


PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


# ---- OCR awareness
_CONFUSABLE = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "S": "5",
                             "B": "8", "Z": "2", "G": "6", "T": "7"})


def confusable(a: str, b: str) -> bool:
    """True if a and b could be one OCR misreading apart."""
    ca = re.sub(r"\s+", "", a.upper()).translate(_CONFUSABLE)
    cb = re.sub(r"\s+", "", b.upper()).translate(_CONFUSABLE)
    if ca == cb:
        return True
    pairs = {("3", "8"), ("8", "3"), ("6", "8"), ("8", "6"), ("5", "6"), ("6", "5"), ("1", "7"), ("7", "1"), ("0", "8"), ("8", "0")}
    return len(ca) == len(cb) and sum(x != y for x, y in zip(ca, cb)) == 1 and all(
        (x, y) in pairs for x, y in zip(ca, cb) if x != y)


def edit_distance(a: str, b: str) -> int:
    return Levenshtein.distance(a, b)


def _second_engine_agrees(fields: list[Field], docs: dict) -> bool | None:
    """Re-read OCR values with an independent engine. True: every value read the same. False: at
    least one read differently. None: couldn't be checked."""
    from pipeline.ocr import reread_region

    def squish(text: str) -> str:
        return re.sub(r"[^0-9a-z]", "", text.casefold())

    results = []
    for f in fields:
        doc = docs.get(f.doc_id)
        if doc is None or f.source in (TextSource.text_layer, TextSource.llm):
            continue
        reading = reread_region(doc, f.page, f.bbox)
        if reading is None:
            continue
        results.append(squish(f.value_raw) in squish(reading))
    if not results:
        return None
    return all(results)


def ocr_adjustment(fields: list[Field], a: str | None = None, b: str | None = None,
                   docs: dict | None = None) -> tuple[float, str | None]:
    """How much to discount a conflict because the values came from OCR.

    Returns (factor for confidence, note for the explanation). Text-layer values can't be misread,
    but they aren't assumed to be true either. With `docs`, values that differ only by confusable
    characters are re-read by a second OCR engine rather than simply being discounted.
    """
    # An AI reading of handwriting is the least certain source, so it gets the same discount.
    ocr_fields = [f for f in fields if f.source != TextSource.text_layer]
    if not ocr_fields:
        return 1.0, None
    low = min(f.confidence for f in ocr_fields)
    if low < settings.low_ocr_confidence:
        return 0.5, (f"OCR confidence on an involved field is low ({low:.2f}), so this could be a "
                     "reading error. Check the source image first.")
    if a is not None and b is not None and confusable(a, b):
        agrees = _second_engine_agrees(fields, docs) if docs else None
        if agrees is True:
            return 0.9, ("The values differ only by characters OCR commonly confuses, but a second, "
                         "independent OCR engine read the same values, so a reading error is less "
                         "likely. It is still worth checking the source image.")
        if agrees is False:
            return 0.5, ("The values differ only by characters OCR commonly confuses, and a second OCR "
                         "engine read one of them differently, so this may well be a reading error. "
                         "Check the source image first.")
        return 0.6, ("The two values differ only by characters OCR commonly confuses, so this could "
                     "be a reading error. Check the source image first.")
    return 0.75 + 0.25 * low, None
