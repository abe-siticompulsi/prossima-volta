import logging

from prossima import testi
from prossima.regole import Voto
from prossima.telegram import TelegramRifiuto, TelegramTroppeRichieste
from tests.aggiornamenti import GRUPPO, comando, risposta, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, PIPPO, SEM, SESE, d

FRASE = testi.FRASI_NESSUNA[0]  # `caso` sceglie la prima restante
SETTIMANA = ["lun 13/10", "mar 14/10", "mer 15/10", "gio 16/10", "ven 17/10", "sab 18/10", "dom 19/10"]


def menzionati(chiamata):
    unita = chiamata["testo"].encode("utf-16-le")
    return [
        unita[2 * e["offset"] : 2 * (e["offset"] + e["length"])].decode("utf-16-le")
        for e in chiamata["entita"]
    ]


# --- /sondaggio


def test_senza_parole_la_settimana_seguente(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio@ProssimaVoltaBot")])
    assert telegram.di_tipo("manda_sondaggio") == [
        {"chat_id": GRUPPO, "domanda": "Prossima volta?", "opzioni": [*SETTIMANA, FRASE]}
    ]
    aperto = store.sondaggio_aperto()
    assert aperto.date == tuple(d(f"{g}/10") for g in range(13, 20))
    assert (aperto.poll_id, aperto.messaggio) == (
        telegram.ultimo_sondaggio["poll_id"],
        telegram.ultimo_sondaggio["messaggio"],
    )
    assert aperto.frase == FRASE
    assert aperto.aperto_alle == orologio.adesso
    assert telegram.scritti() == []


def test_la_settimana_seguente_e_quella_di_zurigo(bot, telegram, orologio):
    # domenica 12/10 alle 22:30 UTC è già lunedì 13/10 a Zurigo
    orologio.adesso = orologio.adesso.replace(day=12, hour=22, minute=30)
    bot.ricevi([comando("/sondaggio")])
    assert telegram.ultimo_sondaggio["opzioni"][0] == "lun 20/10"


def test_il_comando_per_un_altro_bot_si_ignora(bot, telegram, store):
    bot.ricevi([comando("/sondaggio@AltroBot"), comando("/sondaggio@altrobot 32/10")])
    assert telegram.chiamate == []
    assert store.sondaggio_aperto() is None


def test_il_nome_del_bot_non_conta_le_maiuscole(bot, telegram):
    bot.ricevi([comando("/sondaggio@prossimavoltabot mar")])
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", FRASE]


def test_fuori_dal_gruppo_non_risponde_a_niente(bot, telegram, store):
    privata = GIO.telegram_id
    bot.ricevi([comando("/sondaggio", chat=privata), comando("/sondaggio 32/10", chat=privata)])
    assert telegram.chiamate == []
    assert store.sondaggio_aperto() is None


def test_un_messaggio_che_non_e_un_comando_si_ignora(bot, telegram):
    bot.ricevi([comando("ciao"), comando(""), comando("/aiuto")])
    assert telegram.chiamate == []


def test_giorni_e_date(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio sab")])
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", "gio 16/10", "sab 18/10", FRASE]
    store.chiudi_sondaggio(store.sondaggio_aperto().id, store.sondaggio_aperto().aperto_alle)
    bot.ricevi([comando("/sondaggio 16.10 14/10 gio")])
    assert telegram.ultimo_sondaggio["opzioni"][:2] == ["mar 14/10", "gio 16/10"]


def test_i_rifiuti_rispondono_al_comando_e_non_aprono_niente(bot, telegram, store):
    sbagliati = [
        comando("/sondaggio 32/10"),
        comando("/sondaggio 3/10"),
        comando("/sondaggio " + " ".join(f"{g}/10" for g in range(13, 24))),
    ]
    bot.ricevi(sbagliati)
    assert telegram.di_tipo("scrivi") == [
        {
            "chat_id": GRUPPO,
            "testo": "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
            "entita": [],
            "risposta_a": sbagliati[0]["message"]["message_id"],
        },
        {
            "chat_id": GRUPPO,
            "testo": "La data 3/10 è già passata.",
            "entita": [],
            "risposta_a": sbagliati[1]["message"]["message_id"],
        },
        {
            "chat_id": GRUPPO,
            "testo": "Troppe date: al massimo 10.",
            "entita": [],
            "risposta_a": sbagliati[2]["message"]["message_id"],
        },
    ]
    assert telegram.di_tipo("manda_sondaggio") == []
    assert store.sondaggio_aperto() is None


def test_con_un_sondaggio_aperto_risponde_al_sondaggio(bot, telegram):
    bot.ricevi([comando("/sondaggio")])
    messaggio = telegram.ultimo_sondaggio["messaggio"]
    bot.ricevi([comando("/sondaggio mar"), comando("/sondaggio 32/10")])
    gia_aperto = {
        "chat_id": GRUPPO,
        "testo": "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot.",
        "entita": [],
        "risposta_a": messaggio,
    }
    assert telegram.di_tipo("scrivi") == [gia_aperto, gia_aperto]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_le_frasi_di_nessuna_ruotano(bot, telegram, store):
    for _ in range(3):
        bot.ricevi([comando("/sondaggio mar")])
        aperto = store.sondaggio_aperto()
        store.chiudi_sondaggio(aperto.id, aperto.aperto_alle)
    usate = [s["opzioni"][-1] for s in telegram.sondaggi]
    assert usate == list(testi.FRASI_NESSUNA[:3])
    assert store.frasi_usate() == set(testi.FRASI_NESSUNA[:3])


def test_finite_le_frasi_si_ricomincia(bot, telegram, store):
    for frase in testi.FRASI_NESSUNA:
        store.usa_frase(frase)
    bot.ricevi([comando("/sondaggio mar")])
    assert telegram.ultimo_sondaggio["opzioni"][-1] == FRASE
    assert store.frasi_usate() == {FRASE}


def test_un_sondaggio_che_non_parte_non_apre_niente(bot, telegram, store, caplog):
    telegram.guasti["manda_sondaggio"] = telegram_guasto()
    with caplog.at_level(logging.ERROR):
        bot.ricevi([comando("/sondaggio")])
    assert store.sondaggio_aperto() is None
    assert store.frasi_usate() == set()
    assert "non gestito" in caplog.text


# --- i voti


def test_un_voto_si_registra_e_il_piu_recente_vale(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, ABE, "14/10 nessuna")
    vota(bot, telegram, ESTRANEO, "16/10")
    aperto = store.sondaggio_aperto()
    assert store.voti(aperto.id) == {
        ABE.telegram_id: Voto(frozenset({d("14/10")}), nessuna=True),
        ESTRANEO: Voto(frozenset({d("16/10")})),
    }
    vota(bot, telegram, ABE, "")
    assert store.voti(aperto.id)[ABE.telegram_id] == Voto()


def test_un_voto_per_un_altro_sondaggio_si_ignora(bot, store):
    bot.ricevi([comando("/sondaggio mar")])
    bot.ricevi([risposta("poll-di-qualcun-altro", ABE.telegram_id, 0)])
    assert store.voti(store.sondaggio_aperto().id) == {}


def test_un_voto_senza_sondaggio_aperto_si_ignora(bot, telegram):
    bot.ricevi([risposta("poll-1", ABE.telegram_id, 0)])
    assert telegram.chiamate == []


# --- gli annunci


def test_quasi_con_le_menzioni_di_chi_non_ha_votato(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    assert telegram.scritti() == []
    vota(bot, telegram, SEM, "14/10")
    [quasi] = telegram.di_tipo("scrivi")
    assert quasi["testo"] == (
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(quasi) == ["sese", "pippo"]
    assert [e["user"]["id"] for e in quasi["entita"]] == [SESE.telegram_id, PIPPO.telegram_id]
    assert (quasi["chat_id"], quasi["risposta_a"]) == (GRUPPO, None)
    bot.ricevi([])
    assert len(telegram.scritti()) == 1


def test_possibile_non_piu_e_di_nuovo_possibile(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    vota(bot, telegram, SEM, "16/10")
    vota(bot, telegram, PIPPO, "14/10")
    assert telegram.scritti() == [
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo.",
        "✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese.",
        "⚠️ mar 14/10 non va più bene: sem ha tolto il voto.",
        "✅ mar 14/10 va bene: ci sono gio, abe, emi, sese e pippo.",
    ]


def test_impossibile_e_di_nuovo_dopo_che_una_data_e_tornata_in_gioco(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, GIO, "nessuna")
    vota(bot, telegram, GIO, "")  # le date tornano in gioco: niente da dire
    vota(bot, telegram, GIO, "nessuna")
    impossibile = (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date, e nemmeno con tre. "
        "gio, abe: /chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert telegram.scritti() == [impossibile, impossibile]
    assert menzionati(telegram.di_tipo("scrivi")[0]) == ["gio", "abe"]


def test_chi_non_e_nel_roster_non_conta_negli_annunci(bot, telegram):
    bot.ricevi([comando("/sondaggio mar")])
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    vota(bot, telegram, ESTRANEO, "14/10")
    assert telegram.scritti() == []


# --- gli invii che non riescono


def test_un_annuncio_che_non_parte_riparte_al_giro_seguente(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    telegram.guasti["scrivi"] = telegram_guasto()
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "14/10")
    assert telegram.scritti() == []
    assert store.fatti(store.sondaggio_aperto().id).quasi == frozenset()
    del telegram.guasti["scrivi"]
    bot.ricevi([])
    bot.ricevi([])
    assert len(telegram.scritti()) == 1
    assert telegram.scritti()[0].startswith("📅 mar 14/10")


def test_dopo_un_429_niente_parte_prima_di_retry_after(bot, telegram, orologio):
    bot.ricevi([comando("/sondaggio mar gio")])
    telegram.guasti["scrivi"] = TelegramTroppeRichieste("sendMessage: Too Many Requests", 30)
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "14/10")
    del telegram.guasti["scrivi"]
    orologio.avanza(seconds=29)
    bot.ricevi([])
    assert telegram.scritti() == []
    orologio.avanza(seconds=1)
    bot.ricevi([])
    assert len(telegram.scritti()) == 1


def test_la_posta_che_non_parte_resta_e_riparte_in_ordine(bot, telegram, store):
    telegram.guasto = telegram_guasto()
    primo, secondo = comando("/sondaggio 32/10"), comando("/sondaggio 3/10")
    bot.ricevi([primo, secondo])
    assert len(store.posta()) == 2
    telegram.guasto = None
    bot.ricevi([])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        (
            "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
            primo["message"]["message_id"],
        ),
        ("La data 3/10 è già passata.", secondo["message"]["message_id"]),
    ]
    assert store.posta() == []


def test_un_messaggio_rifiutato_da_telegram_si_scarta(bot, telegram, store, caplog):
    telegram.guasti["scrivi"] = TelegramRifiuto("sendMessage: Bad Request: chat not found")
    with caplog.at_level(logging.ERROR):
        bot.ricevi([comando("/sondaggio 32/10")])
    assert store.posta() == []
    assert "messaggio scartato" in caplog.text


def test_la_posta_parte_prima_del_sondaggio(bot, telegram):
    telegram.guasti["scrivi"] = telegram_guasto()
    bot.ricevi([comando("/sondaggio 32/10")])
    del telegram.guasti["scrivi"]
    bot.ricevi([comando("/sondaggio mar")])
    assert [nome for nome, _ in telegram.chiamate] == ["scrivi", "manda_sondaggio"]


# --- il lotto


def test_l_offset_si_salva_dopo_ogni_aggiornamento(bot, store):
    lotto = [comando("/sondaggio mar"), comando("ciao")]
    bot.ricevi(lotto)
    assert store.offset() == lotto[-1]["update_id"] + 1


def test_un_aggiornamento_che_esplode_non_ferma_gli_altri(bot, telegram, store, caplog):
    rotto = {"update_id": 77, "message": {"chat": {"id": GRUPPO}, "text": "/sondaggio 32/10"}}
    buono = comando("/sondaggio mar")
    with caplog.at_level(logging.ERROR):
        bot.ricevi([rotto, buono])
    assert "aggiornamento 77 non gestito" in caplog.text
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", FRASE]
    assert store.offset() == buono["update_id"] + 1


def test_un_aggiornamento_letto_due_volte_non_fa_doppioni(bot, telegram):
    lancio = comando("/sondaggio mar gio")
    bot.ricevi([lancio])
    voti = []
    for persona in (GIO, ABE, EMI, SEM):
        sondaggio = telegram.ultimo_sondaggio
        voti.append(risposta(sondaggio["poll_id"], persona.telegram_id, 0))
    bot.ricevi(voti)
    # dopo un riavvio, lo stesso lotto un'altra volta
    bot.ricevi([lancio, *voti])
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti() == [
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo.",
        "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot.",
    ]
