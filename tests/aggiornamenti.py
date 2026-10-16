"""Gli aggiornamenti di Telegram come li riceve il bot: comandi e voti."""

from __future__ import annotations

from itertools import count

from prossima import regole
from prossima.regole import Persona
from tests.tavolo import GIO, d

GRUPPO = -1000000000001  # il gruppo del party, finto
NOME = "ProssimaVoltaBot"

_numeri = count(1)


def comando(testo: str, da: int = GIO.telegram_id, chat: int = GRUPPO) -> dict:
    """Un messaggio nel gruppo: con la privacy attiva, al bot arrivano solo i comandi."""
    n = next(_numeri)
    return {
        "update_id": 1000 + n,
        "message": {
            "message_id": 9000 + n,
            "from": {"id": da, "is_bot": False, "first_name": "x"},
            "chat": {"id": chat, "type": "supergroup" if chat < 0 else "private"},
            "date": 1760000000,
            "text": testo,
        },
    }


def risposta(poll_id: str, da: int, *opzioni: int) -> dict:
    """Un voto: le opzioni spuntate, da 0; nessuna opzione è il voto tolto."""
    n = next(_numeri)
    return {
        "update_id": 1000 + n,
        "poll_answer": {
            "poll_id": poll_id,
            "user": {"id": da, "is_bot": False, "first_name": "x"},
            "option_ids": list(opzioni),
        },
    }


def tocco(dato: str, messaggio: int, da: int = GIO.telegram_id, chat: int = GRUPPO) -> dict:
    """Un tocco su un bottone sotto il messaggio `messaggio` del bot: arriva come
    `callback_query`, anche con la privacy attiva."""
    n = next(_numeri)
    return {
        "update_id": 1000 + n,
        "callback_query": {
            "id": f"tocco-{n}",
            "from": {"id": da, "is_bot": False, "first_name": "x"},
            "message": {"message_id": messaggio, "chat": {"id": chat, "type": "supergroup"}},
            "chat_instance": "istanza",
            "data": dato,
        },
    }


def vota(bot, telegram, chi: Persona | int, scritto: str = "") -> None:
    """`chi` (una persona, o un identificativo Telegram) vota nell'ultimo
    sondaggio mandato: «14/10 16/10», «nessuna», oppure «» per togliere il voto."""
    sondaggio = telegram.ultimo_sondaggio
    opzioni = []
    for parola in scritto.split():
        if parola == "nessuna":
            opzioni.append(len(sondaggio["opzioni"]) - 1)
        else:
            opzioni.append(sondaggio["opzioni"].index(regole.etichetta(d(parola))))
    utente = chi if isinstance(chi, int) else chi.telegram_id
    bot.ricevi([risposta(sondaggio["poll_id"], utente, *opzioni)])


def fino_al(bot, orologio, giorno: int) -> None:
    """Il tempo passa fino al `giorno` di ottobre, con il bot che legge (senza
    buio, quindi senza ripresa)."""
    while orologio.adesso.day < giorno:
        orologio.avanza(hours=12)
        bot.ricevi([])


def scritto(
    testo: str,
    da: int = GIO.telegram_id,
    chat: int = GRUPPO,
    citato: dict | None = None,
    nome: str = "x",
) -> dict:
    """Un messaggio che non è un comando: nel gruppo arriva solo se risponde a
    un messaggio del bot (`citato`, v. `del_bot`)."""
    aggiornamento = comando(testo, da, chat)
    messaggio = aggiornamento["message"]
    messaggio["from"]["first_name"] = nome
    if citato is not None:
        messaggio["reply_to_message"] = citato
    return aggiornamento


def del_bot(message_id: int, testo: str | None = None, domanda: str | None = None) -> dict:
    """Un messaggio del bot, come compare in `reply_to_message`: un testo o un sondaggio."""
    messaggio = {
        "message_id": message_id,
        "from": {"id": 42, "is_bot": True, "first_name": "Prossima volta", "username": NOME},
        "chat": {"id": GRUPPO, "type": "supergroup"},
        "date": 1760000000,
    }
    if testo is not None:
        messaggio["text"] = testo
    if domanda is not None:
        messaggio["poll"] = {"id": "p", "question": domanda, "options": []}
    return messaggio
