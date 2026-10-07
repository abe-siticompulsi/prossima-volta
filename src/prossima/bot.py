"""Il bot: smista gli aggiornamenti di Telegram, manda gli annunci, fa la ripresa.

Un solo processo e un solo filo: nessuna gara fra un voto e un comando.

Che cosa parte verso Telegram, e quando:
- un sondaggio (`sendPoll`) parte subito: se Telegram non lo conferma, nel
  database non c'è, il bot risponde che Telegram non l'ha confermato, e il
  comando si riscrive;
- la chiusura (`stopPoll`) parte subito: se Telegram non la conferma resta in
  sospeso, il bot lo dice, e la ritenta a ogni giro (`manda`) finché Telegram
  risponde; poi chiude come chiedeva il comando. Uno stop passato senza che la
  risposta arrivasse non blocca il nuovo tentativo: Telegram risponde che il
  sondaggio è già chiuso;
- gli annunci (quasi, possibile, non più possibile, impossibile) si calcolano
  dallo stato a ogni giro (`manda`), e contano come fatti solo dopo che
  Telegram li ha accettati. Uno rifiutato (4xx) va nel log come errore, non
  ferma gli altri, e non si riprova fino al prossimo avvio;
- ogni altro messaggio passa dalla posta in uscita del database, in ordine: se
  non parte resta lì, e riparte al giro seguente. Un rifiuto di Telegram (4xx)
  lo scarta, con un errore nel log: ripeterlo darebbe lo stesso rifiuto.
Dopo un 429 niente parte prima di `retry_after`, contato dalla risposta; nel
frattempo `manda` non prova nemmeno.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from . import regole, testi
from .regole import Roster
from .store import ChiusuraSospesa, LetteraNuova, Sondaggio, Store
from .telegram import (
    MessaggioSparito,
    SondaggioGiaChiuso,
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

log = logging.getLogger(__name__)

COMANDI = (("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio"))
# Un voto per un sondaggio sconosciuto si dice nel gruppo solo se un sondaggio
# non confermato da Telegram è di questi ultimi giorni.
NON_CONFERMATO_DI_RECENTE = timedelta(days=7)


class TelegramInPausa(TelegramError):
    """Dopo un 429: la richiesta non è partita, Telegram ha chiesto di aspettare."""


def _forse_arrivata(e: TelegramError) -> bool:
    """Dopo questo errore la richiesta può essere arrivata a Telegram (la rete,
    un 5xx, una risposta illeggibile): non dopo la pausa (non è partita), non
    dopo un 4xx (Telegram l'ha rifiutata)."""
    return not isinstance(e, TelegramInPausa | TelegramRifiuto | TelegramTroppeRichieste)


def _livello(e: TelegramError) -> int:
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


class Bot:
    def __init__(
        self,
        *,
        telegram,
        store: Store,
        roster: Roster,
        gruppo: int,
        nome: str,
        fuso: tzinfo,
        adesso: Callable[[], datetime],
        caso: Callable[[Sequence[str]], str] = random.choice,
    ) -> None:
        self._tg = telegram
        self._store = store
        self._roster = roster
        self._gruppo = gruppo
        self._nome = nome
        self._fuso = fuso
        self._adesso = adesso
        self._caso = caso
        self._pausa_fino_a: datetime | None = None
        # Quello che Telegram ha rifiutato (4xx) in questo processo, già scritto
        # nel log: gli stop (che si ritentano) e gli annunci (che si saltano,
        # fino al prossimo avvio).
        self._stop_rifiutati: set[int] = set()
        self._annunci_rifiutati: set[tuple[int, regole.Annuncio]] = set()

    # --- il giro

    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii. Dopo più di 23 ore senza letture, la ripresa (§3.8)."""
        ora = self._adesso()
        precedente = self._store.ultima_lettura()
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        self._store.segna_lettura(ora)
        if regole.al_buio(precedente, ora):
            try:
                self.riprendi(precedente, ora)
            except Exception:
                log.exception("ripresa dopo il buio non riuscita")
        self.manda()

    def gestisci(self, aggiornamento: dict) -> None:
        if "poll_answer" in aggiornamento:
            self._voto(aggiornamento["poll_answer"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def manda(self) -> None:
        """La posta in uscita, in ordine; lo stop di una chiusura in sospeso (e,
        se riesce, la posta che la dice); gli annunci del sondaggio aperto.
        Quello che non parte riparte al giro seguente. Durante la pausa chiesta
        da un 429 non si prova nemmeno: il 429 è già nel log."""
        if self._in_pausa():
            return
        try:
            self._manda_posta()
            if self._riprova_chiusura():
                self._manda_posta()
            self._manda_annunci()
        except TelegramError as e:
            log.warning("invio rimandato al giro seguente: %s", e)

    # --- i messaggi e i comandi

    def _messaggio(self, messaggio: dict) -> None:
        if messaggio.get("chat", {}).get("id") != self._gruppo:
            return  # fuori dal gruppo del party il bot non risponde a niente
        parole = (messaggio.get("text") or "").split()
        if not parole:
            return
        comando = self._comando(parole[0])
        if comando == "sondaggio":
            self._sondaggio(messaggio, parole[1:])
        elif comando == "chiudi":
            self._chiudi(messaggio, parole[1:])

    def _comando(self, parola: str) -> str | None:
        """«/sondaggio» o «/sondaggio@<nome del bot>» → «sondaggio»; un comando
        rivolto a un altro bot → None."""
        if not parola.startswith("/"):
            return None
        comando, _, destinatario = parola[1:].partition("@")
        if destinatario and destinatario.lower() != self._nome.lower():
            return None
        return comando.lower()

    def _sondaggio(self, messaggio: dict, parole: list[str]) -> None:
        aperto = self._store.sondaggio_aperto()
        if aperto is not None and self._in_chiusura(aperto):
            # «C'è già un sondaggio aperto» sarebbe falso: chi chiude l'ha chiuso
            self._accoda(testi.non_ancora_chiuso(), risposta_a=messaggio["message_id"])
            return
        if aperto is not None:
            self._accoda(testi.gia_aperto(self._nome), risposta_a=aperto.messaggio)
            return
        try:
            date_ = regole.date_del_comando(parole, self._oggi())
        except regole.Rifiuto as r:
            self._accoda(testi.rifiuto(r), risposta_a=messaggio["message_id"])
            return
        try:
            mandato, frase = self._nuovo_sondaggio(date_)
        except TelegramError as e:
            # rete, 5xx, un rifiuto, la pausa di un 429: la risposta al comando
            # è vera in ogni caso, anche se il sondaggio è partito e la risposta
            # si è persa; il tentativo si ricorda solo se può essere partito
            log.log(_livello(e), "sondaggio non confermato: %s", e)
            risposta = testi.sondaggio_non_confermato(self._nome, parole)
            comando = messaggio["message_id"]
            if _forse_arrivata(e):
                lettera = self._lettera(risposta, risposta_a=comando)
                self._store.segna_non_confermato(self._adesso(), [lettera])
            else:
                self._accoda(risposta, risposta_a=comando)
            return
        self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())

    def _voto(self, risposta: dict) -> None:
        poll_id = risposta.get("poll_id")
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is not None and poll_id == sondaggio.poll_id:
            utente = risposta.get("user")
            if utente is None:
                return
            voto = regole.voto_da_opzioni(sondaggio.date, risposta.get("option_ids", []))
            self._store.registra_voto(sondaggio.id, utente["id"], poll_id, voto, self._adesso())
        elif not self._store.poll_conosciuto(poll_id):
            self._voto_sconosciuto(poll_id)
        # un voto per un sondaggio che il bot conosce, ma non è aperto: si ignora

    def _voto_sconosciuto(self, poll_id: str) -> None:
        """Telegram manda al bot solo i voti dei sondaggi del bot: questo è un
        sondaggio che il bot ha mandato senza registrarlo (una risposta persa),
        o uno del piano reale, nella chat privata di Alberto. Nel gruppo lo si
        dice una volta per sondaggio, e solo se c'è stato da poco un sondaggio
        che Telegram non ha confermato: i voti del piano reale restano nel log.
        Con un sondaggio aperto l'avviso risponde a quello: è lì che si vota."""
        log.warning("voto per un sondaggio sconosciuto: %s", poll_id)
        tentativo = self._store.ultimo_non_confermato()
        adesso = self._adesso()
        if tentativo is None or adesso - tentativo > NON_CONFERMATO_DI_RECENTE:
            return
        aperto = self._store.sondaggio_aperto()
        if aperto is None or self._in_chiusura(aperto):
            avviso = self._lettera(testi.voto_sconosciuto(self._nome))
        else:
            avviso = self._lettera(
                testi.voto_sconosciuto(self._nome, con_sondaggio_aperto=True),
                risposta_a=aperto.messaggio,
            )
        self._store.avvisa_voto_sconosciuto(poll_id, adesso, [avviso])

    # --- /chiudi

    def _chiudi(self, messaggio: dict, parole: list[str]) -> None:
        comando = messaggio["message_id"]
        sospesa = self._store.chiusura_sospesa()
        if self._store.chiuso_dal_comando(comando) or (
            sospesa is not None and sospesa.comando == comando
        ):
            return  # lo stesso /chiudi letto una seconda volta dopo un riavvio
        chi = self._roster.per_id(messaggio.get("from", {}).get("id"))
        if chi is None or not chi.chiude:
            self._accoda(testi.solo_chi_chiude(self._roster.chi_chiude), risposta_a=comando)
            return
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            self._accoda(testi.nessun_sondaggio(), risposta_a=comando)
            return
        if len(parole) > 1:
            rifiuto = regole.NonCapisco(" ".join(parole))
            self._accoda(testi.rifiuto_di_chiudi(rifiuto), risposta_a=comando)
            return
        argomento = None
        if parole and parole[0].lower() == regole.RIMANDA:
            argomento = regole.RIMANDA
        elif parole:
            try:
                argomento = regole.data_da_chiudere(parole[0], sondaggio.date).isoformat()
            except regole.Rifiuto as r:
                self._accoda(testi.rifiuto_di_chiudi(r), risposta_a=comando)
                return
        chiusura = ChiusuraSospesa(sondaggio.id, comando, argomento)
        if self._in_chiusura(sondaggio):
            # lo stop lo ritenta già il bot: vale l'ultima decisione
            self._sospendi(chiusura)
            return
        try:
            fermato = self._ferma(sondaggio)
        except TelegramError as e:
            # rete, 5xx, un rifiuto, la pausa di un 429: forse lo stop è passato
            # e la risposta si è persa; il bot lo ritenta a ogni giro (`manda`)
            log.log(_livello(e), "chiusura del sondaggio %s non confermata: %s", sondaggio.id, e)
            if isinstance(e, TelegramRifiuto):
                self._stop_rifiutati.add(sondaggio.id)
            self._sospendi(chiusura)
            return
        self._completa(chiusura, sondaggio, fermato)

    def _sospendi(self, chiusura: ChiusuraSospesa) -> None:
        risposta = self._lettera(testi.chiusura_non_confermata(), risposta_a=chiusura.comando)
        self._store.sospendi_chiusura(chiusura, self._adesso(), [risposta])

    def _in_chiusura(self, sondaggio: Sondaggio) -> bool:
        """Chi può chiudere l'ha chiuso, ma Telegram non ha ancora confermato lo stop."""
        sospesa = self._store.chiusura_sospesa()
        return sospesa is not None and sospesa.sondaggio == sondaggio.id

    def _riprova_chiusura(self) -> bool:
        """Ritenta lo stop di una chiusura in sospeso; quando Telegram risponde
        (fermato, già chiuso, o il messaggio sparito) chiude come chiedeva il
        comando. Vero se ha chiuso. Un errore di rete esce di qui; un rifiuto
        (4xx) va nel log una volta per processo, e il giro seguente riprova."""
        sospesa = self._store.chiusura_sospesa()
        if sospesa is None:
            return False
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None or sondaggio.id != sospesa.sondaggio:
            self._store.togli_chiusura_sospesa()  # chiuso per un'altra via
            return False
        try:
            fermato = self._ferma(sondaggio)
        except TelegramRifiuto as e:
            if sondaggio.id not in self._stop_rifiutati:
                self._stop_rifiutati.add(sondaggio.id)
                log.error("chiusura del sondaggio %s rifiutata da Telegram: %s", sondaggio.id, e)
            return False
        self._completa(sospesa, sondaggio, fermato)
        return True

    def _completa(self, chiusura: ChiusuraSospesa, sondaggio: Sondaggio, fermato: Fermato) -> None:
        """Chiude il sondaggio, fermo su Telegram, come chiede il `/chiudi`:
        le date possibili, la data tenuta, o `rimanda`. Le date possibili si
        contano adesso, con i voti arrivati fino allo stop."""
        if chiusura.argomento == regole.RIMANDA:
            self._rimanda(sondaggio, chiusura.comando, fermato)
            return
        lettere = [testi.sparito()] if fermato.sparito else []
        if chiusura.argomento is not None:
            lettere.append(testi.si_gioca(date.fromisoformat(chiusura.argomento)))
        else:
            lettere.append(testi.chiuso(regole.possibili(self._stato(sondaggio))))
        self._store.chiudi_sondaggio(
            sondaggio.id, self._adesso(), chiusura.comando, self._lettere(lettere)
        )

    def _rimanda(self, vecchio: Sondaggio, comando: int, fermato: Fermato) -> None:
        """`/chiudi rimanda`, a sondaggio fermo su Telegram: un sondaggio nuovo
        sugli stessi giorni della settimana dopo, senza le date passate. Il
        vecchio si chiude nel database solo insieme al nuovo, in una
        transazione: fino a lì, il comando riletto riprende da capo (lo stop
        dirà che il vecchio è già chiuso)."""
        date_ = [g for g in regole.date_rimandate(vecchio.date) if g >= self._oggi()]
        sparito = [testi.sparito()] if fermato.sparito else []
        if not date_:
            lettere = self._lettere([*sparito, testi.date_passate()])
            self._store.chiudi_sondaggio(vecchio.id, self._adesso(), comando, lettere)
            return
        if sparito:
            # Prima del sondaggio nuovo, che parte dopo la posta: da sola, non con
            # la chiusura. Un'interruzione prima del salvataggio la fa ripetere.
            self._accoda(testi.sparito())
        try:
            mandato, frase = self._nuovo_sondaggio(date_)
        except TelegramError as e:
            log.log(_livello(e), "sondaggio nuovo di rimanda non confermato: %s", e)
            lettere = self._lettere([testi.rimando_non_confermato(self._nome, date_)])
            self._store.chiudi_sondaggio(
                vecchio.id, self._adesso(), comando, lettere, non_confermato=_forse_arrivata(e)
            )
            return
        self._store.rimanda(
            vecchio.id,
            comando,
            date_,
            mandato.poll_id,
            mandato.messaggio,
            frase,
            self._adesso(),
            self._lettere([testi.rimandiamo(regole.lunedi(date_[0]))]),
        )

    def _ferma(self, sondaggio: Sondaggio) -> Fermato:
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

    # --- la ripresa dopo il buio (§3.8)

    def riprendi(self, dal: datetime, al: datetime) -> None:
        self._accoda(testi.buio(dal, al, self._fuso))
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            return
        fermato = self._ferma(sondaggio)
        lettere = self._lettere([testi.sparito()] if fermato.sparito else [])
        self._store.chiudi_sondaggio(sondaggio.id, self._adesso(), lettere=lettere)
        if fermato.sparito:
            return  # il messaggio non c'è più: chiuso, e detto
        # già chiuso su Telegram: i conteggi non ci sono, niente frase, si riapre
        if fermato.conteggi is not None:
            nostri = regole.conteggi_per_opzione(
                sondaggio.date, self._store.voti_del_poll(sondaggio.id, sondaggio.poll_id)
            )
            self._accoda(testi.conteggi(fermato.conteggi == nostri))
        future = [g for g in sondaggio.date if g >= self._oggi()]
        if not future:
            self._accoda(testi.date_passate())
            return
        mandato, frase = self._nuovo_sondaggio(future)
        riaperto = self._store.riapri_sondaggio(
            sondaggio.id, future, mandato.poll_id, mandato.messaggio, frase
        )
        fatti = regole.dopo(self._store.fatti(riaperto.id), regole.Ripresa())
        self._store.salva_fatti(riaperto.id, fatti)
        stato = self._stato(riaperto)
        self._accoda(testi.riapro(stato.votanti, stato.senza_voto))

    # --- i pezzi

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()

    def _stato(self, sondaggio: Sondaggio) -> regole.Stato:
        return regole.Stato(self._roster, sondaggio.date, self._store.voti(sondaggio.id))

    def _frase(self) -> tuple[str, bool]:
        """La frase di «Nessuna» per il prossimo sondaggio, e se comincia un giro
        nuovo: finite tutte si ricomincia, ma non con l'ultima usata."""
        usate = self._store.frasi_usate()
        if usate >= set(testi.FRASI_NESSUNA):
            return testi.scegli_frase({self._store.ultima_frase()}, self._caso), True
        return testi.scegli_frase(usate, self._caso), False

    def _nuovo_sondaggio(self, date_: Sequence[date]) -> tuple[SondaggioMandato, str]:
        """Manda un sondaggio sulle `date_`, in ordine: lo store le salva in
        ordine, e i voti si leggono per indice. Prima la posta in attesa, che
        viene prima nella chat; la frase conta come usata (e il giro nuovo
        comincia) solo se il sondaggio parte."""
        if not self._in_pausa():
            try:
                self._manda_posta()
            except TelegramError as e:
                log.warning("posta rimandata: %s", e)
        frase, nuovo_giro = self._frase()
        mandato = self._invia(
            self._tg.manda_sondaggio, self._gruppo, testi.DOMANDA, testi.opzioni(sorted(date_), frase)
        )
        self._store.usa_frase(frase, nuovo_giro)
        return mandato, frase

    def _lettera(self, testo: testi.Testo, risposta_a: int | None = None) -> LetteraNuova:
        return LetteraNuova(self._gruppo, testo.testo, testo.entita, risposta_a)

    def _lettere(self, testi_: Sequence[testi.Testo]) -> list[LetteraNuova]:
        return [self._lettera(t) for t in testi_]

    def _accoda(self, testo: testi.Testo, risposta_a: int | None = None) -> None:
        self._store.accoda(self._gruppo, testo.testo, testo.entita, risposta_a, self._adesso())

    def _in_pausa(self) -> bool:
        return self._pausa_fino_a is not None and self._adesso() < self._pausa_fino_a

    def _invia(self, chiamata, *argomenti):
        """Ogni chiamata che scrive su Telegram passa di qui: dopo un 429, niente
        parte prima di `retry_after`, contato da quando è arrivata la risposta."""
        if self._in_pausa():
            raise TelegramInPausa(
                f"Telegram ha chiesto di aspettare fino alle {self._pausa_fino_a.isoformat(timespec='seconds')}"
            )
        try:
            return chiamata(*argomenti)
        except TelegramTroppeRichieste as e:
            self._pausa_fino_a = self._adesso() + timedelta(seconds=e.retry_after)
            raise

    def _manda_posta(self) -> None:
        for lettera in self._store.posta():
            try:
                self._invia(
                    self._tg.scrivi, lettera.chat_id, lettera.testo, lettera.entita, lettera.risposta_a
                )
            except TelegramRifiuto as e:
                log.error("messaggio scartato, Telegram lo rifiuta: %s (%r)", e, lettera.testo)
            self._store.togli_lettera(lettera.id)

    def _manda_annunci(self) -> None:
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            return
        stato = self._stato(sondaggio)
        fatti = self._store.fatti(sondaggio.id)
        if regole.rientrato(stato, fatti):
            fatti = regole.dopo(fatti, regole.Rientro())
            self._store.salva_fatti(sondaggio.id, fatti)
        for annuncio in regole.annunci_da_fare(stato, fatti):
            if (sondaggio.id, annuncio) in self._annunci_rifiutati:
                continue
            testo = testi.annuncio(annuncio, self._roster, self._nome)
            try:
                self._invia(self._tg.scrivi, self._gruppo, testo.testo, testo.entita)
            except TelegramRifiuto as e:
                # non è fatto, e lo stesso testo avrebbe lo stesso rifiuto: si
                # salta fino al prossimo avvio; gli altri partono
                log.error("annuncio rifiutato da Telegram: %s (%r)", e, testo.testo)
                self._annunci_rifiutati.add((sondaggio.id, annuncio))
                continue
            fatti = regole.dopo(fatti, annuncio)
            self._store.salva_fatti(sondaggio.id, fatti)
