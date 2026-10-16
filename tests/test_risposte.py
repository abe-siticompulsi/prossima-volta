import json
from datetime import UTC, datetime

import pytest

from prossima import testi
from prossima.ollama import OllamaError, Risposta
from prossima.risposte import (
    APERTO,
    CHIUSO,
    SCHEMA_TIPO,
    Domanda,
    Esito,
    Fatti,
    Modelli,
    da_riscrivere,
    fatti_del_sondaggio,
    per_il_tipo,
    per_la_battuta,
    per_riscrivere,
    risposta_del_codice,
    scrivi,
)
from prossima.store import Sondaggio
from tests.tavolo import ABE, EMI, GIO, OGGI, PIPPO, ROSTER, SEM, SESE, d, voto

SETTIMANA = tuple(d(f"{g}/10") for g in (13, 14, 15, 16, 17, 19))
VOTI = {
    GIO.telegram_id: voto("13/10 14/10 15/10 16/10"),
    ABE.telegram_id: voto("13/10 14/10 16/10 19/10"),
    EMI.telegram_id: voto("13/10 14/10 16/10"),
    SEM.telegram_id: voto("14/10 16/10"),
    SESE.telegram_id: voto("16/10"),
}


def sondaggio(chiuso: bool = False, scelta=None) -> Sondaggio:
    alle = datetime(2025, 10, 7, 18, tzinfo=UTC)
    return Sondaggio(
        id=1, date=SETTIMANA, poll_id="p", messaggio=1, frase="N", aperto_alle=alle,
        chiuso_alle=alle if chiuso else None, date_iniziali=SETTIMANA, scelta=scelta,
    )  # fmt: skip


APERTI = fatti_del_sondaggio(sondaggio(), VOTI, ROSTER, OGGI)
CHIUSI = fatti_del_sondaggio(sondaggio(chiuso=True, scelta=d("16/10")), VOTI, ROSTER, OGGI)
NIENTE = Fatti(OGGI)


def r(tipo, giorno=None, messaggio="", chi="Sem", fatti=APERTI) -> str:
    risposta = risposta_del_codice(tipo, giorno, messaggio, chi, fatti, ROSTER)
    return None if risposta is None else risposta.testo


def test_i_fatti_del_sondaggio():
    assert APERTI.stato == APERTO and CHIUSI.stato == CHIUSO
    assert dict(APERTI.date)[d("16/10")] == (GIO, ABE, EMI, SEM, SESE)
    assert APERTI.senza_voto == (PIPPO,)
    assert CHIUSI.scelta == d("16/10") and APERTI.scelta is None
    assert fatti_del_sondaggio(None, {}, ROSTER, OGGI) == NIENTE


# --- la risposta del codice, riga per riga della tabella della spec


def test_data_senza_sondaggio():
    t = risposta_del_codice("data", None, "Quando si gioca?", "Sem", NIENTE, ROSTER)
    assert t == testi.risposta_senza_sondaggio()
    for tipo in ("chi_c_e", "voto"):
        assert risposta_del_codice(tipo, "martedì", "E martedì?", "Sem", NIENTE, ROSTER) == t


def test_data_a_sondaggio_aperto():
    assert r("data") == "Il sondaggio è ancora aperto. Per ora si può fare giovedì 16/10."
    assert r("data", "martedì", "E martedì?") == (
        "Il sondaggio è ancora aperto. Martedì 14/10: manca un giocatore. "
        "L'hanno votata Gio, Abe, Emi e Sem. Non ha ancora votato: Pippo."
    )
    nessuna = fatti_del_sondaggio(sondaggio(), {}, ROSTER, OGGI)
    assert r("data", fatti=nessuna) == (
        "Il sondaggio è ancora aperto, e nessuna data ha il master e quattro giocatori."
    )


def test_le_date_possibili_sono_quelle_da_oggi_in_poi():
    dopo_il_16 = Fatti(d("17/10"), APERTO, APERTI.date, APERTI.senza_voto)
    assert r("data", fatti=dopo_il_16) == (
        "Il sondaggio è ancora aperto, e nessuna data ha il master e quattro giocatori."
    )


def test_data_a_sondaggio_chiuso_con_la_data_scelta():
    assert r("data", fatti=CHIUSI) == "Si gioca giovedì 16/10."
    assert (
        r("data", "giovedì", "Giovedì confermato?", fatti=CHIUSI) == "Sì: si gioca giovedì 16/10."
    )
    assert r("data", "martedì", "Martedì allora?", fatti=CHIUSI) == "No: si gioca giovedì 16/10."
    # il giorno non nominato nel messaggio non vale: il modello l'ha preso dal messaggio del bot
    assert (
        r("data", "giovedì", "Alla fine che giorno è?", fatti=CHIUSI) == "Si gioca giovedì 16/10."
    )


def test_data_scelta_passata():
    passata = Fatti(d("17/10"), CHIUSO, CHIUSI.date, CHIUSI.senza_voto, d("16/10"))
    assert r("data", fatti=passata) == (
        "Si è giocato giovedì 16/10. Per la prossima volta non c'è ancora un sondaggio."
    )


def test_chiuso_senza_data_con_e_senza_date_possibili():
    senza = fatti_del_sondaggio(sondaggio(chiuso=True), VOTI, ROSTER, OGGI)
    assert r("data", fatti=senza) == (
        "Il sondaggio è chiuso: si può fare giovedì 16/10. Gio, a te la scelta."
    )
    voti = {**VOTI, PIPPO.telegram_id: voto("14/10")}
    due = fatti_del_sondaggio(sondaggio(chiuso=True), voti, ROSTER, OGGI)
    assert r("data", fatti=due) == (
        "Il sondaggio è chiuso: si può fare martedì 14/10 o giovedì 16/10. Gio, a te la scelta."
    )
    vuoto = fatti_del_sondaggio(sondaggio(chiuso=True), {}, ROSTER, OGGI)
    assert r("data", fatti=vuoto) == (
        "Il sondaggio è chiuso senza una data. Per la prossima volta serve un sondaggio nuovo."
    )


def test_chi_c_e():
    assert r("chi_c_e", "giovedì", "Giovedì chi c'è?") == (
        "Giovedì 16/10: si può fare. L'hanno votata Gio, Abe, Emi, Sem e Sese."
    )
    assert r("chi_c_e", "venerdì", "E venerdì?") == (
        "Venerdì 17/10: manca il master, mancano 4 giocatori. Nessuno l'ha votata. "
        "Non ha ancora votato: Pippo."
    )
    assert r("chi_c_e", "sabato", "Sabato si può?") == "Sabato non è nel sondaggio."
    # a sondaggio chiuso, senza chi non ha votato
    assert r("chi_c_e", "martedì", "E martedì?", fatti=CHIUSI) == (
        "Martedì 14/10: manca un giocatore. L'hanno votata Gio, Abe, Emi e Sem."
    )
    # senza un giorno nominato, come «data»
    assert r("chi_c_e", None, "Chi c'è?") == r("data")
    assert r("chi_c_e", "venerdì", "Chi c'è?") == r("data")


def test_un_giorno_che_nel_sondaggio_compare_due_volte():
    due_martedi = Fatti(OGGI, APERTO, ((d("14/10"), (GIO,)), (d("21/10"), ())), ())
    assert r("chi_c_e", "martedì", "Martedì?", fatti=due_martedi) == (
        "Martedì 14/10: mancano 4 giocatori. L'hanno votata Gio. "
        "Martedì 21/10: manca il master, mancano 4 giocatori. Nessuno l'ha votata."
    )


def test_voto_chiusura_non_so_altro_e_battuta():
    assert r("voto", chi="Pippo") == "Pippo, conta solo il sondaggio: aggiorna lì il tuo voto."
    chiuso = risposta_del_codice("voto", None, "Non ci sono", "Sese", CHIUSI, ROSTER)
    assert chiuso == testi.voto_a_sondaggio_chiuso("Sese", GIO)
    assert r("chiusura") == "Chiude Gio (o Abe, in emergenza), quando decide."
    assert r("non_so", fatti=CHIUSI) == "Questo non lo so: chiedi a Gio."
    assert r("altro") == "Io conto i voti e basta."
    assert r("battuta") is None


def test_si_riscrive_solo_senza_entita_e_con_al_massimo_un_nome():
    assert da_riscrivere(testi.Testo("Questo non lo so: chiedi a Gio."), ROSTER)
    assert not da_riscrivere(testi.Testo("L'hanno votata Gio e Abe."), ROSTER)
    assert not da_riscrivere(testi.risposta_senza_sondaggio(), ROSTER)
    assert not da_riscrivere(testi.voto_a_sondaggio_chiuso("Sese", GIO), ROSTER)


# --- i prompt


def domanda(testo="Allora, deciso?", del_bot="✅ Giovedì si può fare!", fatti=APERTI, chi="Sem"):
    return Domanda(-100, 77, chi, testo, del_bot, fatti)


def test_il_prompt_del_tipo():
    sistema, utente = per_il_tipo(domanda(), ROSTER)
    assert "Gio è il master" in sistema and "- battuta: saluta" in sistema
    assert (
        utente == "Il tuo messaggio: «✅ Giovedì si può fare!»\nSem ti risponde: «Allora, deciso?»"
    )
    _, in_privato = per_il_tipo(domanda(del_bot=""), ROSTER)
    assert in_privato == "Sem ti scrive: «Allora, deciso?»"


def test_il_prompt_della_riscrittura_e_della_battuta():
    sistema, utente = per_riscrivere(domanda(), "Questo non lo so: chiedi a Gio.", ROSTER)
    assert "Gio è il master" not in sistema  # un nome che non c'era si scarta
    assert utente.startswith(
        "Sem ha risposto a un messaggio del bot: «Allora, deciso?». "
        "Il bot gli risponde così: «Questo non lo so: chiedi a Gio.»"
    )
    assert "- puoi rivolgerti a Sem;" in utente
    _, in_privato = per_riscrivere(domanda(del_bot=""), "x", ROSTER)
    assert in_privato.startswith("Sem ha scritto al bot: «Allora, deciso?».")
    sistema, _ = per_la_battuta(domanda(), ROSTER)
    assert "Niente fatti" in sistema


# --- scrivi, con un Ollama finto


class Finto:
    """Risponde con i testi in fila, per modello; un'eccezione in fila si solleva."""

    def __init__(self, **testi_per_modello):
        self.fila = {m.replace("_", ":"): list(t) for m, t in testi_per_modello.items()}
        self.chiamate = []

    def __call__(self, modello, sistema, utente, **opzioni):
        self.chiamate.append((modello, utente, opzioni))
        prossimo = self.fila[modello].pop(0)
        if isinstance(prossimo, Exception):
            raise prossimo
        return prossimo if isinstance(prossimo, Risposta) else Risposta(prossimo)


MODELLI = Modelli("tipo", "testo")


def tipo(t, giorno=None):
    return json.dumps({"tipo": t, "giorno": giorno})


def test_la_risposta_riscritta():
    finto = Finto(tipo=[tipo("non_so")], testo=["Sem, non lo so proprio: chiedi a Gio!"])
    esito = scrivi(domanda("A che ora?"), finto, ROSTER, MODELLI)
    assert esito == Esito(
        testi.Testo("Sem, non lo so proprio: chiedi a Gio!"), "non_so", None, True
    )
    (_, _, del_tipo), (_, _, del_testo) = finto.chiamate
    assert del_tipo == {"temperatura": 0.0, "massimo_token": 60, "formato": SCHEMA_TIPO}
    assert del_testo == {"temperatura": 0.7, "massimo_token": 200}


def test_la_riscrittura_che_non_passa_si_richiede_poi_resta_quella_del_codice():
    finto = Finto(
        tipo=[tipo("non_so")], testo=["Chiedi a Pippo.", "Alle 20!", "Venerdì, chiedi a Gio."]
    )
    esito = scrivi(domanda("A che ora?"), finto, ROSTER, MODELLI)
    assert esito == Esito(testi.Testo("Questo non lo so: chiedi a Gio."), "non_so", None, True)
    assert len(finto.chiamate) == 4
    assert "non va: manca il nome: gio; nome in più: pippo" in finto.chiamate[2][1]


def test_una_riscrittura_troncata_si_richiede():
    finto = Finto(
        tipo=[tipo("altro")], testo=[Risposta("Io conto", troncata=True), "Conto i voti, e basta."]
    )
    assert scrivi(domanda("Traduci"), finto, ROSTER, MODELLI).testo == testi.Testo(
        "Conto i voti, e basta."
    )


def test_la_risposta_con_piu_nomi_resta_quella_del_codice():
    finto = Finto(tipo=[tipo("chiusura")], testo=[])
    esito = scrivi(domanda("Chi chiude?"), finto, ROSTER, MODELLI)
    assert esito.testo == testi.Testo("Chiude Gio (o Abe, in emergenza), quando decide.")
    assert esito.dai_fatti and len(finto.chiamate) == 1


def test_la_riscrittura_che_cade_lascia_quella_del_codice():
    finto = Finto(tipo=[tipo("altro")], testo=[OllamaError("giù")])
    esito = scrivi(domanda("Traduci"), finto, ROSTER, MODELLI)
    assert esito == Esito(testi.Testo("Io conto i voti e basta."), "altro", None, True)


def test_la_battuta():
    finto = Finto(tipo=[tipo("battuta")], testo=["Sveglissimo, Sem!"])
    esito = scrivi(domanda("Sei sveglio?"), finto, ROSTER, MODELLI)
    assert esito == Esito(testi.Testo("Sveglissimo, Sem!"), "battuta", None, False)
    assert finto.chiamate[1][2] == {"temperatura": 0.8, "massimo_token": 80}


def test_la_battuta_che_non_passa_e_quella_di_riserva():
    finto = Finto(tipo=[tipo("battuta")], testo=["Chiedi a Pippo"] * 3)
    esito = scrivi(domanda("Sei sveglio?"), finto, ROSTER, MODELLI)
    assert esito.testo == testi.battuta_di_riserva()


@pytest.mark.parametrize(
    "fila",
    [
        {"tipo": [OllamaError("giù")]},
        {"tipo": ["non json"]},
        {"tipo": [tipo("sconosciuto")]},
        {"tipo": [tipo("battuta")], "testo": [OllamaError("giù")]},
    ],
)
def test_ollama_giu_o_il_tipo_illeggibile_danno_la_frase_fissa(fila):
    esito = scrivi(domanda(), Finto(**fila), ROSTER, MODELLI)
    assert esito.testo == testi.non_riesco() and not esito.dai_fatti
