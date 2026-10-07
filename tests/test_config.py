from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from prossima import config
from prossima.config import ConfigurazioneErrata
from tests.tavolo import ROSTER

RADICE = Path(__file__).resolve().parents[1]

PERSONA = """
[[persona]]
soprannome = "{soprannome}"
telegram_id = {telegram_id}
ruolo = "{ruolo}"
chiude = {chiude}
"""


def roster(*persone: dict) -> str:
    return "".join(PERSONA.format(**p) for p in persone)


def p(soprannome="gio", telegram_id=100000001, ruolo="master", chiude="true"):
    return {"soprannome": soprannome, "telegram_id": telegram_id, "ruolo": ruolo, "chiude": chiude}


def test_il_roster_d_esempio_e_quello_delle_prove():
    assert config.leggi_roster(RADICE / "config.esempio" / "roster.toml") == ROSTER


def test_chiude_e_falso_se_manca():
    testo = roster(p()) + '[[persona]]\nsoprannome = "emi"\ntelegram_id = 3\nruolo = "giocatore"\n'
    assert [x.chiude for x in config.roster_da_toml(testo).persone] == [True, False]


@pytest.mark.parametrize(
    "testo, messaggio",
    [
        ("[[persona]\n", "non è TOML valido"),
        ("", "nessuna persona"),
        ("[gruppi]\nparty = -1\n" + roster(p()), "sezioni sconosciute: gruppi"),
        (roster(p()).replace("chiude", "chuide"), "chiavi sconosciute: chuide"),
        (roster(p(soprannome=" gio")), "soprannome manca, o ha spazi intorno"),
        (roster(p(telegram_id='"100000001"')), "telegram_id deve essere un numero intero positivo"),
        (roster(p(telegram_id="true")), "telegram_id deve essere un numero intero positivo"),
        (roster(p(telegram_id=-5)), "telegram_id deve essere un numero intero positivo"),
        (roster(p(ruolo="admin")), "ruolo 'admin' sconosciuto"),
        (roster(p(chiude='"sì"')), "chiude deve essere true o false"),
        (roster(p(), p(telegram_id=2, ruolo="giocatore")), "il soprannome 'gio' compare due volte"),
        (roster(p(), p(soprannome="abe", ruolo="giocatore")), "il telegram_id 100000001 compare due volte"),
        (roster(p(ruolo="giocatore")), "serve esattamente un master, ce ne sono 0"),
        (roster(p(), p(soprannome="abe", telegram_id=2)), "serve esattamente un master, ce ne sono 2"),
        (roster(p(chiude="false")), "nessuno può chiudere il sondaggio"),
    ],
)
def test_un_roster_sbagliato_ferma_l_avvio_e_dice_perche(testo, messaggio):
    with pytest.raises(ConfigurazioneErrata, match=messaggio):
        config.roster_da_toml(testo, "config/roster.toml")


def test_l_errore_dice_quale_persona():
    testo = roster(p(), p(soprannome="emi", telegram_id=3, ruolo="cuoco"))
    with pytest.raises(ConfigurazioneErrata, match=r"config/roster.toml, persona 2 \(emi\)"):
        config.roster_da_toml(testo, "config/roster.toml")


def test_un_roster_che_non_c_e(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="non si legge"):
        config.leggi_roster(tmp_path / "manca.toml")


def ambiente(tmp_path, **cambi):
    env = {
        "PV_BOT_TOKEN": "123:SEGRETO",
        "PV_GRUPPO": "-1000000000001",
        "PV_ROSTER": str(RADICE / "config.esempio" / "roster.toml"),
        "PV_DB": str(tmp_path / "prossima.sqlite"),
        "PV_BATTITO": str(tmp_path / "battito"),
        "PV_FUSO": "Europe/Zurich",
    }
    env.update(cambi)
    return env


def test_le_impostazioni_dall_ambiente(tmp_path):
    imp = config.da_ambiente(ambiente(tmp_path))
    assert imp == config.Impostazioni(
        token_bot="123:SEGRETO",
        gruppo=-1000000000001,
        roster=ROSTER,
        db=tmp_path / "prossima.sqlite",
        battito=tmp_path / "battito",
        fuso=ZoneInfo("Europe/Zurich"),
    )


def test_il_fuso_predefinito_e_zurigo(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path, PV_FUSO="")).fuso == ZoneInfo("Europe/Zurich")


@pytest.mark.parametrize("nome", ["PV_BOT_TOKEN", "PV_GRUPPO", "PV_ROSTER", "PV_DB", "PV_BATTITO"])
def test_una_variabile_che_manca(tmp_path, nome):
    with pytest.raises(ConfigurazioneErrata, match=f"{nome} manca"):
        config.da_ambiente(ambiente(tmp_path, **{nome: "  "}))


@pytest.mark.parametrize(
    ("nome", "atteso"),
    [("PV_GRUPPO", "PV_GRUPPO deve essere un numero intero"), ("PV_FUSO", "PV_FUSO: fuso orario sconosciuto")],
)
def test_valori_malformati_senza_eco_del_valore(tmp_path, nome, atteso):
    """Un valore sbagliato non si ripete nel messaggio: se due variabili sono
    scambiate, il token finirebbe nel log (§4)."""
    with pytest.raises(ConfigurazioneErrata, match=atteso) as errore:
        config.da_ambiente(ambiente(tmp_path, **{nome: "123:SEGRETO"}))
    assert "SEGRETO" not in str(errore.value)


def test_pv_fuso_cartella_tzdata(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="PV_FUSO: fuso orario sconosciuto"):
        config.da_ambiente(ambiente(tmp_path, PV_FUSO="Europe"))


def test_roster_non_utf8(tmp_path):
    file_latin1 = tmp_path / "roster.toml"
    file_latin1.write_bytes("[[persona]]\nsoprannome = \"gio\"\ntelegram_id = 1\nruolo = \"master\"\nchiude = true\n# «è»\n".encode("latin-1"))
    with pytest.raises(ConfigurazioneErrata, match="non è UTF-8"):
        config.leggi_roster(file_latin1)


def test_token_bot_non_in_repr(tmp_path):
    imp = config.da_ambiente(ambiente(tmp_path))
    r = repr(imp)
    assert "123:SEGRETO" not in r


def test_una_variabile_che_manca_chiave_assente(tmp_path):
    env = {
        "PV_BOT_TOKEN": "123:SEGRETO",
        "PV_GRUPPO": "-1000000000001",
        "PV_ROSTER": str(RADICE / "config.esempio" / "roster.toml"),
        "PV_DB": str(tmp_path / "prossima.sqlite"),
        "PV_BATTITO": str(tmp_path / "battito"),
        "PV_FUSO": "Europe/Zurich",
    }
    for nome in ["PV_BOT_TOKEN", "PV_GRUPPO", "PV_ROSTER", "PV_DB", "PV_BATTITO"]:
        env_senza = {k: v for k, v in env.items() if k != nome}
        with pytest.raises(ConfigurazioneErrata, match=f"{nome} manca"):
            config.da_ambiente(env_senza)


def test_ruolo_mancante_nel_roster():
    testo = roster(p()) + '[[persona]]\nsoprannome = "emi"\ntelegram_id = 3\n'
    with pytest.raises(ConfigurazioneErrata, match=r"persona 2 \(emi\).*ruolo.*manca"):
        config.roster_da_toml(testo, "config/roster.toml")
