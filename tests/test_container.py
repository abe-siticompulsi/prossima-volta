"""Il container come lo descrivono Dockerfile e compose.yaml. Docker non gira
nelle prove: qui si controlla che le difese non spariscano per sbaglio; che il
servizio parta davvero così lo dice la guida (docs/messa-in-produzione.md)."""

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
UTENTE = "10001:10001"


def stadi() -> dict[str, str]:
    """Il testo di ogni stadio del Dockerfile, per nome."""
    testo = (RADICE / "Dockerfile").read_text()
    pezzi = re.split(r"^FROM .* AS (\w+)$", testo, flags=re.MULTILINE)
    return dict(zip(pezzi[1::2], pezzi[2::2], strict=True))


def servizio(nome: str) -> str:
    """Il blocco di un servizio di compose.yaml, dalla sua riga alla prossima
    allo stesso rientro: il progetto non dipende da un parser YAML."""
    testo = (RADICE / "compose.yaml").read_text()
    inizio = testo.index(f"\n  {nome}:\n")
    fine = re.search(r"\n  \S", testo[inizio + 1 :])
    return testo[inizio : inizio + 1 + fine.start()] if fine else testo[inizio:]


def test_il_servizio_e_la_prova_non_girano_come_root():
    for nome in ("servizio", "prova"):
        utenti = re.findall(r"^USER (\S+)$", stadi()[nome], flags=re.MULTILINE)
        assert utenti and utenti[-1] == UTENTE, nome


def test_il_servizio_non_cambia_niente_fuori_da_data_e_tmp():
    blocco = servizio("prossima")
    assert "\n    read_only: true\n" in blocco
    assert "\n    tmpfs:\n      - /tmp\n" in blocco
    assert "\n      - ./dati:/data\n" in blocco
    assert "\n      - ./config:/config:ro\n" in blocco


def test_il_servizio_non_ha_privilegi_da_guadagnare():
    blocco = servizio("prossima")
    assert "\n    cap_drop:\n      - ALL\n" in blocco
    assert "\n    security_opt:\n      - no-new-privileges:true\n" in blocco


def test_il_servizio_ha_un_limite_di_memoria_e_di_processi():
    blocco = servizio("prossima")
    assert "\n    mem_limit: 256m\n" in blocco
    assert "\n    pids_limit: 64\n" in blocco
