import logging
from datetime import UTC, datetime

from prossima import testi
from prossima.regole import Voto
from tests.aggiornamenti import comando, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, SEM, SESE, d

BUIO = (
    "🔌 Sono rimasto senza Telegram dal 7/10 alle 20:00 al 9/10 alle 2:00. "
    "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
)
UGUALI = "I conteggi del sondaggio sono gli stessi che avevo io."
DIVERSI = (
    "I conteggi del sondaggio sono diversi dai miei: "
    "mentre ero spento qualcuno ha votato o cambiato voto."
)


def dopo_il_buio(bot, orologio, ore=30):
    """L'ultima lettura riuscita è di adesso; la prossima arriva `ore` dopo."""
    orologio.avanza(hours=ore)
    bot.ricevi([])


def test_la_prima_lettura_non_e_buio(bot, telegram):
    bot.ricevi([])
    assert telegram.chiamate == []


def test_23_ore_non_sono_buio(bot, telegram, orologio):
    bot.ricevi([])
    dopo_il_buio(bot, orologio, ore=23)
    assert telegram.chiamate == []


def test_senza_sondaggio_solo_il_messaggio_del_buio(bot, telegram, orologio):
    orologio.adesso = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    bot.ricevi([])
    orologio.adesso = datetime(2025, 10, 14, 7, 30, tzinfo=UTC)
    bot.ricevi([])
    assert telegram.scritti() == [
        "🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10 alle 9:30. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    ]


def sondaggio_con_tre_voti(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, ABE, "14/10")
    vota(bot, telegram, EMI, "14/10 16/10")
    vota(bot, telegram, SEM, "nessuna")
    return store.sondaggio_aperto()


def test_conteggi_uguali_riapre_e_tiene_i_voti(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.di_tipo("ferma_sondaggio")[-1]["messaggio"] == vecchio.messaggio
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", "gio 16/10", testi.FRASI_NESSUNA[1]]
    assert telegram.scritti() == [
        BUIO,
        UGUALI,
        "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: gio, sese, pippo.",
    ]
    # il buio e i conteggi prima del sondaggio nuovo, «Riapro» dopo
    nomi = [nome for nome, _ in telegram.chiamate if nome != "aggiornamenti"]
    assert nomi[-5:] == ["ferma_sondaggio", "scrivi", "scrivi", "manda_sondaggio", "scrivi"]
    riaperto = store.sondaggio_aperto()
    assert riaperto.id == vecchio.id
    assert riaperto.poll_id == telegram.ultimo_sondaggio["poll_id"] != vecchio.poll_id
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("14/10"), d("16/10")}))
    # nel sondaggio nuovo il voto nuovo sostituisce quello tenuto buono
    vota(bot, telegram, EMI, "16/10")
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("16/10")}))


def test_conteggi_diversi(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]  # qualcuno ha votato al buio
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[:2] == [BUIO, DIVERSI]


def test_i_conteggi_comprendono_chi_non_e_nel_roster(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    vota(bot, telegram, ESTRANEO, "16/10")
    telegram.conteggi[vecchio.messaggio] = [2, 2, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[1] == UGUALI


def test_dopo_una_seconda_ripresa_contano_solo_i_voti_del_sondaggio_nuovo(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio, ore=24)
    vota(bot, telegram, GIO, "16/10")  # l'unico voto dato nel sondaggio riaperto
    riaperto = store.sondaggio_aperto()
    telegram.conteggi[riaperto.messaggio] = [0, 1, 0]
    dopo_il_buio(bot, orologio, ore=24)
    assert telegram.scritti().count(UGUALI) == 2


def test_le_date_passate_non_si_riaprono(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 14/10")])
    dopo_il_buio(bot, orologio, ore=30)  # giovedì 9/10 alle 2:00
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", testi.FRASI_NESSUNA[1]]
    assert store.sondaggio_aperto().date == (d("14/10"),)
    # le opzioni sono quelle nuove: la prima ora è il 14/10
    vota(bot, telegram, ABE, "14/10")
    assert store.voti(store.sondaggio_aperto().id)[ABE.telegram_id] == Voto(frozenset({d("14/10")}))


def test_tutte_le_date_passate_chiude_e_basta(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 9/10")])
    dopo_il_buio(bot, orologio, ore=80)
    assert store.sondaggio_aperto() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti()[1:] == [UGUALI, "Le date del sondaggio sono passate: lo chiudo."]


def test_il_sondaggio_cancellato_durante_il_buio(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.cancellati.add(vecchio.messaggio)
    dopo_il_buio(bot, orologio)
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [BUIO, "Il messaggio del sondaggio non c'è più: lo considero chiuso."]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_il_sondaggio_gia_chiuso_su_telegram_si_riapre_senza_conteggi(
    bot, telegram, store, orologio
):
    # per ora (giro B): conteggi ignoti, niente frase sui conteggi, si riapre
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.fermati.add(vecchio.messaggio)  # uno stop passato senza che il bot lo sapesse
    dopo_il_buio(bot, orologio)
    assert telegram.scritti() == [
        BUIO,
        "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: gio, sese, pippo.",
    ]
    assert store.sondaggio_aperto().id == vecchio.id


def test_gli_annunci_fatti_restano_e_dopo_la_ripresa_non_si_sa_chi(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    possibile = "✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese."
    assert possibile in telegram.scritti()
    telegram.conteggi[store.sondaggio_aperto().messaggio] = [5, 0, 0]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti().count(possibile) == 1
    vota(bot, telegram, SEM, "nessuna")
    # il «quasi» del 14/10 era già stato detto prima del «possibile»: non si ripete
    assert telegram.scritti()[-1] == (
        "⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro giocatori."
    )


def test_se_lo_stop_non_riesce_la_ripresa_si_ferma_al_messaggio(bot, telegram, store, orologio, caplog):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    with caplog.at_level(logging.ERROR):
        dopo_il_buio(bot, orologio)
    assert "ripresa dopo il buio non riuscita" in caplog.text
    assert store.sondaggio_aperto() == vecchio
    assert telegram.scritti() == [BUIO]
    # alla lettura seguente il buio è finito: niente ripresa doppia
    del telegram.guasti["ferma_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO]


def test_la_ripresa_arriva_dopo_gli_aggiornamenti_del_lotto(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]
    orologio.avanza(hours=30)
    voto_di_gio = {
        "update_id": 5000,
        "poll_answer": {"poll_id": vecchio.poll_id, "user": {"id": GIO.telegram_id}, "option_ids": [0]},
    }
    bot.ricevi([voto_di_gio])
    # il voto di gio, arrivato nel lotto, conta: i conteggi tornano
    assert telegram.scritti()[:2] == [BUIO, UGUALI]
    assert store.voti(vecchio.id)[GIO.telegram_id] == Voto(frozenset({d("14/10")}))
