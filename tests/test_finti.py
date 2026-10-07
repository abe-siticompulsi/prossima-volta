import inspect

import pytest

from prossima.telegram import (
    BotTelegram,
    MessaggioSparito,
    SondaggioGiaChiuso,
    TelegramError,
    TelegramRifiuto,
)
from tests.conftest import Ucciso
from tests.finti import API, TelegramFinto, telegram_guasto


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
    telegram.guasti["scrivi"] = telegram_guasto("scrivi")
    with pytest.raises(TelegramError):
        telegram.scrivi(-100, "x")
    mandato = telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert telegram.chiamate == [
        ("manda_sondaggio", {"chat_id": -100, "domanda": "Prossima volta?", "opzioni": ["mar 14/10", "Nessuna: x"]})
    ]
    assert telegram.ferma_sondaggio(-100, mandato.messaggio) == [0, 0]
    telegram.cancellati.add(mandato.messaggio)
    with pytest.raises(MessaggioSparito):
        telegram.ferma_sondaggio(-100, mandato.messaggio)


def test_il_finto_rifiuta_il_secondo_stop_come_il_vero():
    telegram = TelegramFinto()
    mandato = telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    telegram.ferma_sondaggio(-100, mandato.messaggio)
    with pytest.raises(SondaggioGiaChiuso, match="stopPoll: Bad Request: poll has already been closed"):
        telegram.ferma_sondaggio(-100, mandato.messaggio)
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1


def test_una_risposta_persa_lascia_la_chiamata_e_il_suo_effetto():
    telegram = TelegramFinto()
    telegram.risposte_perse.add("manda_sondaggio")
    with pytest.raises(TelegramError, match="^sendPoll: errore di rete") as errore:
        telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert not isinstance(errore.value, TelegramRifiuto)
    # il sondaggio è partito: Telegram l'ha fatto, il bot non lo sa
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    messaggio = telegram.ultimo_sondaggio["messaggio"]
    telegram.risposte_perse = {"ferma_sondaggio"}
    with pytest.raises(TelegramError, match="^stopPoll: errore di rete"):
        telegram.ferma_sondaggio(-100, messaggio)
    # e lo stop anche: il secondo lo rifiuta
    with pytest.raises(SondaggioGiaChiuso):
        telegram.ferma_sondaggio(-100, messaggio)


def test_il_guasto_ha_il_nome_del_metodo_dell_api():
    assert str(telegram_guasto("manda_sondaggio")) == "sendPoll: errore di rete (ConnectError)"
    assert str(telegram_guasto("ferma_sondaggio")) == "stopPoll: errore di rete (ConnectError)"
    assert str(telegram_guasto("scrivi")) == "sendMessage: errore di rete (ConnectError)"
    assert set(API) == {nome for nome in vars(BotTelegram) if not nome.startswith("_")}


def test_con_la_rete_giu_il_finto_non_risponde_gia_chiuso():
    telegram = TelegramFinto()
    mandato = telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    telegram.ferma_sondaggio(-100, mandato.messaggio)
    telegram.cancellati.add(mandato.messaggio)
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    with pytest.raises(TelegramError) as errore:
        telegram.ferma_sondaggio(-100, mandato.messaggio)
    assert not isinstance(errore.value, TelegramRifiuto)


def test_un_lotto_con_la_risposta_persa_si_riconsegna():
    telegram = TelegramFinto()
    lotto = [{"update_id": 7}, {"update_id": 8}]
    telegram.aggiornamenti_da_dare = list(lotto)
    telegram.risposte_perse.add("aggiornamenti")
    with pytest.raises(TelegramError, match="^getUpdates: "):
        telegram.aggiornamenti(None, 0)
    telegram.risposte_perse.clear()
    assert telegram.aggiornamenti(None, 0) == lotto


def test_uccidi_rimette_solo_il_metodo_ucciso(uccidi, monkeypatch, telegram, store):
    monkeypatch.setattr(telegram, "nome", "UnAltroBot")
    uccidi(store, "posta")
    with pytest.raises(Ucciso):
        store.posta()
    uccidi.basta()
    assert store.posta() == []
    assert telegram.nome == "UnAltroBot"
