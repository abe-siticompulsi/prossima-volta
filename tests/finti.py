"""I finti dei sistemi esterni.

Ognuno mette per iscritto una convinzione sul vero: dove quella convinzione
viene messa alla prova lo dice docs/differenze-fra-test-e-realta.md. Prima di
aggiungere un comportamento qui, la domanda è: quale convinzione sto scrivendo,
e dove la verifica il piano reale?
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prossima.telegram import MessaggioSparito, SondaggioMandato, TelegramError


class TelegramFinto:
    """Risponde subito e con successo, salvo i guasti: `guasto` vale per ogni
    chiamata, `guasti[metodo]` per un metodo solo. Una chiamata fallita non
    lascia traccia in `chiamate`: lì c'è solo quello che Telegram ha accettato."""

    def __init__(self, nome: str = "ProssimaVoltaBot") -> None:
        self.nome = nome
        self.chiamate: list[tuple[str, dict]] = []
        self.guasto: Exception | None = None
        self.guasti: dict[str, Exception] = {}
        self.aggiornamenti_da_dare: list[dict] = []
        self.sondaggi: list[dict] = []  # i sondaggi mandati, il più recente in fondo
        self.conteggi: dict[int, list[int]] = {}  # per messaggio: quello che darà stopPoll
        self.cancellati: set[int] = set()  # messaggi cancellati da qualcuno nel gruppo
        self._ultimo_id = 500

    def _registra(self, nome: str, **argomenti) -> int:
        guasto = self.guasti.get(nome) or self.guasto
        if guasto is not None:
            raise guasto
        self.chiamate.append((nome, argomenti))
        self._ultimo_id += 1
        return self._ultimo_id

    def io(self) -> str:
        self._registra("io")
        return self.nome

    def aggiornamenti(self, offset, attesa):
        self._registra("aggiornamenti", offset=offset, attesa=attesa)
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
        return mandato

    def scrivi(self, chat_id, testo, entita=(), risposta_a=None):
        messaggio = self._registra(
            "scrivi", chat_id=chat_id, testo=testo, entita=list(entita), risposta_a=risposta_a
        )
        return {"message_id": messaggio, "chat": {"id": chat_id}, "text": testo}

    def ferma_sondaggio(self, chat_id, messaggio):
        if messaggio in self.cancellati:
            raise MessaggioSparito("stopPoll: Bad Request: message to stop not found")
        self._registra("ferma_sondaggio", chat_id=chat_id, messaggio=messaggio)
        sondaggio = next(s for s in self.sondaggi if s["messaggio"] == messaggio)
        return list(self.conteggi.get(messaggio, [0] * len(sondaggio["opzioni"])))

    def registra_comandi(self, comandi):
        self._registra("registra_comandi", comandi=list(comandi))

    # --- per le prove

    def di_tipo(self, nome: str) -> list[dict]:
        return [argomenti for n, argomenti in self.chiamate if n == nome]

    def scritti(self) -> list[str]:
        return [a["testo"] for a in self.di_tipo("scrivi")]

    @property
    def ultimo_sondaggio(self) -> dict:
        return self.sondaggi[-1]


def telegram_guasto() -> TelegramError:
    return TelegramError("sendMessage: errore di rete (ConnectError)")


class Orologio:
    def __init__(self, inizio: datetime) -> None:
        self.adesso = inizio

    def __call__(self) -> datetime:
        return self.adesso

    def avanza(self, **quanto) -> None:
        self.adesso += timedelta(**quanto)
