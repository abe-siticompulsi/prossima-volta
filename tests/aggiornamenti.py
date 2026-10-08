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
