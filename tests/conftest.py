import pytest

@pytest.fixture(autouse=True)
def _isolated_local_backend(tmp_path, monkeypatch):
    """Every test gets its own store and the local backend, regardless of any
    developer .env (which would otherwise point tests at a live Hindsight)."""
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("PK_MEMORY_BACKEND", "local")
