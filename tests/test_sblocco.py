import logging

import pytest

from prossima import principale
from prossima.store import ChiusuraSospesa
from tests.aggiornamenti import comando
from tests.conftest import INIZIO
from tests.tavolo import d


def sblocca(tmp_path, caplog) -> tuple[int, list[str]]:
    """`prossima sblocca` sul database delle prove: l'esito e le righe del log."""
    with caplog.at_level(logging.INFO):
        esito = principale.main(["sblocca"], {"PV_DB": str(tmp_path / "prossima.sqlite")})
    return esito, [r.getMessage() for r in caplog.records if r.name == "prossima.principale"]


def test_toglie_la_chiusura_in_sospeso_la_ripresa_e_chiude_il_sondaggio(
    store, tmp_path, caplog, riavvia, telegram
):
    aperto = store.apri_sondaggio([d("14/10"), d("16/10")], "poll-1", 501, "Nessuna: x", INIZIO)
    store.sospendi_chiusura(ChiusuraSospesa(aperto.id, 9001, "rimanda"), INIZIO)
    store.inizia_ripresa(INIZIO, [], aperto.id)
    esito, righe = sblocca(tmp_path, caplog)
    assert esito == 0
    assert righe == [
        f"sblocca: tolta la chiusura in sospeso del sondaggio {aperto.id} (/chiudi rimanda)",
        f"sblocca: tolta la ripresa del sondaggio {aperto.id}, nella fase «fermare»",
        f"sblocca: chiuso nel database il sondaggio {aperto.id} (mar 14/10, gio 16/10): "
        "su Telegram resta com'è, e il bot ne ignora i voti",
    ]
    assert store.chiusura_sospesa() is None
    assert store.ripresa() is None
    assert store.sondaggio_aperto() is None
    assert store.posta() == []  # nel gruppo non dice niente
    # il bot, ripartito, è sbloccato: un sondaggio nuovo si apre
    riavvia().ricevi([comando("/sondaggio ven")])
    assert store.sondaggio_aperto().date == (d("17/10"),)


def test_una_riapertura_che_aspetta_si_toglie_e_il_sondaggio_resta_chiuso(store, tmp_path, caplog):
    aperto = store.apri_sondaggio([d("14/10")], "poll-1", 501, "Nessuna: x", INIZIO)
    store.inizia_ripresa(INIZIO, [], aperto.id)
    store.fermato_per_riprendere(aperto.id, INIZIO, [])
    esito, righe = sblocca(tmp_path, caplog)
    assert esito == 0
    assert righe == [
        f"sblocca: tolta la ripresa del sondaggio {aperto.id}, nella fase «riaprire»: "
        "il sondaggio, già fermo, resta chiuso"
    ]
    assert store.ripresa() is None
    assert store.sondaggio(aperto.id).chiuso_alle is not None


NIENTE = "sblocca: niente da sbloccare: nessuna chiusura in sospeso, nessuna ripresa"


@pytest.mark.parametrize("cosa", ["chiusura", "ripresa"])
def test_basta_una_delle_due_sul_sondaggio_aperto_per_chiuderlo(store, tmp_path, caplog, cosa):
    aperto = store.apri_sondaggio([d("14/10")], "poll-1", 501, "Nessuna: x", INIZIO)
    if cosa == "chiusura":
        store.sospendi_chiusura(ChiusuraSospesa(aperto.id, 9001, None), INIZIO)
    else:
        store.inizia_ripresa(INIZIO, [], aperto.id)
    esito, righe = sblocca(tmp_path, caplog)
    assert esito == 0
    assert righe[-1].startswith(f"sblocca: chiuso nel database il sondaggio {aperto.id} (mar 14/10)")
    assert store.sondaggio_aperto() is None


def test_senza_niente_da_sbloccare_lo_dice(store, tmp_path, caplog):
    esito, righe = sblocca(tmp_path, caplog)
    assert esito == 0
    assert righe == [NIENTE]


def test_un_sondaggio_aperto_senza_niente_in_sospeso_resta_aperto(store, tmp_path, caplog):
    aperto = store.apri_sondaggio([d("14/10")], "poll-1", 501, "Nessuna: x", INIZIO)
    esito, righe = sblocca(tmp_path, caplog)
    # il comando si può provare senza rischi: un sondaggio sano non si tocca
    assert esito == 0
    assert righe == [NIENTE]
    assert store.sondaggio_aperto() == aperto


def test_una_chiusura_in_sospeso_di_un_altro_sondaggio_non_chiude_quello_aperto(
    store, tmp_path, caplog
):
    vecchio = store.apri_sondaggio([d("14/10")], "poll-1", 501, "Nessuna: x", INIZIO)
    store.chiudi_sondaggio(vecchio.id, INIZIO)
    aperto = store.apri_sondaggio([d("21/10")], "poll-2", 502, "Nessuna: y", INIZIO)
    store.sospendi_chiusura(ChiusuraSospesa(vecchio.id, 9001, None), INIZIO)
    esito, righe = sblocca(tmp_path, caplog)
    assert esito == 0
    assert righe == [f"sblocca: tolta la chiusura in sospeso del sondaggio {vecchio.id} (/chiudi)"]
    assert store.chiusura_sospesa() is None
    assert store.sondaggio_aperto() == aperto


@pytest.mark.parametrize(
    "env, scritto",
    [
        ({}, "configurazione: PV_DB manca"),
        ({"PV_DB": "/non/c/e/prossima.sqlite"}, "il database /non/c/e/prossima.sqlite non c'è"),
    ],
)
def test_senza_database_non_crea_niente(tmp_path, caplog, env, scritto):
    with caplog.at_level(logging.ERROR):
        assert principale.main(["sblocca"], env) == 2
    assert scritto in caplog.text
