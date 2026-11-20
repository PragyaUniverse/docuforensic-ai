# 10-minute presentation run sheet

10 minutes in total: about 2 minutes of slides, 6 of live demo, 1 of honest limits and 1 to close. Questions come after.

## 30 minutes before

1. Open the Ollama app, the local AI. Its icon should appear in the menu bar.
2. In a terminal, in the project folder, run:
   ```bash
   make present
   ```
   This builds the site and opens the app at http://localhost:8000 with only the six demo cases, already analysed. Your normal data is untouched.
3. Open http://localhost:8000 in the browser:
   - The top right should say **DOC ONLINE · AI LIVE**. If it says **Recorded AI**, Ollama isn't running. Everything still works; just say "AI notes are recorded" instead of "live".
   - Browser zoom at 100%, full screen, notifications off (Focus / Do Not Disturb).
   - Close any tab or window that shows `.env`, keys or personal details.
4. Open the slides and keep the backup video (`video/DocuForensic_demo_no_voice.mp4`) ready in another window.
5. No internet is needed. Everything runs on the laptop.

## The 10 minutes

| Time | Who shows what | What to say (short) |
|---|---|---|
| 0:00–1:00 | **Slides:** title, the problem | "Loan fraud often hides in edited documents. Normal OCR reads an edited salary slip perfectly and sees nothing wrong." |
| 1:00–2:00 | **Slides:** how it works (diagram) | "DocuForensic AI checks all six documents of one application together: visual forensics, the documents' own maths, cross-document comparison, and a tamper-evident history. It runs fully offline." |
| 2:00–2:30 | **App: home page** | "All data is synthetic. Six demo cases, each showing one kind of problem." |
| 2:30–3:45 | **Case B: Visual investigation** → Findings → click **#2** → Show: **Error level analysis** | "Three independent signals agree on this figure. It says *potential manipulation, requires human review*, never 'fraud'." Then click **#5**: "Gross minus deductions is 48,320, the words say 48,320, the figure says 84,320." |
| 3:45–4:15 | Same finding → **Draft verification request** → **हिंदी** | "It drafts the letter to confirm with the employer, in English or Hindi." |
| 4:15–5:00 | **Case C: Cross-document investigation** → **Compare** → **See as a map** | "Each document looks clean alone. Together, the account number, dates and employer disagree. Every line goes back to both original spots." |
| 5:00–5:45 | **Case E: Seen before** → Overview → **Seen before** section | "A new applicant with a different name, but the photo, bank account and phone already appear on other applications. Flagged for review, not decided." |
| 5:45–6:30 | **Case D: PDF structure investigation** → Findings → **#1** | "The page shows 86,400. The PDF's hidden text layer says 62,400." |
| 6:30–7:15 | Case B → **Report** → **Download PDF**, then header **Verify report** → drop that PDF | "Every report's fingerprint is recorded. Anyone can check a report is the original." |
| 7:15–8:00 | Case B → **Timeline** → **Verify integrity** → **Try editing an entry** → **Verify integrity** → **Undo the edit** | "If anyone edits the history, the exact entry is caught." **Always press Undo afterwards.** |
| 8:00–9:00 | **Slides:** results and limits | "On synthetic held-out data, every manipulation found, no false flags. On degraded scans recall drops to 40%. Not yet tested on real documents. We publish that openly." |
| 9:00–10:00 | **Slides:** close | "Human in the loop, explainable findings, offline and private. Thank you." |

If time runs short, skip the Case D step first, then the verification letter.

## If something goes wrong

- **The app won't open:** in the terminal press Ctrl+C, run `make present` again, and refresh the browser.
- **The AI is slow or off:** carry on. The checks don't need the AI. Only the explanation notes do.
- **Anything else:** switch to the backup video and talk over it.

## Questions judges may ask

- **"Is it accurate on real documents?"** "Not tested on real documents yet; all numbers are on synthetic data, which we generated so we know the ground truth."
- **"Does the AI make the decision?"** "No. The checks are measurements. The AI only writes explanation notes and can't change a finding. A person confirms or dismisses each one."
- **"Why not just call it fraud?"** "A difference can be innocent: a reprint, a scanner, a typo. So every finding lists innocent explanations and how to check."
- **"Where does data go?"** "Nowhere. It runs on this laptop. If a hosted AI is used, personal details are removed first."
- **"What's the tech stack?"** "Python with FastAPI, OpenCV and Tesseract and RapidOCR for reading, PyMuPDF for PDFs, SQLite with a hash-chained history, and React for the interface."
