from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from prossima.bot import Bot
from prossima.store import Store
from tests.aggiornamenti import GRUPPO, NOME
from tests.finti import Orologio, TelegramFinto
from tests.tavolo import ROSTER

ZURIGO = ZoneInfo("Europe/Zurich")
# Martedì 7/10/2025 alle 20:00 a Zurigo: la settimana seguente va dal 13 al 19.
INIZIO = datetime(2025, 10, 7, 18, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "prossima.sqlite")
    s.crea_schema()
    return s


@pytest.fixture
def orologio():
    return Orologio(INIZIO)


@pytest.fixture
def telegram():
    return TelegramFinto(NOME)


@pytest.fixture
def bot(telegram, store, orologio):
    # `caso` sceglie sempre la prima frase restante: le prove sanno quale arriva.
    return Bot(
        telegram=telegram,
        store=store,
        roster=ROSTER,
        gruppo=GRUPPO,
        nome=NOME,
        fuso=ZURIGO,
        adesso=orologio,
        caso=lambda restanti: restanti[0],
    )
