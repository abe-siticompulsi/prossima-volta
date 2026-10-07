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
  Telegram li ha accettati; con la chiusura in sospeso non ce ne sono. Uno
  rifiutato (4xx) va nel log come errore, non ferma gli altri, e non si
  riprova fino al prossimo avvio;
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
from .store import (
    FERMARE,
    RIAPRIRE,
    ChiusuraSospesa,
    LetteraNuova,
    RipresaInCorso,
    Sondaggio,
    Store,
)
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
# Un errore che si ripete a ogni giro va nel log la prima volta, e poi al
# massimo una volta in questo tempo.
AVVISO_RIPETUTO = timedelta(minutes=10)


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


def _argomenti_di_chiudi(chiusura: ChiusuraSospesa) -> list[str]:
    """L'argomento di un `/chiudi` in sospeso come si scrive: niente, la data
    `g/m`, o «rimanda»."""
    if chiusura.argomento is None:
        return []
    if chiusura.argomento == regole.RIMANDA:
        return [regole.RIMANDA]
    return [regole.breve(date.fromisoformat(chiusura.argomento))]


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
        # I `/chiudi` in sospeso il cui completamento è fallito per un errore che
        # non viene da Telegram (il database, un bug): non si ritentano fino al
        # prossimo avvio, che li riprova una volta. Con `rimanda`, ritentarli a
        # ogni giro manderebbe un sondaggio nuovo a ogni giro.
        self._chiusure_guaste: set[int] = set()
        # Lo stesso per le riprese dopo il buio, per sondaggio: la ripresa resta,
        # e il prossimo avvio la riprova una volta. Anche dopo un `/chiudi`
        # fallito sul sondaggio che aspettava la riapertura: non si riapre.
        self._riprese_guaste: set[int] = set()
        self._avvisati: dict[tuple, datetime] = {}  # v. `_da_avvisare`

    # --- il giro

    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`, anche vuoto. Si chiama solo dopo una
        lettura riuscita: il momento di adesso diventa quello dell'ultima
        lettura, e da lì si conta il buio. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii. Dopo più di 23 ore senza letture comincia la ripresa (§3.8), e a
        ogni lettura una ripresa in corso fa i passi che può."""
        ora = self._adesso()
        precedente = self._store.ultima_lettura()
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        if regole.al_buio(precedente, ora):
            try:
                self._inizia_ripresa(precedente, ora)
            except Exception:
                # la lettura non è segnata: la prossima vede di nuovo il buio
                log.exception("ripresa dopo il buio non cominciata")
        else:
            self._store.segna_lettura(ora)
        self._continua_ripresa()
        self.manda()

    def gestisci(self, aggiornamento: dict) -> None:
        if "poll_answer" in aggiornamento:
            self._voto(aggiornamento["poll_answer"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def manda(self) -> None:
        """La posta in uscita, in ordine; lo stop di una chiusura in sospeso (e,
        se riesce, la posta che la dice); gli annunci del sondaggio aperto, se
        non è in chiusura. Quello che non parte riparte al giro seguente.
        Durante la pausa chiesta da un 429 non si prova nemmeno: il 429 è già
        nel log."""
        if self._in_pausa():
            return
        try:
            self._manda_posta()
            if self._riprova_chiusura():
                self._manda_posta()
            self._manda_annunci()
        except TelegramError as e:
            self._avvisa_invio("invio rimandato al giro seguente: %s", e)

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
            guasta = self._chiusura_guasta(aperto)
            if guasta is not None:
                # lo stop può essere passato: è il completamento che è fallito
                risposta = testi.chiusura_non_completata(self._nome, _argomenti_di_chiudi(guasta))
            elif self._ripresa_guasta(aperto):
                # lo stop della ripresa è partito, ed è fallito quello che veniva dopo
                risposta = testi.chiusura_non_completata(self._nome, [])
            else:
                risposta = testi.non_ancora_chiuso()
            self._accoda(risposta, risposta_a=messaggio["message_id"])
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
                self._store.segna_non_confermato(self._adesso(), parole, [lettera])
            else:
                self._accoda(risposta, risposta_a=comando)
            return
        self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())

    def _voto(self, risposta: dict) -> None:
        poll_id = risposta.get("poll_id")
        sondaggio = self._store.sondaggio_aperto()
        utente = risposta.get("user")
        opzioni = risposta.get("option_ids", [])
        # senza un sondaggio aperto, quello che la ripresa ha fermato e riaprirà
        fermo = self._in_riapertura() if sondaggio is None else None
        if sondaggio is not None and poll_id == sondaggio.poll_id:
            if utente is None:
                return
            voto = regole.voto_da_opzioni(sondaggio.date, opzioni)
            self._store.registra_voto(sondaggio.id, utente["id"], poll_id, voto, self._adesso())
        elif fermo is not None and poll_id == fermo.poll_id:
            # dato poco prima dello stop, arrivato mentre la riapertura aspetta: si
            # tiene, come gli altri voti, per il sondaggio riaperto
            if utente is None:
                return
            voto = regole.voto_da_opzioni(fermo.date, opzioni)
            self._store.registra_voto(fermo.id, utente["id"], poll_id, voto, self._adesso())
        elif sondaggio is not None and sondaggio.poll_prima is not None and poll_id == sondaggio.poll_prima:
            # Dato nel sondaggio di prima della ripresa, poco prima dello stop, e
            # arrivato dopo la riapertura: vale se la persona non ha votato nel
            # sondaggio di adesso. Le opzioni sono quelle di prima.
            if utente is None:
                return
            voto = regole.voto_da_opzioni(sondaggio.date_prima, opzioni)
            self._store.registra_voto_tardivo(
                sondaggio.id, utente["id"], poll_id, voto, self._adesso(), sondaggio.poll_id
            )
        elif not self._store.poll_conosciuto(poll_id):
            self._voto_sconosciuto(poll_id)
        # un voto per un sondaggio che il bot conosce, ma non è aperto: si ignora

    def _voto_sconosciuto(self, poll_id: str) -> None:
        """Telegram manda al bot solo i voti dei sondaggi del bot: questo è un
        sondaggio che il bot ha mandato senza registrarlo (una risposta persa),
        o uno del piano reale, nella chat privata di Alberto. Nel gruppo lo si
        dice una volta per sondaggio, e solo se c'è stato da poco un sondaggio
        che Telegram non ha confermato: i voti del piano reale restano nel log.
        Con un sondaggio aperto l'avviso risponde a quello: è lì che si vota.
        Mentre la ripresa aspetta di riaprire, solo il log."""
        log.warning("voto per un sondaggio sconosciuto: %s", poll_id)
        if self._in_riapertura() is not None:
            return  # «Rilanciatelo» farebbe buttare i voti che la riapertura tiene
        tentativo = self._store.ultimo_non_confermato()
        adesso = self._adesso()
        if tentativo is None or adesso - tentativo.alle > NON_CONFERMATO_DI_RECENTE:
            return
        aperto = self._store.sondaggio_aperto()
        if aperto is None or self._in_chiusura(aperto):
            avviso = self._lettera(testi.voto_sconosciuto(self._nome, tentativo.argomenti))
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
        # il sondaggio fermato dalla ripresa, che aspetta di essere riaperto,
        # si chiude come se fosse aperto: vince il comando di chi chiude
        sondaggio = self._store.sondaggio_aperto() or self._in_riapertura()
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
                tenuta = regole.data_da_chiudere(parole[0], sondaggio.date)
                if tenuta < self._oggi():
                    raise regole.DataPassata(regole.breve(tenuta))
            except regole.Rifiuto as r:
                self._accoda(testi.rifiuto_di_chiudi(r), risposta_a=comando)
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
                self._riprese_guaste.add(sondaggio.id)
                log.exception("chiusura del sondaggio %s non completata", sondaggio.id)
            return
        if self._in_sospeso(sondaggio):
            # lo stop lo ritenta già il bot: vale l'ultima decisione, e un
            # completamento fallito si riprova con il comando nuovo
            if self._chiusura_guasta(sondaggio) is not None:
                self._sospendi(chiusura, testi.riprovo_a_completare())
            else:
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
            else:
                # i tentativi del bot ne scrivono un altro fra 10 minuti, non subito
                self._avvisati[("chiusura", sondaggio.id)] = self._adesso()
            self._sospendi(chiusura)
            return
        self._completa(chiusura, sondaggio, fermato)

    def _sospendi(self, chiusura: ChiusuraSospesa, risposta: testi.Testo | None = None) -> None:
        lettera = self._lettera(
            risposta or testi.chiusura_non_confermata(), risposta_a=chiusura.comando
        )
        self._store.sospendi_chiusura(chiusura, self._adesso(), [lettera])

    def _ripresa_guasta(self, sondaggio: Sondaggio) -> bool:
        """La ripresa del sondaggio è ferma fino al prossimo avvio (v.
        `_riprese_guaste`)."""
        ripresa = self._store.ripresa()
        return (
            ripresa is not None
            and ripresa.sondaggio == sondaggio.id
            and sondaggio.id in self._riprese_guaste
        )

    def _chiusura_guasta(self, sondaggio: Sondaggio) -> ChiusuraSospesa | None:
        """La chiusura in sospeso del sondaggio, se il suo completamento è
        fallito (v. `_chiusure_guaste`)."""
        sospesa = self._store.chiusura_sospesa()
        if sospesa is None or sospesa.sondaggio != sondaggio.id:
            return None
        return sospesa if sospesa.comando in self._chiusure_guaste else None

    def _in_riapertura(self) -> Sondaggio | None:
        """Il sondaggio che la ripresa ha fermato e aspetta di riaprire."""
        ripresa = self._store.ripresa()
        if ripresa is None or ripresa.fase != RIAPRIRE:
            return None
        return self._store.sondaggio(ripresa.sondaggio)

    def _in_sospeso(self, sondaggio: Sondaggio) -> bool:
        """Chi può chiudere l'ha chiuso, ma Telegram non ha ancora confermato lo stop."""
        sospesa = self._store.chiusura_sospesa()
        return sospesa is not None and sospesa.sondaggio == sondaggio.id

    def _in_chiusura(self, sondaggio: Sondaggio) -> bool:
        """Il sondaggio è aperto nel database ma forse già fermo su Telegram: una
        chiusura in sospeso, o una ripresa che ha mandato lo stop e non ne ha
        avuto conferma. Non si dice che è aperto, e niente annunci."""
        if self._in_sospeso(sondaggio):
            return True
        ripresa = self._store.ripresa()
        return (
            ripresa is not None
            and ripresa.sondaggio == sondaggio.id
            and ripresa.fase == FERMARE
            and ripresa.stop_provato
        )

    def _riprova_chiusura(self) -> bool:
        """Ritenta lo stop di una chiusura in sospeso; quando Telegram risponde
        (fermato, già chiuso, o il messaggio sparito) chiude come chiedeva il
        comando. Vero se ha chiuso. Se lo stop non riesce, il giro seguente
        riprova: un errore di rete va nel log la prima volta e poi al massimo
        ogni 10 minuti, un rifiuto (4xx) una volta per processo. Un
        completamento fallito per un altro errore non si ritenta fino al
        prossimo avvio."""
        sospesa = self._store.chiusura_sospesa()
        if sospesa is None or sospesa.comando in self._chiusure_guaste:
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
        except TelegramError as e:
            if self._da_avvisare(("chiusura", sondaggio.id)):
                log.warning("chiusura del sondaggio %s ancora non confermata: %s", sondaggio.id, e)
            return False
        try:
            self._completa(sospesa, sondaggio, fermato)
        except Exception:
            self._chiusure_guaste.add(sospesa.comando)
            log.exception("chiusura del sondaggio %s non completata", sondaggio.id)
            return False
        return True

    def _completa(self, chiusura: ChiusuraSospesa, sondaggio: Sondaggio, fermato: Fermato) -> None:
        """Chiude il sondaggio, fermo su Telegram, come chiede il `/chiudi`:
        le date possibili, la data tenuta, o `rimanda`. Le date possibili si
        contano adesso, con i voti arrivati fino allo stop, e solo da oggi in
        poi."""
        if chiusura.argomento == regole.RIMANDA:
            self._rimanda(sondaggio, chiusura.comando, fermato)
            return
        lettere = [testi.sparito()] if fermato.sparito else []
        if chiusura.argomento is not None:
            lettere.append(testi.si_gioca(date.fromisoformat(chiusura.argomento)))
        else:
            # il riepilogo dice solo le date in cui si può ancora giocare
            oggi = self._oggi()
            possibili = [g for g in regole.possibili(self._stato(sondaggio)) if g >= oggi]
            lettere.append(testi.chiuso(possibili))
        self._store.chiudi_sondaggio(
            sondaggio.id, self._adesso(), chiusura.comando, self._lettere(lettere)
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
            argomenti = [regole.breve(g) for g in date_] if _forse_arrivata(e) else None
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

    def _inizia_ripresa(self, dal: datetime, al: datetime) -> None:
        """Il buio dal `dal` al `al`: lo dice e, se c'è un sondaggio aperto da
        prima del lotto, ne comincia la ripresa. Un sondaggio nato nel lotto
        (dopo la lettura del buio) non ha voti persi: non si ferma e rifà.

        La lettura si segna qui, nella stessa transazione del messaggio del
        buio e della ripresa: se la ripresa si ferma a metà, la lettura seguente
        non vede un altro buio (il messaggio non si ripete) e la continua; se il
        processo si ferma prima, non c'è niente, e la lettura seguente rivede
        il buio."""
        aperto = self._store.sondaggio_aperto()
        da_riprendere = aperto.id if aperto is not None and aperto.aperto_alle < al else None
        lettera = self._lettera(testi.buio(dal, al, self._fuso))
        self._store.inizia_ripresa(al, [lettera], da_riprendere)

    def _continua_ripresa(self) -> None:
        """La ripresa in corso, se c'è, fa i passi che può: fermare il sondaggio
        e confrontare i conteggi, poi riaprirlo. Ogni passo si salva con il
        messaggio che lo dice. Un errore di Telegram la lascia dov'è (la
        lettura seguente riprova; nel log la prima volta, poi al massimo ogni
        10 minuti). Un altro errore la lascia dov'è fino al prossimo avvio, con
        il traceback nel log: ritentarla a ogni lettura ripeterebbe l'errore, o
        manderebbe un sondaggio nuovo a ogni lettura."""
        ripresa = self._store.ripresa()
        if ripresa is None or ripresa.sondaggio in self._riprese_guaste:
            return
        sondaggio_id = ripresa.sondaggio
        try:
            if ripresa.fase == FERMARE:
                ripresa = self._ferma_per_riprendere(ripresa)
            if ripresa is not None:
                self._riapri(ripresa)
        except TelegramError as e:
            if self._da_avvisare(("ripresa", sondaggio_id)):
                log.log(
                    _livello(e),
                    "ripresa del sondaggio %s rimandata alla lettura seguente: %s",
                    sondaggio_id,
                    e,
                )
        except Exception:
            self._riprese_guaste.add(sondaggio_id)
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
        if self._in_pausa():
            return None
        if not ripresa.stop_provato:
            self._store.prova_stop_di_ripresa()
        fermato = self._ferma(sondaggio)
        adesso = self._adesso()
        if fermato.sparito:
            lettere = self._lettere([testi.sparito()])
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
            self._store.fine_ripresa(adesso, self._lettere([testi.gia_chiuso()]), chiudi=sondaggio.id)
            return None
        self._store.fermato_per_riprendere(sondaggio.id, adesso, self._lettere([lettera]))
        return RipresaInCorso(sondaggio.id, RIAPRIRE)

    def _riapri(self, ripresa: RipresaInCorso) -> None:
        """La fase «riaprire»: il sondaggio nuovo sulle date non ancora passate,
        con i voti tenuti. Un sondaggio lanciato nel frattempo vale al posto
        suo. Se il sondaggio nuovo non parte, nessun messaggio: «riprovate con
        /sondaggio» butterebbe i voti tenuti, e la lettura seguente riprova."""
        if self._store.sondaggio_aperto() is not None:
            # aprirlo toglie già la ripresa (`store._apri`): questa è la rete
            self._store.fine_ripresa(self._adesso())
            return
        sondaggio = self._store.sondaggio(ripresa.sondaggio)
        oggi = self._oggi()
        future = [g for g in sondaggio.date if g >= oggi]
        if not future:
            self._store.fine_ripresa(self._adesso(), self._lettere([testi.date_passate()]))
            return
        if self._in_pausa():
            return
        mandato, frase = self._nuovo_sondaggio(future)
        stato = regole.Stato(self._roster, tuple(future), self._store.voti(sondaggio.id))
        self._store.riapri_sondaggio(
            sondaggio.id,
            future,
            mandato.poll_id,
            mandato.messaggio,
            frase,
            regole.dopo(self._store.fatti(sondaggio.id), regole.Ripresa()),
            self._adesso(),
            self._lettere([testi.riapro(stato.votanti, stato.senza_voto)]),
        )

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
                self._avvisa_invio("posta rimandata: %s", e)
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

    def _avvisa_invio(self, messaggio: str, e: TelegramError) -> None:
        """Un invio che non parte: nel log la prima volta, e poi al massimo ogni
        `AVVISO_RIPETUTO`. Un 429 sempre: è uno per pausa, e la pausa conta."""
        if isinstance(e, TelegramTroppeRichieste) or self._da_avvisare(("invio",)):
            log.warning(messaggio, e)

    def _da_avvisare(self, chiave: tuple) -> bool:
        """Per un errore che si ripete a ogni giro: vero la prima volta, e poi al
        massimo ogni `AVVISO_RIPETUTO` per la stessa `chiave`."""
        adesso = self._adesso()
        ultimo = self._avvisati.get(chiave)
        if ultimo is not None and adesso - ultimo < AVVISO_RIPETUTO:
            return False
        self._avvisati[chiave] = adesso
        return True

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
        if sondaggio is None or self._in_chiusura(sondaggio):
            # con la chiusura in sospeso la decisione di chiudere è presa: un
            # annuncio nuovo la contraddirebbe
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
