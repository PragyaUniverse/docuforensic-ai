"""The deploy script must never upload a secret, and only copies known AI key names."""
from scripts import deploy_hf


def test_only_known_key_names_with_values_become_secrets(tmp_path):
    env = tmp_path / ".env"
    # Made-up values for this test only.
    env.write_text(
        "# comment\nGROQ_API_KEYS=test-value-1\nGEMINI_API_KEYS=\nAUTH_ENABLED=true\n"
        "OPENROUTER_API_KEYS=\"test-value-2\"\nSOMETHING_ELSE=x\n",
        encoding="utf-8",
    )
    assert deploy_hf.read_env_secrets(env) == {"GROQ_API_KEYS": "test-value-1", "OPENROUTER_API_KEYS": "test-value-2"}
    assert deploy_hf.read_env_secrets(tmp_path / "missing") == {}


def test_upload_list_is_tracked_files_without_secrets_or_state():
    files = deploy_hf.files_to_upload()
    assert "Dockerfile" in files or "backend/app.py" in files
    assert ".env" not in files
    assert not any(f.startswith((".venv/", "var/", "frontend/node_modules/", "frontend/dist/")) for f in files)
    assert "README.md" not in files  # replaced by the copy with the Space header


def test_space_readme_has_the_docker_header():
    text = deploy_hf.space_readme()
    assert text.startswith("---\n")
    assert "sdk: docker" in text and "app_port: 7860" in text
