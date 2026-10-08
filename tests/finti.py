"""I finti dei sistemi esterni.

Ognuno mette per iscritto una convinzione sul vero: dove quella convinzione
viene messa alla prova lo dice docs/differenze-fra-test-e-realta.md. Prima di
aggiungere un comportamento qui, la domanda è: quale convinzione sto scrivendo,
e dove la verifica il piano reale?
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prossima.telegram import (
    MessaggioSparito,
    SondaggioGiaChiuso,
    SondaggioMandato,
    TelegramError,
)

# I metodi del client e i metodi dell'API di Telegram che chiamano: gli errori
# del client vero cominciano con il nome del metodo dell'API.
API = {
    "io": "getMe",
    "aggiornamenti": "getUpdates",
    "manda_sondaggio": "sendPoll",
    "scrivi": "sendMessage",
    "ferma_sondaggio": "stopPoll",
    "registra_comandi": "setMyCommands",
}


class TelegramFinto:
    """Risponde subito e con successo, salvo i guasti: `guasto` vale per ogni
    chiamata, `guasti[metodo]` per un metodo solo. Una chiamata fallita non
    lascia traccia in `chiamate`: lì c'è solo quello che Telegram ha accettato.

    Una risposta persa (`risposte_perse`, per metodo) è l'eccezione: Telegram
    ha eseguito la chiamata, che resta in `chiamate` con il suo effetto, ma la
    risposta non arriva e il client solleva un errore di rete."""

    def __init__(self, nome: str = "ProssimaVoltaBot") -> None:
        self.nome = nome
        self.chiamate: list[tuple[str, dict]] = []
        self.guasto: Exception | None = None
        self.guasti: dict[str, Exception] = {}
        self.risposte_perse: set[str] = set()
        self.aggiornamenti_da_dare: list[dict] = []
        self.sondaggi: list[dict] = []  # i sondaggi mandati, il più recente in fondo
        # Per messaggio, i conteggi che darà stopPoll; senza, zero per opzione. Il
        # finto non vede i voti: una prova con dei voti che arriva a uno stop dice
        # quanti ne conta Telegram, o il bot li troverà diversi dai suoi.
        self.conteggi: dict[int, list[int]] = {}
        self.cancellati: set[int] = set()  # messaggi cancellati da qualcuno nel gruppo
        self.fermati: set[int] = set()  # i messaggi dei sondaggi fermati
        self._ultimo_id = 500

    def _guasto(self, nome: str) -> None:
        guasto = self.guasti.get(nome) or self.guasto
        if guasto is not None:
            raise guasto

    def _registra(self, nome: str, **argomenti) -> int:
        self._guasto(nome)
        self.chiamate.append((nome, argomenti))
        self._ultimo_id += 1
        return self._ultimo_id

    def _risposta(self, nome: str, risultato):
        """Quello che il client restituisce, se la risposta arriva."""
        if nome in self.risposte_perse:
            raise telegram_guasto(nome, "ReadTimeout")
        return risultato

    def io(self) -> str:
        self._registra("io")
        return self._risposta("io", self.nome)

    def aggiornamenti(self, offset, attesa):
        self._registra("aggiornamenti", offset=offset, attesa=attesa)
        if "aggiornamenti" in self.risposte_perse:
            # il vero li riconsegna: nessun offset li ha confermati
            raise telegram_guasto("aggiornamenti", "ReadTimeout")
        dati, self.aggiornamenti_da_dare = self.aggiornamenti_da_dare, []
        return dati

    def manda_sondaggio(self, chat_id, domanda, opzioni):
        messaggio = self._registra(
            "manda_sondaggio", chat_id=chat_id, domanda=domanda, opzioni=list(opzioni)
        )
        mandato = SondaggioMandato(poll_id=f"poll-{messaggio}", messaggio=messaggio)
        self.sondaggi.append(
            {"poll_id": mandato.poll_id, "messaggio": messaggio, "opzioni": list(opzioni)}
        )
        return self._risposta("manda_sondaggio", mandato)

    def scrivi(self, chat_id, testo, entita=(), risposta_a=None):
        messaggio = self._registra(
            "scrivi", chat_id=chat_id, testo=testo, entita=list(entita), risposta_a=risposta_a
        )
        return self._risposta(
            "scrivi", {"message_id": messaggio, "chat": {"id": chat_id}, "text": testo}
        )

    def ferma_sondaggio(self, chat_id, messaggio):
        self._guasto("ferma_sondaggio")  # con la rete giù Telegram non risponde niente
        if messaggio in self.cancellati:
            raise MessaggioSparito("stopPoll: Bad Request: message to stop not found")
        if messaggio in self.fermati:
            raise SondaggioGiaChiuso("stopPoll: Bad Request: poll has already been closed")
        self._registra("ferma_sondaggio", chat_id=chat_id, messaggio=messaggio)
        sondaggio = next(s for s in self.sondaggi if s["messaggio"] == messaggio)
        self.fermati.add(messaggio)
        conteggi = list(self.conteggi.get(messaggio, [0] * len(sondaggio["opzioni"])))
        return self._risposta("ferma_sondaggio", conteggi)

    def registra_comandi(self, comandi):
        self._registra("registra_comandi", comandi=list(comandi))
        return self._risposta("registra_comandi", None)

    # --- per le prove

    def di_tipo(self, nome: str) -> list[dict]:
        return [argomenti for n, argomenti in self.chiamate if n == nome]

    def scritti(self) -> list[str]:
        return [a["testo"] for a in self.di_tipo("scrivi")]

    @property
    def ultimo_sondaggio(self) -> dict:
        return self.sondaggi[-1]


def telegram_guasto(metodo: str, causa: str = "ConnectError") -> TelegramError:
    """L'errore di rete del client vero per `metodo` (un metodo del client)."""
    return TelegramError(f"{API[metodo]}: errore di rete ({causa})")


class Orologio:
    def __init__(self, inizio: datetime) -> None:
        self.adesso = inizio

    def __call__(self) -> datetime:
        return self.adesso

    def avanza(self, **quanto) -> None:
        self.adesso += timedelta(**quanto)
