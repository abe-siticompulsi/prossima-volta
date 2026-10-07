import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima.regole import Fatti, Voto
from prossima.store import Lettera, Sondaggio, Store
from tests.tavolo import ESTRANEO, GIO, d

ALLE = datetime(2025, 10, 7, 18, 0, tzinfo=UTC)
DATE = (d("14/10"), d("16/10"))


def apri(store, poll_id="poll-1", messaggio=501, date_=DATE):
    return store.apri_sondaggio(date_, poll_id, messaggio, "Nessuna: riposo lungo. Molto lungo.", ALLE)


def test_lo_schema_si_crea_due_volte_e_usa_wal(tmp_path):
    s = Store(tmp_path / "x.sqlite")
    s.crea_schema()
    s.crea_schema()
    with sqlite3.connect(tmp_path / "x.sqlite") as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_aprire_e_ritrovare_il_sondaggio_aperto(store):
    assert store.sondaggio_aperto() is None
    s = apri(store)
    assert s == Sondaggio(
        id=s.id,
        date=DATE,
        poll_id="poll-1",
        messaggio=501,
        frase="Nessuna: riposo lungo. Molto lungo.",
        aperto_alle=ALLE,
    )
    assert store.sondaggio_aperto() == s


def test_un_sondaggio_aperto_alla_volta(store):
    apri(store)
    with pytest.raises(sqlite3.IntegrityError):
        apri(store, poll_id="poll-2", messaggio=502)


def test_chiudere_una_volta_sola_e_ricordare_il_comando(store):
    s = apri(store)
    assert store.chiudi_sondaggio(s.id, ALLE + timedelta(hours=1), comando=777)
    assert not store.chiudi_sondaggio(s.id, ALLE + timedelta(hours=2), comando=778)
    assert store.sondaggio_aperto() is None
    assert store.sondaggio(s.id).chiuso_alle == ALLE + timedelta(hours=1)
    assert store.chiuso_dal_comando(777)
    assert not store.chiuso_dal_comando(778)
    # chiuso, se ne apre un altro
    assert apri(store, poll_id="poll-2", messaggio=502).id != s.id


def test_riaprire_cambia_il_messaggio_e_tiene_voti_e_fatti(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset(DATE)), ALLE)
    store.salva_fatti(s.id, Fatti(quasi=frozenset({d("14/10")})))
    store.chiudi_sondaggio(s.id, ALLE)
    riaperto = store.riapri_sondaggio(s.id, (d("16/10"),), "poll-9", 909, "Nessuna: ho tirato 1 sul calendario")
    assert riaperto == Sondaggio(
        id=s.id,
        date=(d("16/10"),),
        poll_id="poll-9",
        messaggio=909,
        frase="Nessuna: ho tirato 1 sul calendario",
        aperto_alle=ALLE,
    )
    assert store.sondaggio_aperto() == riaperto
    assert store.voti(s.id) == {GIO.telegram_id: Voto(frozenset(DATE))}
    assert store.fatti(s.id).quasi == {d("14/10")}


def test_il_voto_piu_recente_sostituisce_il_precedente_anche_vuoto(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset({d("14/10")})), ALLE)
    store.registra_voto(s.id, ESTRANEO, "poll-1", Voto(nessuna=True), ALLE)
    assert store.voti(s.id) == {
        GIO.telegram_id: Voto(frozenset({d("14/10")})),
        ESTRANEO: Voto(nessuna=True),
    }
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(), ALLE)
    assert store.voti(s.id)[GIO.telegram_id] == Voto()


def test_i_voti_di_un_sondaggio_di_telegram(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset({d("14/10")})), ALLE)
    store.registra_voto(s.id, ESTRANEO, "poll-2", Voto(nessuna=True), ALLE)
    assert store.voti_del_poll(s.id, "poll-1") == [Voto(frozenset({d("14/10")}))]
    assert store.voti_del_poll(s.id, "poll-2") == [Voto(nessuna=True)]


def test_i_fatti_tornano_come_sono_stati_salvati(store):
    s = apri(store)
    assert store.fatti(s.id) == Fatti()
    fatti = Fatti(
        quasi=frozenset({d("14/10")}),
        possibili={d("14/10"): frozenset({1, 2}), d("16/10"): None},
        impossibile=True,
    )
    store.salva_fatti(s.id, fatti)
    assert store.fatti(s.id) == fatti


def test_le_frasi_usate(store):
    assert store.frasi_usate() == set()
    store.usa_frase("Nessuna: a")
    store.usa_frase("Nessuna: a")
    store.usa_frase("Nessuna: b")
    assert store.frasi_usate() == {"Nessuna: a", "Nessuna: b"}
    store.dimentica_frasi()
    assert store.frasi_usate() == set()


def test_la_posta_in_ordine_di_arrivo(store):
    menzione = {"type": "text_mention", "offset": 3, "length": 4, "user": {"id": 100000005}}
    primo = store.accoda(-100, "📅 sese", [menzione], None, ALLE)
    secondo = store.accoda(-100, "Troppe date: al massimo 10.", [], 42, ALLE)
    assert store.posta() == [
        Lettera(primo, -100, "📅 sese", (menzione,), None),
        Lettera(secondo, -100, "Troppe date: al massimo 10.", (), 42),
    ]
    store.togli_lettera(primo)
    assert [lettera.id for lettera in store.posta()] == [secondo]


def test_offset_e_ultima_lettura(store):
    assert store.offset() is None
    assert store.ultima_lettura() is None
    store.salva_offset(42)
    zurigo = datetime(2025, 10, 12, 21, 5, tzinfo=ZoneInfo("Europe/Zurich"))
    store.segna_lettura(zurigo)
    assert store.offset() == 42
    assert store.ultima_lettura() == zurigo
    assert store.ultima_lettura().tzinfo == UTC


def test_un_momento_senza_fuso_e_rifiutato(store):
    with pytest.raises(ValueError, match="senza fuso"):
        store.segna_lettura(datetime(2025, 10, 12, 21, 5))
