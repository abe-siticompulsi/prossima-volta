import threading
import time

from prossima import testi
from prossima.rispondente import Rispondente
from prossima.risposte import Domanda, Esito, Fatti
from tests.tavolo import OGGI


def domanda(n: int) -> Domanda:
    return Domanda(-100, n, "Sem", f"messaggio {n}", "", Fatti(OGGI))


def aspetta_pronte(r: Rispondente, quante: int) -> list:
    pronte = []
    fine = time.monotonic() + 5
    while len(pronte) < quante and time.monotonic() < fine:
        pronte += r.pronte()
        time.sleep(0.01)
    return pronte


def test_le_risposte_arrivano_in_ordine_e_poi_non_sono_piu_in_lavoro():
    r = Rispondente(lambda d: Esito(testi.Testo(f"risposta {d.messaggio_id}")))
    assert r.accetta(domanda(1)) and r.accetta(domanda(2))
    pronte = aspetta_pronte(r, 2)
    assert [(d.messaggio_id, e.testo.testo) for d, e in pronte] == [
        (1, "risposta 1"),
        (2, "risposta 2"),
    ]
    assert r.in_lavoro() == ()


def test_al_massimo_tre_in_lavoro_compresa_quella_in_corso():
    via = threading.Event()

    def lenta(d):
        via.wait(5)
        return Esito(testi.Testo("ok"))

    r = Rispondente(lenta)
    assert all(r.accetta(domanda(n)) for n in (1, 2, 3))
    assert not r.accetta(domanda(4))
    assert [d.messaggio_id for d in r.in_lavoro()] == [1, 2, 3]
    via.set()
    assert len(aspetta_pronte(r, 3)) == 3
    assert r.accetta(domanda(5))


def test_un_errore_inatteso_da_la_frase_fissa(caplog):
    def rotta(d):
        raise RuntimeError("bug")

    r = Rispondente(rotta)
    r.accetta(domanda(1))
    [(_, esito)] = aspetta_pronte(r, 1)
    assert esito == Esito(testi.non_riesco())
    assert "risposta non scritta" in caplog.text
