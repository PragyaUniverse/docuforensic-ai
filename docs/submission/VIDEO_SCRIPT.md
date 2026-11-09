# Demo Video Script (about 5:30)

A silent recording of every shot, with a timed voice-over sheet, can be made locally into `video/` (not committed). If the hackathon sets a shorter limit, cut the rows marked *(optional)*. Without them the video runs about 5:00.

**Setup before recording**
- Start the app with `make serve` (builds the site, then serves everything at http://localhost:8000), with Ollama running. `make api` plus `make ui` also works.
- Load every demo case once before recording, so AI answers come from the local cache and nothing waits on screen. "Seen before" loads the cases it compares with first, so give it a minute.
- Before recording, confirm or dismiss two or three findings on "Altered salary slip". That's what makes the line "Reviewers here confirmed … of … earlier flags from this check" appear under a finding.
- For the report check: download the report PDF once, then make a changed copy (open it in Preview, add a text box anywhere, and save it as a new file). In rehearsal, check that the copy shows "Changed since it was issued".
- Doc's tours show once per browser. To film one, use "take a quick tour" on the home page. For the rest of the recording, finish or skip them first so they don't pop up mid-shot.
- Browser at 1440x900 or larger, zoom 100%, notifications off, no `.env` contents or keys on screen.
- Check the note at the top right ("AI notes: on" or "recorded earlier") and say which one applies. Don't describe recorded answers as live.

| Time | On screen | Say | Caption |
|---|---|---|---|
| 0:00 | Salary slip, zoomed on net pay | "OCR reads a forged salary slip perfectly. We catch the forgery. Here's how." | OCR reads. We investigate. |
| 0:15 | Home page | "DocuForensic AI investigates a whole application: six documents for one applicant, all synthetic. Everything you'll see runs locally, on this laptop." | All data is synthetic |
| 0:30 | Open "Altered salary slip", press Run forensic analysis, progress running | "You can watch each step as it happens. Every step is written to a permanent history." | Upload → Classify → OCR → Structure → Forensics → Context → Correlate → Investigate → Evidence → Dossier |
| 0:45 | Evidence tab. Click a row | "Every value is a measurement, not a fact. It keeps its confidence and its exact location. Click a value, and there it is on the page." | OCR is never ground truth |
| 1:05 | Findings tab, salary slip, finding #2. Set Show to Error level analysis | "Here's the altered figure. Three independent signals agree: different ink, a smoother background patch, a different compression response." | 3 independent signals |
| 1:30 | Open the finding "Net pay in figures differs from net pay in words" | "And look at the document's own logic. Gross minus deductions gives 48,320. The words say 48,320. The figure says 84,320." | Figures vs words |
| 1:45 | Same finding: status, Could be innocent if, How to check, then the reviewer line under it | "The system does not call this forgery. It says potential manipulation, requires human review, lists innocent explanations, and says what would confirm or refute it. It even tells you how often reviewers here agreed with this check before." | Hypothesis, not verdict |
| 2:05 | Press How Doc reached this, let it play to Doc's call *(optional)* | "Every finding can replay its own reasoning: where it looked, what it measured, how the signals combined." | Explainable, step by step |
| 2:20 | Press Draft verification request, switch to हिंदी and back | "And the next step is written for you: a request to the issuer to confirm the figure, in English or Hindi, ready to edit and send." | From finding to action |
| 2:35 | Bank statement copied rows, then the signature finding | "A copied row, linked to its source. A signature with the same pixels as another document's." | Copy-move, signature reuse |
| 2:50 | Open "Conflicting documents", Compare documents tab, scroll | "Case C looks perfectly clean. Nothing visual is wrong. But read the documents together: a DOB off by one digit, a swapped account number, a different employer. Nine types of discrepancy. A second OCR engine confirms the digits aren't a misread." | Only visible together |
| 3:15 | See as a map. Click a red line, then Show in document *(optional)* | "Every conflict is a line on this map, and every line goes back to both original spots." | Trace any finding to its source |
| 3:25 | Open "Seen before", scroll to the Seen before section, point at the photo pair and the bank account | "A new applicant, with a different name. But this photo, this bank account and this phone number have already appeared on other applications in the system. Side by side, from the original pages. It could be a family sharing a phone, so it's flagged for review, not decided." | Repeated across applications |
| 3:55 | Open "Edited PDF", Findings tab. Set Show to Revision diff | "Here, a person sees 86,400, but the PDF's text layer says 62,400. A system that only reads text gets a different answer from the page. The file's own revision history shows the edit." | Beneath the page |
| 4:15 | Press Confirm on a finding, open the Report tab, Download PDF, then point at Download redacted PDF | "The reviewer decides, and each decision is logged. The report has every required section, and a redacted copy hides personal details for sharing." | Human oversight |
| 4:30 | Verify report page. Drop the downloaded report: Original report. Drop the changed copy: Changed since it was issued | "Anyone who receives a report can check it. This one is exactly as issued. This copy was changed afterwards, and the system knows." | Reports can't be quietly edited |
| 4:45 | Timeline tab: Verify integrity passes, Try editing an entry, Verify integrity fails at that entry, Undo the edit | "Now watch me edit the log directly. Verify integrity fails, at the exact entry." | Tamper-evident |
| 5:00 | Open Doc, switch to हिं, tap a suggestion *(optional)* | "Doc, the guide, explains findings in plain language, in English or Hindi. It's a guide, not the detector." | Help in Hindi too |
| 5:10 | "Consistent application" (quiet), then "Unreadable files" | "A clean case stays quiet. A corrupt file gets a clear message, not a crash." | Safe failure |
| 5:20 | README benchmark table, degraded row highlighted | "On synthetic held-out data: every manipulation found, no false flags. On degraded scans, recall falls to 40 percent. That's a real limitation, and it's published alongside the rest. It hasn't been tested on real documents." | Honest numbers |

**Rules for the recording**
- Doc, the animated character, is a guide you can chat with, not the detection system. Describe it that way on camera. A good moment: ask "Is this fake?" and show it refuse, then ask "explain #2" and follow the link. Drag it clear of anything you're showing, or hide it.
- The opening line is the hook you chose. It's fine as narration because we injected that edit ourselves and know it's altered. Everywhere else, use the system's wording: "potential manipulation", never "this is forged".
- On "Seen before", never say the applicant is a fraud or the same person. Say the details repeat and need checking.
- Show the "SYNTHETIC" watermark in at least one shot.
- Never say "works on real documents" or quote the held-out numbers without saying they're synthetic.
- Be ready to explain every part of the system on request (Rules 5.3, 11.5).
