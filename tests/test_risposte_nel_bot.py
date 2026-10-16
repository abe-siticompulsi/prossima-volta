"""Le risposte a chi scrive al bot (spec 2026-10-17), con un rispondente finto
che non ha un thread: la prova dice quando una risposta è pronta."""

import pytest

from prossima import testi
from prossima.risposte import APERTO, CHIUSO, NESSUNO, Esito
from tests.aggiornamenti import GRUPPO, comando, del_bot, scritto, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, SEM, SESE, d

PRIVATA = SEM.telegram_id  # la chat privata con Sem ha il suo identificativo


class RispondenteFinto:
    def __init__(self, massimo: int = 3) -> None:
        self.massimo = massimo
        self.domande = []  # tutte quelle accettate, in ordine
        self._lavoro = []
        self._pronte = []

    def accetta(self, domanda) -> bool:
        if len(self._lavoro) >= self.massimo:
            return False
        self.domande.append(domanda)
        self._lavoro.append(domanda)
        return True

    def in_lavoro(self):
        return tuple(self._lavoro)

    def pronte(self):
        pronte, self._pronte = self._pronte, []
        for domanda, _ in pronte:
            self._lavoro.remove(domanda)
        return pronte

    def finisci(self, domanda, esito) -> None:
        self._pronte.append((domanda, esito))


@pytest.fixture
def rispondente():
    return RispondenteFinto()


@pytest.fixture
def bot(riavvia, rispondente):
    return riavvia(rispondente=rispondente)


def mandati(telegram):
    return [(a["chat_id"], a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")]


def test_chi_risponde_a_un_messaggio_del_bot_nel_gruppo(bot, telegram, rispondente):
    msg = scritto(
        "Allora, deciso?", da=SEM.telegram_id, citato=del_bot(600, "✅ Giovedì si può fare!")
    )
    bot.ricevi([msg])
    [domanda] = rispondente.domande
    assert (domanda.chat_id, domanda.messaggio_id, domanda.chi, domanda.testo, domanda.del_bot) == (
        GRUPPO,
        msg["message"]["message_id"],
        "Sem",
        "Allora, deciso?",
        "✅ Giovedì si può fare!",
    )
    assert domanda.citata and domanda.fatti.stato == NESSUNO
    assert telegram.di_tipo("azione") == [{"chat_id": GRUPPO, "azione": "typing"}]
    assert bot.occupato()
    rispondente.finisci(domanda, Esito(testi.Testo("Ancora niente!"), "battuta"))
    bot.ricevi([])
    assert mandati(telegram) == [(GRUPPO, "Ancora niente!", msg["message"]["message_id"])]
    assert not bot.occupato()


def test_chi_risponde_al_sondaggio(bot, telegram, rispondente, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    sondaggio = store.sondaggio_aperto()
    bot.ricevi(
        [
            scritto(
                "Ci sono",
                da=SEM.telegram_id,
                citato=del_bot(sondaggio.messaggio, domanda="Prossima volta?"),
            )
        ]
    )
    [domanda] = rispondente.domande
    assert domanda.del_bot == "Prossima volta?"
    assert domanda.fatti.stato == APERTO
    assert [g for g, _ in domanda.fatti.date] == [d("14/10"), d("16/10")]


@pytest.mark.parametrize(
    "citato",
    [
        None,  # non risponde a nessuno: con la privacy attiva non arriverebbe
        {"message_id": 1, "from": {"id": 7, "is_bot": False, "first_name": "Sem"}, "text": "x"},
        {"message_id": 1, "from": {"id": 8, "is_bot": True, "username": "AltroBot"}, "text": "x"},
    ],
)
def test_nel_gruppo_solo_a_chi_risponde_al_bot(bot, telegram, rispondente, citato):
    bot.ricevi([scritto("Ciao", citato=citato)])
    assert rispondente.domande == [] and telegram.chiamate == []


def test_un_comando_che_risponde_al_bot_resta_un_comando(bot, telegram, rispondente):
    bot.ricevi([scritto("/aiuto", citato=del_bot(600, "x"))])
    assert rispondente.domande == []
    assert telegram.scritti()[0].startswith("Come si usa:")


def test_chi_non_e_nel_roster_ha_il_suo_nome_telegram(bot, rispondente):
    bot.ricevi([scritto("Ehi bot", da=ESTRANEO, nome="Marco", citato=del_bot(600, "x"))])
    assert rispondente.domande[0].chi == "Marco"


def test_in_privato_risponde_a_chi_e_nel_roster_senza_citare(bot, telegram, rispondente):
    bot.ricevi([scritto("Quando si gioca?", da=SEM.telegram_id, chat=PRIVATA)])
    [domanda] = rispondente.domande
    assert (domanda.chat_id, domanda.del_bot, domanda.citata) == (PRIVATA, "", False)
    rispondente.finisci(domanda, Esito(testi.risposta_senza_sondaggio(), "data", None, True))
    bot.ricevi([])
    assert mandati(telegram) == [
        (PRIVATA, "Non c'è ancora un sondaggio: lancialo con /sondaggio.", None)
    ]
    assert telegram.di_tipo("scrivi")[0]["entita"] == [{"type": "code", "offset": 42, "length": 10}]


def test_in_privato_niente_per_chi_non_e_nel_roster(bot, telegram, rispondente):
    bot.ricevi([scritto("Ciao", da=ESTRANEO, chat=ESTRANEO)])
    assert rispondente.domande == [] and telegram.chiamate == []


def test_senza_rispondente_nessuna_risposta(riavvia, telegram):
    bot = riavvia()
    bot.ricevi(
        [
            scritto("Ciao", citato=del_bot(600, "x")),
            scritto("Ciao", da=SEM.telegram_id, chat=PRIVATA),
        ]
    )
    assert telegram.chiamate == [] and not bot.occupato()


def test_con_la_fila_piena_la_frase_fissa_subito(riavvia, telegram):
    bot = riavvia(rispondente=RispondenteFinto(massimo=1))
    primo = scritto("Uno", citato=del_bot(600, "x"))
    secondo = scritto("Due", citato=del_bot(600, "x"))
    bot.ricevi([primo, secondo])
    assert mandati(telegram) == [
        (
            GRUPPO,
            "Ora non riesco a rispondere: riprova più tardi.",
            secondo["message"]["message_id"],
        )
    ]


def test_con_la_chiusura_in_sospeso_la_frase_fissa(bot, telegram, rispondente, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])
    prima = len(telegram.scritti())
    bot.ricevi([scritto("Allora?", citato=del_bot(600, "x"))])
    assert rispondente.domande == []
    assert telegram.scritti()[prima:] == ["Ora non riesco a rispondere: riprova più tardi."]


def test_se_i_fatti_cambiano_la_risposta_del_codice_con_quelli_nuovi(bot, telegram, rispondente):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "14/10")
    bot.ricevi([scritto("Allora, quando?", da=SEM.telegram_id, citato=del_bot(600, "x"))])
    [domanda] = rispondente.domande
    vota(bot, telegram, SESE, "14/10")  # adesso martedì si può fare
    prima = len(telegram.scritti())
    rispondente.finisci(domanda, Esito(testi.Testo("Ancora niente, Sem."), "data", None, True))
    bot.ricevi([])
    assert telegram.scritti()[prima:] == [
        "Il sondaggio è ancora aperto. Per ora si può fare martedì 14/10."
    ]


def test_con_gli_stessi_fatti_la_risposta_del_rispondente(bot, telegram, rispondente):
    bot.ricevi([comando("/sondaggio mar gio")])
    bot.ricevi([scritto("Allora, quando?", da=SEM.telegram_id, citato=del_bot(600, "x"))])
    [domanda] = rispondente.domande
    prima = len(telegram.scritti())
    rispondente.finisci(domanda, Esito(testi.Testo("Ancora niente, Sem."), "data", None, True))
    bot.ricevi([])
    assert telegram.scritti()[prima:] == ["Ancora niente, Sem."]


def test_la_data_scelta_entra_nei_fatti(bot, telegram, rispondente):
    bot.ricevi([comando("/sondaggio mar gio"), comando("/chiudi gio")])
    bot.ricevi([scritto("Alla fine?", citato=del_bot(600, "x"))])
    fatti = rispondente.domande[0].fatti
    assert (fatti.stato, fatti.scelta) == (CHIUSO, d("16/10"))


def test_sta_scrivendo_si_rinnova_ogni_4_secondi(bot, telegram, rispondente, orologio):
    bot.ricevi([scritto("Uno", citato=del_bot(600, "x"))])
    bot.ricevi([scritto("Due", da=SEM.telegram_id, chat=PRIVATA)])
    assert telegram.di_tipo("azione") == [
        {"chat_id": GRUPPO, "azione": "typing"},
        {"chat_id": PRIVATA, "azione": "typing"},
    ]
    orologio.avanza(seconds=3)
    bot.ricevi([])
    assert len(telegram.di_tipo("azione")) == 2
    orologio.avanza(seconds=1)
    bot.ricevi([])
    assert len(telegram.di_tipo("azione")) == 4


def test_sta_scrivendo_non_riuscito_non_ferma_niente(bot, telegram, rispondente):
    telegram.guasti["azione"] = telegram_guasto("azione")
    bot.ricevi([scritto("Uno", citato=del_bot(600, "x"))])
    rispondente.finisci(rispondente.domande[0], Esito(testi.Testo("Eccomi"), "battuta"))
    bot.ricevi([])
    assert telegram.scritti() == ["Eccomi"]


def test_se_il_sondaggio_diventa_incerto_mentre_scrive_la_frase_fissa(bot, telegram, rispondente):
    bot.ricevi([comando("/sondaggio mar gio")])
    bot.ricevi([scritto("Allora?", citato=del_bot(600, "x"))])
    [domanda] = rispondente.domande
    telegram.guasti["ferma_sondaggio"] = telegram_guasto("ferma_sondaggio")
    bot.ricevi([comando("/chiudi")])
    prima = len(telegram.scritti())
    rispondente.finisci(domanda, Esito(testi.Testo("Ancora aperto."), "data", None, True))
    bot.ricevi([])
    assert telegram.scritti()[prima:] == ["Ora non riesco a rispondere: riprova più tardi."]
