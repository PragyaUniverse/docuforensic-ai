# Security and Privacy Review

> **Draft, status as of phase 1 of QA.** Items marked **Pending** are tested by `tests/e2e/` but the
> code under test hasn't landed yet, so they are design intent and not verified behaviour.

## Threat model

This is a local, single-user prototype processing synthetic documents. It has **no authentication**
by design (out of scope for the hackathon), so it must not be exposed to an untrusted network. The
main threats considered are malicious uploaded files, document text that tries to steer the LLM,
leaked API keys, and personal data reaching an external service.

## Review results

| Area | Status | Notes |
|---|---|---|
| Secrets in repo and history | **Verified clean** at this review | `scripts/secret_scan.sh` runs gitleaks over the full history and the working tree, a key-pattern grep, and a check that `.env` was never tracked. `.env` was in `.gitignore` before the first commit. Re-run before every public push. |
| Key handling in code | **Verified** | Only `config/settings.py` reads environment variables; no `os.environ` in `backend`, `pipeline`, `llm` or `audit`. The Gemini key goes in a header, not the URL. Tests with a fake network assert a canary key never appears in errors. |
| Upload: real type check | Verified in `pipeline/ingest.py` by reading | Magic-byte sniffing; a pixel limit guards against decompression bombs; encrypted PDFs handled; page count capped by `max_pages_per_doc`. |
| Upload: limits and filename handling | **Pending** | `test_upload_over_the_limit_is_413`, `test_upload_filename_cannot_escape_the_data_dir`. |
| `/files` path traversal, symlinks | **Pending** | Encoded and double-dot variants, the database file, and a symlink pointing out of `data_dir`. |
| CORS | **Pending** | Allow-list from settings. Test asserts an arbitrary origin isn't allowed. |
| Prompt injection | **Pending** | See below. |
| PII redaction before external LLM calls | **Partial, 1 bug** | Applied to the prompt, verified on the wire with a fake transport. See open issues. |
| PII in logs | Verified by reading the current log statements | Log lines carry exception types and provider names, not field values. `pipeline/ingest.py` uses `log.exception`, so a traceback could include a file path. Re-check when the backend lands. |
| Dependencies | `npm audit --omit=dev`: 0 vulnerabilities at this review | Python dependencies not yet audited (`pip-audit` not run). |
| Audit log integrity | **Pending** | Tamper test against the API. |

## Open issues

1. **Redaction misses identifiers followed by punctuation.** In `llm/redact.py`, the Aadhaar, phone,
   account and pincode patterns end in `(?![\d.,])`. An ID directly before a comma or full stop, such
   as `2345 6789 0123,`, is sent unredacted. Using `(?!\d|[.,]\d)` keeps money values safe while
   fixing this. `test_redaction_removes_identifiers_and_restores_them_locally` fails until it's fixed.
2. **Names and addresses are redacted only if passed in.** They have no pattern, so the investigator
   must pass them as `pii_values`. Must be confirmed when `llm/investigator.py` lands. The `system`
   prompt isn't redacted at all, so it must never contain document data.
3. **The tamper-demo endpoints are on by default** (`AUDIT_TAMPER_DEMO`) and unauthenticated. They
   exist for the demo. Anything beyond a local demo must set this to false.
4. **Stored data isn't encrypted.** Uploaded documents, extracted fields and audit payloads sit in
   plain files and SQLite under `var/`, with no retention policy. Acceptable for synthetic data, not
   for real personal data.

## Prompt injection

A document can contain any text, and that text reaches the LLM. Filtering attack phrases can't work,
so the defence is structural: **whatever the model says, it can only add explanatory text.**

Required properties, tested in `tests/e2e/test_prompt_injection.py` by simulating a model that fully
obeyed an attacker:

- `status`, `severity`, `confidence`, `bbox`, `detector`, `doc_id` and `review` can't change.
- Findings can't be removed or added by an LLM answer.
- Verdict language in a model answer doesn't reach the output.
- Document text in a prompt is fenced and described as untrusted data.
- Injected text can't auto-dismiss anything end to end.

The tests that exercise `llm/investigator.py` are **pending**, because it hasn't landed.

## OWASP Machine Learning Security Top 10 notes

Used as guidance. No claim of compliance.

| Risk | Relevance here | Position |
|---|---|---|
| ML01 Input manipulation | Forged documents crafted to evade detectors are the core adversary | Not defended beyond multiple independent detectors. Stated as a limitation: a careful forger who knows the detectors can evade them. |
| ML02 Data poisoning | No model is trained on user data | Not applicable. |
| ML03 Model inversion, ML04 Membership inference | No proprietary trained model | Not applicable. |
| ML05 Model theft | Only public models | Not applicable. |
| ML06 AI supply chain | Pretrained OCR models, Ollama model, PyPI and npm packages | `THIRD_PARTY.md` inventories them. Python versions are lower-bounded rather than pinned, which is a known gap. No pickled model files are loaded by project code. |
| ML07 Transfer learning | No fine-tuning | Not applicable. |
| ML08 Model skewing | No online learning; reviewer decisions don't retrain anything | Not applicable. |
| ML09 Output integrity | LLM output is untrusted | Schema validation, plus the structural limits above. |
| ML10 Model poisoning | No training | Not applicable beyond supply chain. |

Also relevant from LLM-specific guidance: prompt injection and sensitive data disclosure, covered
above.

## Standards

Handling is aligned with the principles of ISO/IEC 27037, 27041 and 27042 and NIST SP 800-86
(hashing on submission, an append-only log of processing, preserving the link from original to
finding). This project does not claim formal compliance with any of them.
