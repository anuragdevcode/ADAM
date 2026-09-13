"""Tests for the dependency-free .env loader in adam.config."""


def test_load_dotenv_applies_values_without_overriding_environment(tmp_path, monkeypatch):
    from adam.config import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment line",
                "",
                "GROQ_API_KEY=gsk_from_file",
                "ELEVENLABS_API_KEY='quoted value'",
                'ADAM_TTS_PROVIDER="elevenlabs"',
                "OLLAMA_HOST=http://localhost:11434 # inline comment",
                "export ADAM_STT_PROVIDER=groq",
                "ALREADY_SET=from_file",
                "not a valid line",
            ]
        ),
        encoding="utf-8",
    )
    for key in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "ADAM_TTS_PROVIDER", "OLLAMA_HOST", "ADAM_STT_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALREADY_SET", "from_shell")

    applied = load_dotenv(env_file)

    import os
    assert applied == 5
    assert os.environ["GROQ_API_KEY"] == "gsk_from_file"
    assert os.environ["ELEVENLABS_API_KEY"] == "quoted value"
    assert os.environ["ADAM_TTS_PROVIDER"] == "elevenlabs"
    assert os.environ["OLLAMA_HOST"] == "http://localhost:11434"
    assert os.environ["ADAM_STT_PROVIDER"] == "groq"
    # Shell / Compose values win over the file
    assert os.environ["ALREADY_SET"] == "from_shell"


def test_load_dotenv_override_and_missing_file(tmp_path, monkeypatch):
    from adam.config import load_dotenv

    assert load_dotenv(tmp_path / "missing.env") == 0

    env_file = tmp_path / ".env"
    env_file.write_text("ADAM_PROFILE=DEV_SERVER\n", encoding="utf-8")
    monkeypatch.setenv("ADAM_PROFILE", "MACBOOK_AIR_8GB")
    assert load_dotenv(env_file, override=True) == 1
    import os
    assert os.environ["ADAM_PROFILE"] == "DEV_SERVER"
