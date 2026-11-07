"""Draft verification requests: a short letter asking an issuer to confirm exactly the doubtful values.

Built only from the finding's own evidence, so every value in a letter is one the checks read. The
letter is a draft for a person to review, edit and send. The app never sends anything, and the
wording never suggests wrongdoing: it asks for a routine confirmation.
"""
from __future__ import annotations

from typing import Any

from backend.crosscase import applicant_name
from models.schemas import BBox, Case, DocType, Document, EvidenceKind, Finding, FindingCategory

# Who to ask, by the document the doubt is about. Earlier is better: an issuer beats the applicant.
_PRIORITY = [DocType.salary_slip, DocType.bank_statement, DocType.address_proof, DocType.id_proof,
             DocType.declaration, DocType.application_form]

_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "subject": "Request to confirm details, reference {code}",
        "greeting": "Dear Sir or Madam,",
        "greeting_applicant": "Dear {applicant},",
        "intro": "We are reviewing an application (reference {code}) from {applicant}. It includes {a_doc} that appears to have "
                 "been issued by {issuer}. As part of our routine checks, could you please confirm the following from your records?",
        "intro_plain": "We are reviewing an application (reference {code}) from {applicant}, which includes {a_doc}. As part of our "
                       "routine checks, could you please confirm the following from your records?",
        "intro_applicant": "We are reviewing your application (reference {code}). As part of our routine checks, could you please "
                           "confirm the following?",
        "multi": "{label}: our documents show {values}. Which is correct in your records?",
        "on": "{value} on the {doc}",
        "and": " and ",
        "single": "{label}: {value}, as shown on the {doc}. Is this correct?",
        "words": "The amount on the {doc} is printed as {figures} in figures and \"{words}\" in words. Which amount did you issue?",
        "credit": "A credit of {amount} on {date} ({description}). Please confirm it in your records.",
        "balance": "The running balance on page {page} reads {stated}. Please confirm the balance on that date.",
        "region_field": "The {label} on page {page} of the {doc} reads {value}. Is this the figure you issued?",
        "region": "Please confirm that page {page} of the enclosed {doc}, in particular the marked area, matches the copy in your records.",
        "signature": "Please confirm that the signature on the enclosed {doc} was applied by you or your organisation.",
        "signature_applicant": "Please send us a freshly signed copy of the {doc}.",
        "photo_applicant": "Please confirm that the photo on your application is of you. We may ask you to bring photo ID to a branch or a video call.",
        "copy": "If possible, please send us a certified copy of this document.",
        "account_holder": "Please confirm the name of the holder of account {value}.",
        "shared": "{detail} {value}: please confirm in whose name it is registered.",
        "close": "Please reply to this request directly. This is a routine check and doesn't suggest that anyone has done anything wrong.",
        "sign": "Yours faithfully,\n[Your name]\n[Your role and organisation]",
        "issuing_authority": "the issuing authority",
        "note": "Drafted from this finding's evidence. Review and edit it before sending: this app never sends anything.",
    },
    "hi": {
        "subject": "विवरण की पुष्टि हेतु अनुरोध, संदर्भ {code}",
        "greeting": "महोदय/महोदया,",
        "greeting_applicant": "प्रिय {applicant},",
        "intro": "हम {applicant} के एक आवेदन (संदर्भ {code}) की समीक्षा कर रहे हैं। इसमें एक {doc} शामिल है, जो {issuer} द्वारा जारी "
                 "किया गया प्रतीत होता है। नियमित जाँच के अंतर्गत, कृपया अपने अभिलेखों से निम्नलिखित की पुष्टि करें:",
        "intro_plain": "हम {applicant} के एक आवेदन (संदर्भ {code}) की समीक्षा कर रहे हैं, जिसमें एक {doc} शामिल है। नियमित जाँच के "
                       "अंतर्गत, कृपया अपने अभिलेखों से निम्नलिखित की पुष्टि करें:",
        "intro_applicant": "हम आपके आवेदन (संदर्भ {code}) की समीक्षा कर रहे हैं। नियमित जाँच के अंतर्गत, कृपया निम्नलिखित की पुष्टि करें:",
        "multi": "{label}: हमारे दस्तावेज़ों में {values} दिखाया गया है। आपके अभिलेखों के अनुसार कौन-सा सही है?",
        "on": "{doc} पर {value}",
        "and": " और ",
        "single": "{label}: {value}, जैसा कि {doc} पर दिखाया गया है। क्या यह सही है?",
        "words": "{doc} पर राशि अंकों में {figures} और शब्दों में \"{words}\" छपी है। आपने कौन-सी राशि जारी की थी?",
        "credit": "{date} को {amount} की जमा राशि ({description})। कृपया अपने अभिलेखों में इसकी पुष्टि करें।",
        "balance": "पृष्ठ {page} पर चालू शेष {stated} दर्ज है। कृपया उस तिथि का शेष बताएं।",
        "region_field": "{doc} के पृष्ठ {page} पर {label} {value} दर्ज है। क्या यही आपने जारी किया था?",
        "region": "कृपया पुष्टि करें कि संलग्न {doc} का पृष्ठ {page}, विशेष रूप से चिह्नित भाग, आपके अभिलेखों की प्रति से मेल खाता है।",
        "signature": "कृपया पुष्टि करें कि संलग्न {doc} पर हस्ताक्षर आपके या आपकी संस्था द्वारा किए गए थे।",
        "signature_applicant": "कृपया {doc} की नए सिरे से हस्ताक्षरित प्रति भेजें।",
        "photo_applicant": "कृपया पुष्टि करें कि आपके आवेदन पर लगी फ़ोटो आपकी ही है। हम आपसे शाखा में या वीडियो कॉल पर फ़ोटो पहचान पत्र दिखाने को कह सकते हैं।",
        "copy": "यदि संभव हो, तो कृपया इस दस्तावेज़ की प्रमाणित प्रति भेजें।",
        "account_holder": "कृपया खाता {value} के धारक का नाम बताएं।",
        "shared": "{detail} {value}: कृपया बताएं कि यह किसके नाम पर दर्ज है।",
        "close": "कृपया इस अनुरोध का सीधे उत्तर दें। यह एक नियमित जाँच है और इसका अर्थ यह नहीं है कि किसी ने कुछ गलत किया है।",
        "sign": "भवदीय,\n[आपका नाम]\n[आपका पद और संस्था]",
        "issuing_authority": "जारीकर्ता प्राधिकरण",
        "note": "यह मसौदा इस निष्कर्ष के प्रमाणों से तैयार किया गया है। भेजने से पहले इसे जाँचें और बदलें: यह ऐप कुछ भी नहीं भेजता।",
    },
}

FIELD_LABELS = {
    "en": {
        "net_pay": "Net pay", "gross_pay": "Gross pay", "date_of_birth": "Date of birth", "bank_account_number": "Bank account number",
        "pan_number": "PAN", "id_number": "ID number", "employer_name": "Employer name", "date_of_joining": "Date of joining",
        "declared_monthly_income": "Declared monthly income", "person_name": "Name", "address": "Address", "phone": "Mobile number",
        "email": "Email", "designation": "Designation", "total_deductions": "Total deductions", "basic_pay": "Basic pay",
    },
    "hi": {
        "net_pay": "शुद्ध वेतन", "gross_pay": "सकल वेतन", "date_of_birth": "जन्म तिथि", "bank_account_number": "बैंक खाता संख्या",
        "pan_number": "पैन", "id_number": "पहचान संख्या", "employer_name": "नियोक्ता का नाम", "date_of_joining": "कार्यग्रहण तिथि",
        "declared_monthly_income": "घोषित मासिक आय", "person_name": "नाम", "address": "पता", "phone": "मोबाइल नंबर",
        "email": "ईमेल", "designation": "पद", "total_deductions": "कुल कटौती", "basic_pay": "मूल वेतन",
    },
}
DOC_LABELS = {
    "en": {"salary_slip": "salary slip", "bank_statement": "bank statement", "application_form": "application form",
           "id_proof": "ID document", "address_proof": "address proof", "declaration": "declaration", "unknown": "document"},
    "hi": {"salary_slip": "वेतन पर्ची", "bank_statement": "बैंक विवरण", "application_form": "आवेदन पत्र",
           "id_proof": "पहचान पत्र", "address_proof": "पते का प्रमाण", "declaration": "घोषणा पत्र", "unknown": "दस्तावेज़"},
}
_DETAIL_HI = {"Mobile number": "मोबाइल नंबर", "Email address": "ईमेल", "Bank account number": "बैंक खाता संख्या",
              "PAN": "पैन", "ID number": "पहचान संख्या", "Applicant photo": "फ़ोटो", "Signature": "हस्ताक्षर"}


def case_code(case_id: str) -> str:
    """The same short reference the screens show."""
    return "DF-" + case_id.removeprefix("case_")[:6].upper()


def _label(name: str, lang: str) -> str:
    return FIELD_LABELS[lang].get(name) or name.replace("_", " ").capitalize()


def _doc_label(doc: Document | None, lang: str) -> str:
    return DOC_LABELS[lang].get(doc.doc_type.value if doc else "unknown", DOC_LABELS[lang]["unknown"])


def _field(doc: Document | None, name: str) -> str | None:
    if doc is None:
        return None
    hit = next((f for f in doc.fields if f.name == name and f.value_raw.strip()), None)
    return hit.value_raw.strip() if hit else None


def _overlaps(a: BBox, b: BBox) -> bool:
    return a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1


def _target(finding: Finding, docs: dict[str, Document]) -> Document | None:
    ids = [finding.doc_id, *finding.related_doc_ids, *[e.doc_id for e in finding.evidence]]
    involved = [docs[i] for i in dict.fromkeys(i for i in ids if i in docs)]
    if not involved:
        return None
    rank = {t: i for i, t in enumerate(_PRIORITY)}
    return min(involved, key=lambda d: rank.get(d.doc_type, len(rank)))


def _issuer(doc: Document, lang: str) -> str:
    t = doc.doc_type
    if t == DocType.salary_slip:
        name = _field(doc, "employer_name")
        return (f"HR / Payroll, {name}" if lang == "en" else f"मानव संसाधन / वेतन विभाग, {name}") if name else (
            "your HR or payroll team" if lang == "en" else "आपका मानव संसाधन विभाग")
    if t == DocType.bank_statement:
        bank, ifsc = _field(doc, "bank_name"), _field(doc, "ifsc")
        if bank:
            return f"{bank}" + (f" ({ifsc})" if ifsc else "")
        return "your bank" if lang == "en" else "आपका बैंक"
    if t == DocType.address_proof:
        return _field(doc, "issuer_name") or ("the issuer" if lang == "en" else "जारीकर्ता")
    return _TEXT[lang]["issuing_authority"]


def _join_docs(labels: list[str], lang: str) -> str:
    labels = list(dict.fromkeys(labels))
    joiner = ", " if lang == "en" else ", "
    return labels[0] if len(labels) == 1 else joiner.join(labels[:-1]) + _TEXT[lang]["and"] + labels[-1]


def _questions(finding: Finding, docs: dict[str, Document], target: Document, lang: str, to_applicant: bool) -> list[str]:
    t = _TEXT[lang]
    out: list[str] = []
    refs: dict[str, list[tuple[str, str, Document | None]]] = {}
    for e in finding.evidence:
        if e.kind == EvidenceKind.field_ref and e.data.get("field") and e.data.get("value"):
            raw = str(e.data["value"]).strip()
            norm = str(e.data.get("normalized") or raw).strip().casefold()
            refs.setdefault(e.data["field"], []).append((norm, raw, docs.get(e.doc_id or "")))
    for name, values in refs.items():
        # One value printed in two formats is one value: group by the normalised form.
        groups: dict[str, tuple[str, list[str]]] = {}
        for norm, raw, doc in values:
            shown, labels = groups.setdefault(norm, (raw, []))
            labels.append(_doc_label(doc, lang))
        if len(groups) > 1:
            parts = [t["on"].format(value=raw, doc=_join_docs(labels, lang)) for raw, labels in list(groups.values())[:3]]
            out.append(t["multi"].format(label=_label(name, lang), values="; ".join(parts) if len(parts) > 2 else t["and"].join(parts)))
        else:
            (raw, labels), = groups.values()
            out.append(t["single"].format(label=_label(name, lang), value=raw, doc=_join_docs(labels, lang)))
    for e in finding.evidence:
        d = e.data or {}
        doc = docs.get(e.doc_id or "") or target
        if "value_in_words" in d and "value_in_figures" in d:
            words = str(d.get("text") or d["value_in_words"]).split(":", 1)[-1].strip()
            out.append(t["words"].format(doc=_doc_label(doc, lang), figures=d["value_in_figures"], words=words))
        elif {"amount", "date"} <= d.keys():
            out.append(t["credit"].format(amount=d["amount"], date=d["date"], description=d.get("description") or "-"))
        elif {"expected", "stated"} <= d.keys():
            out.append(t["balance"].format(page=(e.page or 0) + 1, stated=d["stated"]))
        elif "other_case_id" in d and d.get("detail") in ("Applicant photo", "Signature"):
            if to_applicant:
                out.append(t["photo_applicant"] if d["detail"] == "Applicant photo" else
                           t["signature_applicant"].format(doc=_doc_label(doc, lang)))
        elif "other_case_id" in d and d.get("value"):
            # The screens mask the value. The letter goes to whoever holds it, so it uses this application's own reading.
            own = next((f.value_raw for f in doc.fields if f.id == e.field_id), None) if e.field_id else None
            value = own or d["value"]
            if d.get("detail") == "Bank account number":
                out.append(t["account_holder"].format(value=value))
            else:
                detail = d.get("detail", "")
                out.append(t["shared"].format(detail=_DETAIL_HI.get(detail, detail) if lang == "hi" else detail, value=value))
    if not out and finding.detector == "visual.signature_reuse":
        key = "signature_applicant" if to_applicant else "signature"
        out.append(t[key].format(doc=_doc_label(target, lang)))
    if not out and finding.bbox is not None and finding.page is not None:
        primary = docs.get(finding.doc_id or "") or target
        near = [f for f in primary.fields if f.page == finding.page and _overlaps(f.bbox, finding.bbox)]
        if near:
            f = near[0]
            out.append(t["region_field"].format(label=_label(f.name, lang).lower() if lang == "en" else _label(f.name, lang),
                                                page=finding.page + 1, doc=_doc_label(primary, lang), value=f.value_raw))
        else:
            out.append(t["region"].format(page=finding.page + 1, doc=_doc_label(primary, lang)))
    if finding.category in (FindingCategory.visual, FindingCategory.structural) and not to_applicant:
        out.append(t["copy"])
    return list(dict.fromkeys(out))[:6]


def draft(case: Case, docs: list[Document], finding: Finding, lang: str = "en") -> dict[str, Any]:
    lang = lang if lang in _TEXT else "en"
    t = _TEXT[lang]
    by_id = {d.id: d for d in docs}
    target = _target(finding, by_id)
    code = case_code(case.id)
    applicant = applicant_name(docs) or ("the applicant" if lang == "en" else "आवेदक")
    if target is None:
        return {"available": False, "lang": lang, "message": "This finding has no document to ask about."}
    if finding.detector.startswith("crosscase."):
        # A shared account is the bank's to confirm. Other shared details are the applicant's to explain.
        shared_account = any((e.data or {}).get("detail") == "Bank account number" for e in finding.evidence)
        bank = next((d for d in docs if d.doc_type == DocType.bank_statement), None)
        target = bank if shared_account and bank else next(
            (d for d in docs if d.doc_type == DocType.application_form), target)
    to_applicant = target.doc_type in (DocType.application_form, DocType.declaration)
    questions = _questions(finding, by_id, target, lang, to_applicant)
    if to_applicant:
        to = applicant
        opening = [t["greeting_applicant"].format(applicant=applicant), "", t["intro_applicant"].format(code=code)]
    else:
        to = _issuer(target, lang)
        doc_label = _doc_label(target, lang)
        a_doc = (("an " if doc_label[:1].lower() in "aeiou" or doc_label.startswith("ID") else "a ") + doc_label) if lang == "en" else doc_label
        key = "intro_plain" if to == t["issuing_authority"] else "intro"
        opening = [t["greeting"], "", t[key].format(applicant=applicant, code=code, doc=doc_label, a_doc=a_doc, issuer=to.rstrip("."))]
    numbered = [f"{i}. {q}" for i, q in enumerate(questions, start=1)]
    body = "\n".join([*opening, "", *numbered, "", t["close"], "", t["sign"]])
    return {
        "available": True, "lang": lang, "to": to, "subject": t["subject"].format(code=code), "body": body,
        "about_document": target.filename, "questions": len(questions), "note": t["note"],
    }
