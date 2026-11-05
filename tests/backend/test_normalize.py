from decimal import Decimal

import pytest

from backend.normalize import (
    clean_address,
    compare_addresses,
    compare_employers,
    compare_ids,
    compare_names,
    confusable,
    money_well_formed,
    parse_date,
    parse_money,
    parse_period,
    verhoeff_valid,
)


@pytest.mark.parametrize("a,b", [
    ("Priya Raman Menon", "PRIYA RAMAN MENON"), ("Priya Raman Menon", "Priya R. Menon"),
    ("Priya Raman Menon", "Priya Menon"), ("Mr. Priya Menon", "Priya Menon"), ("Menon Priya", "Priya Menon"),
    ("P. R. Menon", "Priya Raman Menon"), ("Meenakshi Iyer", "Meenakshi lyer"),
])
def test_benign_name_variation_is_not_a_conflict(a, b):
    assert compare_names(a, b).same


@pytest.mark.parametrize("a,b", [
    ("Meenakshi Sundaram Iyer", "Minakshi S. Iyengar"), ("Priya Menon", "Priya Nair"), ("Rahul Sharma", "Rohit Verma"),
])
def test_different_names_conflict(a, b):
    assert not compare_names(a, b).same


@pytest.mark.parametrize("a,b", [
    ("12th Main Road, Indiranagar", "12th Main Rd., Indiranagar"),
    ("Flat No 304, Lakeview, Bengaluru 560038", "Flat 304, Lakeview, Bengaluru, 560038"),
    ("Flat 304, Lakeview Apts, Bengaluru", "FLAT 304 LAKEVIEW APARTMENTS BANGALORE"),
    ("Flat 304, Lakeview, Bengaluru 560038", "Flat 304, Lakeview, Bengaluru 560038, +91 90000 01234"),
    ("Flat 304, Lakeview, Bengaluru 560038", "Flat 304, Lakeview, Bengaluru 560038, BPD-77120394"),
    ("Flat 304, Lakeview", "Flat 304, Lakeview, Bengaluru"),
])
def test_benign_address_variation_is_not_a_conflict(a, b):
    assert compare_addresses(a, b).same


@pytest.mark.parametrize("a,b", [
    ("Flat 12B, Sai Krupa Apartments, Bengaluru 560003", "Flat 21B, Sai Krupa Apartments, Bengaluru 560003"),
    ("Flat 12B, Sai Krupa Apartments, Bengaluru 560003", "Flat 12B, Sai Krupa Apartments, Bengaluru 560055"),
    ("22 Lake Road, Pune", "9 Hill Lane, Nagpur"),
])
def test_real_address_differences_conflict(a, b):
    assert not compare_addresses(a, b).same


def test_clean_address_trims_run_on_text():
    assert clean_address("Flat 1, Pune 411001, Brightleaf Analytics") == "Flat 1, Pune 411001"


def test_employer_suffix_is_benign_but_a_different_name_is_not():
    assert compare_employers("Zenvora Technologies Pvt. Ltd.", "ZENVORA TECHNOLOGIES PRIVATE LIMITED").same
    assert compare_employers("Zenvora Tech Pvt Ltd", "Zenvora Technologies").same
    assert not compare_employers("Zenvora Technologies Pvt. Ltd.", "Zenvora Infotech Solutions").same


def test_masked_numbers_compare_on_visible_digits():
    assert compare_ids("XXXXXXXX1730", "40212208841730").same
    assert compare_ids("9999 5966 1312", "999959661312").same
    assert not compare_ids("50100234567812", "50100234567821").same


@pytest.mark.parametrize("raw,value", [
    ("Rs. 85,400.00", "85400.00"), ("₹1,20,000.00", "120000.00"), ("85400", "85400"), ("58,430.00 CR", "58430.00"),
])
def test_parse_money(raw, value):
    assert parse_money(raw) == Decimal(value)


def test_truncated_money_is_not_well_formed():
    assert money_well_formed("1,20,000.00") and money_well_formed("85400") and money_well_formed("Rs. 5,600.00")
    assert not money_well_formed("26,4")


def test_dates_and_periods():
    assert parse_date("19/07/1988").isoformat() == "1988-07-19"
    assert parse_date("01-May-2026").isoformat() == "2026-05-01"
    assert parse_period("March 2026")[1].isoformat() == "2026-03-31"
    assert parse_period("01-May-2026 to 31-0ct-2026")[1].isoformat() == "2026-10-31"
    assert parse_period("2026-05-01/2026-10-31")[1].isoformat() == "2026-10-31"


def test_verhoeff():
    assert verhoeff_valid("123456789012") is False
    assert verhoeff_valid("2363") is True  # the textbook example


def test_confusable_catches_ocr_pairs():
    assert confusable("Iyer", "lyer")
    assert confusable("1988", "1986")
    assert not confusable("62400", "86400")
