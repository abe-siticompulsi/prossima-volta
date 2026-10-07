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
def riavvia(telegram, store, orologio):
    """Un bot nuovo sugli stessi Telegram, database e orologio: il processo
    ripartito. `caso` sceglie sempre la prima frase restante: le prove sanno
    quale arriva."""

    def nuovo() -> Bot:
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

    return nuovo


@pytest.fixture
def bot(riavvia):
    return riavvia()


class Ucciso(BaseException):
    """Il processo ucciso a metà: nessun `except Exception` del bot lo ferma."""


_ASSENTE = object()


@pytest.fixture
def uccidi():
    """`uccidi(oggetto, "metodo")`: il processo muore quando arriva a quel
    metodo, prima che faccia niente; con `dopo=True`, appena il metodo ha
    finito. `uccidi.basta()` rimette i metodi uccisi, e solo quelli."""
    uccisi: list[tuple[object, str, object]] = []

    def uccidi(oggetto, metodo: str, dopo: bool = False) -> None:
        vero = getattr(oggetto, metodo)

        def muore(*argomenti, **chiavi):
            if dopo:
                vero(*argomenti, **chiavi)
            raise Ucciso(metodo)

        uccisi.append((oggetto, metodo, vars(oggetto).get(metodo, _ASSENTE)))
        setattr(oggetto, metodo, muore)

    def basta() -> None:
        while uccisi:
            oggetto, metodo, prima = uccisi.pop()
            if prima is _ASSENTE:
                delattr(oggetto, metodo)
            else:
                setattr(oggetto, metodo, prima)

    uccidi.basta = basta
    yield uccidi
    basta()
