#!/usr/bin/env python
"""Deploys the app to a free Hugging Face Space in one command. See docs/DEPLOY.md.

    .venv/bin/python -m pip install huggingface_hub
    .venv/bin/hf auth login            # paste your Hugging Face token in YOUR terminal
    .venv/bin/python -m scripts.deploy_hf <your-hf-username>/docuforensic

It creates the Space (Docker, public) if needed, uploads the code, and copies any AI keys found in
your local .env into the Space's secrets. Keys are never printed, logged or uploaded as files.
It uploads the files tracked in git, so commit new files first. Use --dry-run to list what would
be uploaded without contacting Hugging Face.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Uploaded: exactly the files tracked in git, so secrets, local state and builds never leave the
# machine. README.md is replaced by a copy carrying the Space header.
NEVER = (".env", ".key", ".pem", ".sqlite3")
# Copied from .env to the Space's secrets when present. Values are never shown.
SECRET_NAMES = ["GROQ_API_KEYS", "GEMINI_API_KEYS", "OPENROUTER_API_KEYS"]

SPACE_HEADER = """---
title: DocuForensic AI
emoji: 🔎
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: AI document forensics with a human reviewer in charge
---

"""


def read_env_secrets(env_path: Path) -> dict[str, str]:
    """Only the AI key names we know about, and only non-empty values."""
    found: dict[str, str] = {}
    if not env_path.is_file():
        return found
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name in SECRET_NAMES and value:
            found[name] = value
    return found


def space_readme() -> str:
    return SPACE_HEADER + (REPO / "README.md").read_text(encoding="utf-8")


def files_to_upload() -> list[str]:
    """Tracked files only. Untracked or ignored files (.env, .venv, var/) are never uploaded."""
    import subprocess

    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    files = [f for f in out.decode("utf-8").split("\0") if f and (REPO / f).is_file()]
    files = [f for f in files if f != "README.md"]
    leaked = [f for f in files if f.endswith(NEVER) and not f.endswith(".env.example")]
    if leaked:
        raise SystemExit(f"Refusing to deploy: secret-looking files are tracked in git: {leaked}")
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("space", help="<hf-username>/<space-name>, for example asha/docuforensic")
    ap.add_argument("--private", action="store_true",
                    help="Make the Space private. PyMuPDF is AGPL-3.0, so a public app should keep its source public.")
    ap.add_argument("--dry-run", action="store_true", help="List what would be uploaded, contact nothing.")
    args = ap.parse_args()

    if args.space.count("/") != 1:
        print("Give the Space as <hf-username>/<space-name>.", file=sys.stderr)
        return 2
    secrets = read_env_secrets(REPO / ".env")
    files = files_to_upload()

    if args.dry_run:
        print(f"Would upload {len(files)} files plus a README with the Space header to {args.space}.")
        for name in SECRET_NAMES:
            print(f"  secret {name}: {'from .env' if name in secrets else 'not set'}")
        return 0

    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError:
        print("Install the uploader first: .venv/bin/python -m pip install huggingface_hub", file=sys.stderr)
        return 2

    api = HfApi()
    try:
        user = api.whoami()["name"]
    except Exception:
        print("Not logged in to Hugging Face. Run: .venv/bin/hf auth login", file=sys.stderr)
        return 2
    print(f"Logged in as {user}.")

    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    print(f"Space ready: https://huggingface.co/spaces/{args.space}")

    for name, value in secrets.items():
        api.add_space_secret(args.space, name, value)
        print(f"  secret {name}: set from .env")
    if not secrets:
        print("  no AI keys in .env: the app will replay recorded AI notes, labelled. You can add a key later.")

    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(REPO / f)) for f in files]
    ops.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=space_readme().encode("utf-8")))
    print(f"Uploading {len(files) + 1} files...")
    api.create_commit(repo_id=args.space, repo_type="space", operations=ops,
                      commit_message="Deploy DocuForensic AI")

    owner, name = args.space.split("/")
    print("\nUploaded. Hugging Face is now building the app, which takes about 5 to 10 minutes.")
    print(f"Watch it at https://huggingface.co/spaces/{args.space}")
    print(f"Your website will be at https://{owner.lower()}-{name.lower().replace('_', '-')}.hf.space")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
