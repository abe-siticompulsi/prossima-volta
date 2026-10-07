"""La configurazione del bot, dall'ambiente, e il roster.

Sul server stanno in `config/prossima.env` (permessi 600) e in
`config/roster.toml`; nel repository ci sono solo gli esempi di
`config.esempio/`, con identificativi finti. Un valore mancante o sbagliato
ferma l'avvio con un messaggio che dice quale: mai un default silenzioso per
un segreto, per il gruppo o per una persona.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .regole import MASTER, RUOLI, Persona, Roster

FUSO_PREDEFINITO = "Europe/Zurich"
_CHIAVI_PERSONA = frozenset({"soprannome", "telegram_id", "ruolo", "chiude"})


class ConfigurazioneErrata(ValueError):
    """Una variabile d'ambiente o il roster non hanno la forma attesa."""


@dataclass(frozen=True)
class Impostazioni:
    token_bot: str = field(repr=False)
    gruppo: int
    roster: Roster
    db: Path
    battito: Path
    fuso: ZoneInfo


def _testo(env: Mapping[str, str], nome: str) -> str:
    valore = (env.get(nome) or "").strip()
    if not valore:
        raise ConfigurazioneErrata(f"{nome} manca")
    return valore


def _intero(env: Mapping[str, str], nome: str) -> int:
    grezzo = _testo(env, nome)
    try:
        return int(grezzo)
    except ValueError:
        raise ConfigurazioneErrata(f"{nome} deve essere un numero intero") from None


def _fuso(env: Mapping[str, str]) -> ZoneInfo:
    nome = (env.get("PV_FUSO") or "").strip() or FUSO_PREDEFINITO
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ConfigurazioneErrata("PV_FUSO: fuso orario sconosciuto (per esempio Europe/Zurich)") from None


def _persona(voce: object, dove: str) -> Persona:
    if not isinstance(voce, dict):
        raise ConfigurazioneErrata(f"{dove}: non è una sezione [[persona]]")
    sconosciute = set(voce) - _CHIAVI_PERSONA
    if sconosciute:
        raise ConfigurazioneErrata(f"{dove}: chiavi sconosciute: {', '.join(sorted(sconosciute))}")
    soprannome = voce.get("soprannome")
    if not isinstance(soprannome, str) or not soprannome.strip() or soprannome != soprannome.strip():
        raise ConfigurazioneErrata(f"{dove}: soprannome manca, o ha spazi intorno")
    dove = f"{dove} ({soprannome})"
    telegram_id = voce.get("telegram_id")
    if isinstance(telegram_id, bool) or not isinstance(telegram_id, int) or telegram_id <= 0:
        raise ConfigurazioneErrata(f"{dove}: telegram_id deve essere un numero intero positivo")
    ruolo = voce.get("ruolo")
    if ruolo is None:
        raise ConfigurazioneErrata(f"{dove}: ruolo manca")
    if ruolo not in RUOLI:
        raise ConfigurazioneErrata(f"{dove}: ruolo {ruolo!r} sconosciuto: «master» o «giocatore»")
    chiude = voce.get("chiude", False)
    if not isinstance(chiude, bool):
        raise ConfigurazioneErrata(f"{dove}: chiude deve essere true o false")
    return Persona(soprannome, telegram_id, ruolo, chiude)


def roster_da_toml(testo: str, origine: str = "roster") -> Roster:
    try:
        dati = tomllib.loads(testo)
    except tomllib.TOMLDecodeError as e:
        raise ConfigurazioneErrata(f"{origine}: non è TOML valido ({e})") from None
    sconosciute = set(dati) - {"persona"}
    if sconosciute:
        raise ConfigurazioneErrata(f"{origine}: sezioni sconosciute: {', '.join(sorted(sconosciute))}")
    voci = dati.get("persona")
    if not isinstance(voci, list) or not voci:
        raise ConfigurazioneErrata(f"{origine}: nessuna persona: servono le sezioni [[persona]]")
    persone = tuple(_persona(voce, f"{origine}, persona {i}") for i, voce in enumerate(voci, 1))
    soprannomi = [p.soprannome for p in persone]
    for s in soprannomi:
        if soprannomi.count(s) > 1:
            raise ConfigurazioneErrata(f"{origine}: il soprannome {s!r} compare due volte")
    identificativi = [p.telegram_id for p in persone]
    for i in identificativi:
        if identificativi.count(i) > 1:
            raise ConfigurazioneErrata(f"{origine}: il telegram_id {i} compare due volte")
    master = [p for p in persone if p.ruolo == MASTER]
    if len(master) != 1:
        raise ConfigurazioneErrata(
            f"{origine}: serve esattamente un master, ce ne sono {len(master)}"
        )
    if not any(p.chiude for p in persone):
        raise ConfigurazioneErrata(
            f"{origine}: nessuno può chiudere il sondaggio: serve almeno una persona con chiude = true"
        )
    return Roster(persone)


def leggi_roster(percorso: Path) -> Roster:
    try:
        testo = percorso.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigurazioneErrata(f"il roster {percorso} non si legge: {e.strerror}") from None
    except UnicodeDecodeError:
        raise ConfigurazioneErrata(f"il roster {percorso} non è UTF-8") from None
    return roster_da_toml(testo, str(percorso))


def da_ambiente(env: Mapping[str, str]) -> Impostazioni:
    return Impostazioni(
        token_bot=_testo(env, "PV_BOT_TOKEN"),
        gruppo=_intero(env, "PV_GRUPPO"),
        roster=leggi_roster(Path(_testo(env, "PV_ROSTER"))),
        db=Path(_testo(env, "PV_DB")),
        battito=Path(_testo(env, "PV_BATTITO")),
        fuso=_fuso(env),
    )
