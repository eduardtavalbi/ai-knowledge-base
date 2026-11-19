from app.core.config import Settings


def test_gemini_model_defaults_to_gemini_3_8_flash():
    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-3.8-flash"


def test_gemini_model_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "custom-gemini-model")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "custom-gemini-model"
