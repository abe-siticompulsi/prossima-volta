import inspect

import pytest

from prossima.telegram import BotTelegram, MessaggioSparito
from tests.finti import TelegramFinto, telegram_guasto


def firma(funzione):
    return [(p.name, p.default) for p in inspect.signature(funzione).parameters.values()]


def test_il_finto_ha_i_metodi_del_client_vero_con_gli_stessi_argomenti():
    pubblici = [nome for nome in vars(BotTelegram) if not nome.startswith("_")]
    assert pubblici == [
        "io", "aggiornamenti", "manda_sondaggio", "scrivi", "ferma_sondaggio", "registra_comandi",
    ]
    for nome in pubblici:
        assert firma(getattr(TelegramFinto, nome)) == firma(getattr(BotTelegram, nome)), nome


def test_il_finto_registra_solo_quello_che_telegram_accetta():
    telegram = TelegramFinto()
    telegram.guasti["scrivi"] = telegram_guasto()
    with pytest.raises(type(telegram_guasto())):
        telegram.scrivi(-100, "x")
    mandato = telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert telegram.chiamate == [
        ("manda_sondaggio", {"chat_id": -100, "domanda": "Prossima volta?", "opzioni": ["mar 14/10", "Nessuna: x"]})
    ]
    assert telegram.ferma_sondaggio(-100, mandato.messaggio) == [0, 0]
    telegram.cancellati.add(mandato.messaggio)
    with pytest.raises(MessaggioSparito):
        telegram.ferma_sondaggio(-100, mandato.messaggio)
