import logging
import os
import threading
import time
from pathlib import Path

from prossima import principale
from prossima.telegram import TelegramError
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
    assert "uso: prossima [salute]" in caplog.text
