"""Redacted dossier: personal details are blacked out in text and images; findings, amounts and hashes stay."""
from PIL import Image

from backend import dossier
from models.schemas import BBox, DocType, Document, Field, Page, TextSource, ValueType

BOX = BBox(x0=20, y0=20, x1=120, y1=50)


def _doc() -> Document:
    doc = Document(case_id="case_x", filename="application_form.png", sha256="x", doc_type=DocType.application_form,
                   pages=[Page(index=0, width=300, height=300, image_path="none.png")],
                   metadata={"photo_regions": {"0": [{"x0": 150, "y0": 150, "x1": 250, "y1": 280}]}})

    def field(name, value, vt=ValueType.string):
        return Field(doc_id=doc.id, name=name, value_raw=value, value_type=vt, confidence=0.9, page=0, bbox=BOX,
                     source=TextSource.text_layer)

    doc.fields = [
        field("person_name", "Kavya Anand Rao", ValueType.name),
        field("address", "Plot 9, Green Glen Layout,\nBellandur", ValueType.address),
        field("bank_account_number", "50100234567812", ValueType.account_number),
        field("net_pay", "52,800.00", ValueType.money),
    ]
    return doc


def test_personal_values_and_patterns_are_removed_but_amounts_and_hashes_stay():
    r = dossier._Redactor([_doc()])
    text = r.text("Kavya Anand Rao of Green Glen Layout, account 50100234567812, PAN ZZEPR6247Q, "
                  "mobile +91 90000 01234, kavya@example.com, net pay 52,800.00, sha 9f3a12345678901bc")
    for gone in ("Kavya", "Green Glen", "50100234567812", "ZZEPR6247Q", "90000 01234", "kavya@example.com"):
        assert gone not in text, gone
    assert "52,800.00" in text
    assert "9f3a12345678901bc" in text  # part of a hash, not an account number
    assert text.count(dossier.REDACTED) >= 5


def test_text_helper_redacts_only_inside_a_redacted_render():
    r = dossier._Redactor([_doc()])
    assert "Kavya" in dossier._t("Kavya Anand Rao")
    token = dossier._REDACT.set(r)
    try:
        assert "Kavya" not in dossier._t("Kavya Anand Rao")
    finally:
        dossier._REDACT.reset(token)
    assert "Kavya" in dossier._t("Kavya Anand Rao")


def test_field_boxes_and_photos_are_painted_over():
    r = dossier._Redactor([_doc()])
    doc = _doc()
    im = Image.new("RGB", (300, 300), "white")
    r.paint(im, doc.id, 0)
    assert im.getpixel((70, 35)) == (255, 255, 255)  # another doc's boxes aren't painted here
    r2 = dossier._Redactor([doc])
    r2.paint(im, doc.id, 0)
    assert im.getpixel((70, 35)) != (255, 255, 255)  # the field value
    assert im.getpixel((200, 200)) != (255, 255, 255)  # the photo
    assert im.getpixel((10, 290)) == (255, 255, 255)  # everything else
