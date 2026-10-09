"""I bottoni sotto il messaggio «impossibile» (spec §3.10)."""

import logging

import pytest

from prossima.bot import ATTESA_ANNUNCI
from tests.aggiornamenti import GRUPPO, comando, fino_al, tocco, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, GIO, PIPPO, SEM, SESE

IMPOSSIBILE = (
    "😬 Con i voti attuali non ci sono date con quattro giocatori. Con tre: lunedì. Gio, decidi tu:"
)
CHI_CHIUDE = "Il sondaggio lo chiude Gio (o Abe, in emergenza)."


@pytest.fixture
def impossibile(riavvia, telegram, store, orologio):
    """Lunedì con Gio e tre giocatori, hanno votato tutti: con l'attesa vera,
    dopo due minuti, solo «impossibile» con i bottoni. Restituisce il bot, il
    sondaggio e il messaggio con i bottoni."""
    bot = riavvia(attesa_annunci=ATTESA_ANNUNCI)
    bot.ricevi([comando("/sondaggio lun mar")])
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "13/10")
    for persona in (SESE, PIPPO):
        vota(bot, telegram, persona, "nessuna")
    orologio.avanza(minutes=3)
    bot.ricevi([])
    assert telegram.scritti() == [IMPOSSIBILE]
    return bot, store.sondaggio_aperto(), telegram.ultimo_scritto


def test_impossibile_ha_i_bottoni_con_il_sondaggio(impossibile, telegram):
    _, sondaggio, _ = impossibile
    [messaggio] = telegram.di_tipo("scrivi")
    assert messaggio["bottoni"] == [
        [("Tieni lunedì", f"chiudi:{sondaggio.id}:13/10")],
        [("Rimanda alla prossima settimana", f"chiudi:{sondaggio.id}:rimanda")],
    ]


def test_gio_tiene_una_data_con_un_tocco(telegram, store, impossibile):
    bot, sondaggio, messaggio = impossibile
    t = tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)
    bot.ricevi([t])
    assert telegram.di_tipo("rispondi_al_tocco") == [{"tocco_id": t["callback_query"]["id"], "avviso": None}]
    assert telegram.scritti()[-1] == "🎲 Si gioca lunedì 13/10."
    assert store.sondaggio_aperto() is None
    assert telegram.di_tipo("togli_bottoni") == [{"chat_id": GRUPPO, "messaggio": messaggio}]


def test_abe_rimanda_con_un_tocco(telegram, store, impossibile):
    bot, sondaggio, messaggio = impossibile
    bot.ricevi([tocco(f"chiudi:{sondaggio.id}:rimanda", messaggio, da=ABE.telegram_id)])
    assert telegram.scritti()[-1] == "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."
    assert store.sondaggio_aperto().id != sondaggio.id
    assert telegram.di_tipo("togli_bottoni") == [{"chat_id": GRUPPO, "messaggio": messaggio}]


def test_chi_non_puo_chiudere_ha_un_avviso_e_non_cambia_niente(telegram, store, impossibile):
    bot, sondaggio, messaggio = impossibile
    t = tocco(f"chiudi:{sondaggio.id}:13/10", messaggio, da=EMI.telegram_id)
    bot.ricevi([t])
    assert telegram.di_tipo("rispondi_al_tocco") == [
        {"tocco_id": t["callback_query"]["id"], "avviso": CHI_CHIUDE}
    ]
    assert store.sondaggio_aperto() == sondaggio
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert telegram.di_tipo("togli_bottoni") == []
    assert telegram.scritti() == [IMPOSSIBILE]


def test_un_bottone_di_un_sondaggio_gia_chiuso(telegram, store, impossibile):
    bot, sondaggio, messaggio = impossibile
    bot.ricevi([comando("/chiudi")])
    t = tocco(f"chiudi:{sondaggio.id}:rimanda", messaggio)
    bot.ricevi([t])
    assert telegram.di_tipo("rispondi_al_tocco") == [
        {"tocco_id": t["callback_query"]["id"], "avviso": "Il sondaggio è già chiuso."}
    ]
    assert telegram.di_tipo("togli_bottoni") == [{"chat_id": GRUPPO, "messaggio": messaggio}]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1  # niente rimando


def test_lo_stesso_tocco_letto_due_volte_chiude_una_volta(telegram, impossibile):
    bot, sondaggio, messaggio = impossibile
    t = tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)
    bot.ricevi([t])
    bot.ricevi([t])  # dopo un riavvio, lo stesso aggiornamento
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1
    assert telegram.scritti().count("🎲 Si gioca lunedì 13/10.") == 1


def test_due_bottoni_toccati_di_fila_vale_il_primo(telegram, store, impossibile):
    bot, sondaggio, messaggio = impossibile
    bot.ricevi([tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)])
    bot.ricevi([tocco(f"chiudi:{sondaggio.id}:rimanda", messaggio, da=ABE.telegram_id)])
    assert telegram.scritti()[-1] == "🎲 Si gioca lunedì 13/10."
    assert store.sondaggio_aperto() is None
    assert telegram.di_tipo("rispondi_al_tocco")[-1]["avviso"] == "Il sondaggio è già chiuso."


@pytest.mark.parametrize(
    ("dato", "chat"),
    [("chiudi:{id}:13/10", -42), ("boh", GRUPPO), ("chiudi:x:13/10", GRUPPO), ("chiudi:{id}", GRUPPO)],
)
def test_un_tocco_che_non_e_per_il_bot_non_fa_niente(telegram, store, impossibile, dato, chat):
    bot, sondaggio, messaggio = impossibile
    t = tocco(dato.format(id=sondaggio.id), messaggio, chat=chat)
    bot.ricevi([t])
    assert telegram.di_tipo("rispondi_al_tocco") == [{"tocco_id": t["callback_query"]["id"], "avviso": None}]
    assert store.sondaggio_aperto() == sondaggio
    assert telegram.di_tipo("togli_bottoni") == []


def test_una_risposta_al_tocco_che_non_riesce_non_ferma_la_chiusura(
    bot, telegram, store, impossibile, caplog
):
    bot, sondaggio, messaggio = impossibile
    telegram.guasti["rispondi_al_tocco"] = telegram_guasto("rispondi_al_tocco")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti()[-1] == "🎲 Si gioca lunedì 13/10."
    assert "risposta al tocco non mandata" in caplog.text


def test_bottoni_che_non_si_tolgono_vanno_nel_log(telegram, store, impossibile, caplog):
    bot, sondaggio, messaggio = impossibile
    telegram.guasti["togli_bottoni"] = telegram_guasto("togli_bottoni")
    with caplog.at_level(logging.WARNING):
        bot.ricevi([tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)])
    assert store.sondaggio_aperto() is None
    assert f"bottoni non tolti dal messaggio {messaggio}" in caplog.text


def test_una_data_passata_ha_il_rifiuto_di_chiudi_e_i_bottoni_restano(
    bot, telegram, store, orologio, impossibile
):
    bot, sondaggio, messaggio = impossibile
    fino_al(bot, orologio, 14)
    bot.ricevi([tocco(f"chiudi:{sondaggio.id}:13/10", messaggio)])
    assert telegram.scritti()[-1] == "La data 13/10 è già passata."
    assert store.sondaggio_aperto() == sondaggio
    assert telegram.di_tipo("togli_bottoni") == []
