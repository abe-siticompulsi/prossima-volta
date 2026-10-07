import json

import httpx
import pytest

from prossima.telegram import (
    BotTelegram,
    MessaggioSparito,
    SondaggioGiaChiuso,
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

TOKEN = "123:SEGRETO"


def bot_con(gestore):
    return BotTelegram(TOKEN, http=httpx.Client(transport=httpx.MockTransport(gestore)))


def ok(risultato):
    return httpx.Response(200, json={"ok": True, "result": risultato})


def rifiuto(codice, descrizione, **altro):
    return httpx.Response(
        codice, json={"ok": False, "error_code": codice, "description": descrizione, **altro}
    )


def registra(risultato):
    viste = []

    def gestore(richiesta):
        viste.append(richiesta)
        return ok(risultato)

    return viste, gestore


def corpo(richiesta):
    return json.loads(richiesta.content)


def test_io_restituisce_il_nome_del_bot():
    viste, gestore = registra({"id": 1, "is_bot": True, "username": "ProssimaVoltaBot"})
    assert bot_con(gestore).io() == "ProssimaVoltaBot"
    assert viste[0].url.path == f"/bot{TOKEN}/getMe"


def test_aggiornamenti_chiede_messaggi_e_voti():
    viste, gestore = registra([{"update_id": 5}])
    bot = bot_con(gestore)
    assert bot.aggiornamenti(7, 25) == [{"update_id": 5}]
    assert corpo(viste[0]) == {
        "timeout": 25,
        "allowed_updates": ["message", "poll_answer"],
        "offset": 7,
    }
    assert viste[0].extensions["timeout"]["read"] == 35.0
    bot.aggiornamenti(None, 0)
    assert "offset" not in corpo(viste[1])


def test_manda_un_sondaggio_non_anonimo_a_risposta_multipla():
    viste, gestore = registra({"message_id": 501, "poll": {"id": "5432", "options": []}})
    mandato = bot_con(gestore).manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert mandato == SondaggioMandato(poll_id="5432", messaggio=501)
    assert viste[0].url.path.endswith("/sendPoll")
    assert corpo(viste[0]) == {
        "chat_id": -100,
        "question": "Prossima volta?",
        "options": [{"text": "mar 14/10"}, {"text": "Nessuna: x"}],
        "is_anonymous": False,
        "allows_multiple_answers": True,
        "allows_revoting": True,
    }


def test_scrivi_testo_semplice():
    viste, gestore = registra({"message_id": 42, "text": "ciao *non* markdown"})
    assert bot_con(gestore).scrivi(-100, "ciao *non* markdown") == {
        "message_id": 42,
        "text": "ciao *non* markdown",
    }
    assert viste[0].url.path.endswith("/sendMessage")
    # niente parse_mode, niente entità vuote, niente risposta
    assert corpo(viste[0]) == {"chat_id": -100, "text": "ciao *non* markdown"}


def test_scrivi_con_le_menzioni_in_risposta_a_un_messaggio():
    viste, gestore = registra({"message_id": 43})
    menzione = {"type": "text_mention", "offset": 3, "length": 4, "user": {"id": 100000005}}
    bot_con(gestore).scrivi(-100, "📅 sese", [menzione], risposta_a=501)
    assert corpo(viste[0]) == {
        "chat_id": -100,
        "text": "📅 sese",
        "entities": [menzione],
        "reply_parameters": {"message_id": 501, "allow_sending_without_reply": True},
    }


def test_ferma_sondaggio_restituisce_i_conteggi():
    viste, gestore = registra(
        {
            "id": "5432",
            "is_closed": True,
            "options": [
                {"text": "mar 14/10", "voter_count": 3},
                {"text": "gio 16/10", "voter_count": 0},
                {"text": "Nessuna: x", "voter_count": 1},
            ],
        }
    )
    assert bot_con(gestore).ferma_sondaggio(-100, 501) == [3, 0, 1]
    assert viste[0].url.path.endswith("/stopPoll")
    assert corpo(viste[0]) == {"chat_id": -100, "message_id": 501}


def test_ferma_sondaggio_di_un_messaggio_cancellato():
    bot = bot_con(lambda r: rifiuto(400, "Bad Request: message to stop not found"))
    with pytest.raises(MessaggioSparito):
        bot.ferma_sondaggio(-100, 501)


def test_ferma_sondaggio_gia_chiuso():
    bot = bot_con(lambda r: rifiuto(400, "Bad Request: poll has already been closed"))
    with pytest.raises(SondaggioGiaChiuso, match="stopPoll: Bad Request: poll has already") as errore:
        bot.ferma_sondaggio(-100, 501)
    assert isinstance(errore.value, TelegramRifiuto)
    assert not isinstance(errore.value, MessaggioSparito)


def test_ferma_sondaggio_rifiutato_per_un_altro_motivo_non_e_sparito_ne_chiuso():
    bot = bot_con(lambda r: rifiuto(400, "Bad Request: chat not found"))
    with pytest.raises(TelegramRifiuto) as errore:
        bot.ferma_sondaggio(-100, 501)
    assert not isinstance(errore.value, MessaggioSparito | SondaggioGiaChiuso)


def test_registra_comandi():
    viste, gestore = registra(True)
    bot_con(gestore).registra_comandi(
        [("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio")]
    )
    assert viste[0].url.path.endswith("/setMyCommands")
    assert corpo(viste[0]) == {
        "commands": [
            {"command": "sondaggio", "description": "Sondaggio per la prossima volta"},
            {"command": "chiudi", "description": "Chiude il sondaggio"},
        ]
    }


def test_un_429_dice_quanto_aspettare():
    bot = bot_con(
        lambda r: rifiuto(429, "Too Many Requests: retry after 7", parameters={"retry_after": 7})
    )
    with pytest.raises(TelegramTroppeRichieste) as errore:
        bot.scrivi(-100, "x")
    assert errore.value.retry_after == 7
    assert not isinstance(errore.value, TelegramRifiuto)


def test_un_4xx_e_un_rifiuto():
    bot = bot_con(lambda r: rifiuto(403, "Forbidden: bot was kicked from the group chat"))
    with pytest.raises(TelegramRifiuto, match="sendMessage: Forbidden: bot was kicked"):
        bot.scrivi(-100, "x")


def test_un_5xx_non_e_un_rifiuto():
    bot = bot_con(lambda r: rifiuto(502, "Bad Gateway"))
    with pytest.raises(TelegramError) as errore:
        bot.scrivi(-100, "x")
    assert not isinstance(errore.value, TelegramRifiuto)


def test_un_errore_di_rete_non_rivela_il_token():
    def gestore(richiesta):
        raise httpx.ConnectError(f"impossibile raggiungere {richiesta.url}", request=richiesta)

    with pytest.raises(TelegramError) as errore:
        bot_con(gestore).scrivi(1, "x")
    assert "SEGRETO" not in str(errore.value)
    assert errore.value.__cause__ is None
    assert errore.value.__suppress_context__


def test_una_risposta_non_json():
    with pytest.raises(TelegramError, match="HTTP 502") as errore:
        bot_con(lambda r: httpx.Response(502, text="Bad gateway")).scrivi(1, "x")
    assert not isinstance(errore.value, TelegramRifiuto)
