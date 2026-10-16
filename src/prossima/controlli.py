"""I controlli dei testi scritti da Ollama (dal prototipo, `prototipo-ollama`). Ogni `controlla_*` rende i
motivi per scartare il testo: nessun motivo, il testo passa. Si controllano
fatti (giorni, date, nomi, comandi, orari) e la forma (lunghezza, righe,
emoji), mai la presenza di una parola: il senso si giudica leggendo."""

import re
import unicodedata
from collections.abc import Collection
from datetime import date

from . import regole

MASSIMO_RISPOSTA = 400
MASSIMO_BATTUTA = 200

_VIRGOLETTE = {"«": "»", '"': '"', "“": "”", "'": "'"}
_SENZA_ACCENTO = {g: g.replace("ì", "i") for g in regole.GIORNI_INTERI}
_GIORNO = re.compile(
    r"\b("
    + "|".join(sorted({*regole.GIORNI_INTERI, *_SENZA_ACCENTO.values()}, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
_DATA = re.compile(r"(?<!\d)(\d{1,2})[/.](\d{1,2})(?!\d)")
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")  # fmt: skip
_DATA_A_PAROLE = re.compile(rf"(?<!\d)(\d{{1,2}})\s+({'|'.join(MESI)})\b", re.IGNORECASE)
# «venerdì 16», senza il mese: gemma3 lo scrive per «venerdì 16/10» (strada unita, 15/10)
_GIORNO_E_NUMERO = re.compile(
    _GIORNO.pattern + rf"\s+(\d{{1,2}})(?!\d|[/.]\d|\s+(?:{'|'.join(MESI)})\b)", re.IGNORECASE
)
_COMANDO = re.compile(r"(?<![\w/:])/[A-Za-z]\w*")
_ORARIO = re.compile(
    r"\b(?:alle|all'|dalle|verso le)\s*\d{1,2}(?::\d{2})?\b|\b\d{1,2}:\d{2}\b", re.IGNORECASE
)


def pulisci(testo: str) -> str:
    """Spazi ai bordi, e una coppia di virgolette attorno a tutto il testo."""
    t = testo.strip()
    if len(t) >= 2 and _VIRGOLETTE.get(t[0]) == t[-1]:
        t = t[1:-1].strip()
    return t


def emoji(testo: str) -> set[str]:
    """I simboli (categoria `So`, dove stanno le emoji) e i caratteri non
    assegnati o d'uso privato, che il modello a volte scrive per emoji."""
    return {c for c in testo if unicodedata.category(c) in ("So", "Cn", "Co")}


def _emoji_non_ammesse(testo: str, ammesse: Collection[str]) -> list[str]:
    fuori = emoji(testo) - set(ammesse)
    return [f"emoji non ammesse: {' '.join(sorted(fuori))}"] if fuori else []


def nomi_in(testo: str, soprannomi: Collection[str]) -> list[str]:
    """I soprannomi nominati in `testo`, come parole intere: «gio» non è in «giovedì»."""
    return [s for s in soprannomi if re.search(rf"\b{re.escape(s)}\b", testo, re.IGNORECASE)]


def giorni_in(testo: str) -> set[str]:
    """I giorni della settimana nominati in `testo`, con l'accento: «giovedi» → «giovedì»."""
    return {_giorno(g) for g in _GIORNO.findall(testo)}


def date_in(testo: str) -> set[tuple[int, int | None]]:
    """Le date nominate in `testo`, come (giorno, mese): «15/10», «15.10» e
    «15 ottobre» sono la stessa. «Giovedì 15», senza il mese, è (15, None)."""
    a_parole = {(int(g), MESI.index(m.lower()) + 1) for g, m in _DATA_A_PAROLE.findall(testo)}
    senza_mese = {(int(n), None) for _, n in _GIORNO_E_NUMERO.findall(testo)}
    return {(int(g), int(m)) for g, m in _DATA.findall(testo)} | a_parole | senza_mese


def _con_il_mese(
    date_: Collection[tuple[int, int | None]], note: Collection[tuple[int, int | None]]
) -> set[tuple[int, int | None]]:
    """Una data senza il mese è quella nota con lo stesso giorno del mese, se c'è:
    «venerdì 16» accanto a «venerdì 16/10». Il giorno della settimana lo
    controlla `giorni_in`."""
    mesi = {g: m for g, m in note if m}
    return {(g, m or mesi.get(g)) for g, m in date_}


def _scritta(data: tuple[int, int | None]) -> str:
    giorno, mese = data
    return f"{giorno}/{mese}" if mese else str(giorno)


def _normale(testo: str) -> str:
    return re.sub(r"[^\w]+", " ", testo.casefold()).strip()


def _giorno(parola: str) -> str:
    """«Giovedi» → «giovedì»."""
    minuscola = parola.lower()
    return next((g for g, s in _SENZA_ACCENTO.items() if minuscola in (g, s)), minuscola)


def controlla_riscrittura(
    riscritta: str,
    originale: str,
    *,
    soprannomi: Collection[str],
    nomi_ammessi: Collection[str] = (),
    uguale_ammesso: bool = False,
) -> list[str]:
    """Un annuncio riscritto dice gli stessi fatti della frase di oggi: gli
    stessi giorni, le stesse date e gli stessi nomi, nessuno in più; e le emoji
    solo fra quelle che c'erano. Nessun limite di lunghezza, per ora (Alberto,
    2026-10-11): si guarda come va."""
    motivi = []
    ammessi = set(nomi_ammessi)  # per una risposta: chi ha scritto, a cui il bot si rivolge
    for cosa, prima, dopo in (
        ("il giorno", giorni_in(originale), giorni_in(riscritta)),
        (
            "la data",
            {_scritta(d) for d in date_in(originale)},
            {_scritta(d) for d in _con_il_mese(date_in(riscritta), date_in(originale))},
        ),
        ("il nome", set(nomi_in(originale, soprannomi)), set(nomi_in(riscritta, soprannomi))),
    ):
        motivi += [f"manca {cosa}: {x}" for x in sorted(prima - dopo)]
        motivi += [f"{cosa.split()[1]} in più: {x}" for x in sorted(dopo - prima - ammessi)]
    motivi += _emoji_non_ammesse(riscritta, emoji(originale))
    if "\n" in riscritta:
        motivi.append("più di una riga")
    if not uguale_ammesso and _normale(riscritta) == _normale(originale):
        motivi.append("uguale al testo di oggi")
    return motivi


def controlla_risposta(
    risposta: str,
    date_note: Collection[date],
    *,
    ammesse: Collection[str] = (),
    giorni_ammessi: Collection[str] = (),
) -> list[str]:
    """Giorni e date solo fra quelli che il bot conosce (le date del sondaggio
    e quella scelta) e i giorni che ha nominato chi scrive: «Sabato non è nel
    sondaggio» è una risposta giusta."""
    giorni = {regole.GIORNI_INTERI[d.weekday()] for d in date_note} | set(giorni_ammessi)
    note = {(d.day, d.month) for d in date_note}
    motivi = [f"giorno non nei fatti: {g}" for g in sorted(giorni_in(risposta) - giorni)]
    fuori = _con_il_mese(date_in(risposta), note) - note
    motivi += [f"data non nei fatti: {d}" for d in sorted(map(_scritta, fuori))]
    motivi += [f"contiene un comando: {c}" for c in dict.fromkeys(_COMANDO.findall(risposta))]
    motivi += [f"orario inventato: {o}" for o in dict.fromkeys(_ORARIO.findall(risposta))]
    motivi += _emoji_non_ammesse(risposta, ammesse)
    if len(risposta) > MASSIMO_RISPOSTA:
        motivi.append(f"troppo lunga: {len(risposta)} su {MASSIMO_RISPOSTA}")
    return motivi


def controlla_battuta(
    battuta: str, *, soprannomi_vietati: Collection[str], ammesse: Collection[str] = ()
) -> list[str]:
    """Una battuta non dice fatti: nessun giorno, data, orario o comando, e
    nessuno del gruppo tranne chi ha scritto."""
    motivi = controlla_risposta(battuta, set(), ammesse=ammesse)
    motivi += [f"nomina: {n}" for n in nomi_in(battuta, soprannomi_vietati)]
    if MASSIMO_BATTUTA < len(battuta) <= MASSIMO_RISPOSTA:
        motivi.append(f"troppo lunga: {len(battuta)} su {MASSIMO_BATTUTA}")
    return motivi
