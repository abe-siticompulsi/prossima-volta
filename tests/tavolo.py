"""Il tavolo delle prove: il giorno di oggi e, dal task 2, il roster della spec,
con identificativi Telegram finti."""

from __future__ import annotations

from datetime import date

# Martedì 7 ottobre 2025: la settimana seguente va da lunedì 13 a domenica 19, e
# il 14/10 è un martedì, come negli esempi della spec.
OGGI = date(2025, 10, 7)


def d(scritta: str, anno: int = 2025) -> date:
    """«14/10» → il 14 ottobre 2025."""
    giorno, mese = scritta.split("/")
    return date(anno, int(mese), int(giorno))
