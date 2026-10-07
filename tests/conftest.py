import pytest

from prossima.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "prossima.sqlite")
    s.crea_schema()
    return s
