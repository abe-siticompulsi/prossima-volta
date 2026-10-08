"""Lo sblocco a mano, `prossima sblocca`, a servizio fermo: per quando il bot
resta bloccato su una chiusura in sospeso o su una ripresa che non va avanti
nemmeno dopo un riavvio (v. docs/messa-in-produzione.md, «Se il bot resta
bloccato»).

Toglie la chiusura in sospeso e la ripresa e, se una delle due era del
sondaggio aperto, chiude nel database quel sondaggio. Su Telegram il sondaggio
resta com'è, e il bot ne ignora i voti: chi vuole un sondaggio nuovo lo lancia
con `/sondaggio`. Un sondaggio aperto senza niente in sospeso non si tocca:
il comando si può provare senza rischi. Nel gruppo non scrive niente.
Restituisce, in parole, che cosa ha tolto: `principale` lo scrive nel log.
"""

from __future__ import annotations

from datetime import datetime

from . import regole
from .chiusura import argomenti_di_chiudi
from .store import RIAPRIRE, Store


def sblocca(store: Store, adesso: datetime) -> list[str]:
    """Toglie quello che tiene bloccato il bot; una riga per ogni cosa tolta."""
    fatto = []
    bloccati = set()  # i sondaggi della chiusura in sospeso e della ripresa
    sospesa = store.chiusura_sospesa()
    if sospesa is not None:
        store.togli_chiusura_sospesa()
        bloccati.add(sospesa.sondaggio)
        comando = " ".join(["/chiudi", *argomenti_di_chiudi(sospesa)])
        fatto.append(f"tolta la chiusura in sospeso del sondaggio {sospesa.sondaggio} ({comando})")
    ripresa = store.ripresa()
    if ripresa is not None:
        store.fine_ripresa(adesso)
        bloccati.add(ripresa.sondaggio)
        riga = f"tolta la ripresa del sondaggio {ripresa.sondaggio}, nella fase «{ripresa.fase}»"
        if ripresa.fase == RIAPRIRE:
            riga += ": il sondaggio, già fermo, resta chiuso"
        fatto.append(riga)
    aperto = store.sondaggio_aperto()
    if aperto is not None and aperto.id in bloccati:
        store.chiudi_sondaggio(aperto.id, adesso)
        date_ = ", ".join(regole.etichetta(g) for g in aperto.date)
        fatto.append(
            f"chiuso nel database il sondaggio {aperto.id} ({date_}): "
            "su Telegram resta com'è, e il bot ne ignora i voti"
        )
    return fatto
