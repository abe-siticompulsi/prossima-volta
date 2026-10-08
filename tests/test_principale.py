import logging
import os
import threading
import time
from pathlib import Path

import httpx
import pytest

from prossima import principale
from prossima.telegram import (
    BotTelegram,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)
from tests.aggiornamenti import GRUPPO, comando
from tests.finti import TelegramFinto

RADICE = Path(__file__).resolve().parents[1]


class TelegramACicli(TelegramFinto):
    """Dà un lotto di aggiornamenti per chiamata; finiti i lotti, ferma il ciclo."""

    def __init__(self, fermo, lotti):
        super().__init__()
        self._fermo = fermo
        self._lotti = list(lotti)

    def aggiornamenti(self, offset, attesa):
        self.chiamate.append(("aggiornamenti", {"offset": offset, "attesa": attesa}))
        if not self._lotti:
            self._fermo.set()
            return []
        lotto = self._lotti.pop(0)
        if isinstance(lotto, Exception):
            raise lotto
        return lotto


class BotFinto:
    def __init__(self, store, esplodi=False):
        self.lotti = []
        self._store = store
        self._esplodi = esplodi

    def ricevi(self, aggiornamenti):
        self.lotti.append([a["update_id"] for a in aggiornamenti])
        if self._esplodi:
            self._esplodi = False
            raise RuntimeError("boom")
        if aggiornamenti:
            self._store.salva_offset(aggiornamenti[-1]["update_id"] + 1)


class FermoFinto(threading.Event):
    """Un `fermo` che non aspetta: ricorda quanto avrebbe aspettato (`attese`) e,
    se ha il file del battito, se a ogni attesa il ciclo l'aveva toccato da
    quella prima (`battiti`). Una prova non aspetta mai davvero."""

    def __init__(self, battito: Path | None = None):
        super().__init__()
        self.attese: list[float] = []
        self.battiti: list[bool] = []
        self._battito = battito

    def wait(self, timeout=None):
        self.attese.append(timeout)
        if self._battito is not None:
            toccato = self._battito.exists() and self._battito.stat().st_mtime > 1
            self.battiti.append(toccato)
            if self._battito.exists():
                os.utime(self._battito, (0, 0))  # da toccare di nuovo, per la prossima attesa
        return self.is_set()


def offset_chiesti(telegram):
    return [a["offset"] for nome, a in telegram.chiamate if nome == "aggiornamenti"]


def test_il_ciclo_passa_i_lotti_al_bot_con_l_offset_salvato(store, tmp_path):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[{"update_id": 5}, {"update_id": 6}], [{"update_id": 7}]])
    bot = BotFinto(store)
    principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=0)
    assert bot.lotti == [[5, 6], [7], []]
    assert offset_chiesti(telegram) == [None, 7, 8]
    assert (tmp_path / "battito").exists()


def test_un_errore_di_telegram_o_del_bot_non_ferma_il_ciclo(store, tmp_path, caplog):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [TelegramError("getUpdates: errore di rete"), [{"update_id": 1}], [{"update_id": 2}]])
    bot = BotFinto(store, esplodi=True)
    with caplog.at_level(logging.WARNING):
        principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=0)
    assert bot.lotti == [[1], [2], []]
    assert "lettura del bot non riuscita: getUpdates: errore di rete" in caplog.text
    assert "errore inatteso" in caplog.text


def test_il_battito(tmp_path):
    battito = tmp_path / "battito"
    assert not principale.in_salute(battito)
    battito.touch()
    assert principale.in_salute(battito)
    vecchio = time.time() - 121
    os.utime(battito, (vecchio, vecchio))
    assert not principale.in_salute(battito)


def test_prossima_salute(tmp_path):
    battito = tmp_path / "battito"
    assert principale.main(["salute"], {"PV_BATTITO": str(battito)}) == 1
    battito.touch()
    assert principale.main(["salute"], {"PV_BATTITO": str(battito)}) == 0
    assert principale.main(["salute"], {}) == 1


def test_i_log_di_httpx_non_scrivono_gli_url_col_token():
    principale.configura_log()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def ambiente(tmp_path):
    return {
        "PV_BOT_TOKEN": "123:SEGRETO",
        "PV_GRUPPO": "-1000000000001",
        "PV_ROSTER": str(RADICE / "config.esempio" / "roster.toml"),
        "PV_DB": str(tmp_path / "prossima.sqlite"),
        "PV_BATTITO": str(tmp_path / "battito"),
    }


def test_all_avvio_chiede_il_nome_e_registra_i_comandi(tmp_path):
    telegram = TelegramFinto("ProssimaVoltaBot")
    fermo = threading.Event()
    fermo.set()
    principale.avvia(ambiente(tmp_path), telegram=telegram, fermo=fermo)
    assert telegram.di_tipo("io") == [{}]
    assert telegram.di_tipo("registra_comandi") == [
        {"comandi": [("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio")]}
    ]
    assert (tmp_path / "prossima.sqlite").exists()


def test_una_configurazione_sbagliata_ferma_l_avvio(tmp_path, caplog):
    env = {**ambiente(tmp_path), "PV_GRUPPO": "party"}
    with caplog.at_level(logging.ERROR):
        assert principale.main([], env) == 2
    assert "PV_GRUPPO deve essere un numero intero" in caplog.text
    assert "SEGRETO" not in caplog.text


def test_un_argomento_sconosciuto(caplog):
    with caplog.at_level(logging.ERROR):
        assert principale.main(["boh"], {}) == 2
    assert "uso: prossima [salute | sblocca]" in caplog.text


def test_il_battito_si_tocca_a_ogni_giro_anche_dopo_un_errore(store, tmp_path):
    battito = tmp_path / "battito"
    visto = []

    class Spia(TelegramACicli):
        def aggiornamenti(self, offset, attesa):
            visto.append(battito.exists())
            return super().aggiornamenti(offset, attesa)

    fermo = threading.Event()
    telegram = Spia(fermo, [TelegramError("getUpdates: errore di rete"), [{"update_id": 1}]])
    principale.ciclo(telegram, BotFinto(store), store, battito, fermo, attesa=0, pausa_errore=0)
    assert visto == [False, True, True]


@pytest.mark.parametrize(
    "errore",
    [
        TelegramRifiuto("getUpdates: Conflict: terminated by other getUpdates request"),
        TelegramTroppeRichieste("getUpdates: Too Many Requests", 30),
    ],
)
def test_un_409_o_un_429_su_getupdates_non_ferma_il_ciclo(store, tmp_path, errore):
    fermo = FermoFinto()
    telegram = TelegramACicli(fermo, [errore, [{"update_id": 1}]])
    bot = BotFinto(store)
    principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=0)
    assert bot.lotti == [[1], []]


@pytest.mark.parametrize(
    "retry_after, attese",
    [
        (30, [30]),  # Telegram chiede più della pausa normale
        (2, [5]),  # Telegram chiede meno: la pausa normale
        (150, [60, 60, 30]),  # a fette, per toccare il battito nel mezzo
    ],
)
def test_dopo_un_429_su_getupdates_si_aspetta_quanto_chiede_telegram(
    store, tmp_path, retry_after, attese
):
    battito = tmp_path / "battito"
    fermo = FermoFinto(battito)
    telegram = TelegramACicli(
        fermo,
        [TelegramTroppeRichieste("getUpdates: Too Many Requests", retry_after), [{"update_id": 1}]],
    )
    principale.ciclo(telegram, BotFinto(store), store, battito, fermo, attesa=0, pausa_errore=5)
    assert fermo.attese == attese
    # il battito dice che il ciclo gira, non che Telegram risponde: anche mentre aspetta
    assert fermo.battiti == [True] * len(attese)


def test_con_errori_di_fila_la_pausa_cresce_fino_a_60_secondi_e_alla_lettura_riuscita_torna_normale(
    store, tmp_path
):
    fermo = FermoFinto()
    errore = TelegramError("getUpdates: errore di rete")
    telegram = TelegramACicli(
        fermo, [errore] * 6 + [[{"update_id": 1}], errore, [{"update_id": 2}]]
    )
    principale.ciclo(
        telegram, BotFinto(store), store, tmp_path / "battito", fermo, attesa=0, pausa_errore=5
    )
    assert fermo.attese == [5, 10, 20, 40, 60, 60, 5]


def errori(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


def test_quando_la_pausa_arriva_al_massimo_un_errore_nel_log_fino_alla_lettura_riuscita(
    store, tmp_path, caplog
):
    fermo = FermoFinto()
    errore = TelegramError("getUpdates: errore di rete (ConnectError)")
    telegram = TelegramACicli(fermo, [errore] * 8 + [[{"update_id": 1}]] + [errore] * 5)
    with caplog.at_level(logging.WARNING):
        principale.ciclo(
            telegram, BotFinto(store), store, tmp_path / "battito", fermo, attesa=0, pausa_errore=5
        )
    # alla quinta la pausa arriva a 60 secondi: un errore, non uno a ogni
    # tentativo; dopo la lettura riuscita, di nuovo alla quinta
    assert fermo.attese == [5, 10, 20, 40, 60, 60, 60, 60, 5, 10, 20, 40, 60]
    da_cinque = (
        "lettura del bot non riuscita da 5 tentativi di fila, "
        "l'ultimo: getUpdates: errore di rete (ConnectError)"
    )
    assert errori(caplog) == [da_cinque, da_cinque]


def test_gli_errori_del_bot_non_dicono_che_la_lettura_non_riesce(store, tmp_path, caplog):
    class BotRotto(BotFinto):
        def ricevi(self, aggiornamenti):
            super().ricevi(aggiornamenti)
            if aggiornamenti:
                raise RuntimeError("boom")

    fermo = FermoFinto()
    telegram = TelegramACicli(fermo, [[{"update_id": 1}]] * 6)
    with caplog.at_level(logging.WARNING):
        principale.ciclo(
            telegram, BotRotto(store), store, tmp_path / "battito", fermo, attesa=0, pausa_errore=5
        )
    # Telegram ha risposto ogni volta: gli errori sono del bot, con il traceback
    assert errori(caplog) == ["ciclo del bot: errore inatteso, riprovo"] * 6


def test_un_errore_del_bot_dopo_una_lettura_riuscita_conta_fra_quelli_di_fila(store, tmp_path):
    fermo = FermoFinto()
    telegram = TelegramACicli(
        fermo, [TelegramError("getUpdates: errore di rete"), [{"update_id": 1}], [{"update_id": 1}]]
    )
    bot = BotFinto(store, esplodi=True)
    principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=5)
    assert bot.lotti == [[1], [1], []]
    assert fermo.attese == [5, 10]


def test_migliaia_di_errori_di_fila_non_fermano_il_ciclo(store, tmp_path):
    fermo = FermoFinto()
    errore = TelegramError("getUpdates: errore di rete")
    telegram = TelegramACicli(fermo, [errore] * 1100 + [[{"update_id": 1}]])
    bot = BotFinto(store)
    principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=5)
    assert bot.lotti == [[1], []]
    assert set(fermo.attese[5:]) == {60}


@pytest.fixture
def log_di_httpx_da_zero():
    nomi = ("httpx", "httpcore")
    prima = {n: logging.getLogger(n).level for n in nomi}
    for n in nomi:
        logging.getLogger(n).setLevel(logging.NOTSET)
    yield
    for n, livello in prima.items():
        logging.getLogger(n).setLevel(livello)


def test_main_configura_i_log_di_httpx(log_di_httpx_da_zero):
    principale.main(["salute"], {})
    assert logging.getLogger("httpx").level == logging.WARNING


def test_httpx_non_scrive_il_token_nei_log(log_di_httpx_da_zero, caplog):
    principale.configura_log()
    http = httpx.Client(
        transport=httpx.MockTransport(
            lambda richiesta: httpx.Response(200, json={"ok": True, "result": {"username": "x"}})
        )
    )
    with caplog.at_level(logging.INFO):
        BotTelegram("123:SEGRETO", http).io()
    assert "SEGRETO" not in caplog.text


def test_avvia_collega_il_ciclo_il_battito_e_il_gruppo(tmp_path):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[comando("/sondaggio mar gio")]])
    principale.avvia(ambiente(tmp_path), telegram=telegram, fermo=fermo)
    assert (tmp_path / "battito").exists()
    assert [s["chat_id"] for s in telegram.di_tipo("manda_sondaggio")] == [GRUPPO]
