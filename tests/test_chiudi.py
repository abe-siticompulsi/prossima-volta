import logging
import sqlite3

import pytest

from prossima import testi
from prossima.store import ChiusuraSospesa, NonConfermato
from prossima.telegram import TelegramRifiuto, TelegramTroppeRichieste
from tests.aggiornamenti import GRUPPO, comando, risposta, vota
from tests.conftest import Ucciso
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, SEM, SESE, d

NESSUNA_POSSIBILE = "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
CHIUSURA_NON_CONFERMATA = "Telegram non ha confermato la chiusura del sondaggio: riprovo da solo."


@pytest.fixture
def aperto(bot, telegram, store):
    """Un sondaggio su martedì 14/10 e giovedì 16/10."""
    bot.ricevi([comando("/sondaggio mar gio")])
    return store.sondaggio_aperto()


def fino_al(bot, orologio, giorno: int) -> None:
    """Il tempo passa fino al `giorno` di ottobre, con il bot che legge (senza
    buio, quindi senza ripresa)."""
    while orologio.adesso.day < giorno:
        orologio.avanza(hours=12)
        bot.ricevi([])


def possibile_il_14(bot, telegram):
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")


def test_solo_chi_chiude(bot, telegram, store, aperto):
    da_emi = comando("/chiudi", da=EMI.telegram_id)
    bot.ricevi([da_emi])
    assert telegram.di_tipo("scrivi") == [
        {
            "chat_id": GRUPPO,
            "testo": "Il sondaggio lo chiudono gio o abe.",
            "entita": [],
            "risposta_a": da_emi["message"]["message_id"],
        }
    ]
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto


def test_chi_non_e_nel_roster_non_chiude(bot, telegram, store, aperto):
    da_estraneo = comando("/chiudi", da=ESTRANEO)
    bot.ricevi([da_estraneo])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        ("Il sondaggio lo chiudono gio o abe.", da_estraneo["message"]["message_id"])
    ]
    assert store.sondaggio_aperto() == aperto


@pytest.mark.parametrize(
    "testo, scritto",
    [
        ("/chiudi", "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."),
        ("/chiudi 14/10", "🎲 Si gioca martedì 14/10."),
    ],
)
def test_chiudi_letto_due_volte_chiude_una_volta(bot, telegram, store, aperto, testo, scritto):
    chiudi = comando(testo)
    bot.ricevi([chiudi])
    bot.ricevi([chiudi])  # dopo un riavvio, lo stesso aggiornamento
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1
    assert telegram.scritti() == [scritto]
    assert store.sondaggio_aperto() is None


def test_senza_sondaggio_aperto(bot, telegram):
    da_gio = comando("/chiudi")
    bot.ricevi([da_gio])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        ("Non c'è nessun sondaggio aperto.", da_gio["message"]["message_id"])
    ]


def test_chiudi_dice_le_date_possibili(bot, telegram, store, aperto):
    possibile_il_14(bot, telegram)
    bot.ricevi([comando("/chiudi@ProssimaVoltaBot", da=ABE.telegram_id)])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert store.sondaggio_aperto() is None
    assert telegram.scritti()[-1] == "🔒 Sondaggio chiuso. Date possibili: mar 14/10."


def test_chiudi_senza_date_possibili(bot, telegram, aperto):
    bot.ricevi([comando("/chiudi")])
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]


@pytest.mark.parametrize("parola", ["14/10", "14.10", "mar", "MAR"])
def test_chiudi_tenendo_una_data(bot, telegram, store, aperto, parola):
    bot.ricevi([comando(f"/chiudi {parola}")])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == ["🎲 Si gioca martedì 14/10."]


@pytest.mark.parametrize(
    "argomento, testo",
    [
        ("15/10", "La data 15/10 non era nel sondaggio."),
        ("ven", "Nel sondaggio non c'è nessun venerdì."),
        ("dom", "Nel sondaggio non c'è nessuna domenica."),
        (
            "boh",
            "Non capisco «boh»: scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda.",
        ),
        (
            "14/10 16/10",
            "Non capisco «14/10 16/10»: "
            "scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda.",
        ),
    ],
)
def test_chiudi_con_una_data_sbagliata_lascia_il_sondaggio_aperto(
    bot, telegram, store, aperto, argomento, testo
):
    chiudi = comando(f"/chiudi {argomento}")
    bot.ricevi([chiudi])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        (testo, chiudi["message"]["message_id"])
    ]
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto


def test_il_riepilogo_della_chiusura_non_elenca_le_date_passate(bot, telegram, orologio, aperto):
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10 16/10")
    fino_al(bot, orologio, 15)  # mercoledì 15/10: il 14 è passato
    bot.ricevi([comando("/chiudi")])
    assert telegram.scritti()[-1] == "🔒 Sondaggio chiuso. Date possibili: gio 16/10."


@pytest.mark.parametrize("parola", ["14/10", "14/10/2025", "mar"])
def test_chiudi_con_una_data_passata_lascia_il_sondaggio_aperto(
    bot, telegram, store, orologio, aperto, parola
):
    fino_al(bot, orologio, 15)
    chiudi = comando(f"/chiudi {parola}")
    bot.ricevi([chiudi])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        ("La data 14/10 è già passata.", chiudi["message"]["message_id"])
    ]
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto


def test_chiudi_con_un_giorno_che_nel_sondaggio_compare_due_volte(bot, telegram, store):
    bot.ricevi([comando("/sondaggio 16/10 21/10 14/10")])
    aperto = store.sondaggio_aperto()
    chiudi = comando("/chiudi mar")
    bot.ricevi([chiudi])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        ("Nel sondaggio c'è più di un martedì: scrivi la data (14/10).", chiudi["message"]["message_id"])
    ]
    assert store.sondaggio_aperto() == aperto


def test_rimanda_rifa_il_sondaggio_sulla_settimana_dopo(bot, telegram, store, aperto):
    bot.ricevi([comando("/chiudi rimanda")])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 21/10", "gio 23/10", testi.FRASI_NESSUNA[1]]
    nuovo = store.sondaggio_aperto()
    assert nuovo.id != aperto.id
    assert nuovo.date == (d("21/10"), d("23/10"))
    assert telegram.scritti() == ["🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."]
    # il messaggio dice del sondaggio nuovo solo dopo che è partito
    assert [nome for nome, _ in telegram.chiamate][-3:] == ["ferma_sondaggio", "manda_sondaggio", "scrivi"]


def test_rimanda_letto_due_volte_non_chiude_il_sondaggio_nuovo(bot, telegram, store, aperto):
    rimanda = comando("/chiudi rimanda")
    bot.ricevi([rimanda])
    nuovo = store.sondaggio_aperto()
    bot.ricevi([rimanda])  # dopo un riavvio, lo stesso aggiornamento
    assert store.sondaggio_aperto() == nuovo
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1
    assert len(telegram.di_tipo("manda_sondaggio")) == 2


RIMANDO_NON_CONFERMATO = (
    "🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: "
    "se non lo vedete, lanciatelo con:\n/sondaggio@ProssimaVoltaBot 21/10 23/10"
)


def test_rimanda_se_il_sondaggio_nuovo_non_parte(bot, telegram, store, orologio, aperto, caplog):
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    rimanda = comando("/chiudi rimanda")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([rimanda])
    assert store.sondaggio_aperto() is None
    assert store.chiuso_dal_comando(rimanda["message"]["message_id"])
    assert telegram.scritti() == [RIMANDO_NON_CONFERMATO]
    [avviso] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert (avviso.levelno, avviso.exc_info) == (logging.WARNING, None)
    assert "sendPoll: errore di rete" in avviso.getMessage()
    assert store.ultimo_non_confermato() == NonConfermato(orologio.adesso, ("21/10", "23/10"))


def test_rimanda_con_il_sondaggio_nuovo_rifiutato(bot, telegram, store, aperto, caplog):
    telegram.guasti["manda_sondaggio"] = TelegramRifiuto("sendPoll: Bad Request: x")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([comando("/chiudi rimanda")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [RIMANDO_NON_CONFERMATO]
    [avviso] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert (avviso.levelno, avviso.exc_info) == (logging.ERROR, None)
    # rifiutato: non può essere partito, nessun sondaggio orfano da aspettarsi
    assert store.ultimo_non_confermato() is None


def test_rimanda_con_la_risposta_del_sondaggio_nuovo_persa(bot, telegram, store, aperto):
    telegram.risposte_perse.add("manda_sondaggio")
    bot.ricevi([comando("/chiudi rimanda")])
    # il sondaggio nuovo c'è, ma Telegram non l'ha confermato: lo si dice così
    assert len(telegram.di_tipo("manda_sondaggio")) == 2
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [RIMANDO_NON_CONFERMATO]


def test_rimanda_non_confermato_e_poi_un_voto_al_sondaggio_nuovo(bot, telegram, store, aperto):
    telegram.risposte_perse.add("manda_sondaggio")
    bot.ricevi([comando("/chiudi rimanda")])
    bot.ricevi([risposta(telegram.ultimo_sondaggio["poll_id"], ABE.telegram_id, 0)])
    assert telegram.scritti() == [
        RIMANDO_NON_CONFERMATO,
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot 21/10 23/10",
    ]


def test_rimanda_ucciso_dopo_il_sondaggio_nuovo_si_riprende(
    bot, telegram, store, aperto, uccidi, riavvia
):
    rimanda = comando("/chiudi rimanda")
    uccidi(store, "usa_frase", dopo=True)  # dopo sendPoll, prima del salvataggio
    with pytest.raises(Ucciso):
        bot.ricevi([rimanda])
    uccidi.basta()
    riavvia().ricevi([rimanda])
    # il vecchio era ancora aperto nel database: lo stop dice «già chiuso», e
    # rimanda riprende (nel gruppo resta un sondaggio doppio: caso raro, accettato)
    assert store.sondaggio(aperto.id).chiuso_alle is not None
    nuovo = store.sondaggio_aperto()
    assert nuovo.date == (d("21/10"), d("23/10"))
    assert nuovo.messaggio == telegram.ultimo_sondaggio["messaggio"]
    assert len(telegram.di_tipo("manda_sondaggio")) == 3
    assert telegram.scritti() == ["🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."]


def test_rimanda_ucciso_prima_del_salvataggio_si_riprende(
    bot, telegram, store, aperto, uccidi, riavvia
):
    rimanda = comando("/chiudi rimanda")
    uccidi(store, "rimanda")
    with pytest.raises(Ucciso):
        bot.ricevi([rimanda])
    uccidi.basta()
    assert store.sondaggio_aperto() == aperto
    riavvia().ricevi([rimanda])
    assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))
    assert telegram.scritti() == ["🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."]


def test_rimanda_toglie_le_date_passate(bot, telegram, store, orologio, aperto):
    fino_al(bot, orologio, 22)  # mercoledì 22/10: il 21 è passato
    bot.ricevi([comando("/chiudi rimanda")])
    assert telegram.ultimo_sondaggio["opzioni"] == ["gio 23/10", testi.FRASI_NESSUNA[1]]
    assert store.sondaggio_aperto().date == (d("23/10"),)
    assert telegram.scritti() == ["🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."]


def test_rimanda_con_tutte_le_date_passate_chiude_e_basta(bot, telegram, store, orologio, aperto):
    fino_al(bot, orologio, 24)  # venerdì 24/10: 21 e 23 sono passati
    bot.ricevi([comando("/chiudi rimanda")])
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == ["Le date del sondaggio sono passate: lo chiudo."]


def test_rimanda_con_il_messaggio_cancellato(bot, telegram, store, aperto):
    telegram.cancellati.add(aperto.messaggio)
    bot.ricevi([comando("/chiudi rimanda")])
    assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))
    assert telegram.scritti() == [
        "Il messaggio del sondaggio non c'è più: lo considero chiuso.",
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10.",
    ]
    # «non c'è più» prima del sondaggio nuovo, «Rimandiamo» dopo
    assert [nome for nome, _ in telegram.chiamate][-3:] == ["scrivi", "manda_sondaggio", "scrivi"]


def test_il_messaggio_del_sondaggio_cancellato(bot, telegram, store, aperto):
    telegram.cancellati.add(aperto.messaggio)
    bot.ricevi([comando("/chiudi 14/10")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [
        "Il messaggio del sondaggio non c'è più: lo considero chiuso.",
        "🎲 Si gioca martedì 14/10.",
    ]


# --- la chiusura in sospeso: lo stop non confermato lo ritenta il bot


def test_uno_stop_che_non_riesce_lo_ritenta_il_bot(bot, telegram, store, aperto, caplog):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    chiudi = comando("/chiudi")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([chiudi])
    assert store.sondaggio_aperto() == aperto
    assert store.chiusura_sospesa() == ChiusuraSospesa(aperto.id, chiudi["message"]["message_id"], None)
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        (CHIUSURA_NON_CONFERMATA, chiudi["message"]["message_id"])
    ]
    avvisi = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert {(r.levelno, r.exc_info) for r in avvisi} == {(logging.WARNING, None)}
    assert "chiusura del sondaggio" in avvisi[0].getMessage()
    assert "stopPoll: errore di rete" in avvisi[0].getMessage()
    bot.ricevi([])  # la rete è ancora giù: il sondaggio resta aperto
    assert store.sondaggio_aperto() == aperto
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([])  # il giro seguente
    assert store.sondaggio_aperto() is None
    assert store.chiuso_dal_comando(chiudi["message"]["message_id"])
    assert store.chiusura_sospesa() is None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, NESSUNA_POSSIBILE]
    bot.ricevi([])
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1


@pytest.mark.parametrize(
    "testo, scritto",
    [
        ("/chiudi", NESSUNA_POSSIBILE),
        ("/chiudi 14/10", "🎲 Si gioca martedì 14/10."),
        ("/chiudi rimanda", "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."),
    ],
)
def test_la_risposta_dello_stop_persa_il_bot_finisce_da_solo(
    bot, telegram, store, aperto, caplog, testo, scritto
):
    telegram.risposte_perse.add("ferma_sondaggio")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([comando(testo)])
        bot.ricevi([])
    # Telegram l'aveva fermato: il nuovo tentativo trova «già chiuso», e il
    # bot chiude come chiedeva il comando, una volta
    assert store.sondaggio(aperto.id).chiuso_alle is not None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, scritto]
    assert "già chiuso" in caplog.text


def test_il_rimanda_in_sospeso_apre_il_sondaggio_nuovo(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi rimanda")])
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([])
    assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))
    assert telegram.scritti() == [
        CHIUSURA_NON_CONFERMATA,
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10.",
    ]


def test_il_rimanda_in_sospeso_con_il_sondaggio_nuovo_che_non_parte(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    rimanda = comando("/chiudi rimanda")
    bot.ricevi([rimanda])
    del telegram.guasti["ferma_sondaggio"]
    telegram.guasti["manda_sondaggio"] = telegram_guasto("manda_sondaggio")
    bot.ricevi([])  # lo stop ritentato passa, il sondaggio nuovo no
    assert store.sondaggio_aperto() is None
    assert store.chiuso_dal_comando(rimanda["message"]["message_id"])
    assert store.chiusura_sospesa() is None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, RIMANDO_NON_CONFERMATO]


def test_un_completamento_che_fallisce_non_si_ritenta_fino_al_riavvio(
    bot, telegram, store, aperto, riavvia, monkeypatch, caplog
):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    rimanda = comando("/chiudi rimanda")
    bot.ricevi([rimanda])
    del telegram.guasti["ferma_sondaggio"]

    def rotta(*argomenti, **chiavi):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "usa_frase", rotta)  # dopo sendPoll, il database non risponde
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            bot.ricevi([])
    # un sondaggio nuovo solo, non uno a ogni giro; la chiusura resta in sospeso
    assert len(telegram.di_tipo("manda_sondaggio")) == 2
    sospesa = ChiusuraSospesa(aperto.id, rimanda["message"]["message_id"], "rimanda")
    assert store.chiusura_sospesa() == sospesa
    [errore] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errore.getMessage() == f"chiusura del sondaggio {aperto.id} non completata"
    assert errore.exc_info is not None
    # «Telegram non ha ancora confermato…» sarebbe falso: lo stop è passato
    lancio = comando("/sondaggio")
    bot.ricevi([lancio])
    completare = (
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot rimanda"
    )
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-1] == (
        completare,
        lancio["message"]["message_id"],
    )
    monkeypatch.undo()
    riavvia().ricevi([])  # dopo un riavvio si riprova, una volta
    assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))
    assert store.chiusura_sospesa() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 3
    assert telegram.scritti() == [
        CHIUSURA_NON_CONFERMATA,
        completare,
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10.",
    ]


@pytest.mark.parametrize(
    "testo, riga",
    [("/chiudi", "/chiudi@ProssimaVoltaBot"), ("/chiudi mar", "/chiudi@ProssimaVoltaBot 14/10")],
)
def test_dopo_un_completamento_fallito_un_chiudi_nuovo_lo_riprova(
    bot, telegram, store, aperto, monkeypatch, testo, riga
):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando(testo)])
    del telegram.guasti["ferma_sondaggio"]

    def rotta(*argomenti, **chiavi):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "chiudi_sondaggio", rotta)
    bot.ricevi([])  # lo stop passa, il completamento no
    lancio = comando("/sondaggio")
    bot.ricevi([lancio])
    assert telegram.scritti()[-1] == (
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n" + riga
    )
    monkeypatch.undo()
    nuovo = comando("/chiudi 16/10", da=ABE.telegram_id)
    bot.ricevi([nuovo])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-2:] == [
        ("Riprovo a completare la chiusura del sondaggio.", nuovo["message"]["message_id"]),
        ("🎲 Si gioca giovedì 16/10.", None),
    ]
    assert store.sondaggio_aperto() is None
    assert store.chiuso_dal_comando(nuovo["message"]["message_id"])


def test_uno_stop_durante_la_pausa_di_un_429_parte_finita_la_pausa(
    bot, telegram, store, orologio, aperto
):
    telegram.guasti["scrivi"] = TelegramTroppeRichieste("sendMessage: Too Many Requests", 30)
    bot.ricevi([comando("/sondaggio")])  # la risposta, «già aperto», prende il 429
    del telegram.guasti["scrivi"]
    bot.ricevi([comando("/chiudi 14/10")])
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto
    orologio.avanza(seconds=30)
    bot.ricevi([])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti()[-2:] == [CHIUSURA_NON_CONFERMATA, "🎲 Si gioca martedì 14/10."]


def test_uno_stop_rifiutato_va_nel_log_una_volta_e_si_ritenta(bot, telegram, store, aperto, caplog):
    rifiuto = TelegramRifiuto("stopPoll: Bad Request: message can't be stopped")
    telegram.guasti["ferma_sondaggio"] = rifiuto
    with caplog.at_level(logging.WARNING):
        bot.ricevi([comando("/chiudi")])
        bot.ricevi([])
        bot.ricevi([])
    errori = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [(r.levelno, r.exc_info) for r in errori] == [(logging.ERROR, None)]
    assert "message can't be stopped" in errori[0].getMessage()
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA]
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, NESSUNA_POSSIBILE]


def test_lo_stop_ritentato_va_nel_log_la_prima_volta_e_poi_ogni_dieci_minuti(
    bot, telegram, store, orologio, aperto, caplog
):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([comando("/chiudi")])
        for _ in range(3):
            orologio.avanza(seconds=25)
            bot.ricevi([])
    avvisi = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(avvisi) == 1
    assert "stopPoll: errore di rete" in avvisi[0]
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        orologio.avanza(minutes=10)
        bot.ricevi([])
        bot.ricevi([])
    avvisi = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(avvisi) == 1
    assert f"chiusura del sondaggio {aperto.id}" in avvisi[0]
    assert "stopPoll: errore di rete" in avvisi[0]


@pytest.mark.parametrize(
    "guasto",
    [telegram_guasto("ferma_sondaggio"), TelegramRifiuto("stopPoll: Bad Request: x")],
    ids=["rete", "rifiuto"],
)
def test_con_la_chiusura_in_sospeso_niente_annunci(bot, telegram, store, aperto, guasto):
    telegram.guasti["ferma_sondaggio"] = guasto
    bot.ricevi([comando("/chiudi")])
    possibile_il_14(bot, telegram)  # il 14/10 diventa possibile: la decisione è già presa
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA]
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([])
    assert telegram.scritti() == [
        CHIUSURA_NON_CONFERMATA,
        "🔒 Sondaggio chiuso. Date possibili: mar 14/10.",
    ]


def test_con_la_chiusura_in_sospeso_un_sondaggio_aspetta(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])
    lancio = comando("/sondaggio")
    bot.ricevi([lancio])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][-1] == (
        "Telegram non ha ancora confermato la chiusura del sondaggio di prima: riprovate fra poco.",
        lancio["message"]["message_id"],
    )
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_con_la_chiusura_in_sospeso_vale_l_ultimo_chiudi(bot, telegram, store, aperto, monkeypatch):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])
    tentativi = []
    vero = telegram.ferma_sondaggio

    def conta(chat_id, messaggio):
        tentativi.append(messaggio)
        return vero(chat_id, messaggio)

    monkeypatch.setattr(telegram, "ferma_sondaggio", conta)
    secondo = comando("/chiudi 14/10", da=ABE.telegram_id)
    bot.gestisci(secondo)  # il comando da solo, senza il giro di `manda`
    assert tentativi == []  # non manda un altro stop: lo ritenta il giro
    assert store.chiusura_sospesa() == ChiusuraSospesa(
        aperto.id, secondo["message"]["message_id"], "2025-10-14"
    )
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([])
    assert store.sondaggio_aperto() is None
    assert store.chiuso_dal_comando(secondo["message"]["message_id"])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")][1:] == [
        (CHIUSURA_NON_CONFERMATA, secondo["message"]["message_id"]),
        ("🎲 Si gioca martedì 14/10.", None),
    ]


def test_con_la_chiusura_in_sospeso_il_chiudi_riletto_non_ripete(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    chiudi = comando("/chiudi")
    bot.ricevi([chiudi])
    bot.ricevi([chiudi])  # dopo un riavvio, lo stesso aggiornamento
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA]


def test_con_la_chiusura_in_sospeso_chi_non_chiude_non_cambia_niente(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    chiudi = comando("/chiudi")
    bot.ricevi([chiudi, comando("/chiudi rimanda", da=EMI.telegram_id), comando("/chiudi boh")])
    assert store.chiusura_sospesa().comando == chiudi["message"]["message_id"]
    assert telegram.scritti()[1:] == [
        "Il sondaggio lo chiudono gio o abe.",
        "Non capisco «boh»: scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda.",
    ]


def test_ucciso_prima_di_mettere_in_sospeso(bot, telegram, store, aperto, uccidi, riavvia):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    chiudi = comando("/chiudi")
    uccidi(store, "sospendi_chiusura")
    with pytest.raises(Ucciso):
        bot.ricevi([chiudi])
    uccidi.basta()
    del telegram.guasti["ferma_sondaggio"]
    riavvia().ricevi([chiudi])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [NESSUNA_POSSIBILE]


def test_ucciso_dopo_aver_messo_in_sospeso(bot, telegram, store, aperto, uccidi, riavvia):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    chiudi = comando("/chiudi")
    uccidi(store, "sospendi_chiusura", dopo=True)
    with pytest.raises(Ucciso):
        bot.ricevi([chiudi])
    uccidi.basta()
    del telegram.guasti["ferma_sondaggio"]
    riavvia().ricevi([chiudi])  # riletto: è già in sospeso, e il giro lo chiude
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, NESSUNA_POSSIBILE]


@pytest.mark.parametrize("dopo", [False, True])
def test_ucciso_mentre_chiude_quello_in_sospeso(bot, telegram, store, aperto, uccidi, riavvia, dopo):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])  # lo stop non parte: in sospeso
    del telegram.guasti["ferma_sondaggio"]
    uccidi(store, "chiudi_sondaggio", dopo=dopo)
    with pytest.raises(Ucciso):
        bot.ricevi([])  # lo stop passa, poi il processo muore prima o dopo il salvataggio
    uccidi.basta()
    riavvia().ricevi([])
    assert store.sondaggio_aperto() is None
    assert store.chiusura_sospesa() is None
    assert telegram.scritti() == [CHIUSURA_NON_CONFERMATA, NESSUNA_POSSIBILE]


def test_ucciso_mentre_rimanda_quello_in_sospeso(bot, telegram, store, aperto, uccidi, riavvia):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi rimanda")])
    del telegram.guasti["ferma_sondaggio"]
    uccidi(store, "rimanda")
    with pytest.raises(Ucciso):
        bot.ricevi([])
    uccidi.basta()
    riavvia().ricevi([])
    # il vecchio era ancora aperto e in sospeso: «già chiuso», e rimanda riprende
    # (nel gruppo resta un sondaggio doppio: caso raro, accettato)
    assert store.sondaggio_aperto().date == (d("21/10"), d("23/10"))
    assert store.chiusura_sospesa() is None
    assert telegram.scritti() == [
        CHIUSURA_NON_CONFERMATA,
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10.",
    ]


def test_un_voto_sconosciuto_con_la_chiusura_in_sospeso_non_dice_votate_qui(
    bot, telegram, store, aperto
):
    store.segna_non_confermato(aperto.aperto_alle, ["mar", "gio"])
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])
    bot.ricevi([risposta("poll-orfano", ABE.telegram_id, 0)])
    avviso = telegram.di_tipo("scrivi")[-1]
    assert (avviso["testo"], avviso["risposta_a"]) == (
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot mar gio",
        None,
    )


@pytest.mark.parametrize(
    "testo, scritto", [("/chiudi", NESSUNA_POSSIBILE), ("/chiudi 14/10", "🎲 Si gioca martedì 14/10.")]
)
def test_ucciso_fra_lo_stop_e_il_salvataggio_lo_stesso_chiudi_ripreso(
    bot, telegram, store, aperto, uccidi, riavvia, testo, scritto
):
    chiudi = comando(testo)
    uccidi(store, "chiudi_sondaggio")
    with pytest.raises(Ucciso):
        bot.ricevi([chiudi])
    uccidi.basta()
    assert store.sondaggio_aperto() == aperto
    # dopo il riavvio Telegram ridà lo stesso aggiornamento: l'offset non era salvato
    riavvia().ricevi([chiudi])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [scritto]


def test_ucciso_dopo_la_chiusura_la_lettera_non_si_perde(
    bot, telegram, store, aperto, uccidi, riavvia
):
    chiudi = comando("/chiudi")
    uccidi(store, "chiudi_sondaggio", dopo=True)
    with pytest.raises(Ucciso):
        bot.ricevi([chiudi])
    uccidi.basta()
    assert store.sondaggio_aperto() is None
    riavvia().ricevi([chiudi])
    assert telegram.scritti() == [NESSUNA_POSSIBILE]


def test_dopo_la_chiusura_niente_annunci(bot, telegram, aperto):
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    bot.ricevi([comando("/chiudi")])
    vota(bot, telegram, SEM, "14/10")  # un voto arrivato tardi: il sondaggio è chiuso
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]
