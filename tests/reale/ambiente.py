"""Le variabili del piano reale.

Una variabile mancante fa saltare il test, e il messaggio dice quale contratto
resta non verificato. Un salto non è un successo: il piano reale è verde solo
quando non salta niente (`pytest -rs` elenca i salti con il loro motivo).
"""

import os

import pytest

# Quello che il servizio legge per partire (`prossima.config.da_ambiente`),
# senza `PV_FUSO`, che ha un valore predefinito.
CONFIGURAZIONE = ("PV_BOT_TOKEN", "PV_GRUPPO", "PV_ROSTER", "PV_DB", "PV_BATTITO")


def richiesta(nome: str, non_verificato: str | None = None) -> str:
    """Il valore della variabile `nome`; se manca (o è vuota) il test salta,
    dicendo che cosa resta non verificato: `non_verificato`, o il test stesso."""
    valore = os.environ.get(nome, "").strip()
    if not valore:
        if non_verificato is None:
            # «percorso::nome (call)», come lo dà pytest mentre il test gira
            non_verificato = os.environ.get("PYTEST_CURRENT_TEST", "questo contratto").split(" ")[0]
        pytest.skip(f"{nome} non impostata: NON verificato: {non_verificato}")
    return valore


def richiedi_la_configurazione(non_verificato: str) -> None:
    """Salta se manca una qualunque delle variabili di `CONFIGURAZIONE`."""
    for nome in CONFIGURAZIONE:
        richiesta(nome, non_verificato)
