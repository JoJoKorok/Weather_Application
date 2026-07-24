import uuid

from src.data.client_identity import get_or_create_client_id


def test_client_id_is_valid_and_persistent(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    first = get_or_create_client_id()
    second = get_or_create_client_id()

    assert first == second
    assert str(uuid.UUID(first)) == first


def test_invalid_stored_client_id_is_replaced(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    identity_dir = tmp_path / "weather_application"
    identity_dir.mkdir()
    (identity_dir / "client_id").write_text("not-a-uuid", encoding="utf-8")

    replacement = get_or_create_client_id()
    assert str(uuid.UUID(replacement)) == replacement
