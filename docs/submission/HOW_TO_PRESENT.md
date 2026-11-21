# How to present the deck (10 minutes)

Deck: https://claude.ai/artifact/Hq2mUEXS8pQAbegxWXQJUP (14 slides, speaker notes on every slide).
Two speakers: **Unnati** opens and closes, **Pragya** drives the live demo. Swap if you prefer, but
decide before you start.

## Before you go on (30 minutes)

1. Plug in the laptop and turn off notifications.
2. Start Ollama (the app), then in a terminal run `make present` and wait for it to say it is serving.
3. Open http://localhost:8000. The top bar should say **AI LIVE**. If it says "Recorded AI", Ollama is not running. It still works.
4. Open the deck full screen in one window and the app in another, so you can switch with one key.
5. Open the six cases once so nothing loads for the first time in front of the judges.
6. Keep `docs/sample_dossier.pdf` and the demo video ready as a fallback.

## Timeline

| Time | What | Slides |
|---|---|---|
| 0:00 to 2:00 | Slides: who we are, the problem, our answer | 1 to 3 |
| 2:00 to 3:00 | Architecture and workflow, one breath each | 4 to 5 |
| 3:00 to 3:30 | Skip or touch lightly: project structure, tech stack | 6 to 7 |
| 3:30 to 8:00 | **Live demo** (see below) | switch to app |
| 8:00 to 9:00 | Feasibility, then limitations said openly | 11 to 12 |
| 9:00 to 10:00 | Future scope, thank you, questions | 13 to 14 |

If you are running late, cut slides 6 and 7 first. Never cut limitations.

## Slide by slide: what to say

1. **Cover.** "We are Team OhLLMa: Unnati and Pragya. Our problem statement is PS-2, AI-powered document forensics and contextual intelligence."
2. **Problem.** "This salary slip was edited from 48,320 to 84,320. OCR reads it perfectly and the loan moves on. Reading text is not the same as trusting it." Name the three gaps: visual edits, conflicts across documents, PDFs with hidden text.
3. **Solution.** "We treat the whole application as a case: look, reason, compare, explain." Point at the three statuses. "We never say fraud. A person decides."
4. **Architecture.** Trace the diagram left to right. Stress that independent signals must agree before anything is called a potential manipulation.
5. **Workflow.** "Ten stages, each one logged in a tamper-evident history. Six documents take under a minute."
6. **Project structure.** One sentence: eight folders, typed contracts, 469 tests on every push.
7. **Tech stack.** One sentence: open source, runs fully offline, local AI is optional.
8. **Features: forensics.** The edited net pay boxed with the ELA overlay. Say the four families of evidence.
9. **Features: review.** The reviewer's side: confirm, dismiss, escalate, report, verify.
10. **Features: visuals.** Cross-document map on the left, "seen before" on the right.
11. **Feasibility.** 469 tests, under a minute, no keys, one Docker image.
12. **Limitations.** Say it plainly: synthetic data only, 40% recall on poor scans, handwriting and Hindi partial, cannot tell who signed, hosted AI not tried with real keys. Judges trust this more than a polished claim.
13. **Future scope.** First: prove it on real, authorised samples.
14. **Thank you.** Leave the GitHub link on screen: github.com/PragyaUniverse/docuforensic-ai. Say "Questions?"

## Live demo click path (4.5 minutes)

1. **Home.** Open "An altered salary slip". Show the boxed net pay and the three signals pointing at it.
2. **Findings.** Click one finding, read the "innocent explanations" and "how to verify" lines.
3. **Compare documents.** "Nothing looks wrong on the page. Every conflict appears only when documents are read together." Open the map.
4. **An edited PDF.** The page shows 86,400, the PDF text layer stores 62,400.
5. **Seen before (Case E).** Same photo, account and phone as earlier applications under new names.
6. **History tab.** Edit a log entry, press Verify integrity, show it caught at the exact entry. Then restore it.
7. **Doc.** Ask "what did you find?", then press हिं to show Hindi. Keep it short.
8. **Report tab.** Download the PDF dossier, only if time allows.

## If something breaks

- **App will not load:** play the demo video, or show `docs/sample_dossier.pdf` and the screenshots in the README.
- **AI says "Recorded AI":** carry on. Say "this is a replay of a real run, clearly labelled".
- **Audit chain shows broken before you start:** press restore on the History tab first.

## Likely questions

- **Is it accurate?** "On synthetic data we generated, 30/30 manipulations on held-out seeds. On degraded scans only 40%. We don't claim real-world accuracy."
- **Why not just ask an LLM?** "The AI can't create or change a finding. Detection is deterministic and traceable; the AI only writes explanations."
- **Could it flag innocent people?** "It reports observations for a human. Every finding lists benign explanations. The clean case raises zero flags."
- **Real documents?** "Not tested yet. That is the first item in future scope."
- **Who signed?** "Unsupported. We detect reuse of the same signature pixels, not identity."
- **Privacy?** "Runs on your machine. Personal data is redacted before any optional hosted AI call."
