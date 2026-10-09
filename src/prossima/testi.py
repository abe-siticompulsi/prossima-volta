"""I testi che il bot scrive, e le frasi predefinite di «Nessuna di queste».

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

DOMANDA = "Prossima volta?"  # predefinita: `PV_DOMANDA` la cambia
LUNGHEZZA_DOMANDA = 300  # il limite di Telegram per la domanda di un sondaggio
LUNGHEZZA_OPZIONE = 100  # il limite di Telegram per il testo di un'opzione

# Le frasi predefinite, quando `PV_FRASI` non c'è; con `PV_FRASI` le frasi
# stanno in un file sul server (spec §3.6).
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
        scritto = nome(persona)
        self._entita.append(
            {
                "type": "text_mention",
                "offset": self._lunghezza,
                "length": utf16(scritto),
                "user": {"id": persona.telegram_id},
            }
        )
        return self.testo(scritto)

    def menzioni(self, persone: Sequence[Persona], ultima: str = ", ") -> _Scrittura:
        """«Sese, Pippo»: un nome per menzione, separati da virgole; con
        `ultima=" e "`, «Sese e Pippo»."""
        for i, persona in enumerate(persone):
            if i:
                self.testo(ultima if i == len(persone) - 1 else ", ")
            self.menzione(persona)
        return self

    def fatto(self) -> Testo:
        return Testo("".join(self._pezzi), tuple(self._entita))


def elenco(nomi: Sequence[str], congiunzione: str = "e") -> str:
    """«gio, abe, emi e sem»."""
    if len(nomi) <= 1:
        return "".join(nomi)
    return f"{', '.join(nomi[:-1])} {congiunzione} {nomi[-1]}"


def nome(persona: Persona) -> str:
    """Il soprannome con l'iniziale maiuscola: «gio» → «Gio»."""
    return persona.soprannome[:1].upper() + persona.soprannome[1:]


def _nomi(persone: Sequence[Persona]) -> list[str]:
    return [nome(p) for p in persone]


def _maiuscola(testo: str) -> str:
    return testo[:1].upper() + testo[1:]


# --- le date dette a parole (§3.5)


def una_settimana(date_sondaggio: Sequence[date]) -> bool:
    """Tutte le date nella stessa settimana di calendario, da lunedì a domenica."""
    return len({regole.lunedi(g) for g in date_sondaggio}) <= 1


def giorno_detto(giorno: date, solo_il_giorno: bool) -> str:
    """«martedì», o «martedì 13» se il sondaggio non sta in una settimana."""
    intero = regole.GIORNI_INTERI[giorno.weekday()]
    return intero if solo_il_giorno else f"{intero} {giorno.day}"


def date_dette(giorni: Sequence[date], solo_il_giorno: bool) -> str:
    """«lunedì e giovedì», nell'ordine del calendario."""
    return elenco([giorno_detto(g, solo_il_giorno) for g in sorted(giorni)])


def chi_chiude(roster: regole.Roster) -> str:
    """«chiude Gio (o Abe, in emergenza)»: il master, e chi può chiudere quando
    il master non c'è. Se il master non può chiudere, chi può."""
    master = roster.master
    if not master.chiude:
        chiudono = roster.chi_chiude
        verbo = "chiude" if len(chiudono) == 1 else "chiudono"
        return f"{verbo} {elenco(_nomi(chiudono))}"
    altri = [p for p in roster.chi_chiude if p != master]
    if not altri:
        return f"chiude {nome(master)}"
    return f"chiude {nome(master)} (o {elenco(_nomi(altri), 'o')}, in emergenza)"


# --- il sondaggio


def opzioni(date_sondaggio: Sequence[date], frase: str) -> list[str]:
    return [regole.etichetta(g) for g in date_sondaggio] + [frase]


def scegli_frase(
    frasi: Sequence[str], usate: Collection[str], caso: Callable[[Sequence[str]], str]
) -> str:
    """Una delle `frasi`, a caso fra quelle non ancora usate. Se sono state usate
    tutte, a caso fra tutte: chi la sceglie dimentica le usate e ricomincia."""
    restanti = [f for f in frasi if f not in usate]
    return caso(restanti or list(frasi))


# --- gli annunci


def annunci(
    gruppo: Sequence[regole.Annuncio],
    roster: regole.Roster,
    nome_bot: str,
    date_sondaggio: Sequence[date],
) -> Testo:
    """Un messaggio per un gruppo di annunci dello stesso tipo, nell'ordine
    delle date (§3.5). Le date si dicono per giorno se il sondaggio sta in una
    settimana: `date_sondaggio` sono tutte le sue date."""
    solo_il_giorno = una_settimana(date_sondaggio)
    giorni = [a.giorno for a in gruppo if not isinstance(a, regole.Impossibile)]
    match gruppo[0]:
        case regole.Quasi(senza_voto=senza_voto):
            domanda = "ci sei?" if len(senza_voto) == 1 else "ci siete?"
            return (
                _Scrittura()
                .testo(f"{_maiuscola(date_dette(giorni, solo_il_giorno))} ci siamo quasi. ")
                .menzioni(senza_voto, " e ")
                .testo(f", {domanda}")
                .fatto()
            )
        case regole.Possibile():
            return Testo(f"✅ {_maiuscola(date_dette(giorni, solo_il_giorno))} si può fare!")
        case regole.NonPiu():
            return _non_piu(gruppo, roster, giorni, solo_il_giorno)
        case regole.Impossibile() as a:
            return _impossibile(a, roster, nome_bot, solo_il_giorno)
    raise TypeError(f"annuncio sconosciuto: {gruppo[0]!r}")


def _non_piu(
    gruppo: Sequence[regole.Annuncio],
    roster: regole.Roster,
    giorni: Sequence[date],
    solo_il_giorno: bool,
) -> Testo:
    """I nomi solo se il bot sa chi se n'è andato per tutte le date (dopo una
    ripresa non lo sa); ognuno una volta, nell'ordine del roster. Domenica è
    femminile."""
    femminile = all(g.weekday() == 6 for g in giorni)
    if len(giorni) == 1:
        saltato = "è saltata" if femminile else "è saltato"
    else:
        saltato = "sono saltate" if femminile else "sono saltati"
    inizio = f"{_maiuscola(date_dette(giorni, solo_il_giorno))} {saltato}"
    andati_via = [a.andati_via for a in gruppo if isinstance(a, regole.NonPiu)]
    if not all(andati_via):
        return Testo(f"{inizio}.")
    andati = {p.telegram_id for persone in andati_via for p in persone}
    persone = [p for p in roster.persone if p.telegram_id in andati]
    verbo = "non può più" if len(persone) == 1 else "non possono più"
    return Testo(f"{inizio}, {elenco(_nomi(persone))} {verbo}.")


def _impossibile(
    a: regole.Impossibile, roster: regole.Roster, nome_bot: str, solo_il_giorno: bool
) -> Testo:
    """Menziona il master, che decide; se il master non può chiudere, chi può."""
    chi = (roster.master,) if roster.master.chiude else roster.chi_chiude
    rimanda = f"/chiudi@{nome_bot} rimanda per rimandare alla prossima settimana."
    s = _Scrittura()
    if a.con_tre:
        giorni = [g for g, _ in a.con_tre]
        tenere = "per tenerla" if len(giorni) == 1 else "per tenerne una"
        s.testo(
            "😬 Con i voti attuali non ci sono date con quattro giocatori. "
            f"Con tre: {date_dette(giorni, solo_il_giorno)}. "
        )
        s.menzioni(chi, " e ").testo(
            f": /chiudi@{nome_bot} {regole.breve(giorni[0])} {tenere}, {rimanda}"
        )
    else:
        s.testo("😬 Con i voti attuali non ci sono date con quattro giocatori, e nemmeno con tre. ")
        s.menzioni(chi, " e ").testo(f": {rimanda}")
    return s.fatto()


# --- le istruzioni (§3.9)


def aiuto(nome_bot: str, roster: regole.Roster, giorni_di_sempre: Collection[int]) -> Testo:
    """Le istruzioni di `/aiuto`: i giorni fuori e chi chiude vengono dalla
    configurazione (`PV_GIORNI` e il roster)."""
    sondaggio, chiudi = f"/sondaggio@{nome_bot}", f"/chiudi@{nome_bot}"
    fuori = [g for g in range(7) if g not in giorni_di_sempre]
    righe = ["Come si usa:"]
    if fuori:
        nomi = [regole.GIORNI_INTERI[g] for g in fuori]
        if len(fuori) > 1:
            esclusi = "esclusi"
        else:
            esclusi = "esclusa" if fuori[0] == 6 else "escluso"  # la domenica
        articolo = "la" if fuori[0] == 6 else "il"
        righe += [
            f"{sondaggio} — sondaggio sulla settimana prossima, {elenco(nomi)} {esclusi}",
            f"{sondaggio} con {nomi[0]} — anche {articolo} {nomi[0]}",
        ]
    else:
        righe.append(f"{sondaggio} — sondaggio sulla settimana prossima")
    righe += [
        f"{sondaggio} mar gio — solo quei giorni",
        f"{sondaggio} 14/10 16/10 — quelle date",
        f"{_maiuscola(chi_chiude(roster))}:",
        f"{chiudi} — chiude e dice le date possibili",
        f"{chiudi} 14/10 (o mar) — chiude e tiene quella data",
        f"{chiudi} rimanda — chiude e rifà il sondaggio sulla settimana dopo",
    ]
    return Testo("\n".join(righe))


# --- le risposte ai comandi


def rifiuto(
    r: regole.Rifiuto, nome_bot: str, giorni_di_sempre: Collection[int] = regole.GIORNI_DI_SEMPRE
) -> Testo:
    """I rifiuti di `/sondaggio`. L'esempio di «con» usa il primo giorno fuori
    da quelli di sempre (il sabato, se non ce n'è nessuno)."""
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
        case regole.ConSbagliato():
            fuori = [g for g in range(7) if g not in giorni_di_sempre]
            esempio = regole.GIORNI_INTERI[fuori[0] if fuori else 5]
            return Testo(
                f"Per aggiungere un giorno a quelli di sempre: /sondaggio@{nome_bot} con {esempio}."
            )
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


def solo_chi_chiude(roster: regole.Roster) -> Testo:
    return Testo(f"Il sondaggio lo {chi_chiude(roster)}.")


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
