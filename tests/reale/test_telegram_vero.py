"""Il bot vero, nella chat privata di Alberto (`PV_REALE_CHAT`).

Si lancia **a servizio fermo** (`docker compose stop prossima`): due lettori
dello stesso bot si rubano gli aggiornamenti. Questi test leggono `getUpdates`
senza offset, quindi non confermano niente a Telegram: alla ripartenza il
servizio ritrova quello che è arrivato nel frattempo, e ignora i voti di prova
(sono di sondaggi che non conosce).

Un test chiede ad Alberto di votare: la domanda del sondaggio dice cosa fare,
e il test aspetta fino a tre minuti.
"""

import os
import time
from datetime import date, timedelta

import pytest

from prossima import config, regole, testi
from prossima.bot import COMANDI
from prossima.regole import Persona
from prossima.telegram import BotTelegram, MessaggioSparito, SondaggioGiaChiuso, TelegramRifiuto
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale

ATTESA_VOTI = 180  # secondi


def bot() -> BotTelegram:
    return BotTelegram(richiesta("PV_BOT_TOKEN"))


def frase_piu_lunga() -> str:
    """Fra le frasi che il servizio usa (dal file di `PV_FRASI`, o le
    predefinite se la variabile non c'è), quella con più byte in UTF-8. Come
    Telegram conti i 100 caratteri di un'opzione non è scritto: in caratteri, in
    UTF-16 (come il bot) o in byte, la frase con più byte è quella che rischia
    di più."""
    return max(config.frasi_da_ambiente(os.environ), key=lambda frase: len(frase.encode()))


def chat() -> int:
    return int(richiesta("PV_REALE_CHAT"))


def risposte(b: BotTelegram, poll_id: str, quante: int) -> list[dict]:
    """Le prime `quante` risposte al sondaggio `poll_id`, lette senza offset."""
    trovate: list[dict] = []
    fine = time.monotonic() + ATTESA_VOTI
    while time.monotonic() < fine:
        trovate = [
            a["poll_answer"]
            for a in b.aggiornamenti(None, 5)
            if a.get("poll_answer", {}).get("poll_id") == poll_id
        ]
        if len(trovate) >= quante:
            return trovate[:quante]
        time.sleep(1)
    pytest.fail(
        f"in {ATTESA_VOTI} secondi sono arrivate {len(trovate)} risposte su {quante}: "
        "il servizio è davvero fermo? (due lettori si rubano i voti) "
        f"hai votato entro {ATTESA_VOTI // 60} minuti?"
    )


def test_il_nome_del_bot():
    assert bot().io().lower().endswith("bot")


def test_i_comandi_del_menu():
    b = bot()
    b.registra_comandi(COMANDI)
    # getMyCommands al bot non serve: lo si chiama qui solo per rileggere.
    letti = b._chiama("getMyCommands")
    assert [(c["command"], c["description"]) for c in letti] == list(COMANDI)


def test_una_menzione_dopo_un_emoji_cade_sul_nome():
    """Contratto: Telegram conta gli scostamenti delle entità in UTF-16, come
    `testi.py`, e accetta una `text_mention` con il solo identificativo."""
    alberto = Persona("abe", chat(), "giocatore")
    altri = tuple(Persona(n, 100000001 + i, "giocatore") for i, n in enumerate(("gio", "emi", "sem", "sese")))
    t = testi.quasi(regole.Quasi(date.today() + timedelta(days=7), altri, (alberto,)))
    messaggio = bot().scrivi(chat(), t.testo, t.entita)
    [entita] = messaggio["entities"]
    assert entita["type"] == "text_mention"
    assert (entita["offset"], entita["length"]) == (t.entita[0]["offset"], 3)
    assert entita["user"]["id"] == chat()


def test_un_sondaggio_con_undici_opzioni_parte():
    """Contratto: Telegram accetta un sondaggio con 11 opzioni (10 date e la
    frase di «Nessuna» più lunga fra quelle vere, di al massimo 100 caratteri),
    non anonimo e a risposta multipla. Non serve votare: `stopPoll` dà un
    conteggio per ognuna."""
    b = bot()
    date_ = [date.today() + timedelta(days=i) for i in range(1, regole.MASSIMO_DATE + 1)]
    frase = frase_piu_lunga()
    assert testi.utf16(frase) <= testi.LUNGHEZZA_OPZIONE
    mandato = b.manda_sondaggio(
        chat(), "🧪 Prova di Prossima volta: 11 opzioni, non serve votare.", testi.opzioni(date_, frase)
    )
    assert b.ferma_sondaggio(chat(), mandato.messaggio) == [0] * (regole.MASSIMO_DATE + 1)


def test_sondaggio_voto_ritiro_e_conteggi():
    """Contratti: un sondaggio non anonimo a risposta multipla con 11 opzioni
    (10 date e la frase più lunga) parte; ogni voto arriva come `poll_answer`
    con l'identificativo di chi vota e le opzioni da 0; il voto ritirato arriva
    con le opzioni vuote; `stopPoll` dà i conteggi per opzione, in ordine."""
    b = bot()
    date_ = [date.today() + timedelta(days=i) for i in range(1, regole.MASSIMO_DATE + 1)]
    frase = frase_piu_lunga()
    mandato = b.manda_sondaggio(
        chat(),
        "🧪 Prova di Prossima volta: spunta la prima e la terza data e vota; "
        "poi ritira il voto; poi spunta la seconda e vota.",
        testi.opzioni(date_, frase),
    )
    primo, ritiro, secondo = risposte(b, mandato.poll_id, 3)
    assert primo["user"]["id"] == chat()
    assert primo["option_ids"] == [0, 2]
    assert ritiro["option_ids"] == []
    assert secondo["option_ids"] == [1]
    assert b.ferma_sondaggio(chat(), mandato.messaggio) == [0, 1] + [0] * 9


def test_fermare_un_sondaggio_cancellato():
    """Contratto: per un messaggio cancellato `stopPoll` risponde con una
    descrizione che `MessaggioSparito` riconosce."""
    b = bot()
    mandato = b.manda_sondaggio(chat(), "🧪 Prova di Prossima volta: sparisco da solo.", ["sì", "no"])
    # deleteMessage al bot non serve: qui fa la parte di chi cancella il sondaggio.
    b._chiama("deleteMessage", {"chat_id": chat(), "message_id": mandato.messaggio})
    with pytest.raises(MessaggioSparito):
        b.ferma_sondaggio(chat(), mandato.messaggio)


def test_fermare_due_volte():
    """Contratto: un secondo `stopPoll` sullo stesso sondaggio risponde con una
    descrizione che `SondaggioGiaChiuso` riconosce (il 2026-10-08: «Bad Request:
    poll can't be stopped»). Da lì dipende la ripresa di una chiusura
    interrotta: se Telegram cambia descrizione, la prova la riporta, e si
    corregge `_GIA_CHIUSO` in `telegram.py` (e le differenze fra test e realtà)."""
    b = bot()
    mandato = b.manda_sondaggio(chat(), "🧪 Prova di Prossima volta: mi fermo due volte.", ["sì", "no"])
    assert b.ferma_sondaggio(chat(), mandato.messaggio) == [0, 0]
    try:
        b.ferma_sondaggio(chat(), mandato.messaggio)
    except SondaggioGiaChiuso:
        return
    except TelegramRifiuto as e:
        pytest.fail(
            f"il secondo stopPoll è stato rifiutato con «{e}», che il client non riconosce "
            "come «già chiuso»: aggiorna `_GIA_CHIUSO` in telegram.py"
        )
    pytest.fail("il secondo stopPoll sullo stesso sondaggio è riuscito: Telegram non lo rifiuta")
