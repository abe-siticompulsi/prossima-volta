from datetime import date

from prossima.controlli import (
    controlla_battuta,
    controlla_riscrittura,
    controlla_risposta,
    date_in,
    emoji,
    giorni_in,
    pulisci,
)

SOPRANNOMI = ("gio", "abe", "emi", "sem", "sese", "pippo")
MARTEDI = date(2026, 10, 20)
GIOVEDI = date(2026, 10, 22)


def test_pulisci_toglie_spazi_e_virgolette_attorno():
    assert pulisci("  «Nessuna: ho tirato 1»\n") == "Nessuna: ho tirato 1"
    assert pulisci('"Nessuna: x"') == "Nessuna: x"
    assert pulisci("“Nessuna: x”") == "Nessuna: x"
    assert pulisci("«Nessuna» di queste") == "«Nessuna» di queste"


def test_emoji():
    assert emoji("✅ Martedì si può fare! 😬") == {"✅", "😬"}
    assert emoji("«Nessuna» — 14/10") == set()
    assert emoji("riposi forzati \U0001f2b6") == {"\U0001f2b6"}  # non assegnato


def test_una_risposta_con_i_fatti_passa():
    assert controlla_risposta("Per martedì manca Pippo", {MARTEDI, GIOVEDI}) == []
    assert controlla_risposta("Il 22/10, cioè giovedi", {MARTEDI, GIOVEDI}, ammesse=set()) == []


def test_una_risposta_che_inventa():
    def controlla(r: str) -> list[str]:
        return controlla_risposta(r, {MARTEDI}, ammesse=set())

    assert controlla("Si gioca sabato!") == ["giorno non nei fatti: sabato"]
    assert controlla("Si gioca il 24/10") == ["data non nei fatti: 24/10"]
    assert controlla("Si gioca il 24 ottobre") == ["data non nei fatti: 24/10"]
    assert controlla("Usa /chiudi rimanda") == ["contiene un comando: /chiudi"]
    assert controlla("Ci sentiamo alle 20!") == ["orario inventato: alle 20"]
    assert controlla("Si comincia alle 20:30") == ["orario inventato: alle 20:30"]
    assert controlla("Verso le 20:30?") == ["orario inventato: Verso le 20:30"]
    assert controlla("Certo 🎉") == ["emoji non ammesse: 🎉"]
    assert controlla("a" * 401) == ["troppo lunga: 401 su 400"]


def test_la_battuta_senza_fatti_ne_altri_nomi():
    assert (
        controlla_battuta("Sveglissimo, Sese!", soprannomi_vietati=["pippo"], ammesse=set()) == []
    )
    assert controlla_battuta("Ci vediamo martedì", soprannomi_vietati=[], ammesse=set()) == [
        "giorno non nei fatti: martedì"
    ]
    assert controlla_battuta("Chiedi a Pippo", soprannomi_vietati=["pippo"], ammesse=set()) == [
        "nomina: pippo"
    ]
    assert controlla_battuta("a" * 201, soprannomi_vietati=[], ammesse=set()) == [
        "troppo lunga: 201 su 200"
    ]


def test_i_giorni_e_le_date_nominati():
    assert giorni_in("Sabato si può? E giovedi?") == {"sabato", "giovedì"}
    assert giorni_in("Gio, a che ora?") == set()
    assert date_in("Il 15/10 o il 16.10") == {(15, 10), (16, 10)}
    assert date_in("Giovedì 15 Ottobre") == {(15, 10)}  # la stessa data, a parole


def test_la_data_con_il_giorno_della_settimana_e_senza_il_mese():
    assert date_in("Abe, venerdì 16? Ci manca il master") == {(16, None)}
    assert date_in("È venerdi 16.") == {(16, None)}
    assert date_in("Venerdì 16/10") == {(16, 10)}
    assert date_in("Venerdì 16 ottobre") == {(16, 10)}


def test_la_data_senza_il_mese_e_quella_del_giorno_del_mese():
    risposta = "Il sondaggio è ancora aperto. Venerdì 16/10: manca il master."
    assert (
        controlla_riscrittura(
            "Abe, venerdì 16 manca il master.",
            risposta,
            soprannomi=SOPRANNOMI,
            nomi_ammessi={"abe"},
        )
        == []
    )
    assert controlla_riscrittura(
        "Abe, venerdì 17 manca il master.", risposta, soprannomi=SOPRANNOMI, nomi_ammessi={"abe"}
    ) == ["manca la data: 16/10", "data in più: 17"]
    assert controlla_risposta("Giovedì 22 si può fare", {GIOVEDI}) == []
    assert controlla_risposta("Giovedì 23 si può fare", {GIOVEDI}) == ["data non nei fatti: 23"]


def test_i_giorni_nominati_da_chi_scrive_sono_ammessi():
    assert (
        controlla_risposta(
            "Sabato non è nel sondaggio.", {MARTEDI}, ammesse=set(), giorni_ammessi={"sabato"}
        )
        == []
    )


QUASI = "Martedì ci siamo quasi. Pippo, ci sei?"


def test_una_riscrittura_con_gli_stessi_fatti_passa():
    assert (
        controlla_riscrittura("Pippo, martedì manca solo il tuo sì!", QUASI, soprannomi=SOPRANNOMI)
        == []
    )
    assert controlla_riscrittura(
        "✅ Giovedì 15/10 si gioca!", "🎲 Si gioca giovedì 15/10.", soprannomi=SOPRANNOMI
    ) == ["emoji non ammesse: ✅"]


def test_una_riscrittura_che_perde_o_aggiunge_fatti():
    def controlla(riscritta: str, originale: str = QUASI) -> list[str]:
        return controlla_riscrittura(riscritta, originale, soprannomi=SOPRANNOMI)

    assert controlla("Ci siamo quasi. Pippo, ci sei?") == ["manca il giorno: martedì"]
    assert controlla("Martedì o giovedì? Pippo, ci sei?") == ["giorno in più: giovedì"]
    assert controlla("Martedì ci siamo quasi, ci sei?") == ["manca il nome: pippo"]
    assert controlla("Martedì ci siamo quasi. Pippo e Sese, ci siete?") == ["nome in più: sese"]
    assert controlla("Si gioca giovedì 16/10.", "🎲 Si gioca giovedì 15/10.") == [
        "manca la data: 15/10", "data in più: 16/10",
    ]  # fmt: skip
    assert controlla("Martedì ci siamo quasi! Pippo, ci sei?") == ["uguale al testo di oggi"]
    assert controlla("Martedì quasi ci siamo.\nPippo, ci sei?") == ["più di una riga"]
    assert controlla("Martedì " + "a" * 70 + " Pippo") == []  # nessun limite di lunghezza, per ora


def test_la_data_a_parole_e_la_stessa():
    originale = "🎲 Si gioca giovedì 15/10."
    assert (
        controlla_riscrittura(
            "🎲 Giovedì 15 ottobre, si torna a giocare!", originale, soprannomi=SOPRANNOMI
        )
        == []
    )


def test_per_le_risposte_il_nome_di_chi_scrive_e_l_uguale_sono_ammessi():
    risposta = "Questo non lo so: chiedi a Gio."
    assert controlla_riscrittura(
        "Sem, non lo so: chiedi a Gio!", risposta, soprannomi=SOPRANNOMI
    ) == ["nome in più: sem"]
    assert (
        controlla_riscrittura(
            "Sem, non lo so: chiedi a Gio!", risposta, soprannomi=SOPRANNOMI, nomi_ammessi={"sem"}
        )
        == []
    )
    assert (
        controlla_riscrittura(risposta, risposta, soprannomi=SOPRANNOMI, uguale_ammesso=True) == []
    )
