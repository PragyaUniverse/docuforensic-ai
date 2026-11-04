"""PII redaction applied before any external LLM call.

Replaces identifiers with stable placeholders, and restores them in the response so local
display keeps the real values. Amounts are deliberately kept: reasoning needs them, and on their
own they don't identify anyone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("AADHAAR", re.compile(r"(?<!\d)(?<!\d[.,])\d{4}[ -]\d{4}[ -]\d{4}(?!\d|[.,]\d)")),
    ("PHONE", re.compile(r"(?<!\d)(?<!\d[.,])(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d|[.,]\d)")),
    ("ACCOUNT", re.compile(r"(?<!\d)(?<!\d[.,])\d{9,18}(?!\d|[.,]\d)")),
    ("MASKED_ID", re.compile(r"\b[Xx*]{4,}[ -]?[Xx*]{0,4}[ -]?\d{3,4}\b")),
    ("DATE", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")),
    ("PINCODE", re.compile(r"(?<!\d)(?<!\d[.,])\d{6}(?!\d|[.,]\d)")),
]


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original

    def restore(self, text: str) -> str:
        # Longest placeholder first, so [PII_10] is never clobbered by [PII_1].
        for placeholder in sorted(self.mapping, key=len, reverse=True):
            text = text.replace(placeholder, self.mapping[placeholder])
        return text


def redact(text: str, known_values: list[str] | None = None) -> Redaction:
    """Replace known values (names, addresses from extracted fields) and pattern matches."""
    mapping: dict[str, str] = {}
    seen: dict[str, str] = {}
    counts: dict[str, int] = {}

    def placeholder(kind: str, original: str) -> str:
        key = original.casefold()
        if key in seen:
            return seen[key]
        counts[kind] = counts.get(kind, 0) + 1
        ph = f"[{kind}_{counts[kind]}]"
        seen[key] = ph
        mapping[ph] = original
        return ph

    values = {v.strip() for v in (known_values or []) if v and len(v.strip()) >= 3}
    for value in sorted(values, key=len, reverse=True):
        pattern = re.compile(re.escape(value), re.IGNORECASE)
        text = pattern.sub(lambda m: placeholder("PII", m.group(0)), text)
    for kind, pattern in _PATTERNS:
        text = pattern.sub(lambda m: placeholder(kind, m.group(0)), text)
    return Redaction(text=text, mapping=mapping)


_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"gsk_[0-9A-Za-z]{10,}"),
    re.compile(r"sk-or-[0-9A-Za-z\-]{10,}"),
    re.compile(r"(?i)(bearer\s+)[0-9A-Za-z_\-.]{10,}"),
    re.compile(r"(?i)(key=)[0-9A-Za-z_\-.]{10,}"),
]


def scrub_secrets(text: str) -> str:
    """Remove anything shaped like an API key from a string destined for logs or the UI."""
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else m.group(0)[:4]) + "****", text)
    return text
