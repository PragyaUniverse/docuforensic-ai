# Demo Video Script (about 4:45)

**Setup before recording**
- Run `make api` and `make ui`, with Ollama running, and load each demo case once so that AI answers come from the local cache and the recording is fast and repeatable.
- Browser at 1440x900 or larger, zoom 100%, notifications off, no `.env` contents or keys on screen.
- Check the note at the top right ("AI notes: on" or "recorded earlier") and say which one applies. Don't describe recorded answers as live.

| Time | On screen | Say | Caption |
|---|---|---|---|
| 0:00 | Salary slip, zoomed on net pay | "OCR reads a forged salary slip perfectly. We catch the forgery. Here's how." | OCR reads. We investigate. |
| 0:15 | Home page | "DocuForensic AI investigates a whole application: six documents for one applicant, all synthetic. Everything you'll see runs locally, on this laptop." | All data is synthetic |
| 0:30 | Open "An altered salary slip", press Check these documents, progress running | "You can watch each step as it happens. Every step is written to a permanent history." | Upload → Classify → OCR → Structure → Forensics → Context → Correlate → Investigate → Evidence → Dossier |
| 0:50 | Extracted data tab. Click a row | "Every value is a measurement, not a fact. It keeps its confidence and its exact location. Click a value, and there it is on the page." | OCR is never ground truth |
| 1:15 | Findings tab, salary slip, finding #2. Set Show to Error level analysis | "Here's the altered figure. Three independent signals agree: different ink, a smoother background patch, a different compression response." | 3 independent signals |
| 1:45 | Open the finding "Net pay in figures differs from net pay in words" | "And look at the document's own logic. Gross minus deductions gives 48,320. The words say 48,320. The figure says 84,320." | Figures vs words |
| 2:05 | Same finding: status, Could be innocent if, How to check | "The system does not call this forgery. It says potential manipulation, requires human review, lists innocent explanations, and says what would confirm or refute it." | Hypothesis, not verdict |
| 2:25 | Bank statement copied rows, then the signature finding | "A copied row, linked to its source. A signature with the same pixels as another document's." | Copy-move, signature reuse |
| 2:45 | Open "Documents that disagree", Compare documents tab, scroll | "Case C looks perfectly clean. Nothing visual is wrong. But read the documents together: a DOB off by one digit, a swapped account number, a different employer. Nine types of discrepancy. A second OCR engine confirms the digits aren't a misread." | Only visible together |
| 3:15 | See as a map. Click a red line, then Show in document | "Every conflict is a line on this map, and every line goes back to both original spots." | Trace any finding to its source |
| 3:30 | Open "An edited PDF", Findings tab. Set Show to Revision diff | "Here, a person sees 86,400, but the PDF's text layer says 62,400. A system that only reads text gets a different answer from the page. The file's own revision history shows the edit." | Beneath the page |
| 3:55 | Press Confirm on a finding, open the Report tab, Download PDF | "The reviewer decides, and each decision is logged. The report has every required section." | Human oversight |
| 4:10 | History tab: Verify integrity passes, Try editing an entry, Verify integrity fails at that entry, Undo the edit | "Now watch me edit the log directly. Verify integrity fails, at the exact entry." | Tamper-evident |
| 4:25 | "A clean application" (quiet), then "Files it can't read" | "A clean case stays quiet. A corrupt file gets a clear message, not a crash." | Safe failure |
| 4:35 | README benchmark table, degraded row highlighted | "On synthetic held-out data: every manipulation found, no false flags. On degraded scans, about a quarter. That's a real limitation, and it's published alongside the rest. It hasn't been tested on real documents." | Honest numbers |

**Rules for the recording**
- The opening line is the hook you chose. It's fine as narration because we injected that edit ourselves and know it's altered. Everywhere else, use the system's wording: "potential manipulation", never "this is forged".
- Show the "SYNTHETIC" watermark in at least one shot.
- Never say "works on real documents" or quote the held-out numbers without saying they're synthetic.
- Be ready to explain every part of the system on request (Rules 5.3, 11.5).
