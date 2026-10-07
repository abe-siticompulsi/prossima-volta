"""Le regole del sondaggio. Niente I/O: date, conteggi, annunci.

Tutto ciò che dipende dal giorno lo riceve come argomento (`oggi`, già nel fuso
del party): le prove non dipendono dall'orologio vero. I giorni della
settimana sono quelli di `date.weekday()`: lunedì 0, domenica 6. I testi per
le persone non stanno qui ma in `testi.py`: un rifiuto porta solo i dati che
servono a scriverlo.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
GIORNI_INTERI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MASSIMO_DATE = 10
RIMANDA = "rimanda"

# «14/10», «14/10/2025», e anche con il punto: «14.10», «14.10.2025».
_DATA = re.compile(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{4}))?")


class Rifiuto(ValueError):
    """Il comando non si esegue. Il testo per chi l'ha scritto lo dà `testi.rifiuto`."""


class NonCapisco(Rifiuto):
    def __init__(self, parola: str) -> None:
        super().__init__(parola)
        self.parola = parola  # come l'ha scritta la persona


class DataPassata(Rifiuto):
    def __init__(self, scritta: str) -> None:
        super().__init__(scritta)
        self.scritta = scritta  # «3/10», o «3/10/2024» se l'anno era scritto


class TroppeDate(Rifiuto):
    pass


class NonNelSondaggio(Rifiuto):
    def __init__(self, scritta: str) -> None:
        super().__init__(scritta)
        self.scritta = scritta  # «15/10», o «15/10/2025» se l'anno era scritto


class GiornoAssente(Rifiuto):
    """`/chiudi ven` senza venerdì nel sondaggio."""

    def __init__(self, giorno: int) -> None:
        super().__init__(giorno)
        self.giorno = giorno  # come `date.weekday()`: lunedì 0


class GiornoAmbiguo(Rifiuto):
    """`/chiudi mar` con più di un martedì nel sondaggio: serve la data."""

    def __init__(self, giorno: int, prima_data: date) -> None:
        super().__init__(giorno, prima_data)
        self.giorno = giorno  # come `date.weekday()`: lunedì 0
        self.prima_data = prima_data  # la prima del sondaggio con quel giorno


def breve(giorno: date) -> str:
    """«14/10»: giorno e mese senza zeri iniziali, nel formato italiano."""
    return f"{giorno.day}/{giorno.month}"


def etichetta(giorno: date) -> str:
    """«mar 14/10»: l'opzione del sondaggio, e la data nei messaggi."""
    return f"{GIORNI[giorno.weekday()]} {breve(giorno)}"


def etichetta_intera(giorno: date) -> str:
    """«martedì 14/10»."""
    return f"{GIORNI_INTERI[giorno.weekday()]} {breve(giorno)}"


def lunedi(giorno: date) -> date:
    """Il lunedì della settimana di `giorno`."""
    return giorno - timedelta(days=giorno.weekday())


def lunedi_seguente(giorno: date) -> date:
    """Il lunedì della settimana di calendario dopo quella di `giorno`: di
    domenica è domani."""
    return giorno + timedelta(days=7 - giorno.weekday())


def _scritta(giorno: date, con_anno: bool) -> str:
    return f"{breve(giorno)}/{giorno.year}" if con_anno else breve(giorno)


def _data_senza_anno(giorno: int, mese: int, oggi: date) -> date | None:
    """La data `g/m` più vicina a oggi fra l'anno scorso, quest'anno e il
    prossimo; a pari distanza vince quella che viene.

    In pratica è «la prossima volta che la data arriva, oggi compreso» (il 28/12,
    «2/1» è il 2 gennaio dopo), salvo per una data passata da meno di sei mesi:
    quella resta nel passato, e il comando la rifiuta come passata (il 7/10,
    «3/10» è il 3 ottobre di quattro giorni prima, non quello dell'anno dopo).
    """
    candidate = []
    for anno in (oggi.year - 1, oggi.year, oggi.year + 1):
        try:
            candidate.append(date(anno, mese, giorno))
        except ValueError:
            continue
    if not candidate:
        return None
    return min(candidate, key=lambda d: (abs((d - oggi).days), d < oggi))


def _data_della_parola(parola: str, oggi: date) -> date:
    minuscola = parola.lower()
    if minuscola in GIORNI:
        return lunedi_seguente(oggi) + timedelta(days=GIORNI.index(minuscola))
    trovata = _DATA.fullmatch(parola)
    if trovata is None:
        raise NonCapisco(parola)
    g, m, a = trovata.groups()
    if a is None:
        giorno = _data_senza_anno(int(g), int(m), oggi)
    else:
        try:
            giorno = date(int(a), int(m), int(g))
        except ValueError:
            giorno = None
    if giorno is None:
        raise NonCapisco(parola)
    if giorno < oggi:
        raise DataPassata(_scritta(giorno, a is not None))
    return giorno


def date_del_comando(parole: Sequence[str], oggi: date) -> list[date]:
    """Le date di `/sondaggio`. Senza parole, i sette giorni della settimana
    seguente; con giorni (`lun` … `dom`) quei giorni della settimana seguente;
    con date, quelle date. Giorni e date si mescolano; il risultato è ordinato,
    senza doppioni. La prima parola che non va ferma tutto."""
    if not parole:
        lunedi = lunedi_seguente(oggi)
        return [lunedi + timedelta(days=i) for i in range(7)]
    scelte = {_data_della_parola(parola, oggi) for parola in parole}
    if len(scelte) > MASSIMO_DATE:
        raise TroppeDate()
    return sorted(scelte)


def data_da_chiudere(parola: str, date_sondaggio: Sequence[date]) -> date:
    """La data che `/chiudi <parola>` tiene: una data del sondaggio (`g/m`,
    `g/m/aaaa`, o con il punto), o il suo giorno della settimana, se nel
    sondaggio ce n'è uno solo."""
    minuscola = parola.lower()
    if minuscola in GIORNI:
        giorno = GIORNI.index(minuscola)
        trovate = sorted(d for d in date_sondaggio if d.weekday() == giorno)
        if not trovate:
            raise GiornoAssente(giorno)
        if len(trovate) > 1:
            raise GiornoAmbiguo(giorno, trovate[0])
        return trovate[0]
    trovata = _DATA.fullmatch(parola)
    if trovata is None:
        raise NonCapisco(parola)
    g, m = int(trovata[1]), int(trovata[2])
    a = None if trovata[3] is None else int(trovata[3])
    for giorno in date_sondaggio:
        if (giorno.day, giorno.month) == (g, m) and a in (None, giorno.year):
            return giorno
    raise NonNelSondaggio(f"{g}/{m}" if a is None else f"{g}/{m}/{a}")


def date_rimandate(date_sondaggio: Sequence[date]) -> list[date]:
    """Le date di `/chiudi rimanda`: gli stessi giorni della settimana, nella
    settimana dopo quella dell'ultima data."""
    lunedi = lunedi_seguente(max(date_sondaggio))
    giorni = sorted({d.weekday() for d in date_sondaggio})
    return [lunedi + timedelta(days=g) for g in giorni]

# --- chi conta, e le regole delle date (§3.3 e §3.4 della spec)

GIOCATORI_PER_GIOCARE = 4
GIOCATORI_PER_QUASI = 3
VOTANTI_PER_QUASI = 4
# Telegram conserva gli aggiornamenti per 24 ore: un'ora di margine.
BUIO = timedelta(hours=23)

MASTER = "master"
GIOCATORE = "giocatore"
RUOLI = (MASTER, GIOCATORE)


@dataclass(frozen=True)
class Persona:
    soprannome: str
    telegram_id: int
    ruolo: str
    chiude: bool = False


@dataclass(frozen=True)
class Roster:
    """Le persone che contano, nell'ordine del file. `config.py` garantisce un
    solo master e soprannomi e identificativi unici."""

    persone: tuple[Persona, ...]

    @property
    def master(self) -> Persona:
        return next(p for p in self.persone if p.ruolo == MASTER)

    @property
    def giocatori(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.persone if p.ruolo == GIOCATORE)

    @property
    def chi_chiude(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.persone if p.chiude)

    def per_id(self, telegram_id: int | None) -> Persona | None:
        return next((p for p in self.persone if p.telegram_id == telegram_id), None)


@dataclass(frozen=True)
class Voto:
    """Le scelte di una persona: le date spuntate e «Nessuna di queste»."""

    date: frozenset[date] = frozenset()
    nessuna: bool = False

    @property
    def dato(self) -> bool:
        """Ha votato: una risposta non vuota, anche solo «Nessuna»."""
        return bool(self.date) or self.nessuna


def voto_da_opzioni(date_sondaggio: Sequence[date], opzioni: Iterable[int]) -> Voto:
    """Le opzioni di un `poll_answer` (indici da 0) come voto: prima le date,
    in fondo «Nessuna». Un indice fuori dal sondaggio non conta."""
    scelte = set(opzioni)
    return Voto(
        date=frozenset(g for i, g in enumerate(date_sondaggio) if i in scelte),
        nessuna=len(date_sondaggio) in scelte,
    )


def conteggi_per_opzione(date_sondaggio: Sequence[date], voti: Iterable[Voto]) -> list[int]:
    """Quanti hanno spuntato ogni opzione, nell'ordine del sondaggio e con
    «Nessuna» in fondo: la forma dei conteggi che restituisce `stopPoll`."""
    voti = list(voti)
    return [sum(g in v.date for v in voti) for g in date_sondaggio] + [
        sum(v.nessuna for v in voti)
    ]


@dataclass(frozen=True)
class Stato:
    """Un sondaggio come lo vedono le regole: le sue date e i voti registrati,
    per identificativo Telegram, anche di chi non è nel roster."""

    roster: Roster
    date: tuple[date, ...]
    voti: Mapping[int, Voto]

    def voto(self, persona: Persona) -> Voto:
        return self.voti.get(persona.telegram_id, Voto())

    @property
    def votanti(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if self.voto(p).dato)

    @property
    def senza_voto(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if not self.voto(p).dato)

    def presenti(self, giorno: date) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if giorno in self.voto(p).date)


@dataclass(frozen=True)
class Conteggio:
    giorno: date
    presenti: tuple[Persona, ...]  # nell'ordine del roster
    master_presente: bool
    master_ha_votato: bool
    giocatori_presenti: int
    giocatori_senza_voto: int
    votanti: int  # persone del roster che hanno votato

    @property
    def possibile(self) -> bool:
        return self.master_presente and self.giocatori_presenti >= GIOCATORI_PER_GIOCARE

    @property
    def quasi(self) -> bool:
        return (
            self.votanti >= VOTANTI_PER_QUASI
            and self.master_presente
            and self.giocatori_presenti == GIOCATORI_PER_QUASI
        )

    @property
    def fuori(self) -> bool:
        return (self.master_ha_votato and not self.master_presente) or (
            self.giocatori_presenti + self.giocatori_senza_voto < GIOCATORI_PER_GIOCARE
        )

    @property
    def con_tre(self) -> bool:
        """Il master e almeno tre giocatori: la data che si terrebbe giocando in tre."""
        return self.master_presente and self.giocatori_presenti >= GIOCATORI_PER_QUASI


def conta(stato: Stato, giorno: date) -> Conteggio:
    presenti = stato.presenti(giorno)
    master = stato.roster.master
    giocatori = stato.roster.giocatori
    return Conteggio(
        giorno=giorno,
        presenti=presenti,
        master_presente=master in presenti,
        master_ha_votato=stato.voto(master).dato,
        giocatori_presenti=sum(p in presenti for p in giocatori),
        giocatori_senza_voto=sum(not stato.voto(p).dato for p in giocatori),
        votanti=len(stato.votanti),
    )


def possibili(stato: Stato) -> list[date]:
    return [g for g in stato.date if conta(stato, g).possibile]


def impossibile(stato: Stato) -> bool:
    """Nessuna data possibile: tutte le date sono fuori."""
    return bool(stato.date) and all(conta(stato, g).fuori for g in stato.date)


# --- gli annunci (§3.5)


@dataclass(frozen=True)
class Quasi:
    giorno: date
    presenti: tuple[Persona, ...]
    senza_voto: tuple[Persona, ...]


@dataclass(frozen=True)
class Possibile:
    giorno: date
    presenti: tuple[Persona, ...]


@dataclass(frozen=True)
class NonPiu:
    giorno: date
    andati_via: tuple[Persona, ...]  # vuoto: il bot non sa chi


@dataclass(frozen=True)
class Impossibile:
    con_tre: tuple[tuple[date, tuple[Persona, ...]], ...]  # le date con il master e tre giocatori


Annuncio = Quasi | Possibile | NonPiu | Impossibile


@dataclass(frozen=True)
class Rientro:
    """Dopo «impossibile» una data è tornata in gioco. Non si annuncia, ma si
    registra: il prossimo «impossibile» si potrà dire di nuovo."""


@dataclass(frozen=True)
class Ripresa:
    """Dopo il buio (§3.8) il bot non sa più chi c'era quando ha annunciato
    «possibile»: un «non più possibile» dirà che non ci sono più il master e
    quattro giocatori, senza nomi."""


Evento = Annuncio | Rientro | Ripresa


@dataclass(frozen=True)
class Fatti:
    """Gli annunci già fatti per un sondaggio, come contano per i prossimi."""

    quasi: frozenset[date] = frozenset()
    # Le date annunciate come possibili e non ancora come «non più»: chi c'era
    # al momento dell'annuncio, o None se il bot non lo sa più.
    possibili: Mapping[date, frozenset[int] | None] = field(default_factory=dict)
    impossibile: bool = False


def dopo(fatti: Fatti, evento: Evento) -> Fatti:
    """I fatti dopo un annuncio accettato da Telegram, o dopo un evento muto."""
    match evento:
        case Quasi():
            return replace(fatti, quasi=fatti.quasi | {evento.giorno})
        case Possibile():
            presenti = frozenset(p.telegram_id for p in evento.presenti)
            return replace(fatti, possibili={**fatti.possibili, evento.giorno: presenti})
        case NonPiu():
            restano = {g: p for g, p in fatti.possibili.items() if g != evento.giorno}
            return replace(fatti, possibili=restano)
        case Impossibile():
            return replace(fatti, impossibile=True)
        case Rientro():
            return replace(fatti, impossibile=False)
        case Ripresa():
            return replace(fatti, possibili=dict.fromkeys(fatti.possibili))
    raise TypeError(f"evento sconosciuto: {evento!r}")


def annunci_da_fare(stato: Stato, fatti: Fatti) -> list[Annuncio]:
    """Gli annunci che lo stato chiede e che non sono ancora stati fatti, data
    per data e con «impossibile» in fondo. Pura: rifarla non ripete niente."""
    annunci: list[Annuncio] = []
    for giorno in stato.date:
        c = conta(stato, giorno)
        if giorno in fatti.possibili and not c.possibile:
            annunci.append(NonPiu(giorno, _andati_via(stato, fatti.possibili[giorno], c)))
        if c.possibile and giorno not in fatti.possibili:
            annunci.append(Possibile(giorno, c.presenti))
        if c.quasi and giorno not in fatti.quasi:
            annunci.append(Quasi(giorno, c.presenti, stato.senza_voto))
    if impossibile(stato) and not fatti.impossibile:
        conteggi = [conta(stato, g) for g in stato.date]
        annunci.append(Impossibile(tuple((c.giorno, c.presenti) for c in conteggi if c.con_tre)))
    return annunci


def _andati_via(
    stato: Stato, prima: frozenset[int] | None, adesso: Conteggio
) -> tuple[Persona, ...]:
    if prima is None:
        return ()
    restano = {p.telegram_id for p in adesso.presenti}
    return tuple(
        p for p in stato.roster.persone if p.telegram_id in prima and p.telegram_id not in restano
    )


def rientrato(stato: Stato, fatti: Fatti) -> bool:
    """«Impossibile» è stato annunciato, e adesso una data è tornata in gioco."""
    return fatti.impossibile and not impossibile(stato)


def al_buio(precedente: datetime | None, adesso: datetime) -> bool:
    """La lettura di adesso arriva più di 23 ore dopo la precedente riuscita."""
    return precedente is not None and adesso - precedente > BUIO
