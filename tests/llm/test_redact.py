import pytest

from llm.redact import redact, scrub_secrets


@pytest.mark.parametrize("text,kind", [
    ("Aadhaar 2345 6789 0123, issued", "AADHAAR"), ("Aadhaar 2345 6789 0123.", "AADHAAR"),
    ("PAN ZZAPM4821K.", "PAN"), ("call 9876543210, today", "PHONE"), ("a/c 123456789012.", "ACCOUNT"),
    ("a/c 123456789012, ok", "ACCOUNT"), ("mail a.b@example.com.", "EMAIL"), ("IFSC ARVL0001108,", "IFSC"),
    ("DOB 19/07/1988,", "DATE"), ("Pune 411001,", "PINCODE"),
])
def test_identifiers_followed_by_punctuation_are_redacted(text, kind):
    result = redact(text)
    assert f"[{kind}_1]" in result.text
    assert result.restore(result.text) == text


def test_amounts_survive_so_reasoning_still_works():
    text = "Net pay 85,400.00 vs 1,20,000.00 and 62400.50"
    assert redact(text).text == text


def test_known_values_and_restore_round_trip():
    text = "Priya Menon lives at Flat 304, Lakeview. PRIYA MENON signed."
    result = redact(text, ["Priya Menon", "Flat 304, Lakeview"])
    assert "Priya" not in result.text and "PRIYA" not in result.text and "Lakeview" not in result.text
    assert result.restore(result.text).casefold() == text.casefold()


def test_ten_placeholders_do_not_collide():
    values = [f"Name{i} Person" for i in range(12)]
    result = redact(" ".join(values), values)
    assert result.restore(result.text) == " ".join(values)


def test_scrub_secrets():
    for secret in ("AIzaSyA1234567890abcdef", "gsk_abcdefghijklmnop1234", "sk-or-v1-abcdefghijklmnop"):
        cleaned = scrub_secrets(f"failed with {secret} here")
        assert secret not in cleaned and "****" in cleaned
    assert "abcdefghijkl12" not in scrub_secrets("Authorization: Bearer abcdefghijkl12")
