"""L'immagine e la configurazione vere. Nel container (`docker compose --profile
prova run --rm --build prova`) l'ambiente è quello di `config/prossima.env`."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima import config
from tests.reale.ambiente import richiedi_la_configurazione

pytestmark = pytest.mark.reale


def test_il_fuso_di_zurigo_c_e_anche_nell_immagine_slim():
    zurigo = ZoneInfo("Europe/Zurich")
    assert datetime(2025, 7, 1, 12, tzinfo=zurigo).utcoffset() == timedelta(hours=2)
    assert datetime(2025, 12, 1, 12, tzinfo=zurigo).utcoffset() == timedelta(hours=1)


def test_la_configurazione_vera_e_il_roster_vero_si_leggono():
    richiedi_la_configurazione("la configurazione vera e il roster vero si leggono")
    imp = config.da_ambiente(os.environ)
    assert imp.gruppo < 0, "PV_GRUPPO deve essere il gruppo del party: un numero negativo"
