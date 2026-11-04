# Build Environment

Recorded at project start (Wed 4 Nov 2026). Values were checked directly; key values were never read.

| Item | Observed |
|---|---|
| Machine | Apple M4 Pro, arm64, 12 CPU cores, 24 GB RAM, 294 GB free. No CUDA; Metal only through Ollama. |
| OS | macOS (Darwin 27.0.0) |
| Python | 3.12.13 used for the venv. **3.11 is not installed**, so the project targets 3.12. |
| Node | v20.20.2, npm 10.8.2 |
| Docker | Client 29.9.2. The daemon did not respond when checked, so Compose is untested at this point. |
| Installed for this project | tesseract, gitleaks, poppler (Homebrew) |
| Not installed | `gh`, ffmpeg, uv, pnpm |
| Ollama | Server running on `:11434`, no models at the start; model pulled for this project |
| LLM API keys in the environment | **None** (no Gemini, Groq, OpenRouter, Hugging Face, Mistral or Anthropic key) |
| MCP/tools usable for verification | Built-in browser (UI checks), Artifact and document tools |

## Tool decisions from what is actually available

- **OCR primary: RapidOCR (`rapidocr-onnxruntime`)** instead of PaddleOCR proper. It runs the
  PP-OCR detection and recognition models through ONNX Runtime, without the Paddle framework, so it
  installs cleanly on arm64 and in CI. Smoke test: 0.99 confidence, 0.32 s on a test image.
- **OCR fallback: Tesseract 5** through `pytesseract`. Verified working.
- **Digital PDF text:** PyMuPDF text layer, with OCR run on the render too for mismatch detection.
- **PDF structure:** pikepdf and PyMuPDF. **Dossier:** ReportLab (no system libraries, unlike
  WeasyPrint).
- **Reasoning:** provider chain Gemini → Groq → OpenRouter → Ollama → deterministic. With no keys
  today, only Ollama and the deterministic path can really be exercised. Remote providers are
  unverified until keys exist, and must be reported that way.
