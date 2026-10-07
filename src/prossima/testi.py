"""I testi che il bot scrive, e le frasi di «Nessuna di queste».

Testo semplice, senza `parse_mode`. Le menzioni sono entità `text_mention` con
l'identificativo Telegram della persona: notificano anche chi non ha un nome
utente. Telegram conta scostamenti e lunghezze delle entità in unità UTF-16,
non in caratteri: un'emoji come 📅 ne vale due, e contare con `len()` farebbe
cadere la menzione due lettere più in là.

Ogni testo qui è copiato alla lettera dalla spec (§3): cambiarlo è cambiare
la spec.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo

from . import regole
from .regole import Persona

DOMANDA = "Prossima volta?"
LUNGHEZZA_OPZIONE = 100  # il limite di Telegram per il testo di un'opzione

FRASI_NESSUNA = (
    "Nessuna: ho fallito il tiro salvezza contro la vita reale",
    "Nessuna: ho tirato 1 sul calendario",
    "Nessuna: il destino ha tirato con svantaggio",
    "Nessuna: ho perso l'iniziativa contro la mia agenda",
    "Nessuna: un mimic travestito da agenda si è mangiato la settimana",
    "Nessuna: questa settimana i danni radiosi me li fa il lavoro",
    "Nessuna: riposo lungo. Molto lungo.",
    "Nessuna: ho perso la concentrazione, e con lei la settimana",
    "Nessuna: il mio slot del martedì è esaurito",
    "Nessuna: questa settimana sono un PNG",
    "Nessuna: il mio personaggio è in un semipiano senza calendario",
    "Nessuna: il master può dire che il mio personaggio dorme",
    "Nessuna: lancio Velocità sulla settimana dopo",
    "Nessuna: 20 naturale per trovare una scusa",
    "Nessuna: il bardo scriverà comunque una canzone sulla mia assenza",
)


@dataclass(frozen=True)
class Testo:
    testo: str
    entita: tuple[dict, ...] = ()  # entità Telegram, pronte per `sendMessage`


def utf16(testo: str) -> int:
    """La lunghezza di `testo` come la conta Telegram: in unità UTF-16."""
    return len(testo.encode("utf-16-le")) // 2


class _Scrittura:
    """Mette insieme un testo e le sue menzioni, contando in UTF-16."""

    def __init__(self) -> None:
        self._pezzi: list[str] = []
        self._entita: list[dict] = []
        self._lunghezza = 0

    def testo(self, pezzo: str) -> _Scrittura:
        self._pezzi.append(pezzo)
        self._lunghezza += utf16(pezzo)
        return self

    def menzione(self, persona: Persona) -> _Scrittura:
        self._entita.append(
            {
                "type": "text_mention",
                "offset": self._lunghezza,
                "length": utf16(persona.soprannome),
                "user": {"id": persona.telegram_id},
            }
        )
        return self.testo(persona.soprannome)

    def menzioni(self, persone: Sequence[Persona]) -> _Scrittura:
        """«sese, pippo»: un nome per menzione, separati da virgole."""
        for i, persona in enumerate(persone):
            if i:
                self.testo(", ")
            self.menzione(persona)
        return self

    def fatto(self) -> Testo:
        return Testo("".join(self._pezzi), tuple(self._entita))


def elenco(nomi: Sequence[str], congiunzione: str = "e") -> str:
    """«gio, abe, emi e sem»."""
    if len(nomi) <= 1:
        return "".join(nomi)
    return f"{', '.join(nomi[:-1])} {congiunzione} {nomi[-1]}"


def _nomi(persone: Sequence[Persona]) -> list[str]:
    return [p.soprannome for p in persone]


# --- il sondaggio


def opzioni(date_sondaggio: Sequence[date], frase: str) -> list[str]:
    return [regole.etichetta(g) for g in date_sondaggio] + [frase]


def scegli_frase(usate: Collection[str], caso: Callable[[Sequence[str]], str]) -> str:
    """Una frase di «Nessuna», a caso fra quelle non ancora usate. Se sono state
    usate tutte, a caso fra tutte: chi la sceglie dimentica le usate e ricomincia."""
    restanti = [f for f in FRASI_NESSUNA if f not in usate]
    return caso(restanti or list(FRASI_NESSUNA))


# --- gli annunci


def quasi(a: regole.Quasi) -> Testo:
    s = _Scrittura().testo(
        f"📅 {regole.etichetta(a.giorno)}: ci sono {elenco(_nomi(a.presenti))}, manca un giocatore."
    )
    if a.senza_voto:
        s.testo(" Non hanno ancora votato: ").menzioni(a.senza_voto).testo(".")
    return s.fatto()


def possibile(a: regole.Possibile) -> Testo:
    return Testo(f"✅ {regole.etichetta(a.giorno)} va bene: ci sono {elenco(_nomi(a.presenti))}.")


def non_piu(a: regole.NonPiu) -> Testo:
    inizio = f"⚠️ {regole.etichetta(a.giorno)} non va più bene: "
    if not a.andati_via:
        return Testo(inizio + "non ci sono più il master e quattro giocatori.")
    verbo = "ha" if len(a.andati_via) == 1 else "hanno"
    return Testo(f"{inizio}{elenco(_nomi(a.andati_via))} {verbo} tolto il voto.")


def impossibile(a: regole.Impossibile, chiude: Sequence[Persona], nome_bot: str) -> Testo:
    s = _Scrittura()
    if a.con_tre:
        date_ = "; ".join(f"{regole.etichetta(g)} ({', '.join(_nomi(p))})" for g, p in a.con_tre)
        s.testo(
            "😬 Con quattro giocatori non ci si sta in nessuna di queste date. "
            f"Con tre: {date_}. "
        )
        s.menzioni(chiude).testo(
            f": /chiudi@{nome_bot} {regole.breve(a.con_tre[0][0])} per tenerla, "
            f"/chiudi@{nome_bot} rimanda per rifare il sondaggio sulla settimana dopo."
        )
    else:
        s.testo(
            "😬 Con quattro giocatori non ci si sta in nessuna di queste date, e nemmeno con tre. "
        )
        s.menzioni(chiude).testo(
            f": /chiudi@{nome_bot} rimanda per rifare il sondaggio sulla settimana dopo."
        )
    return s.fatto()


def annuncio(a: regole.Annuncio, roster: regole.Roster, nome_bot: str) -> Testo:
    match a:
        case regole.Quasi():
            return quasi(a)
        case regole.Possibile():
            return possibile(a)
        case regole.NonPiu():
            return non_piu(a)
        case regole.Impossibile():
            return impossibile(a, roster.chi_chiude, nome_bot)
    raise TypeError(f"annuncio sconosciuto: {a!r}")


# --- le risposte ai comandi


def rifiuto(r: regole.Rifiuto) -> Testo:
    """I rifiuti di `/sondaggio`."""
    match r:
        case regole.NonCapisco():
            return Testo(
                f"Non capisco «{r.parola}»: scrivi i giorni (lun, mar, …) o le date (14/10)."
            )
        case regole.DataPassata():
            return Testo(f"La data {r.scritta} è già passata.")
        case regole.DataTroppoLontana():
            return Testo(f"La data {r.scritta} è troppo lontana.")
        case regole.TroppeDate():
            return Testo(f"Troppe date: al massimo {regole.MASSIMO_DATE}.")
    raise TypeError(f"rifiuto sconosciuto: {r!r}")


def _con_articolo(giorno: int, maschile: str, femminile: str) -> str:
    """«più di un martedì», «più di una domenica»: domenica è l'unico femminile."""
    return f"{femminile if giorno == 6 else maschile} {regole.GIORNI_INTERI[giorno]}"


def rifiuto_di_chiudi(r: regole.Rifiuto) -> Testo:
    """I rifiuti di `/chiudi <argomento>`."""
    match r:
        case regole.NonCapisco():
            return Testo(
                f"Non capisco «{r.parola}»: "
                "scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda."
            )
        case regole.NonNelSondaggio():
            return Testo(f"La data {r.scritta} non era nel sondaggio.")
        case regole.GiornoAmbiguo():
            return Testo(
                f"Nel sondaggio c'è {_con_articolo(r.giorno, 'più di un', 'più di una')}: "
                f"scrivi la data ({regole.breve(r.prima_data)})."
            )
        case regole.GiornoAssente():
            return Testo(f"Nel sondaggio non c'è {_con_articolo(r.giorno, 'nessun', 'nessuna')}.")
        case regole.DataPassata():
            return Testo(f"La data {r.scritta} è già passata.")
    raise TypeError(f"rifiuto sconosciuto: {r!r}")


def gia_aperto(nome_bot: str) -> Testo:
    return Testo(f"C'è già un sondaggio aperto: chiudilo prima con /chiudi@{nome_bot}.")


def _riga_di_comando(comando: str, argomenti: Sequence[str]) -> str:
    """Un comando da copiare: va da solo sull'ultima riga del messaggio, senza
    niente dopo (un punto finale si copierebbe con l'ultima data)."""
    return " ".join([comando, *argomenti])


def sondaggio_non_confermato(nome_bot: str, argomenti: Sequence[str]) -> Testo:
    """`argomenti`: quelli del comando, come li ha scritti chi l'ha lanciato."""
    return Testo(
        "Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:\n"
        + _riga_di_comando(f"/sondaggio@{nome_bot}", argomenti)
    )


def voto_sconosciuto(
    nome_bot: str, argomenti: Sequence[str] = (), con_sondaggio_aperto: bool = False
) -> Testo:
    """`argomenti`: quelli del tentativo non confermato, per il comando da
    copiare. Con un sondaggio aperto il messaggio risponde a quello: «questo»."""
    inizio = (
        "Ho ricevuto un voto per un sondaggio che non conosco: "
        "forse quello che Telegram non mi ha confermato. "
    )
    if con_sondaggio_aperto:
        return Testo(inizio + "Il sondaggio che conto è questo: votate qui.")
    return Testo(
        inizio
        + "Rilanciatelo e votate lì:\n"
        + _riga_di_comando(f"/sondaggio@{nome_bot}", argomenti)
    )


def solo_chi_chiude(chiude: Sequence[Persona]) -> Testo:
    return Testo(f"Il sondaggio lo chiudono {elenco(_nomi(chiude), 'o')}.")


def nessun_sondaggio() -> Testo:
    return Testo("Non c'è nessun sondaggio aperto.")


def chiuso(possibili: Sequence[date]) -> Testo:
    if not possibili:
        return Testo("🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori.")
    return Testo(
        f"🔒 Sondaggio chiuso. Date possibili: {', '.join(regole.etichetta(g) for g in possibili)}."
    )


def chiuso_con_le_date_possibili_passate() -> Testo:
    """Il riepilogo di chiusura quando c'erano date possibili, ma sono tutte già
    passate: «nessuna data con il master e quattro giocatori» sarebbe falso."""
    return Testo("🔒 Sondaggio chiuso. Nessuna data possibile da oggi in poi.")


def si_gioca(giorno: date) -> Testo:
    return Testo(f"🎲 Si gioca {regole.etichetta_intera(giorno)}.")


def rimandiamo(lunedi: date) -> Testo:
    return Testo(f"🔁 Rimandiamo: nuovo sondaggio sulla settimana del {regole.breve(lunedi)}.")


def rimando_non_confermato(nome_bot: str, date_: Sequence[date]) -> Testo:
    """Le date sono quelle del sondaggio nuovo, `g/m`: il comando da copiare."""
    return Testo(
        "🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: "
        "se non lo vedete, lanciatelo con:\n"
        + _riga_di_comando(f"/sondaggio@{nome_bot}", [regole.breve(g) for g in date_])
    )


def sparito() -> Testo:
    return Testo("Il messaggio del sondaggio non c'è più: lo considero chiuso.")


def chiusura_non_confermata() -> Testo:
    return Testo("Telegram non ha confermato la chiusura del sondaggio: riprovo da solo.")


def non_ancora_chiuso() -> Testo:
    return Testo(
        "Telegram non ha ancora confermato la chiusura del sondaggio di prima: riprovate fra poco."
    )


def chiusura_non_completata(nome_bot: str, argomenti: Sequence[str]) -> Testo:
    """`argomenti`: quelli del `/chiudi` in sospeso (nessuno, la data `g/m`, o
    «rimanda»), per il comando da copiare."""
    return Testo(
        "Non sono riuscito a completare la chiusura del sondaggio di prima. "
        "Chi può chiudere la riprovi con:\n" + _riga_di_comando(f"/chiudi@{nome_bot}", argomenti)
    )


def riprovo_a_completare() -> Testo:
    return Testo("Riprovo a completare la chiusura del sondaggio.")


# --- la ripresa dopo il buio (§3.8)


def _quando(momento: datetime, fuso: tzinfo) -> str:
    locale = momento.astimezone(fuso)
    return f"{regole.breve(locale.date())} alle {locale.hour}:{locale.minute:02d}"


def buio(dal: datetime, al: datetime, fuso: tzinfo) -> Testo:
    return Testo(
        f"🔌 Sono rimasto senza Telegram dal {_quando(dal, fuso)} al {_quando(al, fuso)}. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    )


def conteggi(uguali: bool) -> Testo:
    if uguali:
        return Testo("I conteggi del sondaggio sono gli stessi che avevo io.")
    return Testo(
        "I conteggi del sondaggio sono diversi dai miei: "
        "qualcuno ha votato o cambiato voto senza che lo sapessi."
    )


def gia_chiuso() -> Testo:
    return Testo("Il sondaggio risultava già chiuso.")


def gia_chiuso_senza_confronto() -> Testo:
    return Testo("Il sondaggio risultava già chiuso: non posso confrontare i conteggi.")


def riapro(votanti: Sequence[Persona], senza_voto: Sequence[Persona]) -> Testo:
    s = _Scrittura().testo("Riapro il sondaggio.")
    if votanti:
        s.testo(
            f" Ho già i voti di {elenco(_nomi(votanti))}: "
            "se non avete cambiato idea, non serve rivotare."
        )
    if senza_voto:
        s.testo(" Non hanno ancora votato: ").menzioni(senza_voto).testo(".")
    return s.fatto()


def date_passate() -> Testo:
    return Testo("Le date del sondaggio sono passate: lo chiudo.")
