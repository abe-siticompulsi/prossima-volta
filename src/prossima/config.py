"""La configurazione del bot, dall'ambiente, e il roster.

Sul server stanno in `config/prossima.env` (permessi 600), in
`config/roster.toml` e, se c'è `PV_FRASI`, nel file delle frasi di «Nessuna di
queste»; nel repository ci sono solo gli esempi di `config.esempio/`, con
identificativi finti. Un valore mancante o sbagliato ferma l'avvio con un
messaggio che dice quale: mai un default silenzioso per un segreto, per il
gruppo o per una persona. Le frasi sono l'unico valore con un default: senza
`PV_FRASI`, quelle di `testi.FRASI_NESSUNA`.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .regole import MASTER, RUOLI, Persona, Roster
from .testi import FRASI_NESSUNA, LUNGHEZZA_OPZIONE, utf16

FUSO_PREDEFINITO = "Europe/Zurich"
_CHIAVI_PERSONA = frozenset({"soprannome", "telegram_id", "ruolo", "chiude"})
# «NOME=valore» o «chiave = valore»: una riga di prossima.env o del roster
_RIGA_DI_CONFIGURAZIONE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*=")


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
    frasi: tuple[str, ...]


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


def frasi_da_testo(testo: str, origine: str = "frasi") -> tuple[str, ...]:
    """Una frase per riga. Le righe vuote e quelle che cominciano con # non
    contano; gli spazi intorno a una frase si tolgono. Le righe finiscono solo
    con un a capo, come le conta l'editor (`strip` toglie il \\r di Windows).

    Una riga come «NOME=valore» ferma l'avvio senza ripeterla: `PV_FRASI` che
    indica per sbaglio `prossima.env` metterebbe il token in un sondaggio."""
    frasi: list[str] = []
    righe: dict[str, int] = {}
    for numero, riga in enumerate(testo.split("\n"), 1):
        frase = riga.strip()
        if not frase or frase.startswith("#"):
            continue
        if _RIGA_DI_CONFIGURAZIONE.match(frase):
            raise ConfigurazioneErrata(
                f"{origine}, riga {numero}: sembra una riga di configurazione (NOME=valore), "
                "non una frase: PV_FRASI indica il file giusto?"
            )
        lunghezza = utf16(frase)
        if lunghezza > LUNGHEZZA_OPZIONE:
            raise ConfigurazioneErrata(
                f"{origine}, riga {numero}: la frase è lunga {lunghezza} caratteri, il massimo è "
                f"{LUNGHEZZA_OPZIONE} (il limite di Telegram per un'opzione)"
            )
        if frase in righe:
            raise ConfigurazioneErrata(
                f"{origine}, riga {numero}: la stessa frase è già alla riga {righe[frase]}"
            )
        righe[frase] = numero
        frasi.append(frase)
    if not frasi:
        raise ConfigurazioneErrata(
            f"{origine}: nessuna frase (una per riga; le righe che cominciano con # non contano)"
        )
    return tuple(frasi)


def leggi_frasi(percorso: Path) -> tuple[str, ...]:
    try:
        testo = percorso.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConfigurazioneErrata(f"le frasi {percorso} non si leggono: {e.strerror}") from None
    except UnicodeDecodeError:
        raise ConfigurazioneErrata(f"le frasi {percorso} non sono UTF-8") from None
    return frasi_da_testo(testo, str(percorso))


def frasi_da_ambiente(env: Mapping[str, str]) -> tuple[str, ...]:
    """Le frasi di «Nessuna di queste»: dal file di `PV_FRASI`, o quelle
    predefinite se la variabile non c'è."""
    percorso = (env.get("PV_FRASI") or "").strip()
    return leggi_frasi(Path(percorso)) if percorso else FRASI_NESSUNA


def da_ambiente(env: Mapping[str, str]) -> Impostazioni:
    return Impostazioni(
        token_bot=_testo(env, "PV_BOT_TOKEN"),
        gruppo=_intero(env, "PV_GRUPPO"),
        roster=leggi_roster(Path(_testo(env, "PV_ROSTER"))),
        db=Path(_testo(env, "PV_DB")),
        battito=Path(_testo(env, "PV_BATTITO")),
        fuso=_fuso(env),
        frasi=frasi_da_ambiente(env),
    )
