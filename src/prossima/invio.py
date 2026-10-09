"""L'invio verso Telegram: ogni chiamata che scrive su Telegram passa di qui.

Che cosa parte, e come:
- dopo un 429 niente parte prima di `retry_after`, contato da quando è
  arrivata la risposta: nel frattempo una chiamata non parte nemmeno, e
  solleva `TelegramInPausa`;
- la posta in uscita del database parte in ordine: se non parte resta lì, e
  riparte al giro seguente. Un rifiuto di Telegram (4xx) la scarta, con un
  errore nel log: ripeterla darebbe lo stesso rifiuto;
- un sondaggio nuovo parte dopo la posta in attesa, che viene prima nella
  chat; la frase di «Nessuna» conta come usata solo se il sondaggio parte;
- lo stop di un sondaggio dice se Telegram l'ha fermato (`Fermato`), anche
  quando il messaggio non c'è più o il sondaggio era già chiuso; non lo chiude
  nel database.

Per chi chiama: come leggere un errore di Telegram (`forse_arrivata`,
`livello`), e la regola degli errori che si ripetono a ogni giro, nel log la
prima volta e poi al massimo ogni 10 minuti (`Avvisi`).

Dipende dal client di Telegram, dallo store (la posta, le frasi usate) e dai
testi; da nessun'altra parte del bot.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import testi
from .store import LetteraNuova, Sondaggio, Store
from .telegram import (
    MessaggioSparito,
    SondaggioGiaChiuso,
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

log = logging.getLogger(__name__)

# Un errore che si ripete a ogni giro va nel log la prima volta, e poi al
# massimo una volta in questo tempo.
AVVISO_RIPETUTO = timedelta(minutes=10)


class TelegramInPausa(TelegramError):
    """Dopo un 429: la richiesta non è partita, Telegram ha chiesto di aspettare."""


def forse_arrivata(e: TelegramError) -> bool:
    """Dopo questo errore la richiesta può essere arrivata a Telegram (la rete,
    un 5xx, una risposta illeggibile): non dopo la pausa (non è partita), non
    dopo un 4xx (Telegram l'ha rifiutata)."""
    return not isinstance(e, TelegramInPausa | TelegramRifiuto | TelegramTroppeRichieste)


def livello(e: TelegramError) -> int:
    """Un rifiuto (4xx) è un errore: ripetere la stessa richiesta non serve."""
    return logging.ERROR if isinstance(e, TelegramRifiuto) else logging.WARNING


@dataclass(frozen=True)
class Fermato:
    """Il sondaggio è fermo su Telegram. `conteggi` sono quelli di Telegram per
    opzione, o None se Telegram non li dà: il messaggio non c'è più
    (`sparito`), o il sondaggio era già chiuso (uno stop passato senza che la
    risposta arrivasse)."""

    conteggi: list[int] | None
    sparito: bool = False


class Avvisi:
    """Per un errore che si ripete a ogni giro: nel log la prima volta, e poi
    al massimo ogni `AVVISO_RIPETUTO` per la stessa chiave. Ogni parte del bot
    ha i suoi, in memoria: un riavvio ricomincia da capo."""

    def __init__(self, adesso: Callable[[], datetime]) -> None:
        self._adesso = adesso
        self._ultimi: dict[object, datetime] = {}

    def da_avvisare(self, chiave: object) -> bool:
        """Vero la prima volta, e poi al massimo ogni `AVVISO_RIPETUTO`."""
        adesso = self._adesso()
        ultimo = self._ultimi.get(chiave)
        if ultimo is not None and adesso - ultimo < AVVISO_RIPETUTO:
            return False
        self._ultimi[chiave] = adesso
        return True

    def avvisato(self, chiave: object) -> None:
        """Chi chiama ha appena scritto l'avviso: il prossimo fra
        `AVVISO_RIPETUTO`, non subito."""
        self._ultimi[chiave] = self._adesso()


class Invio:
    def __init__(
        self,
        *,
        telegram,
        store: Store,
        gruppo: int,
        adesso: Callable[[], datetime],
        caso: Callable[[Sequence[str]], str],
        frasi: Sequence[str],
        domanda: str,
    ) -> None:
        self._tg = telegram
        self._store = store
        self._gruppo = gruppo
        self._adesso = adesso
        self._caso = caso
        self._frasi = tuple(frasi)
        self._domanda = domanda
        self._pausa_fino_a: datetime | None = None
        self._avvisi = Avvisi(adesso)

    def in_pausa(self) -> bool:
        return self._pausa_fino_a is not None and self._adesso() < self._pausa_fino_a

    def avvisa(self, messaggio: str, e: TelegramError) -> None:
        """Un invio che non parte: nel log la prima volta, e poi al massimo ogni
        `AVVISO_RIPETUTO`. Un 429 sempre: è uno per pausa, e la pausa conta."""
        if isinstance(e, TelegramTroppeRichieste) or self._avvisi.da_avvisare("invio"):
            log.warning(messaggio, e)

    # --- la posta in uscita

    def lettera(self, testo: testi.Testo, risposta_a: int | None = None) -> LetteraNuova:
        """Un messaggio per il gruppo, da accodare insieme al cambio di stato
        che lo giustifica."""
        return LetteraNuova(self._gruppo, testo.testo, testo.entita, risposta_a)

    def lettere(self, testi_: Sequence[testi.Testo]) -> list[LetteraNuova]:
        return [self.lettera(t) for t in testi_]

    def accoda(self, testo: testi.Testo, risposta_a: int | None = None) -> None:
        self._store.accoda(self._gruppo, testo.testo, testo.entita, risposta_a, self._adesso())

    def manda_posta(self) -> None:
        for lettera in self._store.posta():
            try:
                self._invia(
                    self._tg.scrivi, lettera.chat_id, lettera.testo, lettera.entita, lettera.risposta_a
                )
            except TelegramRifiuto as e:
                log.error("messaggio scartato, Telegram lo rifiuta: %s (%r)", e, lettera.testo)
            self._store.togli_lettera(lettera.id)

    # --- le chiamate che non passano dalla posta

    def scrivi(self, testo: testi.Testo) -> int:
        """Un messaggio nel gruppo, subito e senza la posta: un errore esce di
        qui, e chi chiama sa se è partito (un annuncio conta come fatto solo
        dopo che Telegram l'ha accettato). Restituisce il suo identificativo."""
        mandato = self._invia(
            self._tg.scrivi, self._gruppo, testo.testo, testo.entita, None, testo.bottoni
        )
        return mandato["message_id"]

    def rispondi_al_tocco(self, tocco_id: str, avviso: str | None = None) -> None:
        """Al meglio: un tocco vecchio (dopo un buio) Telegram non lo accetta più,
        e l'azione del tocco non dipende dalla risposta."""
        try:
            self._invia(self._tg.rispondi_al_tocco, tocco_id, avviso)
        except TelegramError as e:
            log.warning("risposta al tocco non mandata: %s", e)

    def togli_bottoni(self, messaggio: int) -> None:
        """Al meglio: un bottone rimasto, toccato, dice che il sondaggio è già chiuso."""
        try:
            self._invia(self._tg.togli_bottoni, self._gruppo, messaggio)
        except TelegramError as e:
            log.warning("bottoni non tolti dal messaggio %s: %s", messaggio, e)

    def ferma(self, sondaggio: Sondaggio) -> Fermato:
        """Ferma il sondaggio su Telegram. Non lo chiude nel database: lo fa chi
        chiama, nella stessa transazione della lettera che lo dice. Un errore
        di Telegram che non dice che il sondaggio è fermo esce di qui."""
        try:
            return Fermato(self._invia(self._tg.ferma_sondaggio, self._gruppo, sondaggio.messaggio))
        except MessaggioSparito:
            return Fermato(None, sparito=True)
        except SondaggioGiaChiuso as e:
            # Telegram conferma che è fermo: uno stop di prima è passato
            log.warning("il sondaggio %s era già chiuso su Telegram: %s", sondaggio.id, e)
            return Fermato(None)

    def nuovo_sondaggio(self, date_: Sequence[date]) -> tuple[SondaggioMandato, str]:
        """Manda un sondaggio sulle `date_`, in ordine: lo store le salva in
        ordine, e i voti si leggono per indice. Prima la posta in attesa, che
        viene prima nella chat; la frase conta come usata (e il giro nuovo
        comincia) solo se il sondaggio parte."""
        if not self.in_pausa():
            try:
                self.manda_posta()
            except TelegramError as e:
                self.avvisa("posta rimandata: %s", e)
        frase, nuovo_giro = self._frase()
        mandato = self._invia(
            self._tg.manda_sondaggio, self._gruppo, self._domanda, testi.opzioni(sorted(date_), frase)
        )
        self._store.usa_frase(frase, nuovo_giro)
        return mandato, frase

    def _frase(self) -> tuple[str, bool]:
        """La frase di «Nessuna» per il prossimo sondaggio, e se comincia un giro
        nuovo: finite tutte si ricomincia, ma non con l'ultima usata."""
        usate = self._store.frasi_usate()
        if usate >= set(self._frasi):
            return testi.scegli_frase(self._frasi, {self._store.ultima_frase()}, self._caso), True
        return testi.scegli_frase(self._frasi, usate, self._caso), False

    def _invia(self, chiamata, *argomenti):
        """Ogni chiamata che scrive su Telegram passa di qui: dopo un 429, niente
        parte prima di `retry_after`, contato da quando è arrivata la risposta."""
        if self.in_pausa():
            raise TelegramInPausa(
                f"Telegram ha chiesto di aspettare fino alle {self._pausa_fino_a.isoformat(timespec='seconds')}"
            )
        try:
            return chiamata(*argomenti)
        except TelegramTroppeRichieste as e:
            self._pausa_fino_a = self._adesso() + timedelta(seconds=e.retry_after)
            raise
