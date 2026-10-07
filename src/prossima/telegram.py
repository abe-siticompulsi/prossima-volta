"""Il client del bot Telegram. Nessuna politica: chiama l'API e restituisce
quello che serve.

Il token sta nell'URL di ogni chiamata. Per questo gli errori non riportano mai
il testo delle eccezioni di httpx, che può contenere l'URL, e non le
incatenano (`from None`): un `log.exception` le stamperebbe. Per lo stesso
motivo `principale.py` alza il livello del logger `httpx`, che al livello INFO
scriverebbe ogni URL, token compreso.

Gli errori dicono a chi li riceve se ripetere serve:
- `TelegramTroppeRichieste` (429): sì, ma non prima di `retry_after` secondi;
- `TelegramRifiuto` (gli altri 4xx): no, la stessa richiesta verrà rifiutata
  di nuovo; `MessaggioSparito` è il rifiuto di `stopPoll` per un messaggio
  cancellato;
- `TelegramError` (rete, 5xx, risposta non JSON): sì, al giro seguente.

Nessuna chiamata usa `parse_mode`: i testi sono semplici, e le menzioni sono
entità.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

# Telegram descrive un messaggio che non c'è più come «message to … not found».
_SPARITO = re.compile(r"message[^:]*not found|MESSAGE_ID_INVALID", re.IGNORECASE)


class TelegramError(RuntimeError):
    """Una chiamata all'API di Telegram non è andata a buon fine."""


class TelegramRifiuto(TelegramError):
    """Telegram ha rifiutato la richiesta (4xx): ripeterla non serve."""


class MessaggioSparito(TelegramRifiuto):
    """Il messaggio del sondaggio non c'è più: è stato cancellato."""


class TelegramTroppeRichieste(TelegramError):
    """429: niente richieste prima di `retry_after` secondi."""

    def __init__(self, messaggio: str, retry_after: int) -> None:
        super().__init__(messaggio)
        self.retry_after = retry_after


@dataclass(frozen=True)
class SondaggioMandato:
    poll_id: str
    messaggio: int


class BotTelegram:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._http = http or httpx.Client(timeout=httpx.Timeout(10.0))

    def _chiama(self, metodo: str, corpo: dict | None = None, timeout: float | None = None) -> Any:
        argomenti: dict[str, Any] = {"json": corpo or {}}
        if timeout is not None:
            argomenti["timeout"] = timeout
        try:
            risposta = self._http.post(self._base + metodo, **argomenti)
        except httpx.HTTPError as e:
            raise TelegramError(f"{metodo}: errore di rete ({type(e).__name__})") from None
        try:
            contenuto = risposta.json()
        except ValueError:
            raise TelegramError(
                f"{metodo}: risposta non JSON (HTTP {risposta.status_code})"
            ) from None
        if contenuto.get("ok"):
            return contenuto["result"]
        descrizione = f"{metodo}: {contenuto.get('description', 'errore senza descrizione')}"
        codice = contenuto.get("error_code", risposta.status_code)
        if codice == 429:
            attesa = (contenuto.get("parameters") or {}).get("retry_after", 1)
            raise TelegramTroppeRichieste(descrizione, int(attesa))
        if 400 <= codice < 500:
            raise TelegramRifiuto(descrizione)
        raise TelegramError(descrizione)

    def io(self) -> str:
        """Il nome utente del bot, senza la @."""
        return self._chiama("getMe")["username"]

    def aggiornamenti(self, offset: int | None, attesa: int) -> list[dict]:
        corpo: dict[str, Any] = {"timeout": attesa, "allowed_updates": ["message", "poll_answer"]}
        if offset is not None:
            corpo["offset"] = offset
        return self._chiama("getUpdates", corpo, timeout=attesa + 10.0)

    def manda_sondaggio(self, chat_id: int, domanda: str, opzioni: Sequence[str]) -> SondaggioMandato:
        """Non anonimo, a risposta multipla, con il voto che si può cambiare:
        Telegram manda al bot ogni voto, con chi l'ha dato."""
        messaggio = self._chiama(
            "sendPoll",
            {
                "chat_id": chat_id,
                "question": domanda,
                "options": [{"text": o} for o in opzioni],
                "is_anonymous": False,
                "allows_multiple_answers": True,
                "allows_revoting": True,
            },
        )
        return SondaggioMandato(poll_id=messaggio["poll"]["id"], messaggio=messaggio["message_id"])

    def scrivi(
        self,
        chat_id: int,
        testo: str,
        entita: Sequence[dict] = (),
        risposta_a: int | None = None,
    ) -> dict:
        """Il messaggio come l'ha registrato Telegram, entità comprese."""
        corpo: dict[str, Any] = {"chat_id": chat_id, "text": testo}
        if entita:
            corpo["entities"] = list(entita)
        if risposta_a is not None:
            # Se il messaggio a cui si risponde non c'è più, il messaggio parte lo stesso.
            corpo["reply_parameters"] = {
                "message_id": risposta_a,
                "allow_sending_without_reply": True,
            }
        return self._chiama("sendMessage", corpo)

    def ferma_sondaggio(self, chat_id: int, messaggio: int) -> list[int]:
        """Ferma il sondaggio e restituisce i conteggi per opzione, nell'ordine
        delle opzioni."""
        try:
            sondaggio = self._chiama("stopPoll", {"chat_id": chat_id, "message_id": messaggio})
        except TelegramRifiuto as e:
            if _SPARITO.search(str(e)):
                raise MessaggioSparito(str(e)) from None
            raise
        return [opzione["voter_count"] for opzione in sondaggio["options"]]

    def registra_comandi(self, comandi: Sequence[tuple[str, str]]) -> None:
        self._chiama(
            "setMyCommands",
            {"commands": [{"command": c, "description": d} for c, d in comandi]},
        )
