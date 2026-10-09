import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima import regole, testi
from prossima.regole import Persona, Roster
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
        if e["type"] == "text_mention"
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


SETTIMANA_PROVE = [d("13/10") + timedelta(days=i) for i in range(7)]
DUE_SETTIMANE = [*SETTIMANA_PROVE, d("20/10")]


def test_quasi():
    gruppo = [regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (PIPPO,))]
    t = testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE)
    assert t.testo == "Martedì ci siamo quasi. Pippo, ci sei?"
    assert menzionati(t) == [("Pippo", PIPPO.telegram_id)]
    assert all(e["type"] == "text_mention" for e in t.entita)


def test_quasi_accorpato_con_piu_persone():
    gruppo = [regole.Quasi(d(g), (GIO, ABE, EMI, SEM), (SESE, PIPPO)) for g in ("13/10", "16/10")]
    t = testi.annunci(gruppo, ROSTER, NOME, DUE_SETTIMANE)
    assert t.testo == "Lunedì 13 e giovedì 16 ci siamo quasi. Sese e Pippo, ci siete?"
    assert menzionati(t) == [("Sese", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]


# Un soprannome non ASCII con un'emoji: 5 caratteri, 6 unità UTF-16 (🎲 ne vale due).
SESE_DADO = Persona("sèsè🎲", SESE.telegram_id, "giocatore")


def test_le_menzioni_contano_in_utf16_anche_con_un_soprannome_non_ascii():
    gruppo = [regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE_DADO, PIPPO))]
    t = testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE)
    assert menzionati(t) == [("Sèsè🎲", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]
    # la lunghezza è quella di Telegram, non quella di `len()`...
    assert [e["length"] for e in t.entita] == [6, 5]
    assert len(SESE_DADO.soprannome) == 5
    # ...e la seconda menzione comincia dopo la prima e « e »
    assert t.entita[1]["offset"] == t.entita[0]["offset"] + 6 + 3


def test_riapro_conta_le_menzioni_in_utf16_dopo_un_soprannome_non_ascii():
    t = testi.riapro((ABE,), (SESE_DADO, PIPPO))
    assert menzionati(t) == [("Sèsè🎲", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]
    assert [e["length"] for e in t.entita] == [6, 5]


def test_possibile():
    gruppo = [regole.Possibile(d(g), (GIO, ABE, EMI, SEM, SESE)) for g in ("13/10", "14/10")]
    assert testi.annunci(gruppo[:1], ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo("✅ Lunedì si può fare!")
    assert testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "✅ Lunedì e martedì si può fare!"
    )


def test_non_piu():
    sem, sese = regole.NonPiu(d("14/10"), (SEM,)), regole.NonPiu(d("16/10"), (SESE, SEM))
    assert testi.annunci([sem], ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Martedì è saltato, Sem non può più."
    )
    # le persone di tutte le date, una volta sola e nell'ordine del roster
    assert testi.annunci([sem, sese], ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Martedì e giovedì sono saltati, Sem e Sese non possono più."
    )


def test_non_piu_la_domenica_e_senza_nomi():
    assert testi.annunci([regole.NonPiu(d("19/10"), (SEM,))], ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Domenica è saltata, Sem non può più."
    )
    # per una data il bot non sa chi (dopo una ripresa): nessun nome
    domeniche = [regole.NonPiu(d("19/10"), (SEM,)), regole.NonPiu(d("26/10"), ())]
    assert testi.annunci(domeniche, ROSTER, NOME, [d("19/10"), d("26/10")]) == testi.Testo(
        "Domenica 19 e domenica 26 sono saltate."
    )
    assert testi.annunci([regole.NonPiu(d("14/10"), ())], ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Martedì è saltato."
    )


def test_impossibile():
    con_tre = regole.Impossibile(
        ((d("13/10"), (GIO, ABE, EMI, SEM)), (d("16/10"), (GIO, ABE, EMI, SESE)))
    )
    t = testi.annunci([con_tre], ROSTER, NOME, SETTIMANA_PROVE)
    assert t.testo == (
        "😬 Con i voti attuali non ci sono date con quattro giocatori. Con tre: lunedì e giovedì. "
        "Gio: /chiudi@ProssimaVoltaBot 13/10 per tenerne una, "
        "/chiudi@ProssimaVoltaBot rimanda per rimandare alla prossima settimana."
    )
    assert menzionati(t) == [("Gio", GIO.telegram_id)]
    una = regole.Impossibile(((d("13/10"), (GIO, ABE, EMI, SEM)),))
    assert "Con tre: lunedì. Gio: /chiudi@ProssimaVoltaBot 13/10 per tenerla, " in (
        testi.annunci([una], ROSTER, NOME, SETTIMANA_PROVE).testo
    )
    senza = testi.annunci([regole.Impossibile(())], ROSTER, NOME, SETTIMANA_PROVE)
    assert senza.testo == (
        "😬 Con i voti attuali non ci sono date con quattro giocatori, e nemmeno con tre. "
        "Gio: /chiudi@ProssimaVoltaBot rimanda per rimandare alla prossima settimana."
    )
    assert menzionati(senza) == [("Gio", GIO.telegram_id)]


def test_impossibile_menziona_chi_chiude_se_il_master_non_puo():
    roster = Roster((replace(GIO, chiude=False), ABE, EMI, SEM, SESE, PIPPO))
    t = testi.annunci([regole.Impossibile(())], roster, NOME, SETTIMANA_PROVE)
    assert "nemmeno con tre. Abe: /chiudi@" in t.testo
    assert menzionati(t) == [("Abe", ABE.telegram_id)]


@pytest.mark.parametrize(
    "rifiuto, testo",
    [
        (
            regole.NonCapisco("32/10"),
            "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
        ),
        (regole.DataPassata("3/10"), "La data 3/10 è già passata."),
        (regole.DataTroppoLontana("14/10/2052"), "La data 14/10/2052 è troppo lontana."),
        (regole.TroppeDate(), "Troppe date: al massimo 10."),
        (
            regole.ConSbagliato(),
            "Per aggiungere un giorno a quelli di sempre: /sondaggio@ProssimaVoltaBot con sabato.",
        ),
    ],
)
def test_i_rifiuti(rifiuto, testo):
    assert testi.rifiuto(rifiuto, "ProssimaVoltaBot").testo == testo


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
    assert testi.sondaggio_non_confermato(NOME, []).testo == (
        "Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:\n"
        "/sondaggio@ProssimaVoltaBot"
    )
    assert testi.sondaggio_non_confermato(NOME, ["21/10", "23/10"]).testo == (
        "Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:\n"
        "/sondaggio@ProssimaVoltaBot 21/10 23/10"
    )
    assert testi.voto_sconosciuto(NOME).testo == (
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot"
    )
    assert testi.voto_sconosciuto(NOME, ["mar", "gio"]).testo == (
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. Rilanciatelo e votate lì:\n"
        "/sondaggio@ProssimaVoltaBot mar gio"
    )
    assert testi.voto_sconosciuto(NOME, con_sondaggio_aperto=True) == testi.Testo(
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. "
        "Il sondaggio che conto è questo: votate qui."
    )
    assert testi.nessun_sondaggio() == testi.Testo("Non c'è nessun sondaggio aperto.")
    assert testi.chiuso([d("14/10"), d("16/10")]) == testi.Testo(
        "🔒 Sondaggio chiuso. Date possibili: mar 14/10, gio 16/10."
    )
    assert testi.chiuso([]) == testi.Testo(
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    )
    assert testi.chiuso_con_le_date_possibili_passate() == testi.Testo(
        "🔒 Sondaggio chiuso. Nessuna data possibile da oggi in poi."
    )
    assert testi.si_gioca(d("14/10")) == testi.Testo("🎲 Si gioca martedì 14/10.")
    assert testi.rimandiamo(d("20/10")) == testi.Testo(
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."
    )
    assert testi.rimando_non_confermato(NOME, [d("21/10"), d("23/10")]).testo == (
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
    assert testi.chiusura_non_completata(NOME, []).testo == (
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot"
    )
    assert testi.chiusura_non_completata(NOME, ["rimanda"]).testo == (
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n/chiudi@ProssimaVoltaBot rimanda"
    )
    assert testi.riprovo_a_completare() == testi.Testo(
        "Riprovo a completare la chiusura del sondaggio."
    )


def test_chi_chiude():
    assert testi.solo_chi_chiude(ROSTER) == testi.Testo("Il sondaggio lo chiude Gio (o Abe, in emergenza).")
    assert testi.chi_chiude(Roster((GIO, replace(ABE, chiude=False), EMI))) == "chiude Gio"
    senza_master = Roster((replace(GIO, chiude=False), ABE, replace(EMI, chiude=True)))
    assert testi.chi_chiude(senza_master) == "chiudono Abe e Emi"
    tre = Roster((GIO, ABE, replace(EMI, chiude=True)))
    assert testi.chi_chiude(tre) == "chiude Gio (o Abe o Emi, in emergenza)"


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
        "Riapro il sondaggio. Ho già i voti di Abe, Emi e Sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: Sese, Pippo."
    )
    assert menzionati(t) == [("Sese", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]


def test_riapro_senza_le_parti_vuote():
    assert testi.riapro((), (GIO, ABE)).testo == "Riapro il sondaggio. Non hanno ancora votato: Gio, Abe."
    assert testi.riapro((ABE,), ()) == testi.Testo(
        "Riapro il sondaggio. Ho già i voti di Abe: se non avete cambiato idea, non serve rivotare."
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
        frase = testi.scegli_frase(testi.FRASI_NESSUNA, usate, caso)
        assert frase not in usate
        usate.add(frase)
    assert usate == set(testi.FRASI_NESSUNA)
    # finite tutte: una qualsiasi, e chi la sceglie ricomincia il giro
    assert testi.scegli_frase(testi.FRASI_NESSUNA, usate, caso) in testi.FRASI_NESSUNA


def test_scegli_frase_sceglie_fra_le_restanti():
    usate = set(testi.FRASI_NESSUNA[1:])
    primo = lambda restanti: restanti[0]  # noqa: E731
    assert testi.scegli_frase(testi.FRASI_NESSUNA, usate, primo) == testi.FRASI_NESSUNA[0]


def test_scegli_frase_sceglie_nella_lista_che_riceve():
    primo = lambda restanti: restanti[0]  # noqa: E731
    assert testi.scegli_frase(("Nessuna: a", "Nessuna: b"), {"Nessuna: a"}, primo) == "Nessuna: b"
    # usate tutte, o usate solo frasi che non ci sono più: si sceglie fra tutte
    assert testi.scegli_frase(("Nessuna: a", "Nessuna: b"), {"Nessuna: a", "Nessuna: b"}, primo) == "Nessuna: a"
    assert testi.scegli_frase(("Nessuna: a",), {testi.FRASI_NESSUNA[0]}, primo) == "Nessuna: a"


def test_i_nomi_con_la_maiuscola():
    assert testi.nome(GIO) == "Gio"
    t = testi.riapro((ABE,), (SESE, PIPPO))
    assert t.testo == (
        "Riapro il sondaggio. Ho già i voti di Abe: se non avete cambiato idea, non serve rivotare. "
        "Non hanno ancora votato: Sese, Pippo."
    )
    assert menzionati(t) == [("Sese", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]


def test_la_maiuscola_non_sposta_le_menzioni():
    strano = Persona("èsè🎲", 7, "giocatore")
    assert menzionati(testi.riapro((), (strano, PIPPO))) == [("Èsè🎲", 7), ("Pippo", PIPPO.telegram_id)]


def test_le_date_dette():
    assert testi.una_settimana([d("13/10"), d("14/10"), d("19/10")])
    assert not testi.una_settimana([d("19/10"), d("20/10")])
    assert testi.giorno_detto(d("14/10"), True) == "martedì"
    assert testi.giorno_detto(d("14/10"), False) == "martedì 14"
    assert testi.date_dette([d("16/10"), d("13/10")], True) == "lunedì e giovedì"
    assert testi.date_dette([d("13/10"), d("14/10"), d("16/10")], False) == "lunedì 13, martedì 14 e giovedì 16"


def test_aiuto_dai_giorni_di_sempre():
    tutti = testi.aiuto(NOME, ROSTER, range(7)).testo.split("\n")
    assert tutti[1] == f"/sondaggio@{NOME} — sondaggio sulla settimana prossima"
    assert not any(" con " in riga for riga in tutti)
    senza_domenica = testi.aiuto(NOME, ROSTER, (0, 1, 2, 3, 4, 5)).testo.split("\n")
    assert senza_domenica[1].endswith("— sondaggio sulla settimana prossima, domenica esclusa")
    assert senza_domenica[2] == f"/sondaggio@{NOME} con domenica — anche la domenica"
    senza_due = testi.aiuto(NOME, ROSTER, (0, 1, 2, 3, 4)).testo.split("\n")
    assert senza_due[1].endswith("— sondaggio sulla settimana prossima, sabato e domenica esclusi")
    assert senza_due[2] == f"/sondaggio@{NOME} con sabato — anche il sabato"


def test_aiuto_dal_roster():
    solo_gio = Roster((GIO, replace(ABE, chiude=False), EMI, SEM, SESE, PIPPO))
    assert "\nChiude Gio:\n" in testi.aiuto(NOME, solo_gio, (0, 1, 2, 3, 4, 6)).testo



def test_non_piu_sabato_e_domenica_al_maschile():
    gruppo = [regole.NonPiu(d("18/10"), (SEM,)), regole.NonPiu(d("19/10"), (SEM,))]
    assert testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Sabato e domenica sono saltati, Sem non può più."
    )


def test_non_piu_i_nomi_nell_ordine_del_roster():
    gruppo = [regole.NonPiu(d("14/10"), (SESE,)), regole.NonPiu(d("16/10"), (SEM,))]
    assert testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE) == testi.Testo(
        "Martedì e giovedì sono saltati, Sem e Sese non possono più."
    )


def test_chiude_uno_solo_se_il_master_non_puo():
    roster = Roster((replace(GIO, chiude=False), ABE, EMI))
    assert testi.chi_chiude(roster) == "chiude Abe"
    assert testi.solo_chi_chiude(roster) == testi.Testo("Il sondaggio lo chiude Abe.")


def test_il_rifiuto_di_con_suggerisce_un_giorno_escluso():
    assert testi.rifiuto(regole.ConSbagliato(), NOME, (0, 1, 2, 3, 4, 5)).testo == (
        f"Per aggiungere un giorno a quelli di sempre: /sondaggio@{NOME} con domenica."
    )
    assert testi.rifiuto(regole.ConSbagliato(), NOME, range(7)).testo.endswith("con sabato.")


def codici(t: testi.Testo) -> list[str]:
    """Le parti in codice (`code`), ritagliate in unità UTF-16 come Telegram."""
    unita = t.testo.encode("utf-16-le")
    return [
        unita[2 * e["offset"] : 2 * (e["offset"] + e["length"])].decode("utf-16-le")
        for e in t.entita
        if e["type"] == "code"
    ]


def test_i_comandi_da_copiare_sono_codice():
    """Un comando evidenziato, toccato, parte senza quello che segue
    («/chiudi@bot rimanda» chiuderebbe e basta): i comandi con argomenti si
    scrivono come codice, che un tocco copia intero."""
    s = f"/sondaggio@{NOME}"
    assert codici(testi.sondaggio_non_confermato(NOME, ["mar", "gio"])) == [f"{s} mar gio"]
    assert codici(testi.voto_sconosciuto(NOME, ["14/10"])) == [f"{s} 14/10"]
    assert codici(testi.voto_sconosciuto(NOME, con_sondaggio_aperto=True)) == []
    assert codici(testi.rimando_non_confermato(NOME, [d("21/10")])) == [f"{s} 21/10"]
    assert codici(testi.chiusura_non_completata(NOME, ["rimanda"])) == [f"/chiudi@{NOME} rimanda"]
    assert codici(testi.rifiuto(regole.ConSbagliato(), NOME)) == [f"{s} con sabato"]
    impossibile = regole.Impossibile(((d("13/10"), (GIO, ABE, EMI, SEM)),))
    t = testi.annunci([impossibile], ROSTER, NOME, SETTIMANA_PROVE)
    assert codici(t) == [f"/chiudi@{NOME} 13/10", f"/chiudi@{NOME} rimanda"]
    assert menzionati(t) == [("Gio", GIO.telegram_id)]


def test_in_aiuto_tutti_i_comandi_sono_codice():
    s, c = f"/sondaggio@{NOME}", f"/chiudi@{NOME}"
    assert codici(testi.aiuto(NOME, ROSTER, (0, 1, 2, 3, 4, 6))) == [
        s, f"{s} con sabato", f"{s} mar gio", f"{s} 14/10 16/10", c, f"{c} 14/10", f"{c} rimanda"
    ]
