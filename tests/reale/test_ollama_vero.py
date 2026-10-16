"""Ollama vero, con `PV_OLLAMA_URL` (dal container `prova`, sulla rete `ollama`).

Si controlla il contratto con Ollama, non la qualità dei testi (quella l'ha
giudicata il prototipo, leggendoli): i due modelli ci sono e rispondono, e il
tipo arriva come un JSON che segue lo schema. A freddo ogni modello può
metterci più di un minuto.
"""

import os
from datetime import date
from pathlib import Path

import pytest

from prossima import config, risposte
from prossima.ollama import Ollama
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def ollama() -> Ollama:
    return Ollama(richiesta("PV_OLLAMA_URL"))


def modelli() -> risposte.Modelli:
    """Quelli che usa il servizio: da `PV_OLLAMA_TIPO` e `PV_OLLAMA_TESTO`, o i predefiniti."""
    return risposte.Modelli(
        tipo=os.environ.get("PV_OLLAMA_TIPO", "").strip() or risposte.MODELLI.tipo,
        testo=os.environ.get("PV_OLLAMA_TESTO", "").strip() or risposte.MODELLI.testo,
    )


def test_il_tipo_e_un_json_con_un_tipo_conosciuto():
    roster = config.leggi_roster(Path(richiesta("PV_ROSTER")))
    domanda = risposte.Domanda(0, 0, "Abe", "Quando si gioca?", "", risposte.Fatti(date.today()))
    sistema, utente = risposte.per_il_tipo(domanda, roster)
    r = ollama().chiedi(
        modelli().tipo, sistema, utente, temperatura=0.0, massimo_token=60,
        formato=risposte.SCHEMA_TIPO,
    )  # fmt: skip
    assert risposte.leggi_tipo(r.testo) is not None, r.testo


def test_il_modello_che_scrive_risponde():
    r = ollama().chiedi(
        modelli().testo, "Rispondi in italiano, in una parola.", "Di che colore è il cielo?",
        temperatura=0.5, massimo_token=20,
    )  # fmt: skip
    assert r.testo.strip()
