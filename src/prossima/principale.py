"""Il punto d'ingresso: `prossima` avvia il bot, `prossima salute` controlla il
battito (il controllo di salute del container), `prossima sblocca`, a servizio
fermo, toglie a mano quello che tiene bloccato il bot (v. `sblocco.py`).

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

from . import config, sblocco
from .bot import COMANDI, Bot
from .store import Store
from .telegram import BotTelegram, TelegramError, TelegramTroppeRichieste

log = logging.getLogger(__name__)

ATTESA = 25  # secondi di long polling
BATTITO_MASSIMO = 120  # secondi: oltre, il container è malato
# Dopo errori di fila la pausa raddoppia a ogni errore, fino a qui: con una
# lettura che scade (35 secondi) il battito resta sotto il massimo.
PAUSA_MASSIMA = 60
# Un'attesa più lunga (un 429 con un `retry_after` grande) si fa a fette di
# questa durata, e il battito si tocca a ogni fetta: il ciclo gira, aspetta.
FETTA_DI_ATTESA = 60


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
    battito a ogni giro. Non si ferma per un errore: lo registra, aspetta e
    riprova. La pausa è `pausa_errore`, e raddoppia a ogni errore di fila fino a
    `PAUSA_MASSIMA`; torna normale al primo giro riuscito. Dopo un 429 si aspetta
    almeno quanto chiede Telegram. Il battito dice che il ciclo gira, non che
    Telegram risponde: si tocca anche dopo un errore e durante l'attesa.

    Una lettura che non riesce è un avviso nel log; quando la pausa arriva al
    massimo, anche un errore, una volta sola fino alla prossima lettura
    riuscita: un avviso ogni minuto, da solo, passa inosservato."""
    pausa_corrente = pausa_errore
    massima = max(PAUSA_MASSIMA, pausa_errore)
    letture_fallite = 0  # di fila
    segnalato = False  # l'errore della pausa al massimo, per queste letture fallite
    while not fermo.is_set():
        pausa = 0.0
        try:
            aggiornamenti = telegram.aggiornamenti(store.offset(), attesa)
            letture_fallite, segnalato = 0, False
            bot.ricevi(aggiornamenti)
            pausa_corrente = pausa_errore
        except Exception as e:
            if isinstance(e, TelegramError):
                letture_fallite += 1
                log.warning("lettura del bot non riuscita: %s", e)
                if pausa_corrente >= massima and not segnalato:
                    log.error(
                        "lettura del bot non riuscita da %d tentativi di fila, l'ultimo: %s",
                        letture_fallite,
                        e,
                    )
                    segnalato = True
            else:
                log.exception("ciclo del bot: errore inatteso, riprovo")
            pausa = pausa_corrente
            if isinstance(e, TelegramTroppeRichieste):
                pausa = max(pausa, e.retry_after)
            pausa_corrente = min(pausa_corrente * 2, massima)
        _batti(battito)
        _aspetta(fermo, pausa, battito)


def _aspetta(fermo: threading.Event, secondi: float, battito: Path) -> None:
    """Aspetta `secondi` (o finché `fermo` non è impostato), a fette: dopo ogni
    fetta il battito si tocca."""
    restano = secondi
    while restano > 0 and not fermo.is_set():
        fetta = min(restano, FETTA_DI_ATTESA)
        fermo.wait(fetta)
        restano -= fetta
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
    """Costruisce il bot vero e gira finché `fermo` non è impostato. In esercizio
    non lo è mai: il container lo ferma con SIGTERM, che grazie a `init: true`
    in `compose.yaml` arriva a Python (PID 1 lo ignorerebbe) e lo termina subito,
    a metà di qualunque passo. Lo stato nel database si recupera al riavvio
    (spec §4); i pochi casi che non si recuperano sono in
    docs/differenze-fra-test-e-realta.md."""
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
        frasi=imp.frasi,
    )
    log.info(
        "Prossima volta: @%s nel gruppo %s, %d persone nel roster, frasi di «Nessuna»: %d",
        nome,
        imp.gruppo,
        len(imp.roster.persone),
        len(imp.frasi),
    )
    ciclo(telegram, bot, store, imp.battito, fermo or threading.Event())


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    env = os.environ if env is None else env
    configura_log()
    if argv == ["salute"]:
        battito = (env.get("PV_BATTITO") or "").strip()
        return 0 if battito and in_salute(Path(battito)) else 1
    if argv == ["sblocca"]:
        return _sblocca(env)
    if argv:
        log.error("uso: prossima [salute | sblocca]")
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


def _sblocca(env: Mapping[str, str]) -> int:
    """`prossima sblocca`: legge solo `PV_DB`, e non crea un database che non c'è."""
    percorso = (env.get("PV_DB") or "").strip()
    if not percorso:
        log.error("configurazione: PV_DB manca")
        return 2
    if not Path(percorso).is_file():
        log.error("il database %s non c'è", percorso)
        return 2
    fatto = sblocco.sblocca(Store(percorso), datetime.now(UTC))
    for riga in fatto or [
        "niente da sbloccare: nessuna chiusura in sospeso, nessuna ripresa"
    ]:
        log.info("sblocca: %s", riga)
    return 0
