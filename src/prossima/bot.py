"""Il bot: smista gli aggiornamenti di Telegram e collega le parti.

Un solo processo e un solo filo: nessuna gara fra un voto e un comando.

Qui: il giro (`ricevi`, `manda`), lo smistamento, `/sondaggio`, i voti (anche
quelli per un sondaggio sconosciuto) e gli annunci. Le altre parti, ognuna con
le sue strutture in memoria, che si toccano solo attraverso i loro metodi:
- `chiusura.py`: `/chiudi`, la chiusura in sospeso e il suo completamento;
- `ripresa.py`: la ripresa dopo il buio (§3.8);
- `invio.py`: ogni chiamata che scrive su Telegram, la pausa dopo un 429, la
  posta in uscita, il sondaggio nuovo.
Le dipendenze vanno in un senso solo: bot → chiusura → ripresa → invio (e il
bot usa anche la ripresa e l'invio).

Che cosa parte verso Telegram, e quando:
- un sondaggio (`sendPoll`) parte subito: se Telegram non lo conferma, nel
  database non c'è, il bot risponde che Telegram non l'ha confermato, e il
  comando si riscrive;
- la chiusura (`stopPoll`) parte subito: se Telegram non la conferma resta in
  sospeso, il bot lo dice, e la ritenta a ogni giro (`manda`) finché Telegram
  risponde (v. `chiusura.py`);
- gli annunci (quasi, possibile, non più possibile, impossibile) si calcolano
  dallo stato a ogni giro (`manda`), solo sulle date da oggi in poi, e
  contano come fatti solo dopo che Telegram li ha accettati; con la chiusura
  in sospeso non ce ne sono. Uno rifiutato (4xx) va nel log come errore, non
  ferma gli altri, e non si riprova fino al prossimo avvio;
- ogni altro messaggio passa dalla posta in uscita del database, in ordine
  (v. `invio.py`).
Dopo un 429 niente parte prima di `retry_after`; nel frattempo `manda` non
prova nemmeno.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, tzinfo

from . import regole, testi
from .chiusura import Chiusure, argomenti_di_chiudi
from .invio import Invio, forse_arrivata, livello
from .regole import Roster
from .ripresa import Ripresa
from .store import Sondaggio, Store
from .telegram import MASSIMO_AGGIORNAMENTI, TelegramError, TelegramRifiuto

log = logging.getLogger(__name__)

COMANDI = (
    ("sondaggio", "Sondaggio per la prossima volta"),
    ("chiudi", "Chiude il sondaggio"),
    ("aiuto", "Come si usano i comandi"),
)
# Gli annunci aspettano che i voti si assestino (spec §3.5).
ATTESA_ANNUNCI = timedelta(minutes=2)
# Un voto per un sondaggio sconosciuto si dice nel gruppo solo se un sondaggio
# non confermato da Telegram è di questi ultimi giorni.
NON_CONFERMATO_DI_RECENTE = timedelta(days=7)


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
        frasi: Sequence[str] = testi.FRASI_NESSUNA,
        domanda: str = testi.DOMANDA,
        giorni: Sequence[int] = regole.GIORNI_DI_SEMPRE,
        attesa_annunci: timedelta = ATTESA_ANNUNCI,
    ) -> None:
        self._store = store
        self._roster = roster
        self._gruppo = gruppo
        self._nome = nome
        self._fuso = fuso
        self._giorni = tuple(giorni)
        self._attesa_annunci = attesa_annunci
        # In memoria: dopo un riavvio gli annunci dovuti partono subito.
        self._ultimo_voto: datetime | None = None
        self._adesso = adesso
        self._invio = Invio(
            telegram=telegram,
            store=store,
            gruppo=gruppo,
            adesso=adesso,
            caso=caso,
            frasi=frasi,
            domanda=domanda,
        )
        self._ripresa = Ripresa(
            invio=self._invio, store=store, roster=roster, fuso=fuso, adesso=adesso
        )
        self._chiusure = Chiusure(
            ripresa=self._ripresa,
            invio=self._invio,
            store=store,
            roster=roster,
            nome=nome,
            fuso=fuso,
            adesso=adesso,
        )
        # Gli annunci che Telegram ha rifiutato (4xx) in questo processo, già
        # scritti nel log: si saltano fino al prossimo avvio.
        self._annunci_rifiutati: set[tuple[int, tuple[regole.Annuncio, ...]]] = set()
        # La prima lettura dopo il buio, se il suo lotto era pieno: la ripresa
        # aspetta di aver gestito gli arretrati, ma il buio è finito lì.
        self._fine_del_buio: datetime | None = None

    # --- il giro

    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`, anche vuoto. Si chiama solo dopo una
        lettura riuscita: il momento di adesso diventa quello dell'ultima
        lettura, e da lì si conta il buio. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii. Dopo più di 23 ore senza letture comincia la ripresa (§3.8), e a
        ogni lettura una ripresa in corso fa i passi che può.

        Un lotto pieno dopo il buio lascia forse degli arretrati: la ripresa
        aspetta il primo lotto che non è pieno, così i voti arrivati nel buio
        contano nel confronto, e fino a lì la lettura non si segna (il buio
        resta). Il buio è finito con la prima lettura."""
        ora = self._adesso()
        precedente = self._store.ultima_lettura()
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        if not regole.al_buio(precedente, ora):
            self._store.segna_lettura(ora)
        elif len(aggiornamenti) >= MASSIMO_AGGIORNAMENTI:
            if self._fine_del_buio is None:
                self._fine_del_buio = ora
        else:
            fine = self._fine_del_buio or ora
            try:
                self._ripresa.inizia(precedente, fine)
                self._fine_del_buio = None
            except Exception:
                # la lettura non è segnata: la prossima vede di nuovo il buio
                log.exception("ripresa dopo il buio non cominciata")
        self._ripresa.continua()
        self.manda()

    def gestisci(self, aggiornamento: dict) -> None:
        if "poll_answer" in aggiornamento:
            self._voto(aggiornamento["poll_answer"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])
        elif "callback_query" in aggiornamento:
            self._tocco(aggiornamento["callback_query"])

    def manda(self) -> None:
        """La posta in uscita, in ordine; lo stop di una chiusura in sospeso (e,
        se riesce, la posta che la dice); gli annunci del sondaggio aperto, se
        non è in chiusura. Quello che non parte riparte al giro seguente.
        Durante la pausa chiesta da un 429 non si prova nemmeno: il 429 è già
        nel log."""
        if self._invio.in_pausa():
            return
        try:
            self._invio.manda_posta()
            if self._chiusure.riprova():
                self._invio.manda_posta()
            self._togli_bottoni_superati()
            self._manda_annunci()
        except TelegramError as e:
            self._invio.avvisa("invio rimandato al giro seguente: %s", e)

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
            self._chiusure.chiudi(messaggio, parole[1:])
        elif comando == "aiuto":
            self._invio.accoda(
                testi.aiuto(self._nome, self._roster, self._giorni),
                risposta_a=messaggio["message_id"],
            )

    def _tocco(self, tocco: dict) -> None:
        """Un tocco su un bottone di «impossibile» (§3.10): per chi può chiudere,
        sul sondaggio del bottone, vale come `/chiudi <argomento>` della stessa
        persona, con le risposte al messaggio dei bottoni."""
        messaggio = tocco.get("message") or {}
        azione, _, resto = (tocco.get("data") or "").partition(":")
        sondaggio_id, _, argomento = resto.partition(":")
        if (
            messaggio.get("chat", {}).get("id") != self._gruppo
            or azione != "chiudi"
            or not (sondaggio_id.isascii() and sondaggio_id.isdigit())
            or not argomento
        ):
            self._invio.rispondi_al_tocco(tocco["id"])
            return
        chi = self._roster.per_id(tocco.get("from", {}).get("id"))
        if chi is None or not chi.chiude:
            self._invio.rispondi_al_tocco(tocco["id"], testi.solo_chi_chiude(self._roster).testo)
            return
        sondaggio = self._store.sondaggio_aperto() or self._ripresa.in_riapertura()
        if sondaggio is None or sondaggio.id != int(sondaggio_id):
            self._invio.rispondi_al_tocco(tocco["id"], testi.gia_chiuso_al_tocco().testo)
            self._invio.togli_bottoni(messaggio["message_id"])
            return
        if self._store.messaggio_con_bottoni() != (sondaggio.id, messaggio["message_id"]):
            # un «impossibile» più recente ha i bottoni che valgono
            self._invio.rispondi_al_tocco(tocco["id"], testi.bottoni_vecchi().testo)
            self._invio.togli_bottoni(messaggio["message_id"])
            return
        self._invio.rispondi_al_tocco(tocco["id"])
        comando = {
            "message_id": messaggio["message_id"],
            "from": tocco["from"],
            "chat": messaggio["chat"],
            "tocco": True,
        }
        self._chiusure.chiudi(comando, [argomento])
        # i bottoni li toglie `manda`, appena il sondaggio non è più aperto

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
            guasta = self._chiusure.guasta(aperto)
            if guasta is not None:
                # lo stop può essere passato: è il completamento che è fallito
                risposta = testi.chiusura_non_completata(self._nome, argomenti_di_chiudi(guasta))
            elif self._ripresa.guasta(aperto):
                # lo stop della ripresa è partito, ed è fallito quello che veniva dopo
                risposta = testi.chiusura_non_completata(self._nome, [])
            else:
                risposta = testi.non_ancora_chiuso()
            self._invio.accoda(risposta, risposta_a=messaggio["message_id"])
            return
        if aperto is not None:
            self._invio.accoda(testi.gia_aperto(self._nome), risposta_a=aperto.messaggio)
            return
        try:
            date_ = regole.date_del_comando(parole, self._oggi(), self._giorni)
        except regole.Rifiuto as r:
            self._invio.accoda(
                testi.rifiuto(r, self._nome, self._giorni), risposta_a=messaggio["message_id"]
            )
            return
        try:
            mandato, frase = self._invio.nuovo_sondaggio(date_)
        except TelegramError as e:
            # rete, 5xx, un rifiuto, la pausa di un 429: la risposta al comando
            # è vera in ogni caso, anche se il sondaggio è partito e la risposta
            # si è persa; il tentativo si ricorda solo se può essere partito
            log.log(livello(e), "sondaggio non confermato: %s", e)
            risposta = testi.sondaggio_non_confermato(self._nome, parole)
            comando = messaggio["message_id"]
            if forse_arrivata(e):
                lettera = self._invio.lettera(risposta, risposta_a=comando)
                self._store.segna_non_confermato(self._adesso(), parole, [lettera])
            else:
                self._invio.accoda(risposta, risposta_a=comando)
            return
        self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())

    def _voto(self, risposta: dict) -> None:
        poll_id = risposta.get("poll_id")
        sondaggio = self._store.sondaggio_aperto()
        utente = risposta.get("user")
        opzioni = risposta.get("option_ids", [])
        # senza un sondaggio aperto, quello che la ripresa ha fermato e riaprirà
        fermo = self._ripresa.in_riapertura() if sondaggio is None else None
        if sondaggio is not None and poll_id == sondaggio.poll_id:
            if utente is None:
                return
            voto = regole.voto_da_opzioni(sondaggio.date, opzioni)
            self._store.registra_voto(sondaggio.id, utente["id"], poll_id, voto, self._adesso())
            self._voto_registrato(utente["id"])
        elif fermo is not None and poll_id == fermo.poll_id:
            # dato poco prima dello stop, arrivato mentre la riapertura aspetta: si
            # tiene, come gli altri voti, per il sondaggio riaperto
            if utente is None:
                return
            voto = regole.voto_da_opzioni(fermo.date, opzioni)
            self._store.registra_voto(fermo.id, utente["id"], poll_id, voto, self._adesso())
            self._voto_registrato(utente["id"])
        elif sondaggio is not None and sondaggio.poll_prima is not None and poll_id == sondaggio.poll_prima:
            # Dato nel sondaggio di prima della ripresa, poco prima dello stop, e
            # arrivato dopo la riapertura: vale se la persona non ha votato nel
            # sondaggio di adesso. Le opzioni sono quelle di prima.
            if utente is None:
                return
            voto = regole.voto_da_opzioni(sondaggio.date_prima, opzioni)
            if self._store.registra_voto_tardivo(
                sondaggio.id, utente["id"], poll_id, voto, self._adesso(), sondaggio.poll_id
            ):
                self._voto_registrato(utente["id"])
        elif not self._store.poll_conosciuto(poll_id):
            self._voto_sconosciuto(poll_id)
        # un voto per un sondaggio che il bot conosce, ma non è aperto: si ignora

    def _voto_registrato(self, utente_id: int) -> None:
        """Gli annunci aspettano 2 minuti dall'ultimo voto registrato di una
        persona del roster: gli altri voti non cambiano nessun annuncio."""
        if self._roster.per_id(utente_id) is not None:
            self._ultimo_voto = self._adesso()

    def _voto_sconosciuto(self, poll_id: str) -> None:
        """Telegram manda al bot solo i voti dei sondaggi del bot: questo è un
        sondaggio che il bot ha mandato senza registrarlo (una risposta persa),
        o uno del piano reale, nella chat privata di Alberto. Nel gruppo lo si
        dice una volta per sondaggio, e solo se c'è stato da poco un sondaggio
        che Telegram non ha confermato: i voti del piano reale restano nel log.
        Con un sondaggio aperto l'avviso risponde a quello: è lì che si vota.
        Durante tutta la ripresa (fermare e riaprire), solo il log."""
        log.warning("voto per un sondaggio sconosciuto: %s", poll_id)
        if self._store.ripresa() is not None:
            # «Rilanciatelo» farebbe buttare i voti che la ripresa tiene, e «votate
            # qui» manderebbe a votare un sondaggio che sta per fermarsi
            return
        tentativo = self._store.ultimo_non_confermato()
        adesso = self._adesso()
        if tentativo is None or adesso - tentativo.alle > NON_CONFERMATO_DI_RECENTE:
            return
        aperto = self._store.sondaggio_aperto()
        if aperto is None or self._in_chiusura(aperto):
            avviso = self._invio.lettera(testi.voto_sconosciuto(self._nome, tentativo.argomenti))
        else:
            avviso = self._invio.lettera(
                testi.voto_sconosciuto(self._nome, con_sondaggio_aperto=True),
                risposta_a=aperto.messaggio,
            )
        self._store.avvisa_voto_sconosciuto(poll_id, adesso, [avviso])

    # --- gli annunci

    def _manda_annunci(self) -> None:
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None or self._in_chiusura(sondaggio):
            # con la chiusura in sospeso la decisione di chiudere è presa: un
            # annuncio nuovo la contraddirebbe
            return
        if (
            self._ultimo_voto is not None
            and self._adesso() - self._ultimo_voto < self._attesa_annunci
        ):
            return  # i voti non si sono ancora assestati: si dice com'è dopo
        stato = self._stato(sondaggio)
        fatti = self._store.fatti(sondaggio.id)
        if regole.rientrato(stato, fatti):
            fatti = regole.dopo(fatti, regole.Rientro())
            self._store.salva_fatti(sondaggio.id, fatti)
            self._togli_bottoni()  # una data è tornata in gioco: non c'è più da decidere
        for gruppo in _per_tipo(regole.annunci_da_fare(stato, fatti)):
            if (sondaggio.id, gruppo) in self._annunci_rifiutati:
                continue
            testo = testi.annunci(gruppo, self._roster, self._nome, sondaggio.date, sondaggio.id)
            try:
                messaggio = self._invio.scrivi(testo)
            except TelegramRifiuto as e:
                # non è fatto, e lo stesso testo avrebbe lo stesso rifiuto: si
                # salta fino al prossimo avvio; gli altri partono
                log.error("annuncio rifiutato da Telegram: %s (%r)", e, testo.testo)
                self._annunci_rifiutati.add((sondaggio.id, gruppo))
                continue
            for annuncio in gruppo:
                fatti = regole.dopo(fatti, annuncio)
            self._store.salva_fatti(sondaggio.id, fatti)
            if testo.bottoni:
                self._togli_bottoni()  # quelli di un «impossibile» di prima
                self._store.segna_messaggio_con_bottoni(sondaggio.id, messaggio)

    def _togli_bottoni(self) -> None:
        """Toglie i bottoni dell'ultimo «impossibile», se ci sono: al meglio."""
        con_bottoni = self._store.messaggio_con_bottoni()
        if con_bottoni is not None:
            self._invio.togli_bottoni(con_bottoni[1])
            self._store.togli_messaggio_con_bottoni()

    def _togli_bottoni_superati(self) -> None:
        """Il sondaggio dei bottoni non è più aperto (chiuso, rimandato): via i
        bottoni, che non porterebbero a niente."""
        con_bottoni = self._store.messaggio_con_bottoni()
        if con_bottoni is None:
            return
        aperto = self._store.sondaggio_aperto() or self._ripresa.in_riapertura()
        if aperto is None or aperto.id != con_bottoni[0]:
            self._togli_bottoni()

    # --- i pezzi

    def _in_chiusura(self, sondaggio: Sondaggio) -> bool:
        """Il sondaggio è aperto nel database ma forse già fermo su Telegram: una
        chiusura in sospeso, o una ripresa che ha mandato lo stop e non ne ha
        avuto conferma. Non si dice che è aperto, e niente annunci."""
        return self._chiusure.in_sospeso(sondaggio) or self._ripresa.stop_partito(sondaggio)

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()

    def _stato(self, sondaggio: Sondaggio) -> regole.Stato:
        """Lo stato per gli annunci: solo le date da oggi in poi. Una data
        passata non si annuncia più: né quasi, né possibile, né «non più
        possibile» (un «possibile» su una data che passa resta com'è), né fra
        le date di «impossibile»."""
        oggi = self._oggi()
        future = tuple(g for g in sondaggio.date if g >= oggi)
        return regole.Stato(self._roster, future, self._store.voti(sondaggio.id))


def _per_tipo(annunci: Sequence[regole.Annuncio]) -> list[tuple[regole.Annuncio, ...]]:
    """Gli annunci dello stesso tipo, insieme: `annunci_da_fare` li dà già in
    ordine di tipo, quindi bastano quelli consecutivi."""
    gruppi: list[list[regole.Annuncio]] = []
    for annuncio in annunci:
        if gruppi and type(gruppi[-1][0]) is type(annuncio):
            gruppi[-1].append(annuncio)
        else:
            gruppi.append([annuncio])
    return [tuple(g) for g in gruppi]
