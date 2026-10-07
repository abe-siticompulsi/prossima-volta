"""Il punto d'ingresso: `prossima` avvia il bot, `prossima salute` controlla il
battito (il controllo di salute del container).

Il logger `httpx` sta a WARNING: al livello INFO scriverebbe l'URL di ogni
chiamata a Telegram, e l'URL contiene il token.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from . import config
from .bot import COMANDI, Bot
from .store import Store
from .telegram import BotTelegram, TelegramError

log = logging.getLogger(__name__)

ATTESA = 25  # secondi di long polling
BATTITO_MASSIMO = 120  # secondi: oltre, il container è malato


def configura_log() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def ciclo(
    telegram,
    bot: Bot,
    store: Store,
    battito: Path,
    fermo: threading.Event,
    *,
    attesa: int = ATTESA,
    pausa_errore: float = 5.0,
) -> None:
    """Legge il bot in long polling finché `fermo` non è impostato, e tocca il
    battito a ogni giro. Non si ferma per un errore: lo registra e riprova."""
    while not fermo.is_set():
        try:
            bot.ricevi(telegram.aggiornamenti(store.offset(), attesa))
        except TelegramError as e:
            log.warning("lettura del bot non riuscita: %s", e)
            fermo.wait(pausa_errore)
        except Exception:
            log.exception("ciclo del bot: errore inatteso, riprovo")
            fermo.wait(pausa_errore)
        _batti(battito)


def _batti(battito: Path) -> None:
    try:
        battito.touch()
    except OSError:
        log.exception("battito non scritto: %s", battito)


def in_salute(battito: Path, adesso: float | None = None) -> bool:
    """Il battito ha meno di due minuti."""
    try:
        eta = (time.time() if adesso is None else adesso) - battito.stat().st_mtime
    except OSError:
        return False
    return eta < BATTITO_MASSIMO


def avvia(env: Mapping[str, str], *, telegram=None, fermo: threading.Event | None = None) -> None:
    """Costruisce il bot vero e gira finché `fermo` non è impostato (in esercizio,
    mai: il container lo ferma con un segnale)."""
    imp = config.da_ambiente(env)
    store = Store(imp.db)
    store.crea_schema()
    telegram = telegram or BotTelegram(imp.token_bot)
    nome = telegram.io()
    telegram.registra_comandi(COMANDI)
    bot = Bot(
        telegram=telegram,
        store=store,
        roster=imp.roster,
        gruppo=imp.gruppo,
        nome=nome,
        fuso=imp.fuso,
        adesso=lambda: datetime.now(UTC),
    )
    log.info(
        "Prossima volta: @%s nel gruppo %s, %d persone nel roster",
        nome,
        imp.gruppo,
        len(imp.roster.persone),
    )
    ciclo(telegram, bot, store, imp.battito, fermo or threading.Event())


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    env = os.environ if env is None else env
    configura_log()
    if argv == ["salute"]:
        battito = (env.get("PV_BATTITO") or "").strip()
        return 0 if battito and in_salute(Path(battito)) else 1
    if argv:
        log.error("uso: prossima [salute]")
        return 2
    try:
        avvia(env)
    except config.ConfigurazioneErrata as e:
        log.error("configurazione: %s", e)
        return 2
    except TelegramError as e:
        log.error("Telegram non risponde all'avvio: %s", e)
        return 1
    return 0
