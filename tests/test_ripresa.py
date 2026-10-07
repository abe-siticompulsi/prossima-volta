import logging
import sqlite3
from datetime import UTC, datetime

import pytest

from prossima import testi
from prossima.regole import Voto
from prossima.store import FERMARE, RIAPRIRE, RipresaInCorso
from prossima.telegram import TelegramTroppeRichieste
from tests.aggiornamenti import comando, risposta, vota
from tests.conftest import Ucciso
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, SEM, SESE, d

BUIO = (
    "🔌 Sono rimasto senza Telegram dal 7/10 alle 20:00 al 9/10 alle 2:00. "
    "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
)
UGUALI = "I conteggi del sondaggio sono gli stessi che avevo io."
DIVERSI = (
    "I conteggi del sondaggio sono diversi dai miei: "
    "qualcuno ha votato o cambiato voto senza che lo sapessi."
)
RIAPRO = (
    "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
    "non serve rivotare. Non hanno ancora votato: gio, sese, pippo."
)
GIA_CHIUSO = "Il sondaggio risultava già chiuso."
GIA_CHIUSO_SENZA_CONFRONTO = "Il sondaggio risultava già chiuso: non posso confrontare i conteggi."
CHIUSURA_NON_CONFERMATA = "Telegram non ha confermato la chiusura del sondaggio: riprovo da solo."


def dopo_il_buio(bot, orologio, ore=30):
    """L'ultima lettura riuscita è di adesso; la prossima arriva `ore` dopo."""
    orologio.avanza(hours=ore)
    bot.ricevi([])


def test_la_prima_lettura_non_e_buio(bot, telegram):
    bot.ricevi([])
    assert telegram.chiamate == []


def test_23_ore_non_sono_buio(bot, telegram, orologio):
    bot.ricevi([])
    dopo_il_buio(bot, orologio, ore=23)
    assert telegram.chiamate == []


def test_senza_sondaggio_solo_il_messaggio_del_buio(bot, telegram, orologio):
    orologio.adesso = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    bot.ricevi([])
    orologio.adesso = datetime(2025, 10, 14, 7, 30, tzinfo=UTC)
    bot.ricevi([])
    assert telegram.scritti() == [
        "🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10 alle 9:30. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    ]


def sondaggio_con_tre_voti(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, ABE, "14/10")
    vota(bot, telegram, EMI, "14/10 16/10")
    vota(bot, telegram, SEM, "nessuna")
    return store.sondaggio_aperto()


def test_conteggi_uguali_riapre_e_tiene_i_voti(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.di_tipo("ferma_sondaggio")[-1]["messaggio"] == vecchio.messaggio
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", "gio 16/10", testi.FRASI_NESSUNA[1]]
    assert telegram.scritti() == [BUIO, UGUALI, RIAPRO]
    assert store.ripresa() is None
    # il buio e i conteggi prima del sondaggio nuovo, «Riapro» dopo
    nomi = [nome for nome, _ in telegram.chiamate if nome != "aggiornamenti"]
    assert nomi[-5:] == ["ferma_sondaggio", "scrivi", "scrivi", "manda_sondaggio", "scrivi"]
    riaperto = store.sondaggio_aperto()
    assert riaperto.id == vecchio.id
    assert riaperto.poll_id == telegram.ultimo_sondaggio["poll_id"] != vecchio.poll_id
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("14/10"), d("16/10")}))
    # nel sondaggio nuovo il voto nuovo sostituisce quello tenuto buono
    vota(bot, telegram, EMI, "16/10")
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("16/10")}))


def test_conteggi_diversi(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]  # qualcuno ha votato al buio
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[:2] == [BUIO, DIVERSI]


def test_i_conteggi_comprendono_chi_non_e_nel_roster(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    vota(bot, telegram, ESTRANEO, "16/10")
    telegram.conteggi[vecchio.messaggio] = [2, 2, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[1] == UGUALI


def test_dopo_una_seconda_ripresa_contano_solo_i_voti_del_sondaggio_nuovo(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio, ore=24)
    vota(bot, telegram, GIO, "16/10")  # l'unico voto dato nel sondaggio riaperto
    riaperto = store.sondaggio_aperto()
    telegram.conteggi[riaperto.messaggio] = [0, 1, 0]
    dopo_il_buio(bot, orologio, ore=24)
    assert telegram.scritti().count(UGUALI) == 2


def test_le_date_passate_non_si_riaprono(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 14/10")])
    dopo_il_buio(bot, orologio, ore=30)  # giovedì 9/10 alle 2:00
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", testi.FRASI_NESSUNA[1]]
    assert store.sondaggio_aperto().date == (d("14/10"),)
    # le opzioni sono quelle nuove: la prima ora è il 14/10
    vota(bot, telegram, ABE, "14/10")
    assert store.voti(store.sondaggio_aperto().id)[ABE.telegram_id] == Voto(frozenset({d("14/10")}))


def test_un_voto_al_sondaggio_di_prima_arrivato_dopo_la_riapertura(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 14/10")])
    vecchio = store.sondaggio_aperto()
    vota(bot, telegram, EMI, "8/10")
    dopo_il_buio(bot, orologio)  # giovedì 9/10: l'8 è passato, il sondaggio riaperto ha solo il 14
    riaperto = store.sondaggio_aperto()
    assert riaperto.date == (d("14/10"),)
    vota(bot, telegram, ABE, "nessuna")  # abe vota nel sondaggio riaperto
    # voti dati nel sondaggio di prima poco prima dello stop, arrivati dopo la
    # riapertura: le opzioni sono quelle di prima (la seconda era il 14/10)
    bot.ricevi(
        [
            risposta(vecchio.poll_id, GIO.telegram_id, 1),
            risposta(vecchio.poll_id, EMI.telegram_id, 0, 1),
            risposta(vecchio.poll_id, ABE.telegram_id, 1),
        ]
    )
    voti = store.voti(riaperto.id)
    assert voti[GIO.telegram_id] == Voto(frozenset({d("14/10")}))
    assert voti[EMI.telegram_id] == Voto(frozenset({d("8/10"), d("14/10")}))
    # abe ha già votato nel sondaggio riaperto: vale quel voto
    assert voti[ABE.telegram_id] == Voto(nessuna=True)
    assert not any("non conosco" in t for t in telegram.scritti())


def test_rimanda_dopo_una_riapertura_usa_i_giorni_del_sondaggio_iniziale(
    bot, telegram, store, orologio
):
    bot.ricevi([comando("/sondaggio 8/10 14/10")])  # mercoledì e martedì
    dopo_il_buio(bot, orologio)  # riaperto con il solo martedì 14/10
    bot.ricevi([comando("/chiudi rimanda")])
    assert store.sondaggio_aperto().date == (d("21/10"), d("22/10"))


def test_tutte_le_date_passate_chiude_e_basta(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 9/10")])
    dopo_il_buio(bot, orologio, ore=80)
    assert store.sondaggio_aperto() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti()[1:] == [UGUALI, "Le date del sondaggio sono passate: lo chiudo."]


def test_il_sondaggio_cancellato_durante_il_buio(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.cancellati.add(vecchio.messaggio)
    dopo_il_buio(bot, orologio)
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [BUIO, "Il messaggio del sondaggio non c'è più: lo considero chiuso."]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_gia_chiuso_senza_sapere_da_chi_si_chiude_e_lo_dice(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    # chiuso su Telegram, e nessuno stop di questo bot lo spiega (un /chiudi
    # perso nel buio, con il processo fermato prima di salvarlo)
    telegram.fermati.add(vecchio.messaggio)
    dopo_il_buio(bot, orologio)
    assert telegram.scritti() == [BUIO, GIA_CHIUSO]
    assert store.sondaggio_aperto() is None
    assert store.sondaggio(vecchio.id).chiuso_alle is not None
    assert store.ripresa() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_gia_chiuso_da_uno_stop_della_ripresa_si_riapre_senza_confronto(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.risposte_perse.add("ferma_sondaggio")
    dopo_il_buio(bot, orologio)  # lo stop passa, la risposta no
    assert telegram.scritti() == [BUIO]
    assert store.sondaggio_aperto() == vecchio
    telegram.risposte_perse.clear()
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO, GIA_CHIUSO_SENZA_CONFRONTO, RIAPRO]
    assert store.sondaggio_aperto().id == vecchio.id
    assert store.ripresa() is None


@pytest.mark.parametrize(
    "guasto, chiudi, scritto",
    [
        # lo stop del /chiudi era passato: Telegram dice che è già chiuso
        ("risposta persa", "/chiudi 14/10", "🎲 Si gioca martedì 14/10."),
        # lo stop del /chiudi non era passato: lo ferma adesso
        ("rete", "/chiudi", "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."),
    ],
)
def test_con_una_chiusura_in_sospeso_la_ripresa_completa_il_chiudi(
    bot, telegram, store, orologio, guasto, chiudi, scritto
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    if guasto == "rete":
        telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    else:
        telegram.risposte_perse.add("ferma_sondaggio")
    bot.gestisci(comando(chiudi))  # il comando da solo: la chiusura resta in sospeso
    assert store.chiusura_sospesa().sondaggio == vecchio.id
    telegram.guasti.clear()
    telegram.risposte_perse.clear()
    dopo_il_buio(bot, orologio)
    # chi può chiudere l'aveva chiuso: niente riapertura
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, BUIO, scritto]
    assert store.sondaggio_aperto() is None
    assert store.chiusura_sospesa() is None
    assert store.ripresa() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_gli_annunci_fatti_restano_e_dopo_la_ripresa_non_si_sa_chi(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    possibile = "✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese."
    assert possibile in telegram.scritti()
    telegram.conteggi[store.sondaggio_aperto().messaggio] = [5, 0, 0]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti().count(possibile) == 1
    vota(bot, telegram, SEM, "nessuna")
    # il «quasi» del 14/10 era già stato detto prima del «possibile»: non si ripete
    assert telegram.scritti()[-1] == (
        "⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro giocatori."
    )


def avvisi(caplog):
    return [(r.levelno, r.getMessage(), r.exc_info) for r in caplog.records if r.levelno >= logging.WARNING]


def test_lo_stop_che_non_riesce_si_ritenta_alla_lettura_seguente(
    bot, telegram, store, orologio, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    with caplog.at_level(logging.WARNING):
        dopo_il_buio(bot, orologio)
        orologio.avanza(seconds=25)
        bot.ricevi([])  # ancora giù: lo stop si ritenta, l'avviso no
    [(livello, messaggio, traceback)] = avvisi(caplog)
    assert (livello, traceback) == (logging.WARNING, None)
    assert f"ripresa del sondaggio {vecchio.id}" in messaggio
    assert "stopPoll: errore di rete" in messaggio
    assert store.sondaggio_aperto() == vecchio
    assert store.ripresa() == RipresaInCorso(vecchio.id, FERMARE, stop_provato=True)
    assert telegram.scritti() == [BUIO]
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        orologio.avanza(minutes=10)
        bot.ricevi([])  # dieci minuti dopo il primo avviso, un altro
    assert len(avvisi(caplog)) == 1
    del telegram.guasti["ferma_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO, UGUALI, RIAPRO]
    assert store.sondaggio_aperto().id == vecchio.id
    assert store.ripresa() is None


def test_il_sondaggio_che_non_parte_nella_ripresa_riparte_alla_lettura_seguente(
    bot, telegram, store, orologio, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    with caplog.at_level(logging.WARNING):
        dopo_il_buio(bot, orologio)
    [(livello, messaggio, traceback)] = avvisi(caplog)
    assert (livello, traceback) == (logging.WARNING, None)
    assert "sendPoll: errore di rete" in messaggio
    # niente «riprovate con /sondaggio»: butterebbe i voti tenuti
    assert telegram.scritti() == [BUIO, UGUALI]
    assert store.sondaggio_aperto() is None
    assert store.ripresa() == RipresaInCorso(vecchio.id, RIAPRIRE)
    del telegram.guasti["manda_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO, UGUALI, RIAPRO]
    riaperto = store.sondaggio_aperto()
    assert riaperto.id == vecchio.id
    assert riaperto.poll_id == telegram.ultimo_sondaggio["poll_id"]
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("14/10"), d("16/10")}))
    assert store.ripresa() is None


def test_un_sondaggio_lanciato_mentre_la_riapertura_aspetta_vale_quello(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)
    del telegram.guasti["manda_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([comando("/sondaggio ven")])
    nuovo = store.sondaggio_aperto()
    assert nuovo.id != vecchio.id
    assert nuovo.date == (d("17/10"),)
    assert store.ripresa() is None
    assert telegram.scritti() == [BUIO, UGUALI]
    assert len(telegram.di_tipo("manda_sondaggio")) == 2


@pytest.mark.parametrize(
    "testo, guasto_dopo, scritto",
    [
        ("/chiudi", True, "🔒 Sondaggio chiuso. Date possibili: mar 14/10."),
        ("/chiudi 14/10", True, "🎲 Si gioca martedì 14/10."),
        (
            "/chiudi rimanda",
            True,
            "🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: "
            "se non lo vedete, lanciatelo con:\n/sondaggio@ProssimaVoltaBot 21/10 23/10",
        ),
        ("/chiudi rimanda", False, "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."),
    ],
)
def test_un_chiudi_mentre_la_riapertura_aspetta_chiude_con_i_voti_tenuti(
    bot, telegram, store, orologio, testo, guasto_dopo, scritto
):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    vecchio = store.sondaggio_aperto()
    telegram.conteggi[vecchio.messaggio] = [5, 0, 0]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)  # fermo, e la riapertura aspetta
    assert store.ripresa() == RipresaInCorso(vecchio.id, RIAPRIRE)
    if not guasto_dopo:
        del telegram.guasti["manda_sondaggio"]
    chiudi = comando(testo)
    bot.ricevi([chiudi])
    telegram.guasti.clear()
    orologio.avanza(seconds=25)
    bot.ricevi([])
    # vince il comando: niente riapertura, il messaggio una volta
    assert telegram.scritti()[-3:] == [BUIO, UGUALI, scritto]
    assert telegram.scritti().count(scritto) == 1
    assert not any(t.startswith("Riapro") for t in telegram.scritti())
    assert store.ripresa() is None
    assert store.chiuso_dal_comando(chiudi["message"]["message_id"])
    if guasto_dopo:
        assert store.sondaggio_aperto() is None
        assert len(telegram.di_tipo("manda_sondaggio")) == 1
    else:
        assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))


SCONOSCIUTO_MAR = (
    "Ho ricevuto un voto per un sondaggio che non conosco: "
    "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
    "/sondaggio@ProssimaVoltaBot mar"
)


def test_mentre_lo_stop_della_ripresa_non_e_confermato_il_sondaggio_non_conta_come_aperto(
    bot, telegram, store, orologio
):
    sondaggio_con_tre_voti(bot, telegram, store)
    store.segna_non_confermato(orologio.adesso, ["mar"])  # un tentativo recente, per l'avviso
    telegram.risposte_perse.add("ferma_sondaggio")
    dopo_il_buio(bot, orologio)  # lo stop della ripresa passa, la risposta no
    telegram.risposte_perse.clear()
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    lancio = comando("/sondaggio")
    bot.ricevi([lancio, risposta("poll-orfano", ABE.telegram_id, 0)])
    # né «C'è già un sondaggio aperto» né «votate qui»: forse è già fermo. E il
    # voto sconosciuto resta nel log: la ripresa è in corso
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-1:] == [
        (
            "Telegram non ha ancora confermato la chiusura del sondaggio di prima: "
            "riprovate fra poco.",
            lancio["message"]["message_id"],
        ),
    ]
    assert SCONOSCIUTO_MAR not in telegram.scritti()


def test_i_voti_al_sondaggio_fermato_mentre_la_riapertura_aspetta_si_tengono(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)
    # un voto dato poco prima dello stop, arrivato mentre la riapertura aspetta
    bot.ricevi([risposta(vecchio.poll_id, GIO.telegram_id, 0)])
    del telegram.guasti["manda_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti()[-1] == (
        "Riapro il sondaggio. Ho già i voti di gio, abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: sese, pippo."
    )
    assert store.voti(vecchio.id)[GIO.telegram_id] == Voto(frozenset({d("14/10")}))


def test_mentre_la_riapertura_aspetta_un_voto_sconosciuto_va_solo_nel_log(
    bot, telegram, store, orologio, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    store.segna_non_confermato(orologio.adesso, ["mar"])
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)
    with caplog.at_level(logging.WARNING):
        bot.ricevi([risposta("poll-orfano", ABE.telegram_id, 0)])
    # «Rilanciatelo» farebbe buttare i voti tenuti
    assert telegram.scritti() == [BUIO, UGUALI]
    assert any("poll-orfano" in messaggio for _, messaggio, _ in avvisi(caplog))


def test_mentre_la_ripresa_fa_lo_stop_un_voto_sconosciuto_va_solo_nel_log(
    bot, telegram, store, orologio, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    store.segna_non_confermato(orologio.adesso, ["mar"])
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    dopo_il_buio(bot, orologio)
    assert store.ripresa() == RipresaInCorso(vecchio.id, FERMARE, stop_provato=True)
    with caplog.at_level(logging.WARNING):
        bot.ricevi([risposta("poll-orfano", ABE.telegram_id, 0)])
    # «Rilanciatelo», come «votate qui», farebbe buttare i voti che la ripresa tiene
    assert telegram.scritti() == [BUIO]
    assert any("poll-orfano" in messaggio for _, messaggio, _ in avvisi(caplog))
    assert store.ripresa() == RipresaInCorso(vecchio.id, FERMARE, stop_provato=True)


def test_un_429_nella_ripresa(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["ferma_sondaggio"] = TelegramTroppeRichieste("stopPoll: Too Many Requests", 30)
    dopo_il_buio(bot, orologio)
    del telegram.guasti["ferma_sondaggio"]
    orologio.avanza(seconds=20)
    bot.ricevi([])  # durante la pausa: né lo stop né la posta
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert telegram.scritti() == []
    orologio.avanza(seconds=10)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO, UGUALI, RIAPRO]
    assert store.ripresa() is None


def test_un_sondaggio_lanciato_dopo_una_riapertura_guasta_vale_al_suo_posto(
    bot, telegram, store, orologio, monkeypatch, riavvia
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]

    def rotta(*argomenti, **chiavi):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "usa_frase", rotta)  # dopo il sendPoll della riapertura
    dopo_il_buio(bot, orologio)
    assert store.ripresa() == RipresaInCorso(vecchio.id, RIAPRIRE)
    monkeypatch.undo()
    bot.ricevi([comando("/sondaggio ven")])
    assert store.ripresa() is None  # tolta con l'apertura, nella stessa transazione
    bot.ricevi([comando("/chiudi")])
    riavvia().ricevi([])
    assert not any(t.startswith("Riapro") for t in telegram.scritti())
    assert store.ripresa() is None
    assert store.sondaggio_aperto() is None


def test_sondaggio_e_due_chiudi_nello_stesso_lotto_mentre_la_riapertura_aspetta(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)
    del telegram.guasti["manda_sondaggio"]
    secondo = comando("/chiudi")
    bot.ricevi([comando("/sondaggio ven"), comando("/chiudi"), secondo])
    assert sum(t.startswith("🔒") for t in telegram.scritti()) == 1
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-1] == (
        "Non c'è nessun sondaggio aperto.",
        secondo["message"]["message_id"],
    )
    assert not store.chiuso_dal_comando(secondo["message"]["message_id"])
    assert store.ripresa() is None
    assert not any(t.startswith("Riapro") for t in telegram.scritti())


def test_le_date_passate_mentre_la_riapertura_aspetta(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 9/10")])
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)  # giovedì 9/10 alle 2:00: il 9 non è passato
    assert store.ripresa() is not None
    orologio.avanza(hours=22)  # venerdì 10/10
    bot.ricevi([])
    assert telegram.scritti() == [BUIO, UGUALI, "Le date del sondaggio sono passate: lo chiudo."]
    assert store.sondaggio_aperto() is None
    assert store.ripresa() is None


def test_un_errore_che_non_viene_da_telegram_sospende_la_ripresa_fino_al_riavvio(
    bot, telegram, store, orologio, monkeypatch, riavvia, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)

    def rotta(*argomenti):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "voti_del_poll", rotta)  # dopo lo stop, il database non risponde
    with caplog.at_level(logging.WARNING):
        dopo_il_buio(bot, orologio)
        for _ in range(3):
            orologio.avanza(seconds=25)
            bot.ricevi([])
    errori = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [r.getMessage() for r in errori] == [f"ripresa del sondaggio {vecchio.id} non riuscita"]
    assert errori[0].exc_info is not None
    # la ripresa resta, ma non si ritenta fino al riavvio
    assert store.ripresa() == RipresaInCorso(vecchio.id, FERMARE, stop_provato=True)
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1
    assert telegram.scritti() == [BUIO]
    # lo stop è confermato: «Telegram non ha ancora confermato…» sarebbe falso
    lancio = comando("/sondaggio")
    bot.ricevi([lancio])
    non_completata = (
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot"
    )
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-1] == (
        non_completata,
        lancio["message"]["message_id"],
    )
    monkeypatch.undo()
    riavvia().ricevi([])  # il riavvio riprova, una volta
    assert telegram.scritti() == [BUIO, non_completata, GIA_CHIUSO_SENZA_CONFRONTO, RIAPRO]
    assert store.sondaggio_aperto().id == vecchio.id
    assert store.ripresa() is None


def test_un_chiudi_guasto_mentre_la_riapertura_aspetta_ferma_la_ripresa(
    bot, telegram, store, orologio, monkeypatch, caplog
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    dopo_il_buio(bot, orologio)

    def rotta(*argomenti, **chiavi):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "chiudi_sondaggio", rotta)
    del telegram.guasti["manda_sondaggio"]
    with caplog.at_level(logging.WARNING):
        bot.ricevi([comando("/chiudi")])
        orologio.avanza(seconds=25)
        bot.ricevi([])
    # chi può chiudere ha chiuso: la riapertura non riparte da sola
    assert not any(t.startswith("Riapro") for t in telegram.scritti())
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    errori = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [r.getMessage() for r in errori] == [f"chiusura del sondaggio {vecchio.id} non completata"]
    assert errori[0].exc_info is not None


def test_un_sondaggio_nato_nel_lotto_del_buio_non_si_ferma(bot, telegram, store, orologio):
    bot.ricevi([])
    orologio.avanza(hours=30)
    bot.ricevi([comando("/sondaggio mar gio")])
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti() == [BUIO]
    assert store.ripresa() is None


@pytest.mark.parametrize(
    "dove, metodo, dopo, conteggi",
    [
        ("store", "inizia_ripresa", False, UGUALI),
        ("store", "inizia_ripresa", True, UGUALI),
        ("store", "prova_stop_di_ripresa", False, UGUALI),
        ("store", "prova_stop_di_ripresa", True, UGUALI),
        # lo stop è passato: il nuovo tentativo trova il sondaggio già chiuso
        ("telegram", "ferma_sondaggio", True, GIA_CHIUSO_SENZA_CONFRONTO),
        ("store", "fermato_per_riprendere", False, GIA_CHIUSO_SENZA_CONFRONTO),
        ("store", "fermato_per_riprendere", True, UGUALI),
        ("telegram", "manda_sondaggio", True, UGUALI),
        ("store", "riapri_sondaggio", False, UGUALI),
        ("store", "riapri_sondaggio", True, UGUALI),
    ],
)
def test_la_ripresa_uccisa_a_meta_si_completa_al_giro_seguente(
    bot, telegram, store, orologio, uccidi, riavvia, dove, metodo, dopo, conteggi
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    uccidi(store if dove == "store" else telegram, metodo, dopo=dopo)
    orologio.avanza(hours=30)
    with pytest.raises(Ucciso):
        bot.ricevi([])
    uccidi.basta()
    riavvia().ricevi([])
    assert telegram.scritti() == [BUIO, conteggi, RIAPRO]
    assert store.sondaggio_aperto().id == vecchio.id
    assert store.ripresa() is None


def test_la_ripresa_arriva_dopo_gli_aggiornamenti_del_lotto(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]
    orologio.avanza(hours=30)
    voto_di_gio = {
        "update_id": 5000,
        "poll_answer": {"poll_id": vecchio.poll_id, "user": {"id": GIO.telegram_id}, "option_ids": [0]},
    }
    bot.ricevi([voto_di_gio])
    # il voto di gio, arrivato nel lotto, conta: i conteggi tornano
    assert telegram.scritti()[:2] == [BUIO, UGUALI]
    assert store.voti(vecchio.id)[GIO.telegram_id] == Voto(frozenset({d("14/10")}))
