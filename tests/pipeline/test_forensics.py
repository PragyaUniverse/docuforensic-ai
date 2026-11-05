import json

import numpy as np
import pymupdf
import pytest
from PIL import Image

from models.schemas import BBox, FindingStatus, Severity
from pipeline.common import from_rel, source_path
from pipeline.dev_eval import run_docs
from pipeline.forensics_pdf import analyze_pdf
from pipeline.forensics_visual import (
    analyze_visual,
    build_ctx,
    collect_styles,
    detect_copy_move,
    detect_font_consistency,
    detect_noise,
    detect_overwrite,
    detect_photo_insert,
    find_photo_regions,
)
from pipeline.fusion import fuse_regions
from pipeline.signatures import analyze_signatures
from tests.pipeline.fixtures import (
    add_signature,
    draw_signature,
    overwrite_value,
    salary_slip,
    write_pdf_text,
)


def _overlap(found: BBox, truth: tuple) -> bool:
    b = BBox(x0=truth[0], y0=truth[1], x1=truth[2], y1=truth[3])
    return found.iou(b) > 0.05


def test_clean_page_has_no_potential_manipulation(prepare, workdir):
    doc = prepare(salary_slip()[0])
    fused = fuse_regions(analyze_visual(doc, workdir), doc)
    assert not [f for f in fused if f.status == FindingStatus.POTENTIAL_MANIPULATION]
    assert all(f.severity == Severity.low for f in fused)


def test_every_finding_explains_itself(prepare, workdir):
    im, boxes = salary_slip()
    tampered, _ = overwrite_value(im, boxes["Net Pay"], "Rs. 93,600.00")
    doc = prepare(tampered)
    for f in fuse_regions(analyze_visual(doc, workdir), doc):
        assert f.explanation and f.benign_alternatives and f.recommended_verification and f.evidence
        assert f.doc_id == doc.id and f.page == 0 and f.bbox is not None
        assert "fraud" not in (f.title + f.explanation).lower()


def test_overwrite_detects_patch_on_textured_paper(prepare, workdir):
    im, boxes = salary_slip(noise=2.0)
    tampered, patch = overwrite_value(im, boxes["Net Pay"], "Rs. 93,600.00")
    doc = prepare(tampered)
    ctx = build_ctx(doc, 0)
    found = detect_overwrite(ctx, doc, workdir, [])
    assert any(_overlap(f.bbox, patch) for f in found)


def test_fusion_needs_independent_signals(prepare, workdir):
    im, boxes = salary_slip(noise=2.0)
    tampered, patch = overwrite_value(im, boxes["Net Pay"], "Rs. 93,600.00")
    doc = prepare(tampered)
    fused = fuse_regions(analyze_visual(doc, workdir), doc)
    hits = [f for f in fused if f.status == FindingStatus.POTENTIAL_MANIPULATION and _overlap(f.bbox, patch)]
    assert hits
    assert hits[0].fused_score >= 0.6
    assert len(hits[0].evidence[0].data["contributing_detectors"]) >= 2


def test_single_weak_signal_stays_observation(prepare, workdir):
    from models.schemas import FindingCategory
    from pipeline.common import make_finding

    doc = prepare(salary_slip()[0])
    weak = make_finding(doc, "visual.ela", "t", "e", confidence=0.5, page=0, bbox=BBox(x0=10, y0=10, x1=60, y1=40), category=FindingCategory.visual)
    out = fuse_regions([weak], doc)
    assert out[0].status == FindingStatus.OBSERVATION
    assert out[0].confidence <= 0.5


def test_font_detector_flags_foreign_value(prepare, workdir):
    im, boxes = salary_slip(noise=1.0)
    tampered, patch = overwrite_value(im, boxes["Net Pay"], "Rs. 93,600.00")
    doc = prepare(tampered)
    ctx = build_ctx(doc, 0)
    found = detect_font_consistency(ctx, doc, workdir, collect_styles(ctx))
    assert any(_overlap(f.bbox, patch) for f in found)


def test_noise_detector_finds_foreign_grain(prepare, workdir):
    im, _ = salary_slip(noise=1.5)
    arr = np.asarray(im).copy()
    rng = np.random.default_rng(4)
    x0, y0, x1, y1 = 1100, 1700, 1400, 1900
    arr[y0:y1, x0:x1] = np.clip(arr[y0:y1, x0:x1].astype(float) + rng.normal(0, 14, (y1 - y0, x1 - x0, 1)), 0, 255).astype(np.uint8)
    doc = prepare(Image.fromarray(arr))
    ctx = build_ctx(doc, 0)
    found = detect_noise(ctx, doc, workdir, [])
    assert any(_overlap(f.bbox, (x0, y0, x1, y1)) for f in found)
    assert (workdir / doc.id / "overlays" / "noise_p0.png").exists()


def test_ela_writes_page_sized_rgba_heatmap(prepare, workdir):
    doc = prepare(salary_slip()[0])
    analyze_visual(doc, workdir)
    heat = Image.open(workdir / doc.id / "overlays" / "ela_p0.png")
    assert heat.mode == "RGBA" and heat.size == (doc.pages[0].width, doc.pages[0].height)


def test_copy_move_ignores_repeated_template_text_but_finds_a_clone(prepare, workdir):
    rows = [("Item A", "Rs. 45,000.00 monthly salary credit"), ("Item B", "Rs. 45,000.00 monthly salary credit"), ("Item C", "Rs. 45,000.00 monthly salary credit"), ("Item D", "Rs. 7,000.00 other credit posted")]
    im, boxes = salary_slip(rows=rows, noise=2.5)
    doc = prepare(im)
    assert not detect_copy_move(build_ctx(doc, 0), doc, workdir)

    arr = np.asarray(im).copy()
    a = boxes["Item A"]
    d = boxes["Item D"]
    h, w = a[3] - a[1] + 16, a[2] - a[0] + 16
    arr[d[1] - 8 : d[1] - 8 + h, d[0] - 8 : d[0] - 8 + w] = arr[a[1] - 8 : a[1] - 8 + h, a[0] - 8 : a[0] - 8 + w]
    doc2 = prepare(Image.fromarray(arr), name="clone.png")
    found = detect_copy_move(build_ctx(doc2, 0), doc2, workdir)
    assert found and any(_overlap(f.bbox, d) for f in found)


def _photo(rng, size=(276, 336), grain=0.0):
    h, w = size[1], size[0]
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.dstack([170 + 40 * np.sin(xx / 40), 140 + 30 * np.cos(yy / 50), 120 + 20 * np.sin((xx + yy) / 60)])
    return np.clip(base + rng.normal(0, grain, (h, w, 1)), 0, 255).astype(np.uint8) if grain else base.astype(np.uint8)


def test_photo_grain_mismatch(prepare, workdir, rng):
    im, _ = salary_slip(noise=2.0)
    arr = np.asarray(im).copy()
    arr[1700:2036, 1200:1476] = _photo(rng)
    doc = prepare(Image.fromarray(arr))
    ctx = build_ctx(doc, 0)
    photos = find_photo_regions(ctx)
    assert photos
    found = detect_photo_insert(ctx, doc, workdir, photos)
    assert found and found[0].evidence[0].data["page_grain"] > 0.5


def test_photo_scanned_with_the_page_is_quiet(prepare, workdir, rng):
    im, _ = salary_slip(noise=0.0)
    arr = np.asarray(im).astype(float)
    arr[1700:2036, 1200:1476] = _photo(rng)
    arr = arr + rng.normal(0, 2.0, (arr.shape[0], arr.shape[1], 1))  # noise over everything, as a scan
    doc = prepare(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    ctx = build_ctx(doc, 0)
    found = detect_photo_insert(ctx, doc, workdir, find_photo_regions(ctx))
    assert not [f for f in found if f.confidence >= 0.85]


def _signed(prepare, sig, name, seed):
    im, _ = salary_slip()
    from PIL import ImageDraw

    from tests.pipeline.fixtures import font

    ImageDraw.Draw(im).text((900, 1900), "Signature of Applicant", font=font(size=28), fill=(40, 40, 40))
    add_signature(im, sig, (920, 1760))
    return prepare(im, name=name)


def test_signature_reuse_is_flagged_and_natural_variation_is_not(prepare, workdir):
    a = _signed(prepare, draw_signature(seed=1), "a.png", 1)
    b = _signed(prepare, draw_signature(seed=1), "b.png", 2)
    c = _signed(prepare, draw_signature(seed=2), "c.png", 3)
    assert any(f.detector == "visual.signature_reuse" and f.status == FindingStatus.POTENTIAL_MANIPULATION for f in analyze_signatures([a, b], workdir, "t"))
    assert not any(f.detector == "visual.signature_reuse" for f in analyze_signatures([a, c], workdir, "t"))


def test_missing_signature_is_an_observation(prepare, workdir):
    from PIL import ImageDraw

    from tests.pipeline.fixtures import font

    im, _ = salary_slip()
    ImageDraw.Draw(im).text((900, 1900), "Signature of Applicant", font=font(size=28), fill=(40, 40, 40))
    doc = prepare(im)
    found = analyze_signatures([doc], workdir, "t")
    assert any(f.detector == "visual.signature_placement" and f.status == FindingStatus.OBSERVATION for f in found)


def _pdf(tmp_path, name="d.pdf"):
    p = tmp_path / name
    lines = [(50, 60, "SALARY SLIP")]
    for i, (label, value) in enumerate([("Employee Name:", "Asha Verma"), ("Basic Pay:", "Rs. 45,000.00"), ("Gross Pay:", "Rs. 70,000.00"), ("Total Deductions:", "Rs. 6,400.00"), ("Net Pay:", "Rs. 63,600.00")]):
        lines += [(50, 100 + 30 * i, label), (250, 100 + 30 * i, value)]
    write_pdf_text(p, lines, fontsize=12)
    return p


def test_text_layer_matching_pixels_is_quiet(prepare, tmp_path):
    p = _pdf(tmp_path)
    doc = prepare(p)
    found = analyze_pdf(doc, source_path(doc), tmp_path)
    assert not [f for f in found if f.detector in ("pdf.text_vs_pixels", "pdf.incremental_update", "pdf.overlay_object")]
    assert doc.metadata["text_vs_pixels"]["0"]["lines_compared"] >= 4


def test_pixels_differing_from_text_layer_and_incremental_update(prepare, tmp_path):
    p = _pdf(tmp_path)
    pdf = pymupdf.open(p)
    page = pdf[0]
    rect = pymupdf.Rect(245, 208, 400, 228)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 310, 40), False)
    pix.clear_with(255)
    tmp = pymupdf.open()
    t = tmp.new_page(width=155, height=20)
    t.insert_text((2, 15), "Rs. 93,600.00", fontsize=12)
    page.insert_image(rect, stream=t.get_pixmap(dpi=200).tobytes("png"))
    pdf.saveIncr()
    pdf.close()

    doc = prepare(p)
    found = analyze_pdf(doc, source_path(doc), tmp_path)
    dets = {f.detector for f in found}
    assert "pdf.text_vs_pixels" in dets and "pdf.incremental_update" in dets and "pdf.overlay_object" in dets
    tvp = next(f for f in found if f.detector == "pdf.text_vs_pixels")
    assert tvp.evidence[0].data["digits_differ"]
    fused = fuse_regions(found, doc)
    assert any(f.status == FindingStatus.POTENTIAL_MANIPULATION for f in fused)
    # Both the parsed and the visible value stay available, each with its source.
    values = {f.value_norm for f in doc.fields if f.name == "net_pay"}
    assert {"63600.00", "93600.00"} <= values


def test_pdf_metadata_findings(prepare, tmp_path):
    p = tmp_path / "m.pdf"
    write_pdf_text(p, [(50, 80 + 20 * i, f"Plain line {i} with words") for i in range(8)])
    pdf = pymupdf.open(p)
    pdf.set_metadata({"creator": "PayrollSuite 3", "producer": "iLovePDF", "creationDate": "D:20260101100000Z", "modDate": "D:20260301100000Z"})
    out = tmp_path / "m2.pdf"
    pdf.save(out)
    pdf.close()
    doc = prepare(out)
    dets = {f.detector: f for f in analyze_pdf(doc, source_path(doc), tmp_path)}
    assert "pdf.producer_mismatch" in dets and "metadata.pdf_dates" in dets
    assert dets["metadata.pdf_dates"].status == FindingStatus.OBSERVATION


def test_image_metadata_names_editor(prepare, tmp_path):
    im, _ = salary_slip()
    exif = Image.Exif()
    exif[0x0131] = "Adobe Photoshop 25"
    p = tmp_path / "e.jpg"
    im.save(p, exif=exif, quality=92)
    doc = prepare(p)
    found = analyze_pdf(doc, source_path(doc), tmp_path)
    assert any(f.detector == "metadata.exif" for f in found)


def test_detector_failure_is_recorded_not_raised(prepare, workdir, monkeypatch):
    from pipeline import forensics_visual as mod

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "detect_ela", boom)
    doc = prepare(salary_slip()[0])
    analyze_visual(doc, workdir)
    assert any("ELA" in x for x in doc.metadata["forensics_failures"])


def test_unprocessable_documents_are_skipped(workdir):
    from models.schemas import Document, ProcessingStatus
    from pipeline.classify import classify
    from pipeline.extract import extract_fields
    from pipeline.ocr import extract_words
    from pipeline.structure import analyze_structure

    doc = Document(case_id="c", filename="x", sha256="", status=ProcessingStatus.failed, status_message="bad")
    for fn in (lambda d: extract_words(d, workdir), classify, extract_fields, analyze_structure):
        assert fn(doc).status == ProcessingStatus.failed
    assert analyze_visual(doc, workdir) == []
    assert analyze_pdf(doc, workdir / "none", workdir) == []
    assert analyze_signatures([doc], workdir, "c") == []


def _case(dataset, name, workdir):
    case_dir = dataset / name
    paths = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".pdf"})
    return run_docs(paths, workdir), json.loads((case_dir / "ground_truth.json").read_text())


def test_case_a_has_no_potential_manipulation(dataset, workdir):
    (docs, findings, names, _), _ = _case(dataset, "case_a_clean", workdir)
    assert not [f for f in findings if f.status == FindingStatus.POTENTIAL_MANIPULATION]
    assert all(f.severity == Severity.low for f in findings)


@pytest.mark.parametrize("case", ["case_b_visual", "case_d_pdf"])
def test_injected_manipulations_are_localized(case, dataset, workdir):
    (docs, findings, names, _), truth = _case(dataset, case, workdir)
    for m in truth["manipulations"]:
        hits = [
            f for f in findings
            if names.get(f.doc_id) == m["filename"] and f.status == FindingStatus.POTENTIAL_MANIPULATION
            and f.page == m["page"] and f.bbox is not None and _overlap(f.bbox, m["bbox"])
        ]
        assert hits, f"{m['id']} {m['type']} not localized"


def test_images_stay_available_on_disk(prepare):
    doc = prepare(salary_slip()[0])
    assert from_rel(doc.pages[0].image_path).exists()


def test_signature_copy_is_found_when_crop_bounds_differ():
    from pipeline.signatures import IDENTICAL_CORR, _native_corr, _pixel_corr

    sig = np.asarray(draw_signature(seed=3, size=(400, 90)))
    trimmed = sig[3:-2, 6:-9]  # same pixels, slightly different bounds
    assert _native_corr(sig, trimmed) >= IDENTICAL_CORR
    other = np.asarray(draw_signature(seed=8, size=(400, 90)))
    assert _pixel_corr(sig, other) < IDENTICAL_CORR


def test_second_engine_overrules_a_single_misread_of_the_render():
    from PIL import ImageDraw

    from pipeline.forensics_pdf import _second_engine_matches_layer
    from tests.pipeline.fixtures import font

    im = Image.new("RGB", (500, 90), "white")
    ImageDraw.Draw(im).text((30, 20), "6,000.00", font=font(size=40), fill=(20, 20, 20))
    arr, box = np.asarray(im), BBox(x0=20, y0=10, x1=300, y1=75)
    assert _second_engine_matches_layer(arr, box, "6,000.00")
    # The pixels really do say something else: the mismatch must stand.
    assert not _second_engine_matches_layer(arr, box, "8,000.00")


def test_signature_copy_survives_blur_and_a_small_rotation():
    import cv2

    from pipeline.signatures import SOFTENED_IDENTICAL_CORR, _degraded_corr

    sig = np.asarray(draw_signature(seed=3, size=(400, 90)))
    h, w = sig.shape
    turned = cv2.warpAffine(sig, cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 1.0), (w, h), borderValue=255)
    assert _degraded_corr(sig, cv2.GaussianBlur(turned, (0, 0), 1.5)) >= SOFTENED_IDENTICAL_CORR
    # Softening must not make two different signatures look alike.
    other = np.asarray(draw_signature(seed=8, size=(400, 90)))
    assert _degraded_corr(sig, other) < SOFTENED_IDENTICAL_CORR
