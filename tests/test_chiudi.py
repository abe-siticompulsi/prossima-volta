import pytest

from prossima import testi
from tests.aggiornamenti import GRUPPO, comando, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, GIO, SEM, SESE, d


@pytest.fixture
def aperto(bot, telegram, store):
    """Un sondaggio su martedì 14/10 e giovedì 16/10."""
    bot.ricevi([comando("/sondaggio mar gio")])
    return store.sondaggio_aperto()


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
        ("ven", "La data ven non era nel sondaggio."),
        ("boh", "Non capisco «boh»: scrivi i giorni (lun, mar, …) o le date (14/10)."),
        ("14/10 16/10", "Non capisco «14/10 16/10»: scrivi i giorni (lun, mar, …) o le date (14/10)."),
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


def test_rimanda_se_il_sondaggio_nuovo_non_parte(bot, telegram, store, aperto):
    telegram.guasti["manda_sondaggio"] = telegram_guasto()
    bot.ricevi([comando("/chiudi rimanda")])
    # il vecchio è chiuso; del nuovo nessuno scrive niente, perché non c'è
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == []


def test_il_messaggio_del_sondaggio_cancellato(bot, telegram, store, aperto):
    telegram.cancellati.add(aperto.messaggio)
    bot.ricevi([comando("/chiudi 14/10")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [
        "Il messaggio del sondaggio non c'è più: lo considero chiuso.",
        "🎲 Si gioca martedì 14/10.",
    ]


def test_uno_stop_che_non_riesce_lascia_il_sondaggio_aperto(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto()
    bot.ricevi([comando("/chiudi")])
    assert store.sondaggio_aperto() == aperto
    assert telegram.scritti() == []
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([comando("/chiudi")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]


def test_dopo_la_chiusura_niente_annunci(bot, telegram, aperto):
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    bot.ricevi([comando("/chiudi")])
    vota(bot, telegram, SEM, "14/10")  # un voto arrivato tardi: il sondaggio è chiuso
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]
