# Deploying DocuForensic AI

The whole app is one Docker image: the API also serves the website, on one port. Any host that runs
a Dockerfile works. The free option we recommend is **Hugging Face Spaces**.

## Why Hugging Face Spaces

- Free CPU tier with 2 vCPU and 16 GB RAM, and it builds the `Dockerfile` for you.
- The app uses about 0.5 GB of memory while analysing. Free tiers with 512 MB (Render, Koyeb) are
  too small and will run out of memory.
- A free Space sleeps after about two days without visitors and takes a minute to wake up. Open it
  shortly before the demo.
- Files don't persist across restarts on the free tier. That's fine for a demo: the demo cases
  reload from the home page at any time.

## Deploy in three commands

You need a free Hugging Face account and a token with **write** access, from
https://huggingface.co/settings/tokens. Type the token only into your own terminal, never into a chat.

```bash
.venv/bin/python -m pip install huggingface_hub
```

```bash
.venv/bin/hf auth login
```

```bash
.venv/bin/python -m scripts.deploy_hf <your-hf-username>/docuforensic
```

The script creates the Space, uploads the code, and copies any AI keys from your `.env` into the
Space's secrets. It never prints a key. Hugging Face then builds the image, which takes 5 to 10
minutes. Your site will be at `https://<your-hf-username>-docuforensic.hf.space`.

To see what would be uploaded first, add `--dry-run`. Run the same command again to deploy an update.

## Live AI on the hosted site

Without a key the site still works fully. All checks run on the server, and AI explanations are
replayed from answers recorded in real runs, labelled as replays.

For live AI, get a free key and put it in `.env` before you deploy, or add it later under
**Space → Settings → Variables and secrets → New secret**:

| Secret name | Where to get a free key |
|---|---|
| `GROQ_API_KEYS` (recommended, fastest) | https://console.groq.com/keys |
| `GEMINI_API_KEYS` | https://aistudio.google.com/apikey |
| `OPENROUTER_API_KEYS` | https://openrouter.ai/keys |

After adding a secret, the Space restarts on its own. Personal details are redacted before anything
is sent to a hosted AI model (`REDACT_PII_EXTERNAL`, on by default).

The local Ollama model used on a laptop isn't available on a hosted site, so the image's provider
order is `groq,gemini,openrouter`.

## Keep the source public

PyMuPDF is licensed AGPL-3.0, so a publicly hosted app must offer its source to users. A public
Space does that through its Files tab. If you make the Space private, link a public copy of the
source instead. See [THIRD_PARTY.md](../THIRD_PARTY.md).

## Other hosts, or your own machine

```bash
docker build -t docuforensic .
```

```bash
docker run -p 7860:7860 --env-file .env docuforensic
```

Then open http://localhost:7860. Leave out `--env-file .env` if you have no `.env`. The container
listens on `$PORT` (default 7860), so hosts that set `PORT` themselves work unchanged. Give it at
least 1 GB of memory.

## Optional settings

| Variable | Default | What it does |
|---|---|---|
| `AUTH_ENABLED` | `false` | Require a login. Create users with `scripts/create_user.py` |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` when served over HTTPS (Spaces is) |
| `AUDIT_TAMPER_DEMO` | `true` | The "break the history" demo. Set `false` outside a demo |
| `RATE_LIMIT_PER_MINUTE` | `120` | Requests per client per minute |
| `MAX_UPLOAD_MB` | `25` | Largest upload accepted |
