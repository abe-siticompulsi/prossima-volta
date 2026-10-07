"""Le regole del sondaggio. Niente I/O: date, conteggi, annunci.

Tutto ciò che dipende dal giorno lo riceve come argomento (`oggi`, già nel fuso
del party): le prove non dipendono dall'orologio vero. I giorni della
settimana sono quelli di `date.weekday()`: lunedì 0, domenica 6. I testi per
le persone non stanno qui ma in `testi.py`: un rifiuto porta solo i dati che
servono a scriverlo.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, timedelta

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
        self.scritta = scritta  # «15/10», o il giorno della settimana: «ven»


def breve(giorno: date) -> str:
    """«14/10»: giorno e mese senza zeri iniziali, nel formato italiano."""
    return f"{giorno.day}/{giorno.month}"


def etichetta(giorno: date) -> str:
    """«mar 14/10»: l'opzione del sondaggio, e la data nei messaggi."""
    return f"{GIORNI[giorno.weekday()]} {breve(giorno)}"


def etichetta_intera(giorno: date) -> str:
    """«martedì 14/10»."""
    return f"{GIORNI_INTERI[giorno.weekday()]} {breve(giorno)}"


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
        trovate = [d for d in date_sondaggio if GIORNI[d.weekday()] == minuscola]
        if not trovate:
            raise NonNelSondaggio(minuscola)
        if len(trovate) > 1:
            raise NonCapisco(parola)
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
