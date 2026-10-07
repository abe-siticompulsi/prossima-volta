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


def test_senza_parole_i_sette_giorni_della_settimana_seguente():
    assert regole.date_del_comando([], OGGI) == [d("13/10") + timedelta(days=i) for i in range(7)]


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
    date_ = regole.date_del_comando([], oggi)
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
    "parola", ["32/10", "31/11", "14-10", "domani", "14/10/25", "1/2/3/4", "lunedì", "29/2/2026"]
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


SONDAGGIO = [d("14/10"), d("16/10")]


@pytest.mark.parametrize("parola", ["14/10", "14.10", "14/10/2025", "mar", "MAR"])
def test_chiudere_tenendo_una_data_del_sondaggio(parola):
    assert regole.data_da_chiudere(parola, SONDAGGIO) == d("14/10")


@pytest.mark.parametrize(
    "parola, scritta", [("15/10", "15/10"), ("05.10", "5/10"), ("14/10/2026", "14/10/2026"), ("Ven", "ven")]
)
def test_chiudere_con_una_data_che_non_era_nel_sondaggio(parola, scritta):
    with pytest.raises(regole.NonNelSondaggio) as rifiuto:
        regole.data_da_chiudere(parola, SONDAGGIO)
    assert rifiuto.value.scritta == scritta


def test_chiudere_con_un_giorno_che_nel_sondaggio_compare_due_volte():
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.data_da_chiudere("mar", [d("14/10"), d("21/10")])
    assert rifiuto.value.parola == "mar"


def test_chiudere_con_una_parola_strana():
    with pytest.raises(regole.NonCapisco):
        regole.data_da_chiudere("boh", SONDAGGIO)


def test_rimandare_tiene_i_giorni_della_settimana_nella_settimana_dopo():
    assert regole.date_rimandate([d("14/10"), d("16/10")]) == [d("21/10"), d("23/10")]
    settimana = regole.date_del_comando([], OGGI)
    assert regole.date_rimandate(settimana) == [d("20/10") + timedelta(days=i) for i in range(7)]
    # su due settimane: la settimana dopo quella dell'ultima data
    assert regole.date_rimandate([d("14/10"), d("23/10")]) == [d("28/10"), d("30/10")]
