"""Reproduce the pipeline's numbers: `.venv/bin/python -m pipeline.dev_eval [--noise] [case ...]`.

Ground truth is read only here, after the pipeline has run. Files are copied under anonymous names
first, so no detector could use a filename even by accident.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from config.settings import settings
from models.schemas import BBox, Document, Finding, FindingStatus
from pipeline.classify import classify
from pipeline.common import source_path
from pipeline.extract import extract_fields
from pipeline.forensics_pdf import analyze_pdf
from pipeline.forensics_visual import analyze_visual
from pipeline.fusion import fuse_regions
from pipeline.ingest import ingest_file
from pipeline.ocr import extract_words
from pipeline.signatures import analyze_signatures
from pipeline.structure import analyze_structure

DOC_EXT = {".png", ".jpg", ".jpeg", ".pdf"}


def run_docs(paths: list[Path], workdir: Path, case_id: str = "eval") -> tuple[list[Document], list[Finding], dict[str, str], float]:
    """Full pipeline over one case. Returns docs, fused findings, doc id to name, seconds."""
    start = time.perf_counter()
    staged = workdir / "_input"
    staged.mkdir(parents=True, exist_ok=True)
    docs: list[Document] = []
    names: dict[str, str] = {}
    for i, path in enumerate(paths):
        anon = staged / f"f{i}{path.suffix}"
        shutil.copyfile(path, anon)
        doc = ingest_file(anon, case_id, workdir)
        names[doc.id] = path.name
        extract_words(doc, workdir)
        classify(doc)
        extract_fields(doc)
        analyze_structure(doc)
        docs.append(doc)
    per_doc: dict[str, list[Finding]] = {d.id: [] for d in docs}
    for doc in docs:
        per_doc[doc.id].extend(analyze_visual(doc, workdir))
        src = source_path(doc)
        if src:
            per_doc[doc.id].extend(analyze_pdf(doc, src, workdir))
    findings: list[Finding] = []
    for doc in docs:
        findings.extend(fuse_regions(per_doc[doc.id], doc))
    findings.extend(analyze_signatures(docs, workdir, case_id))
    return docs, findings, names, time.perf_counter() - start


def norm_compare(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value).casefold().strip()
    for ch in " ,":
        s = s.replace(ch, "")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return s


def _box(raw) -> BBox | None:
    if not raw:
        return None
    return BBox(x0=raw[0], y0=raw[1], x1=raw[2], y1=raw[3])


def _localizes(f: Finding, truth: BBox, page: int) -> bool:
    candidates = []
    if f.bbox is not None and f.page == page:
        candidates.append(f.bbox)
    candidates += [ev.bbox for ev in f.evidence if ev.bbox is not None and ev.page == page and ev.doc_id == f.doc_id]
    for box in candidates:
        ix = max(0.0, min(box.x1, truth.x1) - max(box.x0, truth.x0))
        iy = max(0.0, min(box.y1, truth.y1) - max(box.y0, truth.y0))
        small, large = sorted((max(box.area, 1), max(truth.area, 1)))
        if box.iou(truth) >= 0.1 or (large / small <= 12 and ix * iy / small >= 0.5):
            return True
    return False


def evaluate(case_dir: Path, truth_path: Path, verbose: bool) -> dict:
    truth = json.loads(truth_path.read_text())
    paths = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in DOC_EXT)
    with tempfile.TemporaryDirectory() as tmp:
        docs, findings, names, seconds = run_docs(paths, Path(tmp))
        by_name = {names[d.id]: d for d in docs}
        field_total = field_ok = field_present = loc_total = loc_ok = 0
        class_total = class_ok = fmt_ok = 0
        misses: list[str] = []
        for gt_doc in truth.get("documents", []):
            doc = by_name.get(gt_doc["filename"])
            if doc is None:
                continue
            class_total += 1
            class_ok += doc.doc_type.value == gt_doc["doc_type"]
            fmt_ok += doc.format.value == gt_doc["format"]
            if doc.doc_type.value != gt_doc["doc_type"]:
                misses.append(f"{gt_doc['filename']}: type {doc.doc_type.value} != {gt_doc['doc_type']}")
            for name, spec in gt_doc.get("fields", {}).items():
                field_total += 1
                cands = [f for f in doc.fields if f.name == name]
                field_present += bool(cands)
                want = norm_compare(spec["value"] if isinstance(spec, dict) else spec)
                got = [norm_compare(f.value_norm) for f in cands] + [norm_compare(f.value_raw) for f in cands]
                if want in got:
                    field_ok += 1
                else:
                    misses.append(f"{gt_doc['filename']}: {name} want {spec['value']!r} got {[f.value_raw for f in cands]}")
                tb = _box(spec.get("bbox"))
                if tb is not None:
                    loc_total += 1
                    hit = False
                    for f in cands:
                        if f.page == spec.get("page", 0):
                            ix = max(0.0, min(f.bbox.x1, tb.x1) - max(f.bbox.x0, tb.x0))
                            iy = max(0.0, min(f.bbox.y1, tb.y1) - max(f.bbox.y0, tb.y0))
                            hit = hit or ix * iy / tb.area >= 0.3
                    loc_ok += hit

        filename_of = names
        manip_rows = []
        matched: set[str] = set()
        for m in truth.get("manipulations", []):
            tb = _box(m.get("bbox"))
            hits = [f for f in findings if filename_of.get(f.doc_id or "") == m["filename"] and tb and _localizes(f, tb, m.get("page", 0))]
            pm = [f for f in hits if f.status == FindingStatus.POTENTIAL_MANIPULATION]
            matched.update(f.id for f in hits)
            manip_rows.append({
                "id": m["id"], "type": m.get("type"), "file": m["filename"],
                "localized_potential": bool(pm), "localized_any": bool(hits),
                "detectors": sorted({f.detector for f in hits}),
                "score": max((f.fused_score or 0 for f in hits), default=0),
            })
        pm_all = [f for f in findings if f.status == FindingStatus.POTENTIAL_MANIPULATION]
        pm_unmatched = [f for f in pm_all if f.id not in matched]
        result = {
            "case": truth.get("case", case_dir.name),
            "seconds": round(seconds, 1),
            "fields": f"{field_ok}/{field_total}",
            "field_present": f"{field_present}/{field_total}",
            "field_location": f"{loc_ok}/{loc_total}",
            "classification": f"{class_ok}/{class_total}",
            "format": f"{fmt_ok}/{class_total}",
            "manipulations_potential": f"{sum(r['localized_potential'] for r in manip_rows)}/{len(manip_rows)}",
            "manipulations_any": f"{sum(r['localized_any'] for r in manip_rows)}/{len(manip_rows)}",
            "potential_total": len(pm_all),
            "potential_unmatched": len(pm_unmatched),
            "observations": sum(f.status == FindingStatus.OBSERVATION for f in findings),
            "failures": [d.metadata.get("forensics_failures") for d in docs if d.metadata.get("forensics_failures")],
        }
        print(json.dumps({k: v for k, v in result.items() if k != "failures"}))
        if result["failures"]:
            print("  FAILURES:", result["failures"])
        for r in manip_rows:
            print(f"  {'OK ' if r['localized_potential'] else ('obs' if r['localized_any'] else 'MISS')} {r['id']} {r['type']} {r['file']} score={r['score']} {r['detectors']}")
        for f in pm_unmatched:
            print(f"  UNMATCHED PM: {filename_of.get(f.doc_id or '')} {f.detector} {f.fused_score} {_fmt(f.bbox)} {f.title}")
        if verbose:
            for miss in misses:
                print("  field:", miss)
            for f in findings:
                print(f"  {f.status.value[:5]} {filename_of.get(f.doc_id or '')} {f.detector} c={f.confidence} s={f.fused_score} {_fmt(f.bbox)} {f.title}")
    return result


def _fmt(b: BBox | None) -> str:
    return "-" if b is None else f"[{int(b.x0)},{int(b.y0)},{int(b.x1)},{int(b.y1)}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", help="Case folder names; default is all")
    ap.add_argument("--noise", action="store_true", help="Include noise variants")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    root = Path(settings.demo_cases_dir)
    case_dirs = sorted(p for p in root.iterdir() if p.is_dir() and (p / "ground_truth.json").exists())
    for d in case_dirs:
        if args.cases and d.name not in args.cases:
            continue
        evaluate(d, d / "ground_truth.json", args.verbose)
    if args.noise:
        for d in sorted((root / "noise_variants").iterdir()):
            if d.is_dir() and (d / "ground_truth.json").exists() and (not args.cases or d.name in args.cases):
                print("noise:", d.name)
                evaluate(d, d / "ground_truth.json", args.verbose)


if __name__ == "__main__":
    main()
