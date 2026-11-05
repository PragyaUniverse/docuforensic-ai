from pathlib import Path

import numpy as np
import pytest

from models.schemas import Document
from pipeline.classify import classify
from pipeline.extract import extract_fields
from pipeline.ingest import ingest_file
from pipeline.ocr import extract_words
from pipeline.structure import analyze_structure

DATASET = Path(__file__).resolve().parents[2] / "data" / "synthetic_cases"


def _prepare(path: Path, workdir: Path, case_id: str = "t") -> Document:
    doc = ingest_file(path, case_id, workdir)
    extract_words(doc, workdir)
    classify(doc)
    extract_fields(doc)
    analyze_structure(doc)
    return doc


@pytest.fixture
def prepare(tmp_path):
    def run(image_or_path, name="page.png", case_id="t"):
        if isinstance(image_or_path, Path):
            return _prepare(image_or_path, tmp_path, case_id)
        target = tmp_path / name
        image_or_path.save(target)
        return _prepare(target, tmp_path, case_id)

    return run


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def rng():
    return np.random.default_rng(11)


@pytest.fixture
def dataset():
    if not DATASET.exists():
        pytest.skip("demo dataset not generated")
    return DATASET
