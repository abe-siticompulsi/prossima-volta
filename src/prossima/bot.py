"""Il bot: smista gli aggiornamenti di Telegram e manda gli annunci.

Un solo processo e un solo filo: nessuna gara fra un voto e un comando.

Che cosa parte verso Telegram, e quando:
- un sondaggio (`sendPoll`) e la sua chiusura (`stopPoll`) partono subito: se
  falliscono, il comando non ha effetto (resta nel log) e lo si riscrive;
- gli annunci (quasi, possibile, non più possibile, impossibile) si calcolano
  dallo stato a ogni giro (`manda`), e contano come fatti solo dopo che
  Telegram li ha accettati;
- ogni altro messaggio passa dalla posta in uscita del database, in ordine: se
  non parte resta lì, e riparte al giro seguente. Un rifiuto di Telegram (4xx)
  lo scarta, con un errore nel log: ripeterlo darebbe lo stesso rifiuto.
Dopo un 429 niente parte prima di `retry_after`.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, tzinfo

from . import regole, testi
from .regole import Roster
from .store import Sondaggio, Store
from .telegram import (
    MessaggioSparito,
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

log = logging.getLogger(__name__)

COMANDI = (("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio"))


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

    # --- il giro

    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii."""
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        self.manda()

    def gestisci(self, aggiornamento: dict) -> None:
        if "poll_answer" in aggiornamento:
            self._voto(aggiornamento["poll_answer"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def manda(self) -> None:
        """La posta in uscita, in ordine, poi gli annunci del sondaggio aperto.
        Quello che non parte riparte al giro seguente."""
        try:
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
        if aperto is not None:
            self._accoda(testi.gia_aperto(self._nome), risposta_a=aperto.messaggio)
            return
        try:
            date_ = regole.date_del_comando(parole, self._oggi())
        except regole.Rifiuto as r:
            self._accoda(testi.rifiuto(r), risposta_a=messaggio["message_id"])
            return
        mandato, frase = self._nuovo_sondaggio(date_)
        self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())

    def _voto(self, risposta: dict) -> None:
        sondaggio = self._store.sondaggio_aperto()
        utente = risposta.get("user")
        if sondaggio is None or utente is None or risposta.get("poll_id") != sondaggio.poll_id:
            return
        voto = regole.voto_da_opzioni(sondaggio.date, risposta.get("option_ids", []))
        self._store.registra_voto(sondaggio.id, utente["id"], sondaggio.poll_id, voto, self._adesso())

    # --- /chiudi

    def _chiudi(self, messaggio: dict, parole: list[str]) -> None:
        comando = messaggio["message_id"]
        if self._store.chiuso_dal_comando(comando):
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
            self._accoda(testi.rifiuto(regole.NonCapisco(" ".join(parole))), risposta_a=comando)
            return
        argomento = parole[0] if parole else None
        rimanda = argomento is not None and argomento.lower() == regole.RIMANDA
        tenuta = None
        if argomento is not None and not rimanda:
            try:
                tenuta = regole.data_da_chiudere(argomento, sondaggio.date)
            except regole.Rifiuto as r:
                self._accoda(testi.rifiuto(r), risposta_a=comando)
                return
        stato = self._stato(sondaggio)
        self._ferma(sondaggio, comando)
        if rimanda:
            date_ = regole.date_rimandate(sondaggio.date)
            mandato, frase = self._nuovo_sondaggio(date_)
            self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())
            self._accoda(testi.rimandiamo(regole.lunedi_seguente(max(sondaggio.date))))
        elif tenuta is not None:
            self._accoda(testi.si_gioca(tenuta))
        else:
            self._accoda(testi.chiuso(regole.possibili(stato)))

    def _ferma(self, sondaggio: Sondaggio, comando: int | None = None) -> list[int] | None:
        """Ferma il sondaggio su Telegram e lo chiude nel database; restituisce i
        conteggi di Telegram. Se il messaggio non c'è più, lo chiude lo stesso, lo
        dice, e restituisce None."""
        try:
            conteggi = self._invia(self._tg.ferma_sondaggio, self._gruppo, sondaggio.messaggio)
        except MessaggioSparito:
            conteggi = None
        self._store.chiudi_sondaggio(sondaggio.id, self._adesso(), comando)
        if conteggi is None:
            self._accoda(testi.sparito())
        return conteggi

    # --- i pezzi

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()

    def _stato(self, sondaggio: Sondaggio) -> regole.Stato:
        return regole.Stato(self._roster, sondaggio.date, self._store.voti(sondaggio.id))

    def _frase(self) -> str:
        usate = self._store.frasi_usate()
        if usate >= set(testi.FRASI_NESSUNA):
            self._store.dimentica_frasi()  # finite tutte: si ricomincia
            usate = set()
        return testi.scegli_frase(usate, self._caso)

    def _nuovo_sondaggio(self, date_: Sequence[date]) -> tuple[SondaggioMandato, str]:
        """Manda un sondaggio sulle `date_`. Prima la posta in attesa, che viene
        prima nella chat; la frase conta come usata solo se il sondaggio parte."""
        try:
            self._manda_posta()
        except TelegramError as e:
            log.warning("posta rimandata: %s", e)
        frase = self._frase()
        mandato = self._invia(
            self._tg.manda_sondaggio, self._gruppo, testi.DOMANDA, testi.opzioni(date_, frase)
        )
        self._store.usa_frase(frase)
        return mandato, frase

    def _accoda(self, testo: testi.Testo, risposta_a: int | None = None) -> None:
        self._store.accoda(self._gruppo, testo.testo, testo.entita, risposta_a, self._adesso())

    def _invia(self, chiamata, *argomenti):
        """Ogni chiamata che scrive su Telegram passa di qui: dopo un 429, niente
        parte prima di `retry_after`."""
        ora = self._adesso()
        if self._pausa_fino_a is not None and ora < self._pausa_fino_a:
            raise TelegramError(
                f"Telegram ha chiesto di aspettare fino alle {self._pausa_fino_a.isoformat(timespec='seconds')}"
            )
        try:
            return chiamata(*argomenti)
        except TelegramTroppeRichieste as e:
            self._pausa_fino_a = ora + timedelta(seconds=e.retry_after)
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
            testo = testi.annuncio(annuncio, self._roster, self._nome)
            self._invia(self._tg.scrivi, self._gruppo, testo.testo, testo.entita)
            fatti = regole.dopo(fatti, annuncio)
            self._store.salva_fatti(sondaggio.id, fatti)
