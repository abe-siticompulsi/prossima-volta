from datetime import date, timedelta

import pytest

from prossima import regole
from tests.tavolo import OGGI, d


def test_le_etichette_nel_formato_italiano():
    assert regole.breve(d("1/11")) == "1/11"
    assert regole.etichetta(d("14/10")) == "mar 14/10"
    assert regole.etichetta(d("5/1", 2026)) == "lun 5/1"
    assert regole.etichetta_intera(d("14/10")) == "martedì 14/10"


def test_ogni_giorno_ha_il_suo_nome():
    lunedi = d("13/10")
    settimana = [lunedi + timedelta(days=i) for i in range(7)]
    assert [regole.etichetta(g) for g in settimana] == [
        "lun 13/10", "mar 14/10", "mer 15/10", "gio 16/10", "ven 17/10", "sab 18/10", "dom 19/10",
    ]
    assert [regole.etichetta_intera(g) for g in settimana] == [
        "lunedì 13/10", "martedì 14/10", "mercoledì 15/10", "giovedì 16/10",
        "venerdì 17/10", "sabato 18/10", "domenica 19/10",
    ]


def test_senza_parole_i_giorni_di_sempre_senza_il_sabato():
    assert regole.date_del_comando([], OGGI) == [
        d(g) for g in ("13/10", "14/10", "15/10", "16/10", "17/10", "19/10")
    ]


def test_i_giorni_di_sempre_si_scelgono():
    assert regole.date_del_comando([], OGGI, (1, 0)) == [d("13/10"), d("14/10")]


@pytest.mark.parametrize("parole", [["con", "sabato"], ["con", "sab"], ["CON", "Sabato"]])
def test_con_aggiunge_un_giorno_a_quelli_di_sempre(parole):
    assert regole.date_del_comando(parole, OGGI) == [d("13/10") + timedelta(days=i) for i in range(7)]


def test_con_un_giorno_che_c_e_gia_non_cambia_niente():
    assert regole.date_del_comando(["con", "dom"], OGGI) == regole.date_del_comando([], OGGI)


@pytest.mark.parametrize(
    "parole", [["con"], ["con", "14/10"], ["con", "xyz"], ["mar", "con", "sab"], ["con", "sab", "con"]]
)
def test_con_usato_male(parole):
    with pytest.raises(regole.ConSbagliato):
        regole.date_del_comando(parole, OGGI)


@pytest.mark.parametrize("scritta", ["martedì", "martedi", "Martedì", "MARTEDI", "mar"])
def test_i_giorni_per_intero(scritta):
    assert regole.date_del_comando([scritta], OGGI) == [d("14/10")]


@pytest.mark.parametrize("scritta", ["martedì", "Martedi", "mar"])
def test_chiudere_con_il_giorno_per_intero(scritta):
    assert regole.data_da_chiudere(scritta, [d("14/10"), d("16/10")], OGGI) == d("14/10")


@pytest.mark.parametrize(
    "oggi, lunedi",
    [
        (date(2025, 10, 13), date(2025, 10, 20)),  # di lunedì: non la settimana in corso
        (date(2025, 10, 12), date(2025, 10, 13)),  # di domenica: quella che comincia domani
        (date(2025, 12, 31), date(2026, 1, 5)),  # a cavallo dell'anno
        (date(2025, 12, 28), date(2025, 12, 29)),  # domenica 28/12: dal 29/12 al 4/1
    ],
)
def test_la_settimana_seguente(oggi, lunedi):
    date_ = regole.date_del_comando([], oggi, range(7))
    assert date_ == [lunedi + timedelta(days=i) for i in range(7)]


def test_i_giorni_della_settimana_seguente():
    assert regole.date_del_comando(["mar", "gio", "sab"], OGGI) == [d("14/10"), d("16/10"), d("18/10")]
    assert regole.date_del_comando(["Mar", "GIO"], OGGI) == [d("14/10"), d("16/10")]


@pytest.mark.parametrize("scritta", ["14/10", "14.10", "14/10/2025", "14.10.2025", "14/10.2025"])
def test_le_date_con_la_barra_o_con_il_punto(scritta):
    assert regole.date_del_comando([scritta], OGGI) == [d("14/10")]


def test_le_date_si_ordinano_e_i_doppioni_si_tolgono():
    assert regole.date_del_comando(["16/10", "14/10", "16.10"], OGGI) == [d("14/10"), d("16/10")]


def test_giorni_e_date_si_mescolano():
    assert regole.date_del_comando(["gio", "14/10", "16/10", "21/10"], OGGI) == [
        d("14/10"), d("16/10"), d("21/10"),
    ]


def test_senza_anno_la_prossima_volta_che_la_data_arriva_oggi_compreso():
    assert regole.date_del_comando(["7/10"], OGGI) == [d("7/10")]
    assert regole.date_del_comando(["5/1"], OGGI) == [d("5/1", 2026)]
    assert regole.date_del_comando(["1/4"], OGGI) == [d("1/4", 2026)]
    assert regole.date_del_comando(["2/1"], date(2025, 12, 28)) == [d("2/1", 2026)]


def test_una_data_passata_da_poco_e_passata_non_dell_anno_dopo():
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["3/10"], OGGI)
    assert rifiuto.value.scritta == "3/10"
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["28.12"], date(2026, 1, 5))
    assert rifiuto.value.scritta == "28/12"


def test_una_data_con_l_anno_passato():
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["14.10.2024"], OGGI)
    assert rifiuto.value.scritta == "14/10/2024"


def test_oggi_non_e_passata():
    assert regole.date_del_comando(["7/10/2025"], OGGI) == [OGGI]


@pytest.mark.parametrize(
    "parola", ["32/10", "31/11", "14-10", "domani", "14/10/25", "1/2/3/4", "lunedìì", "29/2/2026"]
)
def test_una_parola_non_capita(parola):
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.date_del_comando([parola], OGGI)
    assert rifiuto.value.parola == parola


def test_la_prima_parola_sbagliata_ferma_tutto():
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.date_del_comando(["mar", "boh", "32/10"], OGGI)
    assert rifiuto.value.parola == "boh"


def test_al_massimo_10_date_contate_senza_doppioni():
    dieci = [f"{g}/10" for g in range(13, 23)]
    assert len(regole.date_del_comando(dieci, OGGI)) == 10
    assert len(regole.date_del_comando([*dieci, "13.10"], OGGI)) == 10
    with pytest.raises(regole.TroppeDate):
        regole.date_del_comando([*dieci, "23/10"], OGGI)


@pytest.mark.parametrize(
    "parola",
    [
        "١٤/١٠",  # cifre arabo-indiche
        "１４/１０",  # cifre a larghezza piena
        "१४/१०/२०२५",  # cifre devanagari
        "14/10/２０２５",  # l'anno a metà
    ],
)
def test_le_cifre_che_non_sono_ascii_non_sono_date(parola):
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.date_del_comando([parola], OGGI)
    assert rifiuto.value.parola == parola
    with pytest.raises(regole.NonCapisco):
        regole.data_da_chiudere(parola, [d("14/10")], OGGI)


def test_una_data_oltre_un_anno_da_oggi_e_troppo_lontana():
    # lo stesso giorno dell'anno dopo è ancora buono, il giorno dopo no
    assert regole.date_del_comando(["7/10/2026"], OGGI) == [d("7/10", 2026)]
    for scritta, attesa in [("8/10/2026", "8/10/2026"), ("14.10.2052", "14/10/2052")]:
        with pytest.raises(regole.DataTroppoLontana) as rifiuto:
            regole.date_del_comando([scritta], OGGI)
        assert rifiuto.value.scritta == attesa
    # il 29/2 non ha lo stesso giorno dell'anno dopo: il limite è il 28/2
    assert regole.date_del_comando(["28/2/2025"], date(2024, 2, 29)) == [date(2025, 2, 28)]
    with pytest.raises(regole.DataTroppoLontana):
        regole.date_del_comando(["1/3/2025"], date(2024, 2, 29))


def test_la_data_troppo_lontana_ferma_anche_il_resto_del_comando():
    with pytest.raises(regole.DataTroppoLontana):
        regole.date_del_comando(["14/10", "14/10/2052"], OGGI)
    # «9999» non fa più arrivare un OverflowError alle date rimandate
    with pytest.raises(regole.DataTroppoLontana):
        regole.date_del_comando(["31/12/9999"], OGGI)


def test_il_29_2_senza_anno_e_il_prossimo_29_febbraio():
    # in un anno non bisestile: il prossimo, qualunque cosa dica l'anno scorso
    assert regole.date_del_comando(["29/2"], date(2027, 12, 1)) == [date(2028, 2, 29)]
    assert regole.date_del_comando(["29.2"], date(2027, 3, 1)) == [date(2028, 2, 29)]
    # e se il prossimo è oltre un anno, la data è troppo lontana, con l'anno
    with pytest.raises(regole.DataTroppoLontana) as rifiuto:
        regole.date_del_comando(["29/2"], OGGI)
    assert rifiuto.value.scritta == "29/2/2028"
    # il secolo non bisestile: dopo il 2096 il prossimo è il 2104
    with pytest.raises(regole.DataTroppoLontana) as rifiuto:
        regole.date_del_comando(["29/2"], date(2097, 1, 1))
    assert rifiuto.value.scritta == "29/2/2104"


def test_il_29_2_senza_anno_in_un_anno_bisestile_segue_la_regola_di_tutte_le_date():
    assert regole.date_del_comando(["29/2"], date(2028, 1, 10)) == [date(2028, 2, 29)]
    assert regole.date_del_comando(["29/2"], date(2028, 2, 29)) == [date(2028, 2, 29)]  # oggi compreso
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["29/2"], date(2028, 3, 10))
    assert rifiuto.value.scritta == "29/2"


SONDAGGIO = [d("14/10"), d("16/10")]


@pytest.mark.parametrize("parola", ["14/10", "14.10", "14/10/2025", "mar", "MAR"])
def test_chiudere_tenendo_una_data_del_sondaggio(parola):
    assert regole.data_da_chiudere(parola, SONDAGGIO, OGGI) == d("14/10")


@pytest.mark.parametrize(
    "parola, scritta", [("15/10", "15/10"), ("05.10", "5/10"), ("14/10/2026", "14/10/2026")]
)
def test_chiudere_con_una_data_che_non_era_nel_sondaggio(parola, scritta):
    with pytest.raises(regole.NonNelSondaggio) as rifiuto:
        regole.data_da_chiudere(parola, SONDAGGIO, OGGI)
    assert rifiuto.value.scritta == scritta


@pytest.mark.parametrize("parola, giorno", [("ven", 4), ("Ven", 4), ("dom", 6)])
def test_chiudere_con_un_giorno_che_non_e_nel_sondaggio(parola, giorno):
    with pytest.raises(regole.GiornoAssente) as rifiuto:
        regole.data_da_chiudere(parola, SONDAGGIO, OGGI)
    assert rifiuto.value.giorno == giorno


def test_chiudere_con_un_giorno_che_nel_sondaggio_compare_due_volte():
    with pytest.raises(regole.GiornoAmbiguo) as rifiuto:
        regole.data_da_chiudere("Mar", [d("14/10"), d("16/10"), d("21/10")], OGGI)
    assert (rifiuto.value.giorno, rifiuto.value.prima_data) == (1, d("14/10"))


def test_il_giorno_di_chiudi_conta_solo_le_date_da_oggi_in_poi():
    mercoledi = d("15/10")
    # un solo martedì futuro: è quello da tenere
    assert regole.data_da_chiudere("mar", [d("14/10"), d("21/10")], mercoledi) == d("21/10")
    # più martedì futuri: l'esempio del messaggio è il primo futuro
    with pytest.raises(regole.GiornoAmbiguo) as rifiuto:
        regole.data_da_chiudere("mar", [d("14/10"), d("21/10"), d("28/10")], mercoledi)
    assert (rifiuto.value.giorno, rifiuto.value.prima_data) == (1, d("21/10"))
    # oggi non è passato
    assert regole.data_da_chiudere("mar", [d("7/10"), d("14/10")], d("14/10")) == d("14/10")


def test_il_giorno_di_chiudi_con_soli_martedi_passati_segue_il_percorso_di_oggi():
    mercoledi = d("15/10")
    # un solo martedì, passato: lo restituisce, ed è il bot a dire «è già passata»
    assert regole.data_da_chiudere("mar", SONDAGGIO, mercoledi) == d("14/10")
    # più martedì, tutti passati: come oggi, serve la data
    with pytest.raises(regole.GiornoAmbiguo) as rifiuto:
        regole.data_da_chiudere("mar", [d("7/10"), d("14/10")], mercoledi)
    assert rifiuto.value.prima_data == d("7/10")
    # un giorno che nel sondaggio non c'è resta assente, passato o no
    with pytest.raises(regole.GiornoAssente):
        regole.data_da_chiudere("ven", SONDAGGIO, mercoledi)


def test_la_data_di_chiudi_scritta_per_intero_non_dipende_da_oggi():
    # una data del sondaggio già passata si restituisce: il rifiuto «è già passata» è del bot
    assert regole.data_da_chiudere("14/10", SONDAGGIO, d("15/10")) == d("14/10")


def test_chiudere_con_una_parola_strana():
    with pytest.raises(regole.NonCapisco):
        regole.data_da_chiudere("boh", SONDAGGIO, OGGI)


def test_il_lunedi_della_settimana():
    assert regole.lunedi(d("13/10")) == d("13/10")
    assert regole.lunedi(d("16/10")) == d("13/10")
    assert regole.lunedi(d("19/10")) == d("13/10")


def test_rimandare_tiene_i_giorni_della_settimana_nella_settimana_dopo():
    assert regole.date_rimandate([d("14/10"), d("16/10")]) == [d("21/10"), d("23/10")]
    settimana = regole.date_del_comando([], OGGI)
    # senza il sabato, come la settimana di partenza
    assert regole.date_rimandate(settimana) == [d(g) for g in ("20/10", "21/10", "22/10", "23/10", "24/10", "26/10")]
    # su due settimane: la settimana dopo quella dell'ultima data
    assert regole.date_rimandate([d("14/10"), d("23/10")]) == [d("28/10"), d("30/10")]
