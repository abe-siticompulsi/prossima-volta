"""La ripresa dopo il buio (§3.8): dopo più di 23 ore senza letture il bot lo
dice e, se c'è un sondaggio aperto da prima, lo ferma, confronta i conteggi e
lo riapre con i voti tenuti.

Ogni passo si salva nel database con il messaggio che lo dice, in una
transazione (la chiave `ripresa` dello store, con le fasi «fermare» e
«riaprire»): a ogni lettura la ripresa continua dal passo in cui si era
fermata. Un errore di Telegram la lascia dov'è, e la lettura seguente riprova;
un altro errore la ferma fino al prossimo avvio (le riprese guaste, in
memoria). Dopo un sondaggio riaperto che forse è partito senza che la
risposta arrivasse, il prossimo non parte prima di 10 minuti (in memoria anche
questo): con Telegram che risponde oltre il timeout, ogni lettura ne
manderebbe uno.

Dipende dall'invio (lo stop, il sondaggio nuovo, le lettere, la pausa), dallo
store, dalle regole e dai testi. Una chiusura in sospeso vince sulla ripresa:
la ripresa la legge dallo store, senza dipendere dalle chiusure
(`chiusura.py`), che invece usano la ripresa.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, tzinfo

from . import regole, testi
from .invio import AVVISO_RIPETUTO, Avvisi, Invio, forse_arrivata, livello
from .regole import Roster
from .store import FERMARE, RIAPRIRE, RipresaInCorso, Sondaggio, Store
from .telegram import TelegramError

log = logging.getLogger(__name__)


class Ripresa:
    def __init__(
        self,
        *,
        invio: Invio,
        store: Store,
        roster: Roster,
        fuso: tzinfo,
        adesso: Callable[[], datetime],
    ) -> None:
        self._invio = invio
        self._store = store
        self._roster = roster
        self._fuso = fuso
        self._adesso = adesso
        # Le riprese dopo il buio, per sondaggio, ferme per un errore che non
        # viene da Telegram (il database, un bug): la ripresa resta, e il
        # prossimo avvio la riprova una volta. Anche dopo un `/chiudi` fallito
        # sul sondaggio che aspettava la riapertura: non si riapre.
        self._guaste: set[int] = set()
        # Gli avvisi nel log degli errori di Telegram, per sondaggio.
        self._avvisi = Avvisi(adesso)
        # Le riaperture il cui sondaggio nuovo forse è partito (la rete, un
        # 5xx, una risposta illeggibile), per sondaggio: il momento del
        # tentativo. Il prossimo non parte prima di `AVVISO_RIPETUTO`.
        self._forse_partite: dict[int, datetime] = {}

    # --- lo stato, per le altre parti

    def in_riapertura(self) -> Sondaggio | None:
        """Il sondaggio che la ripresa ha fermato e aspetta di riaprire."""
        ripresa = self._store.ripresa()
        if ripresa is None or ripresa.fase != RIAPRIRE:
            return None
        return self._store.sondaggio(ripresa.sondaggio)

    def stop_partito(self, sondaggio: Sondaggio) -> bool:
        """La ripresa del sondaggio ha mandato lo stop e non ne ha avuto
        conferma: il sondaggio, aperto nel database, può essere già fermo su
        Telegram."""
        ripresa = self._store.ripresa()
        return (
            ripresa is not None
            and ripresa.sondaggio == sondaggio.id
            and ripresa.fase == FERMARE
            and ripresa.stop_provato
        )

    def guasta(self, sondaggio: Sondaggio) -> bool:
        """La ripresa del sondaggio è ferma fino al prossimo avvio (v.
        `_guaste`)."""
        ripresa = self._store.ripresa()
        return (
            ripresa is not None
            and ripresa.sondaggio == sondaggio.id
            and sondaggio.id in self._guaste
        )

    def ferma_fino_al_riavvio(self, sondaggio_id: int) -> None:
        """La ripresa del sondaggio non riparte da sola: la riprova il
        prossimo avvio."""
        self._guaste.add(sondaggio_id)

    # --- i passi

    def inizia(self, dal: datetime, al: datetime) -> None:
        """Il buio dal `dal` al `al` (la prima lettura dopo il buio): lo dice
        e, se c'è un sondaggio aperto da prima, ne comincia la ripresa. Un
        sondaggio nato dopo, in un lotto letto da `al` in poi, non ha voti
        persi: non si ferma e rifà.

        La lettura si segna qui, nella stessa transazione del messaggio del
        buio e della ripresa: se la ripresa si ferma a metà, la lettura seguente
        non vede un altro buio (il messaggio non si ripete) e la continua; se il
        processo si ferma prima, non c'è niente, e la lettura seguente rivede
        il buio."""
        aperto = self._store.sondaggio_aperto()
        da_riprendere = aperto.id if aperto is not None and aperto.aperto_alle < al else None
        lettera = self._invio.lettera(testi.buio(dal, al, self._fuso))
        self._store.inizia_ripresa(al, [lettera], da_riprendere)

    def continua(self) -> None:
        """La ripresa in corso, se c'è, fa i passi che può: fermare il sondaggio
        e confrontare i conteggi, poi riaprirlo. Ogni passo si salva con il
        messaggio che lo dice. Un errore di Telegram la lascia dov'è (la
        lettura seguente riprova; nel log la prima volta, poi al massimo ogni
        10 minuti). Un altro errore la lascia dov'è fino al prossimo avvio, con
        il traceback nel log: ritentarla a ogni lettura ripeterebbe l'errore, o
        manderebbe un sondaggio nuovo a ogni lettura."""
        ripresa = self._store.ripresa()
        if ripresa is None or ripresa.sondaggio in self._guaste:
            return
        sondaggio_id = ripresa.sondaggio
        try:
            if ripresa.fase == FERMARE:
                ripresa = self._ferma_per_riprendere(ripresa)
            if ripresa is not None:
                self._riapri(ripresa)
        except TelegramError as e:
            if self._avvisi.da_avvisare(sondaggio_id):
                log.log(
                    livello(e),
                    "ripresa del sondaggio %s rimandata alla lettura seguente: %s",
                    sondaggio_id,
                    e,
                )
        except Exception:
            self._guaste.add(sondaggio_id)
            log.exception("ripresa del sondaggio %s non riuscita", sondaggio_id)

    def _ferma_per_riprendere(self, ripresa: RipresaInCorso) -> RipresaInCorso | None:
        """La fase «fermare»: lo stop e il confronto dei conteggi. Restituisce
        la ripresa in fase «riaprire», o None se è finita o aspetta."""
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None or sondaggio.id != ripresa.sondaggio or self._in_sospeso(sondaggio):
            # Chiuso da un /chiudi mentre la ripresa aspettava, o chi può
            # chiudere l'ha chiuso: non si riapre. Una chiusura in sospeso la
            # finisce `manda`, con lo stop e il messaggio del comando.
            self._store.fine_ripresa(self._adesso())
            return None
        if self._invio.in_pausa():
            return None
        if not ripresa.stop_provato:
            self._store.prova_stop_di_ripresa()
        fermato = self._invio.ferma(sondaggio)
        adesso = self._adesso()
        if fermato.sparito:
            lettere = self._invio.lettere([testi.sparito()])
            self._store.fine_ripresa(adesso, lettere, chiudi=sondaggio.id)
            return None
        if fermato.conteggi is not None:
            nostri = regole.conteggi_per_opzione(
                sondaggio.date, self._store.voti_del_poll(sondaggio.id, sondaggio.poll_id)
            )
            lettera = testi.conteggi(fermato.conteggi == nostri)
        elif ripresa.stop_provato:
            # è passato uno stop di questa ripresa, senza che la risposta arrivasse
            lettera = testi.gia_chiuso_senza_confronto()
        else:
            # nessuno stop di questo bot lo spiega: chi l'ha chiuso non si sa, e
            # un sondaggio che qualcuno ha chiuso non si riapre
            lettere = self._invio.lettere([testi.gia_chiuso()])
            self._store.fine_ripresa(adesso, lettere, chiudi=sondaggio.id)
            return None
        self._store.fermato_per_riprendere(sondaggio.id, adesso, self._invio.lettere([lettera]))
        return RipresaInCorso(sondaggio.id, RIAPRIRE)

    def _riapri(self, ripresa: RipresaInCorso) -> None:
        """La fase «riaprire»: il sondaggio nuovo sulle date non ancora passate,
        con i voti tenuti, e «Riapro il sondaggio…» in risposta a quello, così
        si sa quale conta. Un sondaggio lanciato nel frattempo vale al posto
        suo. Se il sondaggio nuovo non parte, nessun messaggio: «riprovate con
        /sondaggio» butterebbe i voti tenuti. Se di sicuro non è partito (la
        pausa di un 429, un rifiuto) la lettura seguente riprova; se forse è
        partito, il prossimo tentativo aspetta 10 minuti: nel gruppo può
        restare un sondaggio in più, uno ogni 10 minuti al massimo."""
        if self._store.sondaggio_aperto() is not None:
            # aprirlo toglie già la ripresa (`store._apri`): questa è la rete
            self._store.fine_ripresa(self._adesso())
            return
        sondaggio = self._store.sondaggio(ripresa.sondaggio)
        oggi = self._oggi()
        future = [g for g in sondaggio.date if g >= oggi]
        if not future:
            self._store.fine_ripresa(self._adesso(), self._invio.lettere([testi.date_passate()]))
            return
        if self._invio.in_pausa() or self._da_aspettare(sondaggio.id):
            return
        try:
            mandato, frase = self._invio.nuovo_sondaggio(future)
        except TelegramError as e:
            if forse_arrivata(e):
                self._forse_partite[sondaggio.id] = self._adesso()
            raise
        stato = regole.Stato(self._roster, tuple(future), self._store.voti(sondaggio.id))
        self._store.riapri_sondaggio(
            sondaggio.id,
            future,
            mandato.poll_id,
            mandato.messaggio,
            frase,
            regole.dopo(self._store.fatti(sondaggio.id), regole.Ripresa()),
            self._adesso(),
            [
                self._invio.lettera(
                    testi.riapro(stato.votanti, stato.senza_voto), risposta_a=mandato.messaggio
                )
            ],
        )
        self._forse_partite.pop(sondaggio.id, None)

    # --- i pezzi

    def _in_sospeso(self, sondaggio: Sondaggio) -> bool:
        """Chi può chiudere l'ha chiuso, ma Telegram non ha ancora confermato lo
        stop: la chiusura in sospeso, letta dallo store (v. `chiusura.py`)."""
        sospesa = self._store.chiusura_sospesa()
        return sospesa is not None and sospesa.sondaggio == sondaggio.id

    def _da_aspettare(self, sondaggio_id: int) -> bool:
        """Il sondaggio riaperto forse è partito meno di 10 minuti fa."""
        tentato = self._forse_partite.get(sondaggio_id)
        return tentato is not None and self._adesso() - tentato < AVVISO_RIPETUTO

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()
