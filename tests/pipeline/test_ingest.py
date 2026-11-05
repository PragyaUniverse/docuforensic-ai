from PIL import Image

from models.schemas import DocFormat, ProcessingStatus
from pipeline.ingest import ingest_file, sniff
from tests.pipeline.fixtures import salary_slip, write_pdf_text


def test_magic_bytes():
    assert sniff(b"\x89PNG\r\n\x1a\nrest") == "png"
    assert sniff(b"\xff\xd8\xff\xe0") == "jpg"
    assert sniff(b"%PDF-1.7") == "pdf"
    assert sniff(b"PK\x03\x04") is None


def test_empty_file_fails_clearly(tmp_path):
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    doc = ingest_file(p, "c", tmp_path)
    assert doc.status == ProcessingStatus.failed
    assert "empty" in doc.status_message


def test_renamed_non_image_is_unsupported(tmp_path):
    p = tmp_path / "fake.png"
    p.write_bytes(b"PK\x03\x04" + b"0" * 200)
    doc = ingest_file(p, "c", tmp_path)
    assert doc.status == ProcessingStatus.unsupported
    assert "ZIP" in doc.status_message


def test_truncated_png_fails_without_raising(tmp_path):
    good = tmp_path / "good.png"
    salary_slip()[0].save(good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(good.read_bytes()[:5000])
    doc = ingest_file(bad, "c", tmp_path)
    assert doc.status == ProcessingStatus.failed


def test_corrupt_pdf_never_raises(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7\ngarbage garbage")
    doc = ingest_file(p, "c", tmp_path)
    assert doc.status in (ProcessingStatus.failed, ProcessingStatus.degraded)


def test_missing_file(tmp_path):
    doc = ingest_file(tmp_path / "nope.png", "c", tmp_path)
    assert doc.status == ProcessingStatus.failed


def test_size_guard(tmp_path, monkeypatch):
    from pipeline import ingest as mod

    monkeypatch.setattr(mod.settings, "max_upload_mb", 0)
    p = tmp_path / "a.png"
    salary_slip()[0].save(p)
    doc = ingest_file(p, "c", tmp_path)
    assert doc.status == ProcessingStatus.unsupported
    assert "limit" in doc.status_message


def test_extension_is_not_trusted(tmp_path):
    p = tmp_path / "actually_png.jpg"
    salary_slip()[0].save(p, format="PNG")
    doc = ingest_file(p, "c", tmp_path)
    assert doc.format == DocFormat.png
    assert doc.metadata["extension_mismatch"]["actual"] == "png"


def test_exif_orientation_applied(tmp_path):
    im = Image.new("RGB", (300, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 on display
    p = tmp_path / "o.jpg"
    im.save(p, exif=exif)
    doc = ingest_file(p, "c", tmp_path)
    assert (doc.pages[0].width, doc.pages[0].height) == (100, 300)


def test_digital_pdf_detected_and_scanned_pdf_detected(tmp_path):
    p = tmp_path / "d.pdf"
    write_pdf_text(p, [(50, 80 + 20 * i, f"Line number {i} of the text") for i in range(10)])
    assert ingest_file(p, "c", tmp_path).format == DocFormat.digital_pdf

    img = tmp_path / "s.png"
    salary_slip()[0].save(img)
    pdf_path = tmp_path / "s.pdf"
    Image.open(img).save(pdf_path, "PDF", resolution=200)
    assert ingest_file(pdf_path, "c", tmp_path).format == DocFormat.scanned_pdf


def test_page_limit_is_stated(tmp_path, monkeypatch):
    import pymupdf

    from pipeline import ingest as mod

    monkeypatch.setattr(mod.settings, "max_pages_per_doc", 2)
    pdf = pymupdf.open()
    for i in range(4):
        pdf.new_page().insert_text((50, 80), f"Page number {i} with enough words on it here")
    p = tmp_path / "long.pdf"
    pdf.save(p)
    doc = ingest_file(p, "c", tmp_path)
    assert len(doc.pages) == 2
    assert doc.status == ProcessingStatus.degraded
    assert "first 2 of 4" in doc.status_message
