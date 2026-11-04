"""Anomaly investigation: explanations, counter-hypotheses and correlation of findings.

Every finding gets useful deterministic text from the playbook, with no LLM. An LLM, when one is
available, may only ADD reasoning. It can't create findings, change a status, a severity, a
confidence or a bbox. Its output is rejected if it states a verdict or cites numbers absent from
the evidence.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from pydantic import BaseModel, Field as PField

from llm.client import LLMClient, get_client
from models.schemas import (
    BBox, Document, Finding, FindingStatus, ReasoningProvenance, Severity, ValueType,
)

log = logging.getLogger("docuforensic.investigator")

LLM_MAX_FINDINGS = 14
LLM_TIME_BUDGET_S = 180.0

VERDICT_RE = re.compile(
    r"\b(fraud\w*|forged?|forger\w*|forging|counterfeit\w*|fake[ds]?|falsified|falsification|"
    r"definitely|certainly|undoubtedly|proves?|proven|guilty|illegal|criminal|confirmed\s+(?:manipulation|tamper\w*)|"
    r"is\s+(?:tampered|manipulated|altered))\b", re.I)

SYSTEM = (
    "You help a human examiner weigh a document anomaly. You do not decide anything. Treat the "
    "measurements as given. Give the most plausible reading, then benign explanations, then what "
    "would confirm or refute each. Write 'may', 'could' or 'is consistent with'. Do not state a "
    "conclusion about anyone's intent, and do not use accusatory or legal terms. Quote only numbers "
    "present in the facts."
)


class InvestigationAnswer(BaseModel):
    reasoning: str = PField(description="2 to 3 sentences on what the measurements could mean.")
    benign_alternatives: list[str] = PField(description="Innocent explanations, each one short sentence.")
    what_would_confirm: list[str] = PField(description="Checks that would support the concern.")
    what_would_refute: list[str] = PField(description="Checks that would clear the concern.")


class CaseSummaryAnswer(BaseModel):
    summary: str = PField(description="3 to 5 sentences summarizing the findings for a human reviewer.")


_ORIGINAL_DOC = "Request the original from the issuer, not from the applicant, and compare the region."
_RESCAN = "Obtain a fresh, higher-resolution scan and re-run the analysis."

# detector or discrepancy_type -> (why it matters, benign alternatives, verification)
PLAYBOOK: dict[str, tuple[str, list[str], list[str]]] = {
    "visual.ela": (
        "Regions saved at a different JPEG history re-compress differently, so they can stand out.",
        ["The document was re-saved or exported by several tools.",
         "High-contrast text and stamps naturally show stronger residuals."],
        [_ORIGINAL_DOC, "Check whether extracted values in the region conflict with other documents."]),
    "visual.noise": (
        "Scanner and sensor noise is usually uniform, so a local change can suggest content from another source.",
        ["Stamps, shading or photos naturally have different texture.", "Uneven lighting while scanning."],
        [_RESCAN, _ORIGINAL_DOC]),
    "visual.copy_move": (
        "Near-identical pixel blocks inside one page can come from a cloning edit.",
        ["Repeated logos, watermarks or boilerplate.", "Identical characters in a printed template."],
        ["Inspect both linked regions at full resolution.", _ORIGINAL_DOC]),
    "visual.font_consistency": (
        "Characters that differ in height, stroke or style from their neighbours can indicate an inserted value.",
        ["Mail-merge templates can use a separate font for variable data.", "Bold or emphasized totals."],
        ["Compare with an authentic document from the same issuer.", _ORIGINAL_DOC]),
    "visual.overwrite": (
        "A background patch behind a value can indicate text replaced over an erased area.",
        ["Form fields or table cells can have shaded backgrounds.", "A correction made by the issuer."],
        ["Verify the value directly with the issuer.", "Compare against bank credits or payroll records."]),
    "visual.photo_insert": (
        "A photo whose edges or compression differ from the page can have been pasted in.",
        ["Photos are often printed or attached separately on genuine IDs.", "Lamination or a scan shadow."],
        ["Compare with the issuing authority's record.", "Inspect the photo edges on the physical original."]),
    "visual.alignment": (
        "A value off the baseline or column of its neighbours may have been placed separately.",
        ["Skew from scanning or paper feed.", "Manual filling of a printed form."],
        [_RESCAN, "Compare the layout with an authentic template."]),
    "visual.signature_reuse": (
        "Handwritten signatures vary naturally, so near-identical pixels across documents suggest a copy.",
        ["A digital signature image applied by the signer themselves.", "An issuer's standard signature stamp."],
        ["Ask for a fresh wet signature.", "Check whether the signer normally uses a signature image."]),
    "visual.signature_placement": (
        "A signature outside its expected zone may have been added later.",
        ["The signer ran out of space or the form has an unusual layout."],
        ["Inspect the original.", "Ask the signer to confirm."]),
    "pdf.text_vs_pixels": (
        "A PDF's text layer normally matches what is displayed. A difference means systems and people can read different values.",
        ["Faulty OCR text layer added by a scanning tool.", "Font encoding problems in the exporter."],
        ["Obtain the file directly from the issuer.", "Treat the visible and embedded values as unverified until reconciled."]),
    "pdf.incremental_update": (
        "Appended revisions show the file was changed after first being saved.",
        ["Adding a digital signature or filling a form also appends a revision.", "Benign annotation or re-save."],
        ["Compare the earlier revision with the final one.", "Ask the issuer about the expected workflow."]),
    "pdf.producer_mismatch": (
        "Creator and producer metadata show which software handled the file, which may not fit the claimed source.",
        ["Companies print statements through many PDF tools.", "Re-saving via a viewer changes the producer."],
        ["Compare with an authentic document from the same issuer."]),
    "pdf.overlay_object": (
        "An object drawn over existing content can hide what is underneath.",
        ["Watermarks, stamps and form fields are also drawn as overlays."],
        ["Inspect the content beneath the overlay.", "Obtain the file directly from the issuer."]),
    "metadata.exif": (
        "Image metadata can reveal editing software or a capture date that doesn't fit the story.",
        ["Mobile scanning apps and messaging apps rewrite metadata."],
        ["Ask how the image was produced.", "Obtain the original file."]),
    "metadata.pdf_dates": (
        "Creation and modification dates that differ, or that don't fit the document date, show later handling.",
        ["Re-saving or printing to PDF updates these dates.", "Wrong system clock on the issuing machine."],
        ["Compare the dates with the expected issuing workflow."]),
    "context.arithmetic_salary": (
        "Payroll systems compute these totals, so a broken sum can mean one figure was changed separately.",
        ["Unlisted deductions or a rounding policy.", "An OCR misreading of one digit."],
        ["Recompute from a payroll register or Form 16.", "Compare net pay with the bank credit for that month."]),
    "context.arithmetic_balance": (
        "Bank systems keep running balances exact, so a break can mean a row was changed.",
        ["An omitted row at a page boundary.", "An OCR misreading of a balance or amount."],
        ["Get the statement directly from the bank.", "Recompute the affected rows by hand from the image."]),
    "context.date_order": (
        "These dates have a required logical order, so a violation deserves a check.",
        ["A typing error by the person filling the form.", "Day and month misread by OCR or written in another format."],
        ["Check the printed date on the original.", "Ask the applicant to clarify."]),
    "context.id_checksum": (
        "ID numbers follow fixed formats and check digits, so a failure suggests the number isn't as issued.",
        ["An OCR misreading of one character.", "A typing error when the form was filled in."],
        ["Verify the number through the official issuer's service.", "Re-read the number from a clear image."]),
    "context.missing_field": (
        "Missing expected fields limit what can be cross-checked.",
        ["This issuer's template may not include the field.", "OCR or layout extraction may have missed it."],
        ["Look at the page for the field.", "Request a complete copy if it's absent."]),
    "context.duplicate_field": (
        "A value repeated with differences on one document is unusual for system-generated documents.",
        ["Different contexts, such as permanent and current address.", "An OCR misreading of one instance."],
        ["Inspect both locations on the page."]),
    "dob_mismatch": (
        "Date of birth doesn't change, so documents for one person should agree.",
        ["A clerical error by whoever filled the form.", "Date format confusion between day and month.", "An OCR misreading."],
        ["Verify against the issuing authority's record.", "Ask the applicant for a corrected document."]),
    "name_variant": (
        "Documents for one applicant should name the same person.",
        ["Marriage or a legal name change.", "Transliteration differences.", "A clerical or OCR error."],
        ["Ask for proof of name change, if any.", "Verify the identity document with its issuer."]),
    "address_variant": (
        "A difference that survives normalization may point to a different residence.",
        ["The applicant moved between document dates.", "A permanent vs a current address.", "A clerical error."],
        ["Compare document dates.", "Ask for a recent utility bill, or do a field check."]),
    "employer_mismatch": (
        "Employment documents should name the same employer.",
        ["A group company or trade name vs legal name.", "A recent change of employer."],
        ["Confirm employment with the employer's HR directly.", "Check the employer against a company registry."]),
    "salary_vs_bank_credit": (
        "The credited amount should reconcile with net pay, unless something else explains the gap.",
        ["Reimbursements, bonuses or arrears paid together.", "A split salary across accounts.", "Payment on a different date."],
        ["Ask for payslips and statements for several months.", "Confirm the salary with the employer."]),
    "declared_vs_actual_income": (
        "Declared income can be compared with what the supporting documents show.",
        ["Other income sources not on the slip.", "Annual vs monthly figures.", "Household income declared instead."],
        ["Ask for evidence of the other income, such as tax returns.", "Clarify what the declared figure includes."]),
    "id_number_mismatch": (
        "An identity number is unique, so two values can't both belong to one person's record.",
        ["A typing error on a filled-in form.", "An OCR misreading of a character."],
        ["Verify the number with the official issuer.", "Compare against the ID document's image."]),
    "account_number_mismatch": (
        "The salary and statement accounts should match unless the applicant uses several accounts.",
        ["The applicant has more than one bank account.", "Masked or truncated numbers."],
        ["Ask for statements on every declared account.", "Confirm the salary account with the employer."]),
    "employment_date_conflict": (
        "Employment dates need to fit each other and the applicant's age.",
        ["A clerical error.", "Rehire or transfer inside a group."],
        ["Confirm the joining date with the employer's HR."]),
}
_GENERIC = ("This needs a human reviewer to assess it.",
            ["Normal variation in how documents are produced or scanned."],
            ["Compare with the original document."])
_SEVERITY_RANK = {Severity.high: 3, Severity.medium: 2, Severity.low: 1, Severity.info: 0}


def _play(finding: Finding) -> tuple[str, list[str], list[str]]:
    return PLAYBOOK.get(finding.discrepancy_type or "") or PLAYBOOK.get(finding.detector) or _GENERIC


def apply_playbook(finding: Finding) -> None:
    why, benign, verify = _play(finding)
    if why and why not in finding.explanation:
        finding.explanation = f"{finding.explanation.rstrip()} Why it matters: {why}"
    finding.benign_alternatives = _merge(finding.benign_alternatives, benign)
    finding.recommended_verification = _merge(finding.recommended_verification, verify)
    if finding.status == FindingStatus.POTENTIAL_MANIPULATION and not finding.benign_alternatives:
        finding.benign_alternatives = list(_GENERIC[1])


def _merge(existing: list[str], extra: list[str]) -> list[str]:
    seen = {e.strip().casefold() for e in existing}
    out = list(existing)
    for item in extra:
        key = item.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


# ---- correlation
def _overlap(a: BBox, b: BBox) -> bool:
    ix = min(a.x1, b.x1) - max(a.x0, b.x0)
    iy = min(a.y1, b.y1) - max(a.y0, b.y0)
    if ix <= 0 or iy <= 0:
        return False
    inter = ix * iy
    return inter / max(min(a.area, b.area), 1.0) >= 0.3


def correlate_findings(findings: list[Finding], docs: list[Document]) -> None:
    """Links findings that share a location or a field: the basis for 'relationships between findings'."""
    fields_by_id = {f.id: f for d in docs for f in d.fields}

    def regions(finding: Finding) -> list[tuple[str, int, BBox]]:
        out = []
        if finding.doc_id and finding.page is not None and finding.bbox:
            out.append((finding.doc_id, finding.page, finding.bbox))
        for fid in finding.related_field_ids:
            field = fields_by_id.get(fid)
            if field:
                out.append((field.doc_id, field.page, field.bbox))
        for ev in finding.evidence:
            if ev.doc_id and ev.page is not None and ev.bbox:
                out.append((ev.doc_id, ev.page, ev.bbox))
        return out

    all_regions = {f.id: regions(f) for f in findings}
    for i, a in enumerate(findings):
        for b in findings[i + 1:]:
            shared_field = set(a.related_field_ids) & set(b.related_field_ids)
            spatial = any(
                da == db and pa == pb and _overlap(ba, bb)
                for da, pa, ba in all_regions[a.id] for db, pb, bb in all_regions[b.id]
            )
            if shared_field or spatial:
                if b.id not in a.related_finding_ids:
                    a.related_finding_ids.append(b.id)
                if a.id not in b.related_finding_ids:
                    b.related_finding_ids.append(a.id)

    by_id = {f.id: f for f in findings}
    for finding in findings:
        kinds = {by_id[o].category.value.replace("_", "-") for o in finding.related_finding_ids if o in by_id}
        kinds.discard(finding.category.value.replace("_", "-"))
        if kinds:
            finding.explanation = (
                f"{finding.explanation.rstrip()} Corroboration: {len(finding.related_finding_ids)} other "
                f"finding(s) concern the same field or region, from independent {' and '.join(sorted(kinds))} "
                "checks. Independent signals increase the priority for review, but don't establish a conclusion."
            )


# ---- LLM enrichment
def _stable_facts(finding: Finding, docs_by_id: dict[str, Document]) -> str:
    """Deterministic text only: no generated ids or paths, so replays hit the cache."""
    lines = [
        f"Detector: {finding.detector}",
        f"Status: {finding.status.value}",
        f"Category: {finding.category.value}",
        f"Severity: {finding.severity.value}",
        f"Confidence: {finding.confidence:.2f}",
        f"Title: {finding.title}",
        f"Measured facts: {finding.explanation}",
    ]
    doc = docs_by_id.get(finding.doc_id or "")
    if doc:
        lines.append(f"Primary document type: {doc.doc_type.value}, format {doc.format.value}")
    for ev in finding.evidence[:6]:
        data = {k: v for k, v in sorted(ev.data.items()) if isinstance(v, (str, int, float, bool))}
        if data:
            lines.append(f"Evidence '{ev.label}': {data}")
    return "\n".join(lines)


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for match in _NUM_RE.findall(text):
        value = match.replace(",", "")
        out.add(value.rstrip("0").rstrip(".") if "." in value else value)
    return out


def validate_answer(answer: InvestigationAnswer, facts: str) -> str | None:
    """Returns why an answer must be rejected, or None if acceptable."""
    text = " ".join([answer.reasoning, *answer.benign_alternatives, *answer.what_would_confirm,
                     *answer.what_would_refute])
    if VERDICT_RE.search(text):
        return "states a verdict"
    known = _numbers(facts)
    invented = {n for n in _numbers(text) if len(n.replace(".", "")) >= 3 and n not in known}
    if invented:
        return "cites numbers absent from the evidence"
    if not answer.reasoning.strip():
        return "empty reasoning"
    return None


def pii_values(docs: list[Document]) -> list[str]:
    out = []
    for doc in docs:
        for f in doc.fields:
            if f.value_type in (ValueType.name, ValueType.address, ValueType.id_number,
                                ValueType.account_number) or f.name in ("date_of_birth", "employer_name"):
                out.append(f.value_raw)
    return out


def _priority(finding: Finding) -> tuple:
    status_rank = {FindingStatus.POTENTIAL_MANIPULATION: 2, FindingStatus.INCONSISTENCY: 1,
                   FindingStatus.OBSERVATION: 0}
    return (-status_rank[finding.status], -_SEVERITY_RANK[finding.severity], -finding.confidence,
            finding.detector, finding.title)


def _eligible(finding: Finding) -> bool:
    return finding.status != FindingStatus.OBSERVATION or _SEVERITY_RANK[finding.severity] >= 2


def investigate(findings: list[Finding], docs: list[Document], client: LLMClient | None = None,
                stats: dict[str, Any] | None = None) -> list[Finding]:
    stats = stats if stats is not None else {}
    stats.update({"llm_enriched": 0, "llm_rejected": 0, "llm_failed": 0, "providers": {}, "deterministic": 0,
                  "skipped_budget": 0})
    for finding in findings:
        apply_playbook(finding)
    correlate_findings(findings, docs)

    client = client or get_client()
    docs_by_id = {d.id: d for d in docs}
    pii = pii_values(docs)
    deadline = time.monotonic() + LLM_TIME_BUDGET_S
    queue = sorted((f for f in findings if _eligible(f)), key=_priority)
    for position, finding in enumerate(queue):
        if position >= LLM_MAX_FINDINGS or time.monotonic() > deadline:
            stats["skipped_budget"] = len(queue) - position
            break
        facts = _stable_facts(finding, docs_by_id)
        strength = "strong" if _SEVERITY_RANK[finding.severity] >= 3 else "fast"
        try:
            result = client.complete_json("investigate_finding", facts, InvestigationAnswer,
                                          strength=strength, system=SYSTEM, pii_values=pii)
        except Exception as exc:  # noqa: BLE001 - LLM problems may never reach a user as an error
            log.warning("investigation call failed: %s", type(exc).__name__)
            stats["llm_failed"] += 1
            continue
        if not result.ok:
            stats["llm_failed"] += 1
            stats["last_error"] = result.error
            # Once every provider is out, don't spend time on the remaining findings.
            if not client.any_live_provider() and not _settings_demo():
                break
            continue
        reason = validate_answer(result.data, facts)
        if reason:
            stats["llm_rejected"] += 1
            log.info("llm answer rejected: %s", reason)
            continue
        _apply_answer(finding, result)
        stats["llm_enriched"] += 1
        key = result.provider or "unknown"
        stats["providers"][key] = stats["providers"].get(key, 0) + 1
    stats["deterministic"] = sum(1 for f in findings if f.reasoning.mode == "deterministic")
    return findings


def _settings_demo() -> bool:
    from config.settings import settings

    return settings.demo_cache


def _apply_answer(finding: Finding, result) -> None:
    answer: InvestigationAnswer = result.data
    label = "Cached AI reasoning" if result.mode == "demo_cache" else "AI reasoning"
    finding.explanation = f"{finding.explanation.rstrip()} {label} ({result.provider}/{result.model}): {answer.reasoning.strip()}"
    finding.benign_alternatives = _merge(finding.benign_alternatives, answer.benign_alternatives[:4])
    verify = [f"To confirm: {v}" for v in answer.what_would_confirm[:3]] + \
             [f"To refute: {v}" for v in answer.what_would_refute[:3]]
    finding.recommended_verification = _merge(finding.recommended_verification, verify)
    finding.reasoning = ReasoningProvenance(mode=result.mode, provider=result.provider, model=result.model,
                                            prompt_hash=result.prompt_hash)


# ---- case summary
def deterministic_summary(findings: list[Finding], docs: list[Document], risk: str) -> str:
    processed = [d for d in docs if d.status.value in ("ok", "degraded")]
    counts = {s: sum(1 for f in findings if f.status == s) for s in FindingStatus}
    text = (
        f"{len(processed)} of {len(docs)} document(s) were processed. The system recorded "
        f"{counts[FindingStatus.OBSERVATION]} observation(s), {counts[FindingStatus.INCONSISTENCY]} "
        f"inconsistency(ies) and {counts[FindingStatus.POTENTIAL_MANIPULATION]} potential manipulation "
        f"hypothesis(es). Risk level for prioritizing review: {risk}."
    )
    top = sorted((f for f in findings if f.status != FindingStatus.OBSERVATION), key=_priority)[:3]
    if top:
        text += " Highest priority: " + "; ".join(f.title for f in top) + "."
    text += " These results are prompts for human review, not conclusions."
    return text


def summarize_case(findings: list[Finding], docs: list[Document], risk: str,
                   client: LLMClient | None = None) -> tuple[str, ReasoningProvenance]:
    base = deterministic_summary(findings, docs, risk)
    notable = sorted((f for f in findings if _eligible(f)), key=_priority)[:10]
    if not notable:
        return base, ReasoningProvenance(mode="deterministic")
    client = client or get_client()
    facts = base + "\n" + "\n".join(
        f"- [{f.status.value}/{f.severity.value}, confidence {f.confidence:.2f}] {f.title}" for f in notable)
    try:
        result = client.complete_json("summarize_case", facts, CaseSummaryAnswer, strength="strong",
                                      system=SYSTEM, pii_values=pii_values(docs))
    except Exception:  # noqa: BLE001
        return base, ReasoningProvenance(mode="deterministic")
    if not result.ok or VERDICT_RE.search(result.data.summary) or not result.data.summary.strip():
        return base, ReasoningProvenance(mode="deterministic")
    invented = {n for n in _numbers(result.data.summary) if len(n.replace(".", "")) >= 3 and n not in _numbers(facts)}
    if invented:
        return base, ReasoningProvenance(mode="deterministic")
    return (f"{base}\n\nAI summary ({result.provider}/{result.model}): {result.data.summary.strip()}",
            ReasoningProvenance(mode=result.mode, provider=result.provider, model=result.model,
                                prompt_hash=result.prompt_hash))
