import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima import regole, testi
from tests.tavolo import ABE, EMI, GIO, PIPPO, ROSTER, SEM, SESE, d

NOME = "ProssimaVoltaBot"
ZURIGO = ZoneInfo("Europe/Zurich")


def menzionati(t: testi.Testo) -> list[tuple[str, int]]:
    """Il pezzo di testo su cui cade ogni menzione, ritagliato come lo ritaglia
    Telegram (in unità UTF-16), e l'identificativo della persona."""
    unita = t.testo.encode("utf-16-le")
    return [
        (
            unita[2 * e["offset"] : 2 * (e["offset"] + e["length"])].decode("utf-16-le"),
            e["user"]["id"],
        )
        for e in t.entita
    ]


def test_utf16_conta_come_telegram():
    assert testi.utf16("abe") == 3
    assert testi.utf16("📅") == 2
    assert testi.utf16("⚠️") == 2
    assert testi.utf16("è") == 1


def test_le_opzioni_del_sondaggio():
    frase = testi.FRASI_NESSUNA[0]
    assert testi.opzioni([d("14/10"), d("16/10")], frase) == ["mar 14/10", "gio 16/10", frase]
    assert testi.DOMANDA == "Prossima volta?"


def test_quasi_con_le_menzioni_dopo_un_emoji():
    t = testi.quasi(regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO)))
    assert t.testo == (
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(t) == [("sese", SESE.telegram_id), ("pippo", PIPPO.telegram_id)]
    assert all(e["type"] == "text_mention" for e in t.entita)
    # 📅 vale due unità: contando i caratteri la menzione cadrebbe una lettera prima
    assert t.entita[0]["offset"] == t.testo.index("sese") + 1


def test_quasi_quando_hanno_votato_tutti():
    t = testi.quasi(regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), ()))
    assert t == testi.Testo("📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore.")


def test_possibile():
    t = testi.possibile(regole.Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    assert t == testi.Testo("✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese.")


def test_non_piu_possibile():
    assert testi.non_piu(regole.NonPiu(d("14/10"), (SEM,))) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: sem ha tolto il voto."
    )
    assert testi.non_piu(regole.NonPiu(d("14/10"), (SEM, SESE))) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: sem e sese hanno tolto il voto."
    )
    assert testi.non_piu(regole.NonPiu(d("14/10"), ())) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro giocatori."
    )


def test_impossibile_con_una_data_in_tre():
    a = regole.Impossibile(((d("14/10"), (GIO, ABE, EMI, SEM)),))
    t = testi.impossibile(a, (GIO, ABE), NOME)
    assert t.testo == (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date. "
        "Con tre: mar 14/10 (gio, abe, emi, sem). "
        "gio, abe: /chiudi@ProssimaVoltaBot 14/10 per tenerla, "
        "/chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_impossibile_con_piu_date_in_tre():
    a = regole.Impossibile(
        ((d("14/10"), (GIO, ABE, EMI, SEM)), (d("16/10"), (GIO, ABE, SEM, SESE)))
    )
    t = testi.impossibile(a, (GIO, ABE), NOME)
    assert "Con tre: mar 14/10 (gio, abe, emi, sem); gio 16/10 (gio, abe, sem, sese). " in t.testo
    assert "/chiudi@ProssimaVoltaBot 14/10 per tenerla" in t.testo
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_impossibile_senza_date_in_tre():
    t = testi.impossibile(regole.Impossibile(()), (GIO, ABE), NOME)
    assert t.testo == (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date, e nemmeno con tre. "
        "gio, abe: /chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_annuncio_sceglie_il_testo_e_menziona_chi_chiude_dal_roster():
    assert testi.annuncio(regole.NonPiu(d("14/10"), (SEM,)), ROSTER, NOME) == testi.non_piu(
        regole.NonPiu(d("14/10"), (SEM,))
    )
    t = testi.annuncio(regole.Impossibile(()), ROSTER, NOME)
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


@pytest.mark.parametrize(
    "rifiuto, testo",
    [
        (
            regole.NonCapisco("32/10"),
            "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
        ),
        (regole.DataPassata("3/10"), "La data 3/10 è già passata."),
        (regole.TroppeDate(), "Troppe date: al massimo 10."),
    ],
)
def test_i_rifiuti(rifiuto, testo):
    assert testi.rifiuto(rifiuto) == testi.Testo(testo)


@pytest.mark.parametrize(
    "rifiuto, testo",
    [
        (
            regole.NonCapisco("boh"),
            "Non capisco «boh»: scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda.",
        ),
        (regole.NonNelSondaggio("15/10"), "La data 15/10 non era nel sondaggio."),
        (regole.GiornoAmbiguo(1, d("14/10")), "Nel sondaggio c'è più di un martedì: scrivi la data (14/10)."),
        (regole.GiornoAssente(4), "Nel sondaggio non c'è nessun venerdì."),
        (regole.DataPassata("8/10"), "La data 8/10 è già passata."),
    ],
)
def test_i_rifiuti_di_chiudi(rifiuto, testo):
    assert testi.rifiuto_di_chiudi(rifiuto) == testi.Testo(testo)


def test_i_giorni_dei_rifiuti_di_chiudi_con_l_articolo_giusto():
    lunedi = d("13/10")
    ambigui = [testi.rifiuto_di_chiudi(regole.GiornoAmbiguo(g, lunedi + timedelta(days=g))).testo for g in range(7)]
    assert [t.split(":")[0] for t in ambigui] == [
        "Nel sondaggio c'è più di un lunedì",
        "Nel sondaggio c'è più di un martedì",
        "Nel sondaggio c'è più di un mercoledì",
        "Nel sondaggio c'è più di un giovedì",
        "Nel sondaggio c'è più di un venerdì",
        "Nel sondaggio c'è più di un sabato",
        "Nel sondaggio c'è più di una domenica",
    ]
    assert ambigui[6] == "Nel sondaggio c'è più di una domenica: scrivi la data (19/10)."
    assert [testi.rifiuto_di_chiudi(regole.GiornoAssente(g)).testo for g in range(7)] == [
        "Nel sondaggio non c'è nessun lunedì.",
        "Nel sondaggio non c'è nessun martedì.",
        "Nel sondaggio non c'è nessun mercoledì.",
        "Nel sondaggio non c'è nessun giovedì.",
        "Nel sondaggio non c'è nessun venerdì.",
        "Nel sondaggio non c'è nessun sabato.",
        "Nel sondaggio non c'è nessuna domenica.",
    ]


def test_le_risposte_ai_comandi():
    assert testi.gia_aperto(NOME) == testi.Testo(
        "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot."
    )
    assert testi.sondaggio_non_confermato(NOME, []) == testi.Testo(
        "Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:\n"
        "/sondaggio@ProssimaVoltaBot"
    )
    assert testi.sondaggio_non_confermato(NOME, ["21/10", "23/10"]) == testi.Testo(
        "Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:\n"
        "/sondaggio@ProssimaVoltaBot 21/10 23/10"
    )
    assert testi.voto_sconosciuto(NOME) == testi.Testo(
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot"
    )
    assert testi.voto_sconosciuto(NOME, ["mar", "gio"]) == testi.Testo(
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot mar gio"
    )
    assert testi.voto_sconosciuto(NOME, con_sondaggio_aperto=True) == testi.Testo(
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. "
        "Il sondaggio che conto è questo: votate qui."
    )
    assert testi.solo_chi_chiude((GIO, ABE)) == testi.Testo("Il sondaggio lo chiudono gio o abe.")
    assert testi.solo_chi_chiude((GIO, ABE, EMI)) == testi.Testo(
        "Il sondaggio lo chiudono gio, abe o emi."
    )
    assert testi.nessun_sondaggio() == testi.Testo("Non c'è nessun sondaggio aperto.")
    assert testi.chiuso([d("14/10"), d("16/10")]) == testi.Testo(
        "🔒 Sondaggio chiuso. Date possibili: mar 14/10, gio 16/10."
    )
    assert testi.chiuso([]) == testi.Testo(
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    )
    assert testi.si_gioca(d("14/10")) == testi.Testo("🎲 Si gioca martedì 14/10.")
    assert testi.rimandiamo(d("20/10")) == testi.Testo(
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."
    )
    assert testi.rimando_non_confermato(NOME, [d("21/10"), d("23/10")]) == testi.Testo(
        "🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: "
        "se non lo vedete, lanciatelo con:\n/sondaggio@ProssimaVoltaBot 21/10 23/10"
    )
    assert testi.sparito() == testi.Testo("Il messaggio del sondaggio non c'è più: lo considero chiuso.")
    assert testi.chiusura_non_confermata() == testi.Testo(
        "Telegram non ha confermato la chiusura del sondaggio: riprovo da solo."
    )
    assert testi.non_ancora_chiuso() == testi.Testo(
        "Telegram non ha ancora confermato la chiusura del sondaggio di prima: riprovate fra poco."
    )
    assert testi.chiusura_non_completata(NOME, []) == testi.Testo(
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot"
    )
    assert testi.chiusura_non_completata(NOME, ["rimanda"]) == testi.Testo(
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot rimanda"
    )
    assert testi.riprovo_a_completare() == testi.Testo(
        "Riprovo a completare la chiusura del sondaggio."
    )


def test_il_buio_con_le_ore_di_zurigo():
    # ora legale: UTC+2
    dal = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    al = datetime(2025, 10, 14, 7, 30, tzinfo=UTC)
    assert testi.buio(dal, al, ZURIGO) == testi.Testo(
        "🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10 alle 9:30. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    )
    # ora solare: UTC+1
    t = testi.buio(datetime(2025, 11, 2, 23, 5, tzinfo=UTC), datetime(2025, 11, 4, 8, 0, tzinfo=UTC), ZURIGO)
    assert "dal 3/11 alle 0:05 al 4/11 alle 9:00." in t.testo


def test_i_conteggi_dopo_il_buio():
    assert testi.conteggi(True) == testi.Testo("I conteggi del sondaggio sono gli stessi che avevo io.")
    assert testi.conteggi(False) == testi.Testo(
        "I conteggi del sondaggio sono diversi dai miei: "
        "qualcuno ha votato o cambiato voto senza che lo sapessi."
    )


def test_gia_chiuso_dopo_il_buio():
    assert testi.gia_chiuso() == testi.Testo("Il sondaggio risultava già chiuso.")
    assert testi.gia_chiuso_senza_confronto() == testi.Testo(
        "Il sondaggio risultava già chiuso: non posso confrontare i conteggi."
    )


def test_riapro():
    t = testi.riapro((ABE, EMI, SEM), (SESE, PIPPO))
    assert t.testo == (
        "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(t) == [("sese", SESE.telegram_id), ("pippo", PIPPO.telegram_id)]


def test_riapro_senza_le_parti_vuote():
    assert testi.riapro((), (GIO, ABE)).testo == "Riapro il sondaggio. Non hanno ancora votato: gio, abe."
    assert testi.riapro((ABE,), ()) == testi.Testo(
        "Riapro il sondaggio. Ho già i voti di abe: se non avete cambiato idea, non serve rivotare."
    )
    assert testi.date_passate() == testi.Testo("Le date del sondaggio sono passate: lo chiudo.")


def test_le_frasi_di_nessuna():
    assert len(testi.FRASI_NESSUNA) == 15
    assert len(set(testi.FRASI_NESSUNA)) == 15
    for frase in testi.FRASI_NESSUNA:
        assert frase.startswith("Nessuna"), frase
        assert len(frase) <= testi.LUNGHEZZA_OPZIONE, frase
        assert testi.utf16(frase) <= testi.LUNGHEZZA_OPZIONE, frase


def test_le_frasi_ruotano_senza_ripetersi_e_poi_ricominciano():
    caso = random.Random(7).choice
    usate: set[str] = set()
    for _ in testi.FRASI_NESSUNA:
        frase = testi.scegli_frase(usate, caso)
        assert frase not in usate
        usate.add(frase)
    assert usate == set(testi.FRASI_NESSUNA)
    # finite tutte: una qualsiasi, e chi la sceglie ricomincia il giro
    assert testi.scegli_frase(usate, caso) in testi.FRASI_NESSUNA


def test_scegli_frase_sceglie_fra_le_restanti():
    usate = set(testi.FRASI_NESSUNA[1:])
    assert testi.scegli_frase(usate, lambda restanti: restanti[0]) == testi.FRASI_NESSUNA[0]
