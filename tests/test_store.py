import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima.regole import Fatti, Voto
from prossima.store import (
    FERMARE,
    RIAPRIRE,
    ChiusuraSospesa,
    Lettera,
    LetteraNuova,
    NonConfermato,
    RipresaInCorso,
    Sondaggio,
    Store,
)
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
        date_iniziali=DATE,
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


def test_la_lettera_della_chiusura_si_accoda_con_la_chiusura(store):
    s = apri(store)
    chiuso = LetteraNuova(-100, "🔒 Sondaggio chiuso.", risposta_a=42)
    assert store.chiudi_sondaggio(s.id, ALLE, comando=777, lettere=[chiuso])
    assert [(x.chat_id, x.testo, x.entita, x.risposta_a) for x in store.posta()] == [
        (-100, "🔒 Sondaggio chiuso.", (), 42)
    ]
    # già chiuso: questa chiamata non chiude niente, e non lo dice
    assert not store.chiudi_sondaggio(s.id, ALLE, comando=778, lettere=[chiuso])
    assert len(store.posta()) == 1


def test_rimandare_chiude_apre_e_accoda_in_una_transazione(store):
    vecchio = apri(store)
    rimandiamo = LetteraNuova(-100, "🔁 Rimandiamo")
    nuovo = store.rimanda(
        vecchio.id, 777, (d("21/10"),), "poll-2", 502, "Nessuna: x", ALLE, [rimandiamo]
    )
    assert store.sondaggio(vecchio.id).chiuso_alle == ALLE
    assert store.chiuso_dal_comando(777)
    assert store.sondaggio_aperto() == nuovo
    assert (nuovo.date, nuovo.poll_id, nuovo.messaggio) == ((d("21/10"),), "poll-2", 502)
    assert [x.testo for x in store.posta()] == ["🔁 Rimandiamo"]


def test_rimandare_un_sondaggio_gia_chiuso_non_apre_niente(store):
    vecchio = apri(store)
    store.chiudi_sondaggio(vecchio.id, ALLE, 776)
    with pytest.raises(ValueError, match="non è aperto"):
        store.rimanda(vecchio.id, 777, (d("21/10"),), "poll-2", 502, "Nessuna: x", ALLE)
    assert store.sondaggio_aperto() is None
    assert not store.chiuso_dal_comando(777)


def test_rimandare_a_meta_non_lascia_niente(store):
    vecchio = apri(store)
    rotta = LetteraNuova(-100, "x", entita=({"non": object()},))  # non si scrive in JSON
    with pytest.raises(TypeError):
        store.rimanda(vecchio.id, 777, (d("21/10"),), "poll-2", 502, "Nessuna: x", ALLE, [rotta])
    assert store.sondaggio_aperto() == vecchio
    assert not store.chiuso_dal_comando(777)
    assert store.posta() == []


def test_la_chiusura_in_sospeso_si_ricorda_con_la_risposta(store):
    s = apri(store)
    assert store.chiusura_sospesa() is None
    risposta = LetteraNuova(-100, "riprovo da solo", risposta_a=777)
    store.sospendi_chiusura(ChiusuraSospesa(s.id, 777, None), ALLE, [risposta])
    assert store.chiusura_sospesa() == ChiusuraSospesa(s.id, 777, None)
    assert [(x.testo, x.risposta_a) for x in store.posta()] == [("riprovo da solo", 777)]
    # vale l'ultima decisione
    store.sospendi_chiusura(ChiusuraSospesa(s.id, 778, "rimanda"), ALLE)
    assert store.chiusura_sospesa() == ChiusuraSospesa(s.id, 778, "rimanda")
    store.togli_chiusura_sospesa()
    assert store.chiusura_sospesa() is None


@pytest.mark.parametrize("modo", ["chiudi", "rimanda"])
def test_chiudere_il_sondaggio_toglie_la_sua_chiusura_in_sospeso(store, modo):
    s = apri(store)
    store.sospendi_chiusura(ChiusuraSospesa(s.id, 777, None), ALLE)
    if modo == "chiudi":
        store.chiudi_sondaggio(s.id, ALLE, 777)
    else:
        store.rimanda(s.id, 777, (d("21/10"),), "poll-2", 502, "Nessuna: x", ALLE)
    assert store.chiusura_sospesa() is None


def test_chiudere_un_altro_sondaggio_lascia_la_chiusura_in_sospeso(store):
    s = apri(store)
    store.sospendi_chiusura(ChiusuraSospesa(s.id + 1, 777, None), ALLE)
    store.chiudi_sondaggio(s.id, ALLE)
    assert store.chiusura_sospesa() == ChiusuraSospesa(s.id + 1, 777, None)


def test_la_ripresa_comincia_con_la_lettura_il_buio_e_la_chiave(store):
    s = apri(store)
    assert store.ripresa() is None
    store.inizia_ripresa(ALLE, [LetteraNuova(-100, "🔌 buio")], s.id)
    assert store.ultima_lettura() == ALLE
    assert [x.testo for x in store.posta()] == ["🔌 buio"]
    assert store.ripresa() == RipresaInCorso(s.id, FERMARE)


def test_la_ripresa_senza_sondaggio_e_solo_il_buio(store):
    store.inizia_ripresa(ALLE, [LetteraNuova(-100, "🔌 buio")], None)
    assert store.ultima_lettura() == ALLE
    assert [x.testo for x in store.posta()] == ["🔌 buio"]
    assert store.ripresa() is None


def test_la_ripresa_a_meta_non_lascia_niente(store):
    s = apri(store)
    rotta = LetteraNuova(-100, "x", entita=({"non": object()},))  # non si scrive in JSON
    with pytest.raises(TypeError):
        store.inizia_ripresa(ALLE, [rotta], s.id)
    assert store.ultima_lettura() is None
    assert store.ripresa() is None
    store.inizia_ripresa(ALLE, [], s.id)
    with pytest.raises(TypeError):
        store.fermato_per_riprendere(s.id, ALLE, [rotta])
    assert store.sondaggio_aperto() == s
    assert store.ripresa() == RipresaInCorso(s.id, FERMARE)


def test_un_altro_buio_non_ricomincia_la_ripresa_dello_stesso_sondaggio(store):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    store.prova_stop_di_ripresa()
    assert store.ripresa() == RipresaInCorso(s.id, FERMARE, stop_provato=True)
    store.inizia_ripresa(ALLE + timedelta(days=2), [], s.id)
    assert store.ripresa() == RipresaInCorso(s.id, FERMARE, stop_provato=True)
    # e una riapertura che aspetta resta, dopo un altro buio senza sondaggi aperti
    store.fermato_per_riprendere(s.id, ALLE, [])
    store.inizia_ripresa(ALLE + timedelta(days=4), [], None)
    assert store.ripresa() == RipresaInCorso(s.id, RIAPRIRE)


def test_fermato_per_riprendere_chiude_accoda_e_passa_a_riaprire(store):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    store.fermato_per_riprendere(s.id, ALLE, [LetteraNuova(-100, "I conteggi")])
    assert store.sondaggio_aperto() is None
    assert store.sondaggio(s.id).chiuso_alle == ALLE
    assert [x.testo for x in store.posta()] == ["I conteggi"]
    assert store.ripresa() == RipresaInCorso(s.id, RIAPRIRE)


def test_riaprire_cambia_il_messaggio_e_tiene_voti_e_fatti(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset(DATE)), ALLE)
    store.inizia_ripresa(ALLE, [], s.id)
    store.fermato_per_riprendere(s.id, ALLE, [])
    fatti = Fatti(quasi=frozenset({d("14/10")}), possibili={d("16/10"): None})
    riaperto = store.riapri_sondaggio(
        s.id,
        (d("16/10"),),
        "poll-9",
        909,
        "Nessuna: ho tirato 1 sul calendario",
        fatti,
        ALLE,
        [LetteraNuova(-100, "Riapro il sondaggio.")],
    )
    # le date con cui è nato restano; il sondaggio di Telegram di prima si ricorda
    assert riaperto == Sondaggio(
        id=s.id,
        date=(d("16/10"),),
        poll_id="poll-9",
        messaggio=909,
        frase="Nessuna: ho tirato 1 sul calendario",
        aperto_alle=ALLE,
        date_iniziali=DATE,
        poll_prima="poll-1",
        date_prima=DATE,
    )
    assert store.sondaggio_aperto() == riaperto
    assert store.voti(s.id) == {GIO.telegram_id: Voto(frozenset(DATE))}
    assert store.fatti(s.id) == fatti
    assert [x.testo for x in store.posta()] == ["Riapro il sondaggio."]
    assert store.ripresa() is None


def test_chiudere_il_sondaggio_che_aspetta_la_riapertura_finisce_la_ripresa(store):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    store.fermato_per_riprendere(s.id, ALLE, [])
    dopo = ALLE + timedelta(hours=1)
    assert store.chiudi_sondaggio(s.id, dopo, 777, [LetteraNuova(-100, "🔒")])
    assert store.sondaggio(s.id).chiuso_alle == dopo
    assert store.chiuso_dal_comando(777)
    assert store.ripresa() is None
    assert [x.testo for x in store.posta()] == ["🔒"]
    # un sondaggio chiuso senza una ripresa che aspetta resta chiuso
    assert not store.chiudi_sondaggio(s.id, dopo, 778, [LetteraNuova(-100, "🔒")])
    assert len(store.posta()) == 1


@pytest.mark.parametrize("modo", ["apri", "rimanda"])
def test_aprire_un_sondaggio_toglie_la_riapertura_che_aspetta(store, modo):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    store.fermato_per_riprendere(s.id, ALLE, [])
    if modo == "apri":
        apri(store, poll_id="poll-2", messaggio=502)
    else:
        store.rimanda(s.id, 777, (d("21/10"),), "poll-2", 502, "Nessuna: x", ALLE)
    assert store.ripresa() is None


def test_chiudere_il_sondaggio_da_fermare_finisce_la_ripresa(store):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    store.chiudi_sondaggio(s.id, ALLE, 777)
    assert store.ripresa() is None


@pytest.mark.parametrize("chiudi", [False, True])
def test_la_fine_della_ripresa_accoda_e_toglie_la_chiave(store, chiudi):
    s = apri(store)
    store.inizia_ripresa(ALLE, [], s.id)
    if not chiudi:
        store.fermato_per_riprendere(s.id, ALLE, [])
    store.fine_ripresa(ALLE, [LetteraNuova(-100, "Fine")], chiudi=s.id if chiudi else None)
    assert store.sondaggio_aperto() is None
    assert store.sondaggio(s.id).chiuso_alle == ALLE
    assert [x.testo for x in store.posta()] == ["Fine"]
    assert store.ripresa() is None


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
    assert store.ultima_frase() is None
    store.usa_frase("Nessuna: b")
    store.usa_frase("Nessuna: a")
    store.usa_frase("Nessuna: a")
    assert store.frasi_usate() == {"Nessuna: a", "Nessuna: b"}
    assert store.ultima_frase() == "Nessuna: a"
    store.usa_frase("Nessuna: c", nuovo_giro=True)
    assert store.frasi_usate() == {"Nessuna: c"}
    assert store.ultima_frase() == "Nessuna: c"


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


def test_il_sondaggio_non_confermato_si_ricorda_con_la_risposta(store):
    assert store.ultimo_non_confermato() is None
    risposta = LetteraNuova(-100, "Telegram non ha confermato il sondaggio", risposta_a=42)
    store.segna_non_confermato(ALLE, ["mar", "16.10"], [risposta])
    assert store.ultimo_non_confermato() == NonConfermato(ALLE, ("mar", "16.10"))
    assert [(x.testo, x.risposta_a) for x in store.posta()] == [
        ("Telegram non ha confermato il sondaggio", 42)
    ]
    # vale l'ultimo
    store.segna_non_confermato(ALLE + timedelta(days=1), [])
    assert store.ultimo_non_confermato() == NonConfermato(ALLE + timedelta(days=1), ())


def test_chiudere_e_ricordare_un_sondaggio_non_confermato_insieme(store):
    s = apri(store)
    chiuso = LetteraNuova(-100, "🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo")
    assert store.chiudi_sondaggio(s.id, ALLE, 777, [chiuso], non_confermato=["21/10", "23/10"])
    assert store.ultimo_non_confermato() == NonConfermato(ALLE, ("21/10", "23/10"))
    assert [x.testo for x in store.posta()] == [chiuso.testo]


def test_un_sondaggio_sconosciuto_si_avvisa_una_volta(store):
    avviso = LetteraNuova(-100, "Ho ricevuto un voto per un sondaggio che non conosco")
    assert store.avvisa_voto_sconosciuto("poll-x", ALLE, [avviso])
    assert not store.avvisa_voto_sconosciuto("poll-x", ALLE, [avviso])
    assert store.avvisa_voto_sconosciuto("poll-y", ALLE, [avviso])
    assert len(store.posta()) == 2


def test_i_sondaggi_conosciuti(store):
    s = apri(store, poll_id="poll-1")
    store.chiudi_sondaggio(s.id, ALLE)
    store.riapri_sondaggio(s.id, DATE, "poll-2", 502, "Nessuna: x", Fatti(), ALLE)
    assert store.poll_conosciuto("poll-2")
    assert store.poll_conosciuto("poll-1")  # quello di prima della ripresa, anche senza voti
    store.registra_voto(s.id, GIO.telegram_id, "poll-2", Voto(frozenset({d("14/10")})), ALLE)
    store.chiudi_sondaggio(s.id, ALLE)
    store.riapri_sondaggio(s.id, DATE, "poll-3", 503, "Nessuna: x", Fatti(), ALLE)
    assert store.poll_conosciuto("poll-2")
    assert not store.poll_conosciuto("poll-4")


def test_un_voto_tardivo_vale_solo_senza_un_voto_nel_sondaggio_di_adesso(store):
    s = apri(store, poll_id="poll-1")
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset({d("14/10")})), ALLE)
    store.chiudi_sondaggio(s.id, ALLE)
    store.riapri_sondaggio(s.id, DATE, "poll-2", 502, "Nessuna: x", Fatti(), ALLE)
    store.registra_voto(s.id, ESTRANEO, "poll-2", Voto(nessuna=True), ALLE)
    sedici = Voto(frozenset({d("16/10")}))
    # gio ha solo il voto tenuto, del sondaggio di prima: il voto tardivo lo sostituisce
    assert store.registra_voto_tardivo(s.id, GIO.telegram_id, "poll-1", sedici, ALLE, "poll-2")
    # l'estraneo ha già votato nel sondaggio di adesso: il voto tardivo non vale
    assert not store.registra_voto_tardivo(s.id, ESTRANEO, "poll-1", sedici, ALLE, "poll-2")
    assert store.voti(s.id) == {GIO.telegram_id: sedici, ESTRANEO: Voto(nessuna=True)}
    assert store.voti_del_poll(s.id, "poll-1") == [sedici]


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
