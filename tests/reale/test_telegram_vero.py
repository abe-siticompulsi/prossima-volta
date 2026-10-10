"""Il bot vero, nella chat privata di Alberto (`PV_REALE_CHAT`).

Si lancia **a servizio fermo** (`docker compose stop prossima`): due lettori
dello stesso bot si rubano gli aggiornamenti. Questi test leggono `getUpdates`
senza offset, quindi non confermano niente a Telegram: alla ripartenza il
servizio ritrova quello che è arrivato nel frattempo, e ignora i voti di prova
(sono di sondaggi che non conosce).

Un test chiede ad Alberto di votare: la domanda del sondaggio dice cosa fare,
e il test aspetta fino a tre minuti. Un altro gli chiede di toccare un bottone;
il tocco resta fra gli aggiornamenti non confermati, e alla ripartenza il
servizio prova a rispondergli: Telegram lo rifiuta perché è vecchio, e nel log
compare un avviso «risposta al tocco non mandata». È normale. Un terzo gli
chiede di toccare un comando di `/aiuto` e di incollarlo nella chat: fuori dal
gruppo il servizio non risponde a niente, nemmeno al comando incollato.
"""

import os
import time
from datetime import date, timedelta

import pytest

from prossima import config, regole, testi
from prossima.bot import COMANDI
from prossima.regole import Persona
from prossima.telegram import BotTelegram, MessaggioSparito, SondaggioGiaChiuso, TelegramRifiuto
from tests.reale.ambiente import richiedi_la_configurazione, richiesta

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


def tocco_su(b: BotTelegram, messaggio: int) -> dict:
    """Il primo tocco su un bottone del messaggio `messaggio`, letto senza offset."""
    fine = time.monotonic() + ATTESA_VOTI
    while time.monotonic() < fine:
        for a in b.aggiornamenti(None, 5):
            tocco = a.get("callback_query") or {}
            if (tocco.get("message") or {}).get("message_id") == messaggio:
                return tocco
        time.sleep(1)
    pytest.fail(
        f"in {ATTESA_VOTI} secondi non è arrivato nessun tocco: il servizio è davvero fermo? "
        "(due lettori si rubano gli aggiornamenti) hai toccato il bottone?"
    )


def messaggio_dopo(b: BotTelegram, messaggio: int) -> dict:
    """Il primo messaggio di Alberto nella sua chat dopo il messaggio `messaggio`,
    letto senza offset."""
    fine = time.monotonic() + ATTESA_VOTI
    while time.monotonic() < fine:
        for a in b.aggiornamenti(None, 5):
            m = a.get("message") or {}
            if (
                m.get("chat", {}).get("id") == chat()
                and m.get("from", {}).get("id") == chat()
                and m.get("message_id", 0) > messaggio
            ):
                return m
        time.sleep(1)
    pytest.fail(
        f"in {ATTESA_VOTI} secondi non è arrivato nessun messaggio: il servizio è davvero fermo? "
        "(due lettori si rubano gli aggiornamenti) hai incollato e mandato il comando?"
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
    con l'identificativo di chi vota e le opzioni da 0; togliere una sola data
    manda le opzioni rimaste (il voto intero, che sostituisce il precedente); il
    voto ritirato arriva con le opzioni vuote; `stopPoll` dà i conteggi per
    opzione, in ordine."""
    b = bot()
    date_ = [date.today() + timedelta(days=i) for i in range(1, regole.MASSIMO_DATE + 1)]
    frase = frase_piu_lunga()
    mandato = b.manda_sondaggio(
        chat(),
        "🧪 Prova di Prossima volta: spunta la prima e la terza data e vota; "
        "poi togli solo la terza; poi ritira il voto; poi spunta la seconda e vota.",
        testi.opzioni(date_, frase),
    )
    primo, senza_la_terza, ritiro, secondo = risposte(b, mandato.poll_id, 4)
    assert primo["user"]["id"] == chat()
    assert primo["option_ids"] == [0, 2]
    assert senza_la_terza["option_ids"] == [0]
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


def test_un_bottone_toccato_arriva_al_bot():
    """Contratti: un messaggio con un bottone (inline keyboard) parte; il tocco
    arriva come `callback_query`, con l'identificativo di chi tocca, il dato del
    bottone e il messaggio; la risposta al tocco con un avviso e la rimozione dei
    bottoni riescono. Alberto tocca il bottone: lo dice il messaggio."""
    b = bot()
    messaggio = b.scrivi(
        chat(),
        "🧪 Prova di Prossima volta: tocca il bottone qui sotto.",
        bottoni=[[("Tocca qui", "prova:bottone")]],
    )
    tocco = tocco_su(b, messaggio["message_id"])
    assert tocco["from"]["id"] == chat()
    assert tocco["data"] == "prova:bottone"
    b.rispondi_al_tocco(tocco["id"], "🧪 Tocco ricevuto: bottone a posto.")
    b.togli_bottoni(chat(), messaggio["message_id"])


def test_un_comando_in_codice_si_copia_intero():
    """Contratti: Telegram accetta le entità `code` di `/aiuto` dove le mette
    `testi.py`; un comando scritto come codice, toccato, si copia intero, anche
    quello che segue lo spazio (un comando evidenziato partirebbe senza). Il
    messaggio è quello di `/aiuto` con la configurazione vera; Alberto tocca
    l'ultimo comando e incolla nella chat quello che ha copiato: lo dice il
    messaggio che segue, che non contiene comandi da toccare per sbaglio."""
    richiedi_la_configurazione("un comando di /aiuto, toccato, si copia intero")
    imp = config.da_ambiente(os.environ)
    b = bot()
    nome = b.io()
    t = testi.aiuto(nome, imp.roster, imp.giorni)
    istruzioni = b.scrivi(chat(), t.testo, t.entita)
    assert [(e["offset"], e["length"]) for e in istruzioni["entities"] if e["type"] == "code"] == [
        (e["offset"], e["length"]) for e in t.entita
    ]
    rimanda = f"/chiudi@{nome} rimanda"
    assert t.testo.endswith(f"{rimanda} — chiude e rifà il sondaggio sulla settimana dopo")
    domanda = b.scrivi(
        chat(),
        "🧪 Prova di Prossima volta: qui sopra tocca l'ultimo comando, quello che finisce con "
        "«rimanda»; poi incollalo qui e manda.",
    )
    incollato = (messaggio_dopo(b, domanda["message_id"]).get("text") or "").strip()
    if "rimanda" not in incollato:
        pytest.fail(
            f"è arrivato «{incollato}», senza «rimanda»: il tocco ha mandato il comando invece di "
            "copiarlo intero?"
        )
    assert incollato == rimanda
