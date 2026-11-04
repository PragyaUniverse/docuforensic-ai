# Models and Methods

Forensic methods behind DocuForensic AI, what each one can honestly show, and what makes it wrong.
None of these methods proves manipulation: each gives a measurement that a reviewer weighs. This
file covers the methods and the demo dataset. Actual results belong in
`docs/benchmark_results.md`, and the implementation lives in `pipeline/`.

## 1. Forensic methods

### Error Level Analysis (ELA)

- **Idea:** recompress the image as JPEG at a known quality and map the pixel differences. Content
  with a different compression history can have a different error level.
- **Strengths:** cheap, visual, easy to explain to a reviewer. Works well on patches added after the
  last compression.
- **False positives:** high-contrast edges and text always show higher error, so a typed value can
  look "bright" with no edit at all. Colored banners, stamps and watermarks differ from plain paper.
  Repeated recompression flattens the signal.
- **Use here:** compare like with like (paper background against paper background, or text against
  text). Never read absolute brightness, and never use ELA as the only evidence.

### Noise residual

- **Idea:** subtract a denoised copy of the image and compare local residual statistics. A scan has
  a fairly uniform noise floor, while a synthetic patch is often too clean.
- **Strengths:** catches flat fill patches that are visually invisible.
- **False positives:** dark or saturated regions compress noise differently, and uneven lighting,
  smooth printed tints and heavy JPEG compression all change the residual. Blur removes it.

### Copy-move

- **Idea:** match overlapping blocks or keypoints within one page and look for many matches sharing
  one displacement vector.
- **Strengths:** independent of compression history; localizes both the source and the destination.
- **False positives:** documents repeat by design. Identical words, table rows, digits and rule
  lines match each other, even when never edited. Require a large coherent region, ignore
  single-glyph matches, and treat text-heavy matches as weak.

### Font and stroke consistency

- **Idea:** compare measurements of words that should share a style: stroke width from a distance
  transform, x-height, digit height, ink darkness, edge sharpness and baseline alignment.
- **Strengths:** directly addresses retyped values, and is explainable with numbers.
- **False positives:** legitimate bold, italic or heading text; mixed fonts in one template; rubber
  stamps; OCR box errors that distort measurements. Compare only peers, such as other values in the
  same table or section.

### Signature comparison with perceptual hashes

- **Idea:** crop signature regions and compare them with a perceptual hash (pHash), followed by a
  pixel-level check on the near matches.
- **Strengths:** a repeated signature is a strong reuse signal, because a person's real signatures
  always vary.
- **False positives:** pHash alone isn't enough, since mostly white crops with thin strokes can hash
  close together. An organisation's scanned facsimile signature is legitimately identical across
  documents. This is reuse detection, **not** signature verification: nothing here assesses who
  wrote a signature.

### PDF incremental updates

- **Idea:** ISO 32000 lets a file be changed by appending objects and a new trailer, so earlier
  revisions remain in the file. More than one `%%EOF`, with a `/Prev` chain, shows that the file was
  saved again after creation.
- **Strengths:** a structural fact, readable with no image analysis at all.
- **False positives:** signing, form filling, annotation and some optimizers all add legitimate
  revisions. It shows that a change happened, not that the change was improper. The inverse also
  holds: a full re-save by an editor removes this trace.

### Text layer against rendered pixels

- **Idea:** compare a digital PDF's extracted text with OCR of its rendered page at the same place.
  Disagreement means that what a parser reads differs from what a person sees.
- **Strengths:** among the most compelling signals here, and it survives visual perfection, since
  the edit can look flawless.
- **False positives:** OCR errors (0/O, 1/l), dropped spaces, and scan-then-OCR PDFs with imperfect
  hidden text. Require a meaningful difference on a value, ideally a number, and report OCR confidence
  alongside it.

### Producer, dates and overlays

- **Idea:** compare `Producer`, `Creator` and date metadata between documents, and look for image or
  form objects drawn over text.
- **False positives:** metadata is easy to change in either direction, and legitimate workflows
  (print to PDF, compression, portals that merge files) rewrite it. Page furniture such as watermarks
  and logos are ordinary images. In this dataset, every digital PDF has a full-page raster watermark
  **beneath** its content, which isn't an overlay.

### EXIF

- **Idea:** compare device and software tags. Editing software in a tag is an observation worth a
  look.
- **False positives:** absent EXIF means little, because most messaging apps and portals strip it,
  and benign tools, such as a phone's cropping tool, write their own software tag.

### Contextual and cross-document checks

- **Arithmetic:** gross less deductions against net, and running balances. A failure is a fact about
  the document, but OCR misreads can create one, so confidence must accompany it.
- **Identifier checksums:** the Verhoeff check catches single-digit errors and most transpositions in
  Aadhaar-format numbers. Passing says only that the number is well formed, not that it was issued.
- **Entity matching:** fuzzy name and address comparison must tolerate initials, abbreviations and
  letter case, while still flagging a different surname or PIN. Case A exists to test this tolerance.

## 2. Measured signal in the dataset

To confirm that the planted edits leave real traces, we measured Case B on paper-background pixels
(brightness above 225) inside each tampered box against the rest of its page. This is a dataset
sanity check using one simple setup, not a detector result.

| Manipulation | ELA inside / outside | Noise residual inside / outside | Reading |
|---|---|---|---|
| m1 overwritten net pay | 1.47 / 0.27 | 0.62 / 0.88 | Clear on both |
| m2 pasted photo | 0.66 / 0.25 | 1.56 / 0.85 | Clear on both |
| m3 reused signature | 0.98 / 0.26 | 0.93 / 0.89 | ELA only; a pixel comparison is the better test |
| m4 copy-moved row | 0.37 / 0.33 | 1.35 / 1.04 | Weak; needs block matching, as expected |

m4 shows why fusion matters: a single detector would miss it, while another detector localizes it.

## 3. Demo dataset

Built by `scripts/generate_dataset.py` with a fixed seed. Re-running reproduces every file byte for
byte (checked by comparing SHA-256 hashes of two full runs). `--verify` checks ground truth by OCR at
each box, and `--overlays DIR` draws the boxes for review.

- **Pages:** A4 at 200 DPI, or 1654 x 2339 px. All people, numbers and organisations are fictional,
  and every page has a banner and a watermark reading SYNTHETIC.
- **Numbers:** Aadhaar-format values use a `9999` prefix with a valid Verhoeff digit, PAN-format values
  start with `ZZ`, emails use `example.com`, and photos are abstract shapes rather than faces.
- **Acquisition:** raster documents pass through one simulated scan (paper tone, illumination, slight
  blur, sensor noise, JPEG at quality 88). **Tampering happens after that**, as it would in a real
  edit. Digital PDFs are born-digital, with real text layers.
- **Fonts:** Bitstream Vera (bundled with ReportLab) and the URW base-14 clones (bundled with MuPDF).
  Both are used only to rasterize or reference glyphs while generating samples. No system fonts.

| Case | Purpose | Contents |
|---|---|---|
| A | Doesn't cry wolf | Consistent. Benign variation only, listed in `benign_variations`. |
| B | Visual tampering | Overwritten net pay, pasted photo, reused signature, copy-moved bank row, and the arithmetic and cross-document conflicts these create. |
| C | Cross-document | All 9 discrepancy types from the contract, with no visual edits. Includes a 2-page statement. |
| D | PDF structure | Real incremental updates on the payslip (raster patch) and the statement (form XObject overlay), with text layer against pixel conflicts, a changed producer and later modified dates. |
| Noise variants | Honest false-positive testing | Rotation of 1 to 2 degrees, blur and heavy JPEG versions of 7 documents, with transformed boxes. |
| Unsupported | Safe failure | A `.docx`, a truncated PDF, an empty PNG and text renamed to `.png`. Expected outcomes are in `expected.json`. |

**What this dataset can't show.** The edits were planted by the same team that builds the detectors,
with a simulated scanner rather than real devices, so scores on it are optimistic and don't predict
performance on real documents. Handwriting and non-English text aren't included.

## 4. Free-tier LLM landscape

**Not verified by a live call in this document.** No provider keys existed when this was written, so
nothing here confirms that a key or model works. `scripts/check_keys.py` is the source of truth once
keys exist. A web search in November 2026 turned up only third-party roundups, which disagree with
each other on limits, and warn that limits and free model lists change. So this file deliberately
lists no numbers or model names. Check the official pages before relying on any quota:

- Gemini: <https://ai.google.dev/gemini-api/docs/rate-limits>
- Groq: <https://console.groq.com/docs/rate-limits>
- OpenRouter: <https://openrouter.ai/docs/api-reference/limits>

The practical consequence for the design: model names stay configurable in `config/settings.py`, and
everything has to work with no provider at all.

## 5. References

- N. Krawetz, "A Picture's Worth: Digital Image Analysis and Forensics," Black Hat Briefings, 2007.
- H. Farid, "Exposing Digital Forgeries from JPEG Ghosts," IEEE Trans. Information Forensics and
  Security, 2009.
- B. Mahdian and S. Saic, "Using Noise Inconsistencies for Blind Image Forensics," Image and Vision
  Computing, 2009.
- J. Lukáš, J. Fridrich and M. Goljan, "Digital Camera Identification from Sensor Pattern Noise," IEEE
  Trans. Information Forensics and Security, 2006.
- J. Fridrich, D. Soukal and J. Lukáš, "Detection of Copy-Move Forgery in Digital Images," DFRWS, 2003.
- I. Amerini et al., "A SIFT-Based Forensic Method for Copy-Move Attack Detection and Transformation
  Recovery," IEEE Trans. Information Forensics and Security, 2011.
- C. Zauner, "Implementation and Benchmarking of Perceptual Image Hash Functions," Master's thesis,
  2010.
- ISO 32000-1, Document management: Portable Document Format, section on incremental updates.
- J. Verhoeff, "Error Detecting Decimal Codes," Mathematisch Centrum, 1969.
