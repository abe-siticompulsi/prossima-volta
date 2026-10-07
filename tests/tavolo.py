"""Il tavolo delle prove: il giorno di oggi e il roster della spec, con
identificativi Telegram finti."""

from __future__ import annotations

from datetime import date

from prossima.regole import Persona, Roster, Stato, Voto

# Martedì 7 ottobre 2025: la settimana seguente va da lunedì 13 a domenica 19, e
# il 14/10 è un martedì, come negli esempi della spec.
OGGI = date(2025, 10, 7)


def d(scritta: str, anno: int = 2025) -> date:
    """«14/10» → il 14 ottobre 2025."""
    giorno, mese = scritta.split("/")
    return date(anno, int(mese), int(giorno))


GIO = Persona("gio", 100000001, "master", chiude=True)
ABE = Persona("abe", 100000002, "giocatore", chiude=True)
EMI = Persona("emi", 100000003, "giocatore")
SEM = Persona("sem", 100000004, "giocatore")
SESE = Persona("sese", 100000005, "giocatore")
PIPPO = Persona("pippo", 100000006, "giocatore")
ROSTER = Roster((GIO, ABE, EMI, SEM, SESE, PIPPO))
ESTRANEO = 100000099  # vota, ma non è nel roster


def voto(scritto: str) -> Voto:
    """«14/10 16/10»: le date spuntate; «nessuna» aggiunge «Nessuna di queste»;
    «» è il voto tolto."""
    parole = scritto.split()
    return Voto(
        date=frozenset(d(p) for p in parole if p != "nessuna"), nessuna="nessuna" in parole
    )


def stato(date_sondaggio: str = "14/10 16/10", estraneo: str | None = None, **voti: str) -> Stato:
    """Lo stato di un sondaggio sulle `date_sondaggio`, con i voti per soprannome."""
    soprannomi_roster = {p.soprannome for p in ROSTER.persone}
    for soprannome in voti:
        assert soprannome in soprannomi_roster, f"soprannome sconosciuto: {soprannome!r}"
    per_id = {p.telegram_id: voto(voti[p.soprannome]) for p in ROSTER.persone if p.soprannome in voti}
    if estraneo is not None:
        per_id[ESTRANEO] = voto(estraneo)
    return Stato(ROSTER, tuple(d(g) for g in date_sondaggio.split()), per_id)
