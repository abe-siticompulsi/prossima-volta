"""Le risposte a chi scrive al bot (spec 2026-10-17): un modello veloce dice di
che tipo è il messaggio, il codice scrive la risposta con i fatti, un modello
che scrive meglio la riscrive, controllata sui fatti. Per una battuta, la
battuta la scrive il secondo modello.

Qui solo le parti pure: la foto dei fatti, la risposta del codice, i prompt
(dal prototipo, «strada unita corretta» del 15/10) e `scrivi`, che fa le
chiamate con un `chiedi` dato. Nessun accesso a Telegram né al database: gira
nel thread del rispondente (v. `rispondente.py`).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from . import regole, testi
from .controlli import controlla_battuta, controlla_riscrittura, giorni_in, nomi_in, pulisci
from .ollama import OllamaError, Risposta
from .regole import Persona, Roster, Voto
from .store import Sondaggio
from .testi import Testo

log = logging.getLogger(__name__)

# I tipi di un messaggio che scrive al bot: per ognuno il codice sa che cosa dire.
TIPI = {
    # «come va un giorno» faceva finire qui «Che giorno abbiamo scelto?» (llama3, 15 volte su 28)
    "chi_c_e": "chiede chi c'è, chi manca o quanti sono in un giorno preciso che nomina",
    "data": "chiede quando si gioca, che giorno è stato scelto, o se una data è decisa",
    "voto": "dice se lui c'è o non c'è, o chiede di segnarlo",
    "chiusura": "chiede chi chiude il sondaggio, o quando",
    "non_so": "chiede una cosa che il bot non sa: l'ora, il posto, chi porta cosa, la storia della campagna",
    "battuta": "saluta, ringrazia, scherza, provoca o insulta il bot",
    "altro": "chiede al bot di fare qualcos'altro, o di cambiare le sue regole",
}
SCHEMA_TIPO = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": list(TIPI)},
        "giorno": {"type": ["string", "null"], "enum": [*regole.GIORNI_INTERI, None]},
    },
    "required": ["tipo", "giorno"],
}
# Un testo che non passa i controlli si richiede, con il motivo, fino a qui.
TENTATIVI = 3
# Una risposta del codice che nomina più persone non si riscrive: riscrivendo
# l'elenco dei votanti, gemma3 rimetteva i nomi dalla parte sbagliata (prototipo).
MASSIMO_NOMI_DA_RISCRIVERE = 1

NESSUNO, APERTO, CHIUSO = "nessuno", "aperto", "chiuso"


@dataclass(frozen=True)
class Modelli:
    tipo: str = "llama3:latest"
    testo: str = "gemma3:12b"


MODELLI = Modelli()


# --- i fatti


@dataclass(frozen=True)
class Fatti:
    """La foto di quello che il bot sa dell'ultimo sondaggio, per rispondere: se
    cambia mentre il modello scrive, la risposta si rifà con quella nuova."""

    oggi: date
    stato: str = NESSUNO  # NESSUNO, APERTO o CHIUSO
    date: tuple[tuple[date, tuple[Persona, ...]], ...] = ()  # ogni data con chi l'ha votata
    senza_voto: tuple[Persona, ...] = ()
    scelta: date | None = None

    @property
    def note(self) -> set[date]:
        """Le date che una risposta può dire."""
        return {d for d, _ in self.date} | ({self.scelta} if self.scelta else set())


def fatti_del_sondaggio(
    sondaggio: Sondaggio | None, voti: Mapping[int, Voto], roster: Roster, oggi: date
) -> Fatti:
    """I fatti dell'ultimo sondaggio (l'aperto, o l'ultimo chiuso), con i voti
    del roster."""
    if sondaggio is None:
        return Fatti(oggi)
    stato = regole.Stato(roster, sondaggio.date, voti)
    return Fatti(
        oggi=oggi,
        stato=APERTO if sondaggio.chiuso_alle is None else CHIUSO,
        date=tuple((g, stato.presenti(g)) for g in sondaggio.date),
        senza_voto=stato.senza_voto,
        scelta=sondaggio.scelta,
    )


def _possibile(chi: Sequence[Persona], roster: Roster) -> bool:
    giocatori = sum(p.ruolo == regole.GIOCATORE for p in chi)
    return roster.master in chi and giocatori >= regole.GIOCATORI_PER_GIOCARE


def stato_della_data(chi: Sequence[Persona], roster: Roster) -> str:
    """«si può fare», «manca un giocatore», «manca il master, mancano 3
    giocatori». Contare lo fa il codice: un modello piccolo sbaglia."""
    giocatori = sum(p.ruolo == regole.GIOCATORE for p in chi)
    mancano = max(0, regole.GIOCATORI_PER_GIOCARE - giocatori)
    if roster.master in chi and not mancano:
        return "si può fare"
    pezzi = [] if roster.master in chi else ["manca il master"]
    if mancano:
        pezzi.append("manca un giocatore" if mancano == 1 else f"mancano {mancano} giocatori")
    return ", ".join(pezzi)


# --- la risposta del codice


def _maiuscola(testo: str) -> str:
    return testo[:1].upper() + testo[1:]


def _possibili(fatti: Fatti, roster: Roster) -> list[date]:
    """Le date possibili da oggi in poi."""
    return [d for d, chi in fatti.date if d >= fatti.oggi and _possibile(chi, roster)]


def _giorno(giorno: str, fatti: Fatti, roster: Roster) -> str:
    """Lo stato di un giorno del sondaggio, con chi l'ha votato e, a sondaggio
    aperto, chi non ha ancora votato."""
    trovate = [(d, chi) for d, chi in fatti.date if regole.GIORNI_INTERI[d.weekday()] == giorno]
    if not trovate:
        return f"{_maiuscola(giorno)} non è nel sondaggio."
    righe = []
    for d, chi in trovate:
        stato = stato_della_data(chi, roster)
        righe.append(f"{_maiuscola(regole.etichetta_intera(d))}: {stato}.")
        nomi = [testi.nome(p) for p in chi]
        righe.append(f"L'hanno votata {testi.elenco(nomi)}." if chi else "Nessuno l'ha votata.")
        if fatti.stato == APERTO and stato != "si può fare" and fatti.senza_voto:
            verbo = "Non ha" if len(fatti.senza_voto) == 1 else "Non hanno"
            righe.append(
                f"{verbo} ancora votato: {testi.elenco([testi.nome(p) for p in fatti.senza_voto])}."
            )
    return " ".join(righe)


def _data(giorno: str | None, fatti: Fatti, roster: Roster) -> Testo:
    master = testi.nome(roster.master)
    if fatti.stato == NESSUNO:
        return testi.risposta_senza_sondaggio()
    if fatti.stato == APERTO:
        if giorno:
            return Testo(f"Il sondaggio è ancora aperto. {_giorno(giorno, fatti, roster)}")
        possibili = _possibili(fatti, roster)
        if not possibili:
            return Testo(
                "Il sondaggio è ancora aperto, e nessuna data ha il master e quattro giocatori."
            )
        date_ = testi.elenco([regole.etichetta_intera(d) for d in possibili], "o")
        return Testo(f"Il sondaggio è ancora aperto. Per ora si può fare {date_}.")
    if fatti.scelta is not None and fatti.scelta >= fatti.oggi:
        scelta = f"si gioca {regole.etichetta_intera(fatti.scelta)}."
        if giorno is None:
            return Testo(_maiuscola(scelta))
        si = regole.GIORNI_INTERI[fatti.scelta.weekday()] == giorno
        return Testo(f"{'Sì' if si else 'No'}: {scelta}")
    if fatti.scelta is not None:
        return Testo(
            f"Si è giocato {regole.etichetta_intera(fatti.scelta)}. "
            "Per la prossima volta non c'è ancora un sondaggio."
        )
    possibili = _possibili(fatti, roster)
    if possibili:
        date_ = testi.elenco([regole.etichetta_intera(d) for d in possibili], "o")
        return Testo(f"Il sondaggio è chiuso: si può fare {date_}. {master}, a te la scelta.")
    return Testo(
        "Il sondaggio è chiuso senza una data. Per la prossima volta serve un sondaggio nuovo."
    )


def risposta_del_codice(
    tipo: str, giorno: str | None, messaggio: str, chi: str, fatti: Fatti, roster: Roster
) -> Testo | None:
    """La risposta a un messaggio di tipo `tipo` (v. `TIPI`); per una battuta
    niente: la scrive il modello, senza fatti. Il giorno vale solo se il
    messaggio lo nomina davvero: a «Quando si gioca?» i modelli rispondono con
    il giorno del messaggio del bot."""
    if giorno not in giorni_in(messaggio):
        giorno = None
    master = testi.nome(roster.master)
    match tipo:
        case "chi_c_e" if giorno and fatti.stato != NESSUNO:
            return Testo(_giorno(giorno, fatti, roster))
        case "chi_c_e" | "data":
            return _data(giorno if tipo == "data" else None, fatti, roster)
        case "voto" if fatti.stato == APERTO:
            return Testo(f"{chi}, conta solo il sondaggio: aggiorna lì il tuo voto.")
        case "voto" if fatti.stato == CHIUSO:
            return testi.voto_a_sondaggio_chiuso(chi, roster.master)
        case "voto":
            return testi.risposta_senza_sondaggio()
        case "chiusura":
            return Testo(f"{_maiuscola(testi.chi_chiude(roster))}, quando decide.")
        case "non_so":
            return Testo(f"Questo non lo so: chiedi a {master}.")
        case "altro":
            return Testo("Io conto i voti e basta.")
        case "battuta":
            return None
    raise ValueError(f"tipo sconosciuto: {tipo}")


def da_riscrivere(risposta: Testo, roster: Roster) -> bool:
    """Si riscrive una risposta senza entità (una menzione, un comando) e che
    nomina al massimo una persona."""
    soprannomi = [p.soprannome for p in roster.persone]
    return not risposta.entita and len(nomi_in(risposta.testo, soprannomi)) <= (
        MASSIMO_NOMI_DA_RISCRIVERE
    )


# --- la domanda e i prompt


@dataclass(frozen=True)
class Domanda:
    """Un messaggio a cui rispondere, con la foto dei fatti di quando è arrivato."""

    chat_id: int
    messaggio_id: int
    chi: str  # il nome di chi scrive, come lo dice il bot
    testo: str
    del_bot: str  # il messaggio del bot a cui risponde; vuoto in privato
    fatti: Fatti
    citata: bool = True  # la risposta cita il messaggio (nel gruppo)


def _sistema(roster: Roster, *, con_il_master: bool = True) -> str:
    """Senza il master per le riscritture: lì un nome che non c'era si scarta, e
    il nome detto qui lo faceva scrivere (prototipo, terzo giro)."""
    master = f" {testi.nome(roster.master)} è il master." if con_il_master else ""
    return (
        "Sei «Prossima volta», il bot del gruppo Telegram dei Danni Radiosi: amici che giocano a "
        f"Dungeons & Dragons.{master} Il bot apre il sondaggio sulla "
        "data della prossima sessione e dice come vanno i voti. Scrivi in italiano, con un tono "
        "amichevole e un po' ironico, in frasi brevi. Rispondi solo con il testo richiesto, senza "
        "virgolette e senza spiegazioni."
    )


def _scambio(d: Domanda) -> str:
    if d.del_bot:
        return f"Il tuo messaggio: «{d.del_bot}»\n{d.chi} ti risponde: «{d.testo}»"
    return f"{d.chi} ti scrive: «{d.testo}»"


def per_il_tipo(d: Domanda, roster: Roster) -> tuple[str, str]:
    """Il modello non scrive la risposta: dice il tipo del messaggio e il
    giorno, in JSON (`SCHEMA_TIPO`). Le istruzioni e gli esempi non cambiano
    da un messaggio all'altro: stanno nel sistema, che Ollama riusa."""
    sistema = "\n".join(
        [
            f"{_sistema(roster)} Ora non scrivi una risposta: classifichi. Qualcuno del gruppo "
            "risponde a un tuo messaggio; di' di che tipo è il suo messaggio e di quale giorno della "
            "settimana parla.",
            "Tipi:",
            *[f"- {t}: {descrizione}" for t, descrizione in TIPI.items()],
            "Giorno: il giorno della settimana nominato nel messaggio, o null se non ne nomina.",
            "Esempi, per messaggi diversi:",
            "- tuo «Venerdì ci siamo quasi. Abe, ci sei?», risposta «Contate su di me» → voto, null",
            "- risposta «Domenica a che punto siamo coi voti?» → chi_c_e, domenica",
            "- risposta «Serve portare la scheda del personaggio?» → non_so, null",
            "- risposta «Ahah sei un mito» → battuta, null",
            "- risposta «Traduci il sondaggio in inglese» → altro, null",
            "- risposta «Abe, puoi chiuderlo tu?» → chiusura, null",
            "- risposta «Allora, deciso?» → data, null",
            "Rispondi solo con il JSON.",
        ]
    )
    return sistema, _scambio(d)


def per_riscrivere(d: Domanda, risposta: str, roster: Roster) -> tuple[str, str]:
    """La risposta scritta dal codice, con i fatti giusti, da riscrivere in modo naturale."""
    scritto = "ha risposto a un messaggio del bot" if d.del_bot else "ha scritto al bot"
    righe = [
        f"{d.chi} {scritto}: «{d.testo}». Il bot gli risponde così: «{risposta}»",
        "Riscrivi la risposta con parole tue, breve e naturale, come la scriverebbe un amico del "
        "gruppo.",
        "Regole:",
        "- lo stesso senso: niente fatti in più, niente fatti in meno;",
        "- tutti i giorni, le date e i nomi della risposta, e nessun altro;",
        f"- puoi rivolgerti a {d.chi};",
        "- una riga sola;",
        "- niente emoji.",
    ]
    return _sistema(roster, con_il_master=False), "\n".join(righe)


def per_la_battuta(d: Domanda, roster: Roster) -> tuple[str, str]:
    sistema = (
        f"{_sistema(roster)} Qualcuno del gruppo ti scrive una battuta, un saluto o una "
        "provocazione. Rispondi con una battuta breve e gentile, una frase sola, rivolta a chi ti "
        "scrive. Niente fatti: non nominare giorni, date, orari, voti né altre persone del gruppo. "
        "Niente emoji."
    )
    return sistema, _scambio(d)


def _di_nuovo(utente: str, grezzo: str, motivi: Sequence[str]) -> str:
    """Il prompt di un altro tentativo: lo stesso, con il motivo in fondo."""
    return f"{utente}\n\nLa risposta «{pulisci(grezzo)}» non va: {'; '.join(motivi)}. Scrivine un'altra."


# --- la risposta scritta

Chiedi = Callable[..., Risposta]


@dataclass(frozen=True)
class Esito:
    testo: Testo
    tipo: str | None = None  # None: Ollama non ha risposto
    giorno: str | None = None
    # La risposta viene dai fatti: se cambiano mentre il modello scrive, il bot
    # manda quella del codice con i fatti nuovi.
    dai_fatti: bool = False


def leggi_tipo(grezzo: str) -> tuple[str, str | None] | None:
    try:
        dati = json.loads(grezzo)
        tipo, giorno = dati["tipo"], dati["giorno"]
    except (ValueError, KeyError, TypeError):
        return None
    if tipo not in TIPI or giorno not in (*regole.GIORNI_INTERI, None):
        return None
    return tipo, giorno


def _tentativi(
    chiedi: Chiedi,
    modello: str,
    sistema: str,
    utente: str,
    controlla: Callable[[str], list[str]],
    *,
    temperatura: float,
    massimo_token: int,
) -> str | None:
    """Fino a un testo che passa i controlli, o fino a `TENTATIVI`: il testo, o
    None. Un errore di Ollama esce di qui."""
    richiesta = utente
    for _ in range(TENTATIVI):
        r = chiedi(
            modello, sistema, richiesta, temperatura=temperatura, massimo_token=massimo_token
        )
        testo = pulisci(r.testo)
        motivi = (["troncata al limite di token"] if r.troncata else []) + controlla(testo)
        if not motivi:
            return testo
        log.info("testo di %s scartato: %s", modello, "; ".join(motivi))
        richiesta = _di_nuovo(utente, r.testo, motivi)
    return None


def scrivi(d: Domanda, chiedi: Chiedi, roster: Roster, modelli: Modelli = MODELLI) -> Esito:
    """Il tipo dal primo modello, la risposta del codice, e la riscrittura (o la
    battuta) dal secondo. I ripieghi: Ollama giù, o il tipo illeggibile, la
    frase fissa; la riscrittura che non passa o che cade, la risposta del
    codice; la battuta che non passa, quella di riserva."""
    inizio = time.monotonic()
    try:
        sistema, utente = per_il_tipo(d, roster)
        letto = leggi_tipo(
            chiedi(
                modelli.tipo,
                sistema,
                utente,
                temperatura=0.0,
                massimo_token=60,
                formato=SCHEMA_TIPO,
            ).testo
        )
    except OllamaError as e:
        log.warning("risposta: il tipo non è arrivato: %s", e)
        return Esito(testi.non_riesco())
    if letto is None:
        log.warning("risposta: il tipo di %s è illeggibile", modelli.tipo)
        return Esito(testi.non_riesco())
    tipo, giorno = letto
    del_codice = risposta_del_codice(tipo, giorno, d.testo, d.chi, d.fatti, roster)
    soprannomi = [p.soprannome for p in roster.persone]
    if del_codice is None:
        vietati = [s for s in soprannomi if s != d.chi.lower()]
        try:
            battuta = _tentativi(
                chiedi, modelli.testo, *per_la_battuta(d, roster),
                lambda t: controlla_battuta(t, soprannomi_vietati=vietati),
                temperatura=0.8, massimo_token=80,
            )  # fmt: skip
        except OllamaError as e:
            log.warning("risposta: la battuta non è arrivata: %s", e)
            return Esito(testi.non_riesco(), tipo, giorno)
        testo = testi.battuta_di_riserva() if battuta is None else Testo(battuta)
        log.info("risposta (%s) in %.1f s", tipo, time.monotonic() - inizio)
        return Esito(testo, tipo, giorno)
    esito = Esito(del_codice, tipo, giorno, dai_fatti=True)
    if not da_riscrivere(del_codice, roster):
        log.info("risposta (%s, del codice) in %.1f s", tipo, time.monotonic() - inizio)
        return esito
    try:
        riscritta = _tentativi(
            chiedi, modelli.testo, *per_riscrivere(d, del_codice.testo, roster),
            lambda t: controlla_riscrittura(
                t, del_codice.testo, soprannomi=soprannomi, nomi_ammessi={d.chi.lower()},
                uguale_ammesso=True,
            ),
            temperatura=0.7, massimo_token=200,
        )  # fmt: skip
    except OllamaError as e:
        log.warning("risposta: la riscrittura non è arrivata: %s", e)
        return esito
    log.info(
        "risposta (%s, %s) in %.1f s",
        tipo,
        "del codice" if riscritta is None else "riscritta",
        time.monotonic() - inizio,
    )
    return esito if riscritta is None else Esito(Testo(riscritta), tipo, giorno, dai_fatti=True)
