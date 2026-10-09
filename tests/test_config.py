from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from prossima import config, testi
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
        frasi=testi.FRASI_NESSUNA,
        domanda=testi.DOMANDA,
        giorni=(0, 1, 2, 3, 4, 6),
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


def test_senza_pv_frasi_le_frasi_predefinite(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path)).frasi == testi.FRASI_NESSUNA
    assert config.da_ambiente(ambiente(tmp_path, PV_FRASI="  ")).frasi == testi.FRASI_NESSUNA


def test_le_frasi_da_pv_frasi(tmp_path):
    """Una frase per riga; le righe vuote (anche di soli spazi) e quelle che
    cominciano con # non contano; gli spazi intorno a una frase si tolgono. Un #
    dentro la frase resta, e una riga finisce solo con un a capo."""
    frasi = tmp_path / "frasi.txt"
    frasi.write_text(
        "# commento\n\nNessuna: uno\n  Nessuna: due  \r\n \t \n  # altro\nNessuna: tiro #1\nNessuna: a\u2028b",
        encoding="utf-8",
    )
    imp = config.da_ambiente(ambiente(tmp_path, PV_FRASI=str(frasi)))
    assert imp.frasi == ("Nessuna: uno", "Nessuna: due", "Nessuna: tiro #1", "Nessuna: a\u2028b")


def test_le_frasi_con_il_bom_di_utf8(tmp_path):
    frasi = tmp_path / "frasi.txt"
    frasi.write_text("Nessuna: uno\n", encoding="utf-8-sig")
    assert config.leggi_frasi(frasi) == ("Nessuna: uno",)


def test_le_frasi_d_esempio_sono_quelle_predefinite():
    assert config.leggi_frasi(RADICE / "config.esempio" / "frasi.txt") == testi.FRASI_NESSUNA


@pytest.mark.parametrize(
    ("testo", "messaggio"),
    [
        ("# solo commenti\n\n", r"frasi\.txt: nessuna frase"),
        ("Nessuna: uno\n" + "x" * 101 + "\n", r"frasi\.txt, riga 2: la frase è lunga 101 caratteri, il massimo è 100"),
        # 100 caratteri per Python, 101 per Telegram, che conta in UTF-16
        ("x" * 99 + "🎲\n", r"riga 1: la frase è lunga 101 caratteri"),
        ("Nessuna: uno\n# c\nNessuna: uno\n", r"frasi\.txt, riga 3: la stessa frase è già alla riga 1"),
        # la riga è quella che mostra l'editor: contano solo gli a capo
        ("Nessuna: a\x85b\n" + "x" * 101 + "\n", r"frasi\.txt, riga 2: la frase è lunga 101"),
    ],
)
def test_frasi_sbagliate(tmp_path, testo, messaggio):
    frasi = tmp_path / "frasi.txt"
    frasi.write_text(testo, encoding="utf-8")
    with pytest.raises(ConfigurazioneErrata, match=messaggio):
        config.da_ambiente(ambiente(tmp_path, PV_FRASI=str(frasi)))


def test_le_frasi_al_limite_vanno_bene(tmp_path):
    frasi = tmp_path / "frasi.txt"
    frasi.write_text("x" * 98 + "🎲\n", encoding="utf-8")
    assert config.leggi_frasi(frasi) == ("x" * 98 + "🎲",)


def test_frasi_che_non_si_leggono(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match=r"le frasi .*manca\.txt non si leggono"):
        config.da_ambiente(ambiente(tmp_path, PV_FRASI=str(tmp_path / "manca.txt")))
    latin1 = tmp_path / "latin1.txt"
    latin1.write_bytes("Nessuna: è\n".encode("latin-1"))
    with pytest.raises(ConfigurazioneErrata, match=r"le frasi .*latin1\.txt non sono UTF-8"):
        config.leggi_frasi(latin1)


@pytest.mark.parametrize("riga", ["PV_BOT_TOKEN=123:SEGRETO", 'soprannome = "SEGRETO"'])
def test_un_file_di_configurazione_al_posto_delle_frasi(tmp_path, riga):
    """`PV_FRASI` che indica per sbaglio `prossima.env` o il roster: il token
    non deve finire in un sondaggio nel gruppo, e nemmeno nel messaggio."""
    sbagliato = tmp_path / "prossima.env"
    sbagliato.write_text(f"# commento\n{riga}\n", encoding="utf-8")
    with pytest.raises(
        ConfigurazioneErrata, match=r"prossima\.env, riga 2: sembra una riga di configurazione"
    ) as errore:
        config.da_ambiente(ambiente(tmp_path, PV_FRASI=str(sbagliato)))
    assert "SEGRETO" not in str(errore.value)


def test_l_env_d_esempio_non_passa_per_un_file_di_frasi():
    with pytest.raises(ConfigurazioneErrata, match="sembra una riga di configurazione"):
        config.leggi_frasi(RADICE / "config.esempio" / "prossima.env")
    with pytest.raises(ConfigurazioneErrata, match="sembra una riga di configurazione"):
        config.leggi_frasi(RADICE / "config.esempio" / "roster.toml")


def test_senza_pv_domanda_la_domanda_predefinita(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path)).domanda == "Prossima volta?"
    assert config.da_ambiente(ambiente(tmp_path, PV_DOMANDA="  ")).domanda == "Prossima volta?"


def test_la_domanda_da_pv_domanda(tmp_path):
    imp = config.da_ambiente(ambiente(tmp_path, PV_DOMANDA="  Quando si gioca? 🎲 "))
    assert imp.domanda == "Quando si gioca? 🎲"


def test_una_domanda_oltre_300_caratteri(tmp_path):
    """Il limite di Telegram per la domanda di un sondaggio, contato in UTF-16
    come le opzioni: 299 lettere e un'emoji fanno 301. Il messaggio non ripete
    il valore, come per le altre variabili."""
    config.da_ambiente(ambiente(tmp_path, PV_DOMANDA="x" * 298 + "🎲"))
    with pytest.raises(ConfigurazioneErrata, match="PV_DOMANDA: la domanda è lunga 301 caratteri, il massimo è 300") as errore:
        config.da_ambiente(ambiente(tmp_path, PV_DOMANDA="x" * 299 + "🎲"))
    assert "xxx" not in str(errore.value)


def test_senza_pv_giorni_tutti_tranne_il_sabato(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path)).giorni == (0, 1, 2, 3, 4, 6)
    assert config.da_ambiente(ambiente(tmp_path, PV_GIORNI="  ")).giorni == (0, 1, 2, 3, 4, 6)


def test_i_giorni_da_pv_giorni(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path, PV_GIORNI="ven lun  mercoledì lun")).giorni == (0, 2, 4)


def test_un_giorno_sconosciuto_in_pv_giorni(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="PV_GIORNI: i giorni si scrivono") as errore:
        config.da_ambiente(ambiente(tmp_path, PV_GIORNI="lun SEGRETO"))
    assert "SEGRETO" not in str(errore.value)
