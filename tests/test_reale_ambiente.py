"""Gli aiuti del piano reale (`tests/reale/`), provati nella suite veloce: il
piano reale sa dire perché salta e perché fallisce, senza bisogno del bot vero."""

import pytest

from tests.reale import test_telegram_vero
from tests.reale.ambiente import CONFIGURAZIONE, richiedi_la_configurazione, richiesta

NON_VERIFICATO = "la configurazione vera e il roster vero si leggono"


@pytest.fixture
def ambiente_completo(monkeypatch):
    for nome in CONFIGURAZIONE:
        monkeypatch.setenv(nome, "x")


def test_la_configurazione_richiesta_e_quella_che_il_servizio_legge():
    assert set(CONFIGURAZIONE) == {
        "PV_BOT_TOKEN", "PV_GRUPPO", "PV_ROSTER", "PV_DB", "PV_BATTITO"
    }


def test_con_tutte_le_variabili_il_piano_reale_non_salta(ambiente_completo):
    richiedi_la_configurazione(NON_VERIFICATO)


@pytest.mark.parametrize("nome", CONFIGURAZIONE)
@pytest.mark.parametrize("mancante", ["assente", "vuota", "spazi"])
def test_una_variabile_mancante_fa_saltare_e_dice_cosa_non_e_verificato(
    monkeypatch, ambiente_completo, nome, mancante
):
    if mancante == "assente":
        monkeypatch.delenv(nome)
    else:
        monkeypatch.setenv(nome, "" if mancante == "vuota" else "  ")
    with pytest.raises(pytest.skip.Exception) as salto:
        richiedi_la_configurazione(NON_VERIFICATO)
    messaggio = str(salto.value)
    assert f"{nome} non impostata" in messaggio
    assert f"NON verificato: {NON_VERIFICATO}" in messaggio


def test_una_richiesta_senza_il_dettaglio_dice_quale_test_non_e_verificato(monkeypatch):
    monkeypatch.delenv("PV_REALE_CHAT", raising=False)
    with pytest.raises(pytest.skip.Exception) as salto:
        richiesta("PV_REALE_CHAT")
    assert str(salto.value) == (
        "PV_REALE_CHAT non impostata: NON verificato: "
        "tests/test_reale_ambiente.py::"
        "test_una_richiesta_senza_il_dettaglio_dice_quale_test_non_e_verificato"
    )


def test_il_fallimento_di_risposte_suggerisce_le_due_cause_possibili(monkeypatch):
    class BotMuto:
        def aggiornamenti(self, offset, attesa):
            return []

    class OrologioFinto:
        """Ogni lettura dell'ora vale cento secondi, e dormire non costa niente."""

        def __init__(self):
            self.adesso = 0.0

        def monotonic(self):
            self.adesso += 100
            return self.adesso

        def sleep(self, secondi):
            pass

    monkeypatch.setattr(test_telegram_vero, "time", OrologioFinto())
    with pytest.raises(pytest.fail.Exception) as fallimento:
        test_telegram_vero.risposte(BotMuto(), "poll-1", 3)
    messaggio = str(fallimento.value)
    assert "sono arrivate 0 risposte su 3" in messaggio
    assert "il servizio è davvero fermo? (due lettori si rubano i voti)" in messaggio
    assert "hai votato entro 3 minuti?" in messaggio
