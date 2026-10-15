import pytest
from src import gmail_auth


def test_relative_credentials_path_uses_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", "credentials/credentials.json")
    assert gmail_auth._config_path("GMAIL_CREDENTIALS_PATH", "unused") == (
        gmail_auth.PROJECT_ROOT / "credentials" / "credentials.json")


def test_missing_credentials_gives_setup_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(gmail_auth, "CREDENTIALS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(gmail_auth, "TOKEN_PATH", tmp_path / "token.json")
    with pytest.raises(FileNotFoundError, match="Desktop app OAuth client JSON"):
        gmail_auth.get_credentials()
