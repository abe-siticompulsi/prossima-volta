from datetime import UTC, datetime, timedelta

import pytest

from prossima import regole
from prossima.regole import Fatti, Impossibile, NonPiu, Possibile, Quasi, Voto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, PIPPO, ROSTER, SEM, SESE, d, stato


def ids(*persone):
    return frozenset(p.telegram_id for p in persone)


# --- chi conta


def test_il_roster():
    assert ROSTER.master == GIO
    assert ROSTER.giocatori == (ABE, EMI, SEM, SESE, PIPPO)
    assert ROSTER.chi_chiude == (GIO, ABE)
    assert ROSTER.per_id(SEM.telegram_id) == SEM
    assert ROSTER.per_id(ESTRANEO) is None
    assert ROSTER.per_id(None) is None


def test_ha_votato_chi_ha_una_risposta_non_vuota_anche_solo_nessuna():
    s = stato(gio="14/10", abe="nessuna", emi="")
    assert s.votanti == (GIO, ABE)
    assert s.senza_voto == (EMI, SEM, SESE, PIPPO)


def test_presenti_nell_ordine_del_roster_e_nessuna_non_toglie_le_date():
    s = stato(sem="14/10", gio="14/10 nessuna", abe="16/10")
    assert s.presenti(d("14/10")) == (GIO, SEM)


def test_chi_non_e_nel_roster_non_conta():
    s = stato(estraneo="14/10", gio="14/10")
    assert s.presenti(d("14/10")) == (GIO,)
    assert s.votanti == (GIO,)


def test_le_opzioni_di_telegram_come_voto():
    date_ = [d("14/10"), d("16/10")]
    assert regole.voto_da_opzioni(date_, [0]) == Voto(frozenset({d("14/10")}))
    assert regole.voto_da_opzioni(date_, [1, 2]) == Voto(frozenset({d("16/10")}), nessuna=True)
    assert regole.voto_da_opzioni(date_, [2]) == Voto(nessuna=True)
    assert regole.voto_da_opzioni(date_, [7]) == Voto()
    assert not regole.voto_da_opzioni(date_, []).dato


def test_i_conteggi_per_opzione_come_quelli_di_stop_poll():
    date_ = [d("14/10"), d("16/10")]
    voti = [Voto(frozenset(date_)), Voto(frozenset({d("16/10")}), nessuna=True), Voto()]
    assert regole.conteggi_per_opzione(date_, voti) == [1, 2, 1]
    assert regole.conteggi_per_opzione(date_, []) == [0, 0, 0]


# --- possibile, quasi, fuori: il 14/10 in ogni riga


@pytest.mark.parametrize(
    "voti, possibile, quasi, fuori",
    [
        # il master e quattro giocatori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), True, False, False),
        # quattro giocatori, il master non ha ancora votato
        (dict(abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, False),
        # il master e tre giocatori, pippo non ha votato: quasi, non fuori (3 + 1)
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="16/10"), False, True, False),
        # il master e tre giocatori, hanno votato tutti: quasi, e fuori (3 + 0)
        (
            dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="16/10", pippo="nessuna"),
            False, True, True,
        ),
        # il master ha votato un'altra data
        (dict(gio="16/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, True),
        # il master ha votato solo «Nessuna»
        (dict(gio="nessuna", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, True),
        # due giocatori presenti e due senza voto: 2 + 2 non è fuori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="16/10"), False, False, False),
        # due giocatori presenti e uno senza voto: 2 + 1 è fuori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="16/10", sese="16/10"), False, False, True),
        # il master non ha votato; tre giocatori sulla data e due su un'altra: 3 + 0 < 4
        (dict(abe="14/10", emi="14/10", sem="14/10", sese="16/10", pippo="16/10"), False, False, True),
        # nessun voto
        ({}, False, False, False),
    ],
)
def test_possibile_quasi_fuori(voti, possibile, quasi, fuori):
    c = regole.conta(stato(**voti), d("14/10"))
    assert (c.possibile, c.quasi, c.fuori) == (possibile, quasi, fuori)


def test_il_conteggio_di_una_data():
    s = stato(gio="14/10", abe="14/10", emi="14/10", sem="16/10", estraneo="14/10")
    assert regole.conta(s, d("14/10")) == regole.Conteggio(
        giorno=d("14/10"),
        presenti=(GIO, ABE, EMI),
        master_presente=True,
        master_ha_votato=True,
        giocatori_presenti=2,
        giocatori_senza_voto=2,
        votanti=4,
    )


def test_le_date_possibili():
    s = stato(gio="14/10 16/10", abe="14/10 16/10", emi="14/10", sem="14/10", sese="14/10 16/10")
    assert regole.possibili(s) == [d("14/10")]


def test_impossibile():
    assert not regole.impossibile(stato())
    # il master ha votato senza scegliere una data: tutte fuori
    assert regole.impossibile(stato(gio="nessuna"))
    # in nessuna data i giocatori presenti più quelli senza voto arrivano a quattro
    assert regole.impossibile(
        stato(gio="14/10 16/10", abe="14/10", emi="16/10", sem="nessuna", sese="nessuna")
    )
    # una data ancora in gioco basta: il 14/10 ha il master e cinque giocatori senza voto
    assert not regole.impossibile(stato(gio="14/10"))


# --- gli annunci

QUASI_14 = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10")
POSSIBILE_14 = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10")


def test_quasi_una_volta_con_chi_non_ha_ancora_votato():
    s = stato(**QUASI_14)
    annunci = regole.annunci_da_fare(s, Fatti())
    assert annunci == [Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO))]
    assert regole.annunci_da_fare(s, regole.dopo(Fatti(), annunci[0])) == []


def test_possibile_una_volta():
    s = stato(**POSSIBILE_14)
    annunci = regole.annunci_da_fare(s, Fatti())
    assert annunci == [Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE))]
    assert regole.annunci_da_fare(s, regole.dopo(Fatti(), annunci[0])) == []


def annunci_in_sequenza(*voti_uno_dopo_l_altro):
    """Gli annunci di un sondaggio i cui voti passano per questi stati, ognuno
    registrato come fatto prima del successivo."""
    fatti, annunciati = Fatti(), []
    for voti in voti_uno_dopo_l_altro:
        for annuncio in regole.annunci_da_fare(stato(**voti), fatti):
            annunciati.append(annuncio)
            fatti = regole.dopo(fatti, annuncio)
    return annunciati


def test_il_quasi_non_si_ripete_neanche_dopo_un_possibile():
    annunci = annunci_in_sequenza(QUASI_14, POSSIBILE_14, QUASI_14, QUASI_14)
    assert len(annunci) == 3
    assert annunci == [
        Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO)),
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
        NonPiu(d("14/10"), (SESE,)),
    ]


def test_non_piu_possibile_con_chi_ha_tolto_il_voto():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    s = stato(**{**POSSIBILE_14, "sem": "", "sese": "nessuna"})
    assert regole.annunci_da_fare(s, fatti) == [NonPiu(d("14/10"), (SEM, SESE))]


def test_non_piu_possibile_e_poi_quasi_se_manca_uno_solo():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    s = stato(**{**POSSIBILE_14, "sem": "16/10"})
    assert regole.annunci_da_fare(s, fatti) == [
        NonPiu(d("14/10"), (SEM,)),
        Quasi(d("14/10"), (GIO, ABE, EMI, SESE), (PIPPO,)),
    ]


def test_non_piu_possibile_dopo_una_ripresa_non_sa_chi():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    fatti = regole.dopo(fatti, regole.Ripresa())
    assert fatti.possibili == {d("14/10"): None}
    s = stato(**{**POSSIBILE_14, "sem": "", "sese": ""})
    assert regole.annunci_da_fare(s, fatti) == [NonPiu(d("14/10"), ())]


def test_possibile_di_nuovo_dopo_un_non_piu():
    assert annunci_in_sequenza(POSSIBILE_14, {**POSSIBILE_14, "sem": ""}, POSSIBILE_14) == [
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
        NonPiu(d("14/10"), (SEM,)),
        Quasi(d("14/10"), (GIO, ABE, EMI, SESE), (SEM, PIPPO)),
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
    ]


# hanno votato tutti; il 14/10 ha il master e tre giocatori, il 16/10 non ha il master
CON_TRE = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10 16/10", sese="16/10", pippo="16/10")


def test_impossibile_con_le_date_in_cui_si_gioca_in_tre():
    annunci = regole.annunci_da_fare(stato(**CON_TRE), Fatti())
    assert annunci == [
        Quasi(d("14/10"), (GIO, ABE, EMI, SEM), ()),
        Impossibile(((d("14/10"), (GIO, ABE, EMI, SEM)),)),
    ]


def test_impossibile_senza_date_in_tre_compreso_il_master_che_vota_solo_nessuna():
    assert regole.annunci_da_fare(stato(gio="nessuna"), Fatti()) == [Impossibile(())]


def test_con_tre_esclude_il_master_con_due_giocatori():
    s = stato(gio="14/10", abe="14/10", emi="14/10", sem="16/10", sese="16/10", pippo="16/10")
    assert regole.impossibile(s)
    assert regole.annunci_da_fare(s, Fatti()) == [regole.Impossibile(())]


def test_impossibile_di_nuovo_solo_dopo_un_rientro():
    s = stato(gio="nessuna")
    fatti = regole.dopo(Fatti(), Impossibile(()))
    assert regole.annunci_da_fare(s, fatti) == []
    assert not regole.rientrato(s, fatti)
    # il master toglie il voto: le date tornano in gioco
    tornato = stato(gio="")
    assert regole.rientrato(tornato, fatti)
    fatti = regole.dopo(fatti, regole.Rientro())
    assert not fatti.impossibile
    assert regole.annunci_da_fare(s, fatti) == [Impossibile(())]


def test_rientrato_falso_senza_impossibile_annunciato():
    assert not regole.rientrato(stato(), Fatti())


def test_dopo_registra_ogni_evento():
    f = regole.dopo(Fatti(), Quasi(d("14/10"), (), ()))
    f = regole.dopo(f, Possibile(d("16/10"), (GIO, ABE)))
    assert f == Fatti(quasi=frozenset({d("14/10")}), possibili={d("16/10"): ids(GIO, ABE)})
    f = regole.dopo(f, NonPiu(d("16/10"), (ABE,)))
    assert f.possibili == {}
    assert regole.dopo(f, Impossibile(())).impossibile


def test_il_buio_comincia_dopo_23_ore():
    prima = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    assert not regole.al_buio(None, prima)
    assert not regole.al_buio(prima, prima + timedelta(hours=23))
    assert regole.al_buio(prima, prima + timedelta(hours=23, seconds=1))
