"""Le chiusure (§3.7): `/chiudi` nelle sue forme (le date possibili, la data
tenuta, `rimanda`), la chiusura in sospeso e i suoi tentativi, il
completamento.

Lo stop (`stopPoll`) parte subito: se Telegram non lo conferma la chiusura
resta in sospeso (la chiave nello store), il bot lo dice, e la ritenta a ogni
giro (`riprova`) finché Telegram risponde; poi chiude come chiedeva il
comando. Uno stop passato senza che la risposta arrivasse non blocca il nuovo
tentativo: Telegram risponde che il sondaggio è già chiuso. Il messaggio che
dice la chiusura si salva nella stessa transazione della chiusura.

In memoria, per questo processo: gli stop rifiutati (4xx), già scritti nel
log, e le chiusure guaste (un completamento fallito per un errore che non
viene da Telegram), che non si ritentano fino al prossimo avvio.

Dipende dalla ripresa (il sondaggio che aspetta di riaprire si chiude come se
fosse aperto, e una sua chiusura fallita ferma la ripresa fino al riavvio),
dall'invio, dallo store, dalle regole e dai testi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, tzinfo

from . import regole, testi
from .invio import Avvisi, Fermato, Invio, forse_arrivata, livello
from .regole import Roster
from .ripresa import Ripresa
from .store import ChiusuraSospesa, Sondaggio, Store
from .telegram import TelegramError, TelegramRifiuto

log = logging.getLogger(__name__)


def argomenti_di_chiudi(chiusura: ChiusuraSospesa) -> list[str]:
    """L'argomento di un `/chiudi` in sospeso come si scrive: niente, la data
    `g/m`, o «rimanda»."""
    if chiusura.argomento is None:
        return []
    if chiusura.argomento == regole.RIMANDA:
        return [regole.RIMANDA]
    return [regole.breve(date.fromisoformat(chiusura.argomento))]


class Chiusure:
    def __init__(
        self,
        *,
        ripresa: Ripresa,
        invio: Invio,
        store: Store,
        roster: Roster,
        nome: str,
        fuso: tzinfo,
        adesso: Callable[[], datetime],
    ) -> None:
        self._ripresa = ripresa
        self._invio = invio
        self._store = store
        self._roster = roster
        self._nome = nome
        self._fuso = fuso
        self._adesso = adesso
        # Gli stop che Telegram ha rifiutato (4xx) in questo processo, per
        # sondaggio, già scritti nel log: si ritentano lo stesso.
        self._stop_rifiutati: set[int] = set()
        # I `/chiudi` in sospeso il cui completamento è fallito per un errore che
        # non viene da Telegram (il database, un bug): non si ritentano fino al
        # prossimo avvio, che li riprova una volta. Con `rimanda`, ritentarli a
        # ogni giro manderebbe un sondaggio nuovo a ogni giro.
        self._guaste: set[int] = set()
        # Gli avvisi nel log degli stop che si ritentano, per sondaggio.
        self._avvisi = Avvisi(adesso)

    # --- lo stato, per le altre parti

    def in_sospeso(self, sondaggio: Sondaggio) -> bool:
        """Chi può chiudere l'ha chiuso, ma Telegram non ha ancora confermato lo stop."""
        sospesa = self._store.chiusura_sospesa()
        return sospesa is not None and sospesa.sondaggio == sondaggio.id

    def guasta(self, sondaggio: Sondaggio) -> ChiusuraSospesa | None:
        """La chiusura in sospeso del sondaggio, se il suo completamento è
        fallito (v. `_guaste`)."""
        sospesa = self._store.chiusura_sospesa()
        if sospesa is None or sospesa.sondaggio != sondaggio.id:
            return None
        return sospesa if sospesa.comando in self._guaste else None

    # --- /chiudi

    def chiudi(self, messaggio: dict, parole: list[str]) -> None:
        comando = messaggio["message_id"]
        sospesa = self._store.chiusura_sospesa()
        if self._store.chiuso_dal_comando(comando) or (
            sospesa is not None and sospesa.comando == comando
        ):
            return  # lo stesso /chiudi letto una seconda volta dopo un riavvio
        chi = self._roster.per_id(messaggio.get("from", {}).get("id"))
        if chi is None or not chi.chiude:
            self._invio.accoda(testi.solo_chi_chiude(self._roster.chi_chiude), risposta_a=comando)
            return
        # il sondaggio fermato dalla ripresa, che aspetta di essere riaperto,
        # si chiude come se fosse aperto: vince il comando di chi chiude
        sondaggio = self._store.sondaggio_aperto() or self._ripresa.in_riapertura()
        if sondaggio is None:
            self._invio.accoda(testi.nessun_sondaggio(), risposta_a=comando)
            return
        if len(parole) > 1:
            rifiuto = regole.NonCapisco(" ".join(parole))
            self._invio.accoda(testi.rifiuto_di_chiudi(rifiuto), risposta_a=comando)
            return
        argomento = None
        if parole and parole[0].lower() == regole.RIMANDA:
            argomento = regole.RIMANDA
        elif parole:
            try:
                oggi = self._oggi()
                # anche le date che una ripresa ha tolto perché passate: erano
                # nel sondaggio, e il rifiuto giusto è «è già passata»
                tutte = sorted({*sondaggio.date, *sondaggio.date_iniziali})
                tenuta = regole.data_da_chiudere(parole[0], tutte, oggi)
                if tenuta < oggi:
                    raise regole.DataPassata(regole.breve(tenuta))
            except regole.Rifiuto as r:
                self._invio.accoda(testi.rifiuto_di_chiudi(r), risposta_a=comando)
                return
            argomento = tenuta.isoformat()
        chiusura = ChiusuraSospesa(sondaggio.id, comando, argomento)
        if sondaggio.chiuso_alle is not None:
            # già fermo su Telegram: si chiude con i voti tenuti, senza stop, e la
            # ripresa finisce nella stessa transazione della lettera
            try:
                self._completa(chiusura, sondaggio, Fermato(None))
            except Exception:
                # la riapertura non riparte da sola: chi può chiudere l'ha chiuso
                self._ripresa.ferma_fino_al_riavvio(sondaggio.id)
                log.exception("chiusura del sondaggio %s non completata", sondaggio.id)
            return
        if self.in_sospeso(sondaggio):
            # lo stop lo ritenta già il bot: vale l'ultima decisione, e un
            # completamento fallito si riprova con il comando nuovo
            if self.guasta(sondaggio) is not None:
                self._sospendi(chiusura, testi.riprovo_a_completare())
            else:
                self._sospendi(chiusura)
            return
        try:
            fermato = self._invio.ferma(sondaggio)
        except TelegramError as e:
            # rete, 5xx, un rifiuto, la pausa di un 429: forse lo stop è passato
            # e la risposta si è persa; il bot lo ritenta a ogni giro (`manda`)
            log.log(livello(e), "chiusura del sondaggio %s non confermata: %s", sondaggio.id, e)
            if isinstance(e, TelegramRifiuto):
                self._stop_rifiutati.add(sondaggio.id)
            else:
                # i tentativi del bot ne scrivono un altro fra 10 minuti, non subito
                self._avvisi.avvisato(sondaggio.id)
            self._sospendi(chiusura)
            return
        self._completa(chiusura, sondaggio, fermato)

    def _sospendi(self, chiusura: ChiusuraSospesa, risposta: testi.Testo | None = None) -> None:
        lettera = self._invio.lettera(
            risposta or testi.chiusura_non_confermata(), risposta_a=chiusura.comando
        )
        self._store.sospendi_chiusura(chiusura, self._adesso(), [lettera])

    # --- la chiusura in sospeso

    def riprova(self) -> bool:
        """Ritenta lo stop di una chiusura in sospeso; quando Telegram risponde
        (fermato, già chiuso, o il messaggio sparito) chiude come chiedeva il
        comando. Vero se ha chiuso. Se lo stop non riesce, il giro seguente
        riprova: un errore di rete va nel log la prima volta e poi al massimo
        ogni 10 minuti, un rifiuto (4xx) una volta per processo. Un
        completamento fallito per un altro errore non si ritenta fino al
        prossimo avvio."""
        sospesa = self._store.chiusura_sospesa()
        if sospesa is None or sospesa.comando in self._guaste:
            return False
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None or sondaggio.id != sospesa.sondaggio:
            self._store.togli_chiusura_sospesa()  # chiuso per un'altra via
            return False
        try:
            fermato = self._invio.ferma(sondaggio)
        except TelegramRifiuto as e:
            if sondaggio.id not in self._stop_rifiutati:
                self._stop_rifiutati.add(sondaggio.id)
                log.error("chiusura del sondaggio %s rifiutata da Telegram: %s", sondaggio.id, e)
            return False
        except TelegramError as e:
            if self._avvisi.da_avvisare(sondaggio.id):
                log.warning("chiusura del sondaggio %s ancora non confermata: %s", sondaggio.id, e)
            return False
        try:
            self._completa(sospesa, sondaggio, fermato)
        except Exception:
            self._guaste.add(sospesa.comando)
            log.exception("chiusura del sondaggio %s non completata", sondaggio.id)
            return False
        return True

    # --- il completamento

    def _completa(self, chiusura: ChiusuraSospesa, sondaggio: Sondaggio, fermato: Fermato) -> None:
        """Chiude il sondaggio, fermo su Telegram, come chiede il `/chiudi`:
        le date possibili, la data tenuta, o `rimanda`. Le date possibili si
        contano adesso, con i voti arrivati fino allo stop, e solo da oggi in
        poi; se i conteggi di Telegram allo stop sono diversi da quelli del
        bot (voti persi, per esempio nel buio), il riepilogo è preceduto dalla
        frase che lo dice."""
        if chiusura.argomento == regole.RIMANDA:
            self._rimanda(sondaggio, chiusura.comando, fermato)
            return
        lettere = [testi.sparito()] if fermato.sparito else []
        if chiusura.argomento is not None:
            lettere.append(testi.si_gioca(date.fromisoformat(chiusura.argomento)))
        else:
            if fermato.conteggi is not None and fermato.conteggi != self._conteggi(sondaggio):
                lettere.append(testi.conteggi(False))
            # il riepilogo dice solo le date in cui si può ancora giocare; se c'erano
            # date possibili ma sono tutte passate, non dice che non ce n'erano
            oggi = self._oggi()
            tutte = regole.possibili(self._stato(sondaggio))
            possibili = [g for g in tutte if g >= oggi]
            lettere.append(
                testi.chiuso(possibili)
                if possibili or not tutte
                else testi.chiuso_con_le_date_possibili_passate()
            )
        self._store.chiudi_sondaggio(
            sondaggio.id, self._adesso(), chiusura.comando, self._invio.lettere(lettere)
        )

    def _rimanda(self, vecchio: Sondaggio, comando: int, fermato: Fermato) -> None:
        """`/chiudi rimanda`, a sondaggio fermo su Telegram: un sondaggio nuovo
        sugli stessi giorni della settimana dopo (quelli con cui il vecchio è
        nato, anche se una ripresa ha tolto le date passate), senza le date
        passate. Il vecchio si chiude nel database solo insieme al nuovo, in
        una transazione: fino a lì, il comando riletto riprende da capo (lo
        stop dirà che il vecchio è già chiuso)."""
        oggi = self._oggi()
        date_ = [g for g in regole.date_rimandate(vecchio.date_iniziali) if g >= oggi]
        sparito = [testi.sparito()] if fermato.sparito else []
        if not date_:
            lettere = self._invio.lettere([*sparito, testi.date_passate()])
            self._store.chiudi_sondaggio(vecchio.id, self._adesso(), comando, lettere)
            return
        if sparito:
            # Prima del sondaggio nuovo, che parte dopo la posta: da sola, non con
            # la chiusura. Un'interruzione prima del salvataggio la fa ripetere.
            self._invio.accoda(testi.sparito())
        try:
            mandato, frase = self._invio.nuovo_sondaggio(date_)
        except TelegramError as e:
            log.log(livello(e), "sondaggio nuovo di rimanda non confermato: %s", e)
            lettere = self._invio.lettere([testi.rimando_non_confermato(self._nome, date_)])
            argomenti = [regole.breve(g) for g in date_] if forse_arrivata(e) else None
            self._store.chiudi_sondaggio(
                vecchio.id, self._adesso(), comando, lettere, non_confermato=argomenti
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
            self._invio.lettere([testi.rimandiamo(regole.lunedi(date_[0]))]),
        )

    # --- i pezzi

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()

    def _stato(self, sondaggio: Sondaggio) -> regole.Stato:
        return regole.Stato(self._roster, sondaggio.date, self._store.voti(sondaggio.id))

    def _conteggi(self, sondaggio: Sondaggio) -> list[int]:
        """I conteggi del bot nella forma di quelli di `stopPoll`: solo i voti
        dati nel sondaggio di Telegram di adesso, gli unici che Telegram conta."""
        return regole.conteggi_per_opzione(
            sondaggio.date, self._store.voti_del_poll(sondaggio.id, sondaggio.poll_id)
        )
