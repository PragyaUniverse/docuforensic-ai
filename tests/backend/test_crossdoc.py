from backend.crossdoc import build_entities, build_graph, correlate
from models.schemas import DocType, EntityType, FindingCategory, FindingStatus
from tests.backend.helpers import make_doc, txn_table

SALARY_ROWS = [
    ["29-May-2026", "NEFT CR-ACME-SALARY", "", "58,430.00", "1,00,000.00"],
    ["30-Jun-2026", "NEFT CR-ACME-SALARY", "", "58,430.00", "1,58,430.00"],
    ["31-Jul-2026", "NEFT CR-ACME-SALARY", "", "58,430.00", "2,16,860.00"],
]


def base_docs(**overrides):
    app = {"person_name": "Priya Raman Menon", "date_of_birth": "19/07/1988",
           "address": "Flat 304, Lakeview Apts, 12th Main Road, Bengaluru 560038", "employer_name": "Acme Analytics Pvt Ltd",
           "id_number": "9999 5966 1312", "pan_number": "ZZAPM4821K", "bank_account_number": "40212208841730",
           "declared_monthly_income": "63,600.50", "date_of_joining": "15/06/2019"}
    idp = {"person_name": "PRIYA R. MENON", "date_of_birth": "19-07-1988", "id_number": "999959661312",
           "address": "Flat No 304, Lakeview Apartments, 12th Main Rd., Bengaluru, 560038"}
    slip = {"person_name": "Priya Menon", "employer_name": "ACME ANALYTICS PRIVATE LIMITED", "gross_pay": "63,600.50",
            "net_pay": "58,430.00", "bank_account_number": "XXXXXXXXXX1730", "pay_period": "June 2026",
            "date_of_joining": "15-06-2019", "pan_number": "ZZAPM4821K"}
    bank = {"person_name": "Priya R Menon", "bank_account_number": "40212208841730"}
    for key, value in overrides.items():
        target, field = key.split("__")
        {"app": app, "idp": idp, "slip": slip, "bank": bank}[target][field] = value
    return [
        make_doc(DocType.application_form, app), make_doc(DocType.id_proof, idp), make_doc(DocType.salary_slip, slip),
        make_doc(DocType.bank_statement, bank, tables=[txn_table(SALARY_ROWS)]),
    ]


def run(docs):
    return correlate(docs, build_entities(docs, "c1"), "c1")


def types(findings):
    return {f.discrepancy_type for f in findings}


def test_benign_variation_raises_no_conflict():
    docs = base_docs()
    assert run(docs) == []
    assert not any(e.conflict for e in build_entities(docs, "c1"))


def test_dob_mismatch_links_both_sides():
    docs = base_docs(idp__date_of_birth="19/07/1984")
    finding = next(f for f in run(docs) if f.discrepancy_type == "dob_mismatch")
    assert finding.status == FindingStatus.INCONSISTENCY and finding.category == FindingCategory.cross_document
    assert set(finding.related_doc_ids) == {docs[0].id, docs[1].id}
    assert len(finding.related_field_ids) == 2
    refs = [e for e in finding.evidence if e.field_id]
    assert {e.doc_id for e in refs} == {docs[0].id, docs[1].id} and all(e.bbox for e in refs)
    assert finding.doc_id == docs[0].id, "the less authoritative side is highlighted, without declaring either true"


def test_day_month_swap_is_called_out():
    docs = base_docs(idp__date_of_birth="07/19/1988")
    # 07/19 can't parse as dd/mm, so the string comparison still flags it.
    assert "dob_mismatch" in types(run(docs))


def test_ocr_confusable_date_gets_lower_confidence():
    from models.schemas import TextSource

    docs = base_docs(idp__date_of_birth="19/07/1986")
    for field in docs[1].fields:
        field.source = TextSource.ocr_rapid
    finding = next(f for f in run(docs) if f.discrepancy_type == "dob_mismatch")
    assert finding.confidence < 0.7 and "reading error" in finding.explanation


def test_each_discrepancy_type():
    cases = {
        "name_variant": {"slip__person_name": "Minakshi S. Iyengar"},
        "address_variant": {"idp__address": "Flat No 403, Lakeview Apartments, 12th Main Rd., Bengaluru, 560038"},
        "employer_mismatch": {"slip__employer_name": "Zenvora Infotech Solutions"},
        "id_number_mismatch": {"idp__id_number": "9999 5966 1999"},
        "account_number_mismatch": {"slip__bank_account_number": "40212208841799"},
        "salary_vs_bank_credit": {"slip__net_pay": "86,400.00"},
        "declared_vs_actual_income": {"app__declared_monthly_income": "1,20,000.00"},
        "employment_date_conflict": {"slip__date_of_joining": "01/02/2024"},
    }
    for dtype, overrides in cases.items():
        assert dtype in types(run(base_docs(**overrides))), dtype


def test_declared_equal_to_gross_or_net_is_consistent():
    assert "declared_vs_actual_income" not in types(run(base_docs(app__declared_monthly_income="58,430.00")))
    assert "declared_vs_actual_income" not in types(run(base_docs(app__declared_monthly_income="60,000.00")))


def test_salary_within_a_rupee_reconciles():
    assert "salary_vs_bank_credit" not in types(run(base_docs(slip__net_pay="58,430.75")))


def test_salary_difference_cites_both_amounts_and_the_row():
    finding = next(f for f in run(base_docs(slip__net_pay="86,400.00")) if f.discrepancy_type == "salary_vs_bank_credit")
    assert "86,400.00" in finding.explanation and "58,430.00" in finding.explanation
    assert any(e.data.get("amount") == "58430.00" and e.bbox for e in finding.evidence)
    assert len(finding.related_doc_ids) == 2


def test_lone_matching_credit_stands_out():
    docs = base_docs(slip__net_pay="86,400.00", slip__pay_period="July 2026")
    docs[3].tables[0].rows[2][3].text = "86,400.00"
    finding = next(f for f in run(docs) if f.discrepancy_type == "salary_vs_bank_credit")
    assert "only" in finding.title and "58,430.00" in finding.explanation


def test_no_transactions_means_no_salary_claim():
    docs = base_docs()
    docs[3].tables = []
    assert "salary_vs_bank_credit" not in types(run(docs))


def test_one_document_compares_nothing():
    assert run(base_docs()[:1]) == []


def test_conflict_splits_entities_and_graph_has_red_edges():
    docs = base_docs(idp__date_of_birth="19/07/1984")
    entities = build_entities(docs, "c1")
    dob = [e for e in entities if e.type == EntityType.date_of_birth]
    assert len(dob) == 2 and all(e.conflict for e in dob)
    findings = correlate(docs, entities, "c1")
    graph = build_graph("c1", docs, entities, findings)
    red = [e for e in graph.edges if e.conflict]
    assert red and all(e.finding_id for e in red)
    node_ids = {n.id for n in graph.nodes}
    assert all(e.source in node_ids and e.target in node_ids for e in graph.edges)
    assert {docs[0].id, docs[1].id} <= {x for e in red for x in (e.source, e.target)}
    # The document that agrees with both isn't drawn as conflicting with either.
    assert not any(docs[3].id in (e.source, e.target) for e in red)


def test_one_disagreeing_document_is_one_red_document_edge():
    docs = base_docs(slip__person_name="Rohit Verma")
    entities = build_entities(docs, "c1")
    findings = correlate(docs, entities, "c1")
    graph = build_graph("c1", docs, entities, findings)
    doc_ids = {d.id for d in docs}
    red_doc_edges = [e for e in graph.edges if e.conflict and e.source in doc_ids and e.target in doc_ids]
    name = next(f for f in findings if f.discrepancy_type == "name_variant")
    named = [e for e in red_doc_edges if e.finding_id == name.id]
    assert len(named) == 1
    assert docs[2].id in (named[0].source, named[0].target), "the outlier is on the edge"
    assert docs[1].id in (named[0].source, named[0].target), "paired with the most authoritative other side"


def test_every_red_edge_links_a_real_finding():
    docs = base_docs(idp__date_of_birth="19/07/1984", slip__net_pay="86,400.00", slip__employer_name="Other Corp")
    entities = build_entities(docs, "c1")
    findings = correlate(docs, entities, "c1")
    ids = {f.id for f in findings}
    graph = build_graph("c1", docs, entities, findings)
    red = [e for e in graph.edges if e.conflict]
    assert red and all(e.finding_id in ids for e in red)
    doc_ids = {d.id for d in docs}
    doc_red = [e for e in red if e.source in doc_ids and e.target in doc_ids]
    assert len(doc_red) <= len(findings)


def test_no_verdict_language():
    findings = run(base_docs(idp__date_of_birth="19/07/1984", slip__net_pay="86,400.00", slip__person_name="Rohit Verma"))
    text = " ".join(f.title + " " + f.explanation for f in findings).lower()
    assert "fraud" not in text


def _income_finding(findings):
    return next(f for f in findings if f.discrepancy_type == "declared_vs_actual_income")


def test_declared_income_above_bank_credits_cites_the_bank_too():
    docs = base_docs(app__declared_monthly_income="1,20,000.00")
    finding = _income_finding(run(docs))
    bank = next(d for d in docs if d.doc_type == DocType.bank_statement)
    assert bank.id in finding.related_doc_ids
    assert "bank" in finding.explanation
    assert any(e.doc_id == bank.id for e in finding.evidence)


def test_declared_income_is_checked_against_the_bank_with_no_salary_slip():
    docs = [d for d in base_docs(app__declared_monthly_income="1,20,000.00") if d.doc_type != DocType.salary_slip]
    finding = _income_finding(run(docs))
    assert "bank" in finding.title.lower()


def _registry(monkeypatch, tmp_path, records):
    import json

    from config.settings import settings

    monkeypatch.setattr(settings, "demo_cases_dir", tmp_path)
    (tmp_path / "registry.json").write_text(json.dumps({"records": records}))


def test_registry_flags_a_name_that_differs_and_says_the_source_is_synthetic(monkeypatch, tmp_path):
    from backend import registry

    docs = base_docs()
    pan = next(f for d in docs for f in d.fields if f.name == "pan_number")
    _registry(monkeypatch, tmp_path, {pan.value_raw.replace(" ", ""): {"person_name": "Somebody Else Entirely", "date_of_birth": None}})
    found = registry.check(docs, "c")
    mismatch = [f for f in found if f.detector == "registry.name_mismatch"]
    assert mismatch and "synthetic" in mismatch[0].explanation and mismatch[0].bbox is not None


def test_registry_absent_means_no_findings_and_no_guessing(monkeypatch, tmp_path):
    from backend import registry
    from config.settings import settings

    monkeypatch.setattr(settings, "demo_cases_dir", tmp_path)
    assert registry.check(base_docs(), "c") == []


def test_unknown_number_is_only_an_observation(monkeypatch, tmp_path):
    from backend import registry

    _registry(monkeypatch, tmp_path, {})
    found = registry.check(base_docs(), "c")
    assert found and all(f.status == FindingStatus.OBSERVATION for f in found)
