"""Lo stato del bot, in SQLite: sondaggi, voti, annunci fatti, frasi usate,
posta in uscita, offset del bot e momento dell'ultima lettura; e, in `valori`,
la chiusura in sospeso e la ripresa in corso.

Una connessione per operazione, in modalità WAL, come lo store dei selfie. Le
date dei sondaggi sono giorni di calendario (ISO, `2025-10-14`); i momenti
entrano ed escono come `datetime` con fuso, e nel database sono stringhe ISO in
UTC a larghezza fissa.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path

from .regole import Fatti, Voto

SCHEMA = """
CREATE TABLE IF NOT EXISTS sondaggi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    poll_id TEXT NOT NULL,
    messaggio INTEGER NOT NULL,
    frase TEXT NOT NULL,
    fatti TEXT NOT NULL DEFAULT '{}',
    aperto_alle TEXT NOT NULL,
    chiuso_alle TEXT,
    chiuso_da INTEGER,
    date_iniziali TEXT NOT NULL,
    poll_prima TEXT,
    date_prima TEXT
);
-- Un sondaggio aperto alla volta: la regola la tiene anche il database.
CREATE UNIQUE INDEX IF NOT EXISTS un_solo_aperto
    ON sondaggi ((chiuso_alle IS NULL)) WHERE chiuso_alle IS NULL;
CREATE TABLE IF NOT EXISTS voti (
    sondaggio_id INTEGER NOT NULL REFERENCES sondaggi (id),
    utente_id INTEGER NOT NULL,
    poll_id TEXT NOT NULL,
    date TEXT NOT NULL,
    nessuna INTEGER NOT NULL,
    alle TEXT NOT NULL,
    PRIMARY KEY (sondaggio_id, utente_id)
);
CREATE TABLE IF NOT EXISTS frasi_usate (
    frase TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS posta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    testo TEXT NOT NULL,
    entita TEXT NOT NULL,
    risposta_a INTEGER,
    creata_alle TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valori (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL
);
"""

CHIAVE_OFFSET = "offset_bot"
CHIAVE_LETTURA = "ultima_lettura"
CHIAVE_NON_CONFERMATO = "sondaggio_non_confermato"
CHIAVE_CHIUSURA = "chiusura_sospesa"
CHIAVE_SCONOSCIUTI = "sondaggi_sconosciuti_avvisati"
CHIAVE_RIPRESA = "ripresa"
CHIAVE_BOTTONI = "messaggio_con_bottoni"

# Le fasi della ripresa dopo il buio (§3.8).
FERMARE = "fermare"  # lo stop del sondaggio e il confronto dei conteggi
RIAPRIRE = "riaprire"  # il sondaggio nuovo, con i voti tenuti


@dataclass(frozen=True)
class Sondaggio:
    id: int
    date: tuple[date, ...]
    poll_id: str  # il sondaggio di Telegram di adesso: cambia alla ripresa (§3.8)
    messaggio: int
    frase: str
    aperto_alle: datetime
    chiuso_alle: datetime | None = None
    # Le date con cui è nato: la ripresa toglie da `date` quelle passate, e
    # `/chiudi rimanda` vuole i giorni della settimana di tutte.
    date_iniziali: tuple[date, ...] = ()
    # Il sondaggio di Telegram di prima dell'ultima ripresa, e le sue date: un
    # voto dato lì poco prima dello stop arriva dopo la riapertura.
    poll_prima: str | None = None
    date_prima: tuple[date, ...] = ()


@dataclass(frozen=True)
class Lettera:
    """Un messaggio in attesa di partire."""

    id: int
    chat_id: int
    testo: str
    entita: tuple[dict, ...]
    risposta_a: int | None


@dataclass(frozen=True)
class LetteraNuova:
    """Un messaggio da accodare insieme al cambio di stato che lo giustifica:
    nella stessa transazione, così un processo ucciso a metà non lo perde."""

    chat_id: int
    testo: str
    entita: tuple[dict, ...] = ()
    risposta_a: int | None = None


@dataclass(frozen=True)
class NonConfermato:
    """Un sondaggio che Telegram non ha confermato e che forse è partito: il
    momento del tentativo, e gli argomenti del comando che lo rilancia."""

    alle: datetime
    argomenti: tuple[str, ...]


@dataclass(frozen=True)
class ChiusuraSospesa:
    """Un `/chiudi` di cui Telegram non ha confermato lo stop: il bot lo
    ritenta, e quando Telegram risponde chiude come chiedeva il comando."""

    sondaggio: int
    comando: int  # il messaggio del /chiudi: sarà `chiuso_da`
    argomento: str | None  # None, «rimanda», o la data tenuta (ISO, «2025-10-14»)


@dataclass(frozen=True)
class RipresaInCorso:
    """La ripresa dopo il buio di un sondaggio, a che punto è. Ogni passo si
    salva prima del seguente: un processo fermato a metà, o un errore di
    Telegram, la lascia qui, e la lettura seguente la continua."""

    sondaggio: int
    fase: str  # FERMARE o RIAPRIRE
    # In fase FERMARE: uno stop di questa ripresa è già partito, e forse è
    # passato. Se Telegram dice che il sondaggio è già chiuso, è stato quello.
    stop_provato: bool = False


def _iso(momento: datetime) -> str:
    if momento.tzinfo is None:
        raise ValueError("data senza fuso orario")
    return momento.astimezone(UTC).isoformat(timespec="microseconds")


def _giorni(testo: str) -> tuple[date, ...]:
    return tuple(date.fromisoformat(g) for g in json.loads(testo))


def _giorni_json(giorni: Sequence[date] | frozenset[date]) -> str:
    return json.dumps(sorted(g.isoformat() for g in giorni))


def _sondaggio(riga: sqlite3.Row) -> Sondaggio:
    chiuso = riga["chiuso_alle"]
    return Sondaggio(
        id=riga["id"],
        date=_giorni(riga["date"]),
        poll_id=riga["poll_id"],
        messaggio=riga["messaggio"],
        frase=riga["frase"],
        aperto_alle=datetime.fromisoformat(riga["aperto_alle"]),
        chiuso_alle=None if chiuso is None else datetime.fromisoformat(chiuso),
        date_iniziali=_giorni(riga["date_iniziali"]),
        poll_prima=riga["poll_prima"],
        date_prima=() if riga["date_prima"] is None else _giorni(riga["date_prima"]),
    )


def _voto(riga: sqlite3.Row) -> Voto:
    return Voto(date=frozenset(_giorni(riga["date"])), nessuna=bool(riga["nessuna"]))


def _fatti_json(fatti: Fatti) -> str:
    return json.dumps(
        {
            "quasi": sorted(g.isoformat() for g in fatti.quasi),
            "possibili": {
                g.isoformat(): None if presenti is None else sorted(presenti)
                for g, presenti in sorted(fatti.possibili.items())
            },
            "impossibile": fatti.impossibile,
        }
    )


def _fatti(testo: str) -> Fatti:
    dati = json.loads(testo)
    return Fatti(
        quasi=frozenset(date.fromisoformat(g) for g in dati.get("quasi", [])),
        possibili={
            date.fromisoformat(g): None if presenti is None else frozenset(presenti)
            for g, presenti in dati.get("possibili", {}).items()
        },
        impossibile=bool(dati.get("impossibile", False)),
    )


def _apri(
    c: sqlite3.Connection,
    date_: Sequence[date],
    poll_id: str,
    messaggio: int,
    frase: str,
    alle: datetime,
) -> int:
    """Apre un sondaggio nuovo. Una riapertura che aspettava finisce qui: il
    sondaggio nuovo vale al posto suo (§3.8)."""
    nuovo = c.execute(
        "INSERT INTO sondaggi (date, date_iniziali, poll_id, messaggio, frase, aperto_alle) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_giorni_json(date_), _giorni_json(date_), poll_id, messaggio, frase, _iso(alle)),
    ).lastrowid
    ripresa = _leggi_ripresa(c)
    if ripresa is not None and ripresa.fase == RIAPRIRE:
        _togli_valore(c, CHIAVE_RIPRESA)
    return nuovo


def _chiudi(c: sqlite3.Connection, sondaggio_id: int, alle: datetime, comando: int | None) -> bool:
    """Chiude il sondaggio, e con lui la sua chiusura in sospeso e la sua
    ripresa, se ci sono: un sondaggio chiuso non ha niente da chiudere né da
    riprendere. Il sondaggio fermato da una ripresa, che aspetta di essere
    riaperto, conta ancora come aperto: chiuderlo finisce la ripresa."""
    ripresa = _leggi_ripresa(c)
    in_riapertura = ripresa is not None and ripresa.fase == RIAPRIRE and ripresa.sondaggio == sondaggio_id
    cursore = c.execute(
        "UPDATE sondaggi SET chiuso_alle = ?, chiuso_da = ? "
        "WHERE id = ? AND (chiuso_alle IS NULL OR (? AND chiuso_da IS NULL))",
        (_iso(alle), comando, sondaggio_id, in_riapertura),
    )
    if cursore.rowcount != 1:
        return False
    sospesa = _leggi_valore(c, CHIAVE_CHIUSURA)
    if sospesa is not None and json.loads(sospesa)["sondaggio"] == sondaggio_id:
        _togli_valore(c, CHIAVE_CHIUSURA)
    if ripresa is not None and ripresa.sondaggio == sondaggio_id:
        _togli_valore(c, CHIAVE_RIPRESA)
    return True


def _leggi_valore(c: sqlite3.Connection, chiave: str) -> str | None:
    riga = c.execute("SELECT valore FROM valori WHERE chiave = ?", (chiave,)).fetchone()
    return None if riga is None else riga["valore"]


def _scrivi_valore(c: sqlite3.Connection, chiave: str, valore: str) -> None:
    c.execute(
        "INSERT INTO valori (chiave, valore) VALUES (?, ?) "
        "ON CONFLICT (chiave) DO UPDATE SET valore = excluded.valore",
        (chiave, valore),
    )


def _registra_voto(
    c: sqlite3.Connection, sondaggio_id: int, utente_id: int, poll_id: str, voto: Voto, alle: datetime
) -> None:
    c.execute(
        """
        INSERT INTO voti (sondaggio_id, utente_id, poll_id, date, nessuna, alle)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (sondaggio_id, utente_id) DO UPDATE SET
            poll_id = excluded.poll_id,
            date = excluded.date,
            nessuna = excluded.nessuna,
            alle = excluded.alle
        """,
        (sondaggio_id, utente_id, poll_id, _giorni_json(voto.date), int(voto.nessuna), _iso(alle)),
    )


def _leggi_ripresa(c: sqlite3.Connection) -> RipresaInCorso | None:
    salvata = _leggi_valore(c, CHIAVE_RIPRESA)
    if salvata is None:
        return None
    dati = json.loads(salvata)
    return RipresaInCorso(dati["sondaggio"], dati["fase"], dati["stop_provato"])


def _scrivi_ripresa(c: sqlite3.Connection, ripresa: RipresaInCorso) -> None:
    _scrivi_valore(
        c,
        CHIAVE_RIPRESA,
        json.dumps(
            {"sondaggio": ripresa.sondaggio, "fase": ripresa.fase, "stop_provato": ripresa.stop_provato}
        ),
    )


def _togli_valore(c: sqlite3.Connection, chiave: str) -> None:
    c.execute("DELETE FROM valori WHERE chiave = ?", (chiave,))


def _scrivi_non_confermato(c: sqlite3.Connection, alle: datetime, argomenti: Sequence[str]) -> None:
    _scrivi_valore(
        c, CHIAVE_NON_CONFERMATO, json.dumps({"alle": _iso(alle), "argomenti": list(argomenti)})
    )


def _accoda(c: sqlite3.Connection, lettere: Sequence[LetteraNuova], alle: datetime) -> list[int]:
    """Accoda le `lettere` nella transazione di `c`; restituisce i loro id."""
    return [
        c.execute(
            "INSERT INTO posta (chat_id, testo, entita, risposta_a, creata_alle) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                lettera.chat_id,
                lettera.testo,
                json.dumps(list(lettera.entita), ensure_ascii=False),
                lettera.risposta_a,
                _iso(alle),
            ),
        ).lastrowid
        for lettera in lettere
    ]


class Store:
    def __init__(self, percorso: Path | str) -> None:
        self._percorso = str(percorso)

    @contextmanager
    def _connessione(self) -> Iterator[sqlite3.Connection]:
        connessione = sqlite3.connect(self._percorso, timeout=10)
        connessione.row_factory = sqlite3.Row
        connessione.execute("PRAGMA foreign_keys = ON")
        try:
            with connessione:
                yield connessione
        finally:
            connessione.close()

    def crea_schema(self) -> None:
        with self._connessione() as c:
            c.execute("PRAGMA journal_mode = WAL")
            c.executescript(SCHEMA)

    # --- sondaggi

    def sondaggio_aperto(self) -> Sondaggio | None:
        with self._connessione() as c:
            riga = c.execute("SELECT * FROM sondaggi WHERE chiuso_alle IS NULL").fetchone()
        return None if riga is None else _sondaggio(riga)

    def sondaggio(self, sondaggio_id: int) -> Sondaggio | None:
        with self._connessione() as c:
            riga = c.execute("SELECT * FROM sondaggi WHERE id = ?", (sondaggio_id,)).fetchone()
        return None if riga is None else _sondaggio(riga)

    def apri_sondaggio(
        self, date_: Sequence[date], poll_id: str, messaggio: int, frase: str, alle: datetime
    ) -> Sondaggio:
        """Con un sondaggio già aperto solleva `sqlite3.IntegrityError`."""
        with self._connessione() as c:
            nuovo = _apri(c, date_, poll_id, messaggio, frase, alle)
        return self.sondaggio(nuovo)

    def chiudi_sondaggio(
        self,
        sondaggio_id: int,
        alle: datetime,
        comando: int | None = None,
        lettere: Sequence[LetteraNuova] = (),
        non_confermato: Sequence[str] | None = None,
    ) -> bool:
        """Vero se l'ha chiuso questa chiamata. `comando` è il messaggio del
        `/chiudi` che lo chiude: lo stesso comando letto due volte non chiude il
        sondaggio seguente. Le `lettere` che dicono la chiusura si accodano
        nella stessa transazione, e solo se questa chiamata l'ha chiuso; con
        `non_confermato` (gli argomenti del comando che lo rilancia), anche il
        sondaggio nuovo di `rimanda` che Telegram non ha confermato si ricorda
        lì (v. `segna_non_confermato`)."""
        with self._connessione() as c:
            chiuso = _chiudi(c, sondaggio_id, alle, comando)
            if chiuso:
                _accoda(c, lettere, alle)
                if non_confermato is not None:
                    _scrivi_non_confermato(c, alle, non_confermato)
        return chiuso

    def rimanda(
        self,
        vecchio_id: int,
        comando: int,
        date_: Sequence[date],
        poll_id: str,
        messaggio: int,
        frase: str,
        alle: datetime,
        lettere: Sequence[LetteraNuova] = (),
    ) -> Sondaggio:
        """`/chiudi rimanda` in una transazione: chiude il vecchio con il
        comando, apre il nuovo (dopo: l'indice vuole un solo aperto) e accoda le
        `lettere`. A metà non resta niente: il vecchio è ancora aperto. Se il
        vecchio non è aperto solleva `ValueError`, e non apre niente."""
        with self._connessione() as c:
            if not _chiudi(c, vecchio_id, alle, comando):
                raise ValueError(f"rimanda: il sondaggio {vecchio_id} non è aperto")
            nuovo = _apri(c, date_, poll_id, messaggio, frase, alle)
            _accoda(c, lettere, alle)
        return self.sondaggio(nuovo)

    def poll_conosciuto(self, poll_id: str) -> bool:
        """Un sondaggio di Telegram che il bot ha registrato: quello di un
        sondaggio, quello di prima dell'ultima ripresa, o quello in cui
        qualcuno ha votato (prima di una ripresa)."""
        with self._connessione() as c:
            riga = c.execute(
                "SELECT 1 FROM sondaggi WHERE poll_id = ? OR poll_prima = ? "
                "UNION ALL SELECT 1 FROM voti WHERE poll_id = ? LIMIT 1",
                (poll_id, poll_id, poll_id),
            ).fetchone()
        return riga is not None

    def sospendi_chiusura(
        self, sospesa: ChiusuraSospesa, alle: datetime, lettere: Sequence[LetteraNuova] = ()
    ) -> None:
        """Ricorda la chiusura in sospeso (vale l'ultima) e accoda le `lettere`,
        nella stessa transazione. La toglie la chiusura del sondaggio."""
        with self._connessione() as c:
            _scrivi_valore(
                c,
                CHIAVE_CHIUSURA,
                json.dumps(
                    {
                        "sondaggio": sospesa.sondaggio,
                        "comando": sospesa.comando,
                        "argomento": sospesa.argomento,
                    }
                ),
            )
            _accoda(c, lettere, alle)

    def chiusura_sospesa(self) -> ChiusuraSospesa | None:
        salvata = self.leggi_valore(CHIAVE_CHIUSURA)
        if salvata is None:
            return None
        dati = json.loads(salvata)
        return ChiusuraSospesa(dati["sondaggio"], dati["comando"], dati["argomento"])

    def togli_chiusura_sospesa(self) -> None:
        with self._connessione() as c:
            _togli_valore(c, CHIAVE_CHIUSURA)

    def segna_non_confermato(
        self, alle: datetime, argomenti: Sequence[str], lettere: Sequence[LetteraNuova] = ()
    ) -> None:
        """Ricorda un sondaggio che Telegram non ha confermato, e che forse è
        partito (vale l'ultimo): il momento e gli argomenti del comando che lo
        rilancia. Accoda le `lettere` nella stessa transazione."""
        with self._connessione() as c:
            _scrivi_non_confermato(c, alle, argomenti)
            _accoda(c, lettere, alle)

    def ultimo_non_confermato(self) -> NonConfermato | None:
        salvato = self.leggi_valore(CHIAVE_NON_CONFERMATO)
        if salvato is None:
            return None
        dati = json.loads(salvato)
        return NonConfermato(datetime.fromisoformat(dati["alle"]), tuple(dati["argomenti"]))

    def avvisa_voto_sconosciuto(
        self, poll_id: str, alle: datetime, lettere: Sequence[LetteraNuova]
    ) -> bool:
        """La prima volta per `poll_id` accoda le `lettere` e lo ricorda, nella
        stessa transazione; vero se le ha accodate."""
        with self._connessione() as c:
            avvisati = json.loads(_leggi_valore(c, CHIAVE_SCONOSCIUTI) or "[]")
            if poll_id in avvisati:
                return False
            _scrivi_valore(c, CHIAVE_SCONOSCIUTI, json.dumps([*avvisati, poll_id]))
            _accoda(c, lettere, alle)
        return True

    def chiuso_dal_comando(self, comando: int) -> bool:
        with self._connessione() as c:
            riga = c.execute("SELECT 1 FROM sondaggi WHERE chiuso_da = ?", (comando,)).fetchone()
        return riga is not None

    # --- la ripresa dopo il buio (§3.8): un passo per transazione

    def ripresa(self) -> RipresaInCorso | None:
        with self._connessione() as c:
            return _leggi_ripresa(c)

    def inizia_ripresa(
        self, alle: datetime, lettere: Sequence[LetteraNuova], sondaggio_id: int | None
    ) -> None:
        """Segna la lettura di `alle`, accoda le `lettere` (il buio) e, se c'è
        un sondaggio da riprendere, comincia la sua ripresa in fase FERMARE.
        La ripresa dello stesso sondaggio, già in corso, resta com'è; senza
        sondaggio, resta quella che c'era (una riapertura che aspetta)."""
        with self._connessione() as c:
            _scrivi_valore(c, CHIAVE_LETTURA, _iso(alle))
            _accoda(c, lettere, alle)
            in_corso = _leggi_ripresa(c)
            if sondaggio_id is not None and (in_corso is None or in_corso.sondaggio != sondaggio_id):
                _scrivi_ripresa(c, RipresaInCorso(sondaggio_id, FERMARE))

    def prova_stop_di_ripresa(self) -> None:
        """Prima del primo stop della ripresa: da qui, un sondaggio già chiuso
        può essere stato fermato da lei."""
        with self._connessione() as c:
            in_corso = _leggi_ripresa(c)
            if in_corso is not None:
                _scrivi_ripresa(c, replace(in_corso, stop_provato=True))

    def fermato_per_riprendere(
        self, sondaggio_id: int, alle: datetime, lettere: Sequence[LetteraNuova]
    ) -> None:
        """Il sondaggio è fermo su Telegram: lo chiude, accoda le `lettere`
        (i conteggi) e passa la ripresa alla fase RIAPRIRE."""
        with self._connessione() as c:
            _chiudi(c, sondaggio_id, alle, None)
            _accoda(c, lettere, alle)
            _scrivi_ripresa(c, RipresaInCorso(sondaggio_id, RIAPRIRE))

    def riapri_sondaggio(
        self,
        sondaggio_id: int,
        date_: Sequence[date],
        poll_id: str,
        messaggio: int,
        frase: str,
        fatti: Fatti,
        alle: datetime,
        lettere: Sequence[LetteraNuova] = (),
    ) -> Sondaggio:
        """Lo stesso sondaggio su un messaggio nuovo (§3.8): i voti restano, i
        `fatti` sono quelli di prima dopo la ripresa, il sondaggio di Telegram
        di prima e le sue date si ricordano. Accoda le `lettere` («Riapro…») e
        finisce la ripresa, nella stessa transazione."""
        with self._connessione() as c:
            # a destra di SET le colonne hanno i valori di prima dell'UPDATE
            c.execute(
                "UPDATE sondaggi SET poll_prima = poll_id, date_prima = date, "
                "date = ?, poll_id = ?, messaggio = ?, frase = ?, fatti = ?, "
                "chiuso_alle = NULL, chiuso_da = NULL WHERE id = ?",
                (_giorni_json(date_), poll_id, messaggio, frase, _fatti_json(fatti), sondaggio_id),
            )
            _accoda(c, lettere, alle)
            _togli_valore(c, CHIAVE_RIPRESA)
        return self.sondaggio(sondaggio_id)

    def fine_ripresa(
        self, alle: datetime, lettere: Sequence[LetteraNuova] = (), chiudi: int | None = None
    ) -> None:
        """Finisce la ripresa senza riaprire: accoda le `lettere` e, con
        `chiudi`, chiude quel sondaggio, nella stessa transazione."""
        with self._connessione() as c:
            if chiudi is not None:
                _chiudi(c, chiudi, alle, None)
            _accoda(c, lettere, alle)
            _togli_valore(c, CHIAVE_RIPRESA)

    # --- voti

    def registra_voto(
        self, sondaggio_id: int, utente_id: int, poll_id: str, voto: Voto, alle: datetime
    ) -> None:
        """Il voto più recente di una persona sostituisce il precedente, anche
        quando è vuoto (il voto tolto)."""
        with self._connessione() as c:
            _registra_voto(c, sondaggio_id, utente_id, poll_id, voto, alle)

    def registra_voto_tardivo(
        self,
        sondaggio_id: int,
        utente_id: int,
        poll_id: str,
        voto: Voto,
        alle: datetime,
        attuale: str,
    ) -> bool:
        """Un voto dato nel sondaggio di Telegram di prima della ripresa
        (`poll_id`) e arrivato dopo la riapertura: vale solo se la persona non
        ha un voto nel sondaggio di adesso (`attuale`). Vero se l'ha registrato."""
        with self._connessione() as c:
            riga = c.execute(
                "SELECT poll_id FROM voti WHERE sondaggio_id = ? AND utente_id = ?",
                (sondaggio_id, utente_id),
            ).fetchone()
            if riga is not None and riga["poll_id"] == attuale:
                return False
            _registra_voto(c, sondaggio_id, utente_id, poll_id, voto, alle)
        return True

    def voti(self, sondaggio_id: int) -> dict[int, Voto]:
        """I voti di tutti, anche di chi non è nel roster, per identificativo."""
        with self._connessione() as c:
            righe = c.execute("SELECT * FROM voti WHERE sondaggio_id = ?", (sondaggio_id,)).fetchall()
        return {r["utente_id"]: _voto(r) for r in righe}

    def voti_del_poll(self, sondaggio_id: int, poll_id: str) -> list[Voto]:
        """Solo i voti dati nel sondaggio di Telegram `poll_id`: quelli che
        Telegram conta nei suoi conteggi."""
        with self._connessione() as c:
            righe = c.execute(
                "SELECT * FROM voti WHERE sondaggio_id = ? AND poll_id = ? ORDER BY utente_id",
                (sondaggio_id, poll_id),
            ).fetchall()
        return [_voto(r) for r in righe]

    # --- annunci fatti

    def fatti(self, sondaggio_id: int) -> Fatti:
        with self._connessione() as c:
            riga = c.execute("SELECT fatti FROM sondaggi WHERE id = ?", (sondaggio_id,)).fetchone()
        return Fatti() if riga is None else _fatti(riga["fatti"])

    def salva_fatti(self, sondaggio_id: int, fatti: Fatti) -> None:
        with self._connessione() as c:
            c.execute(
                "UPDATE sondaggi SET fatti = ? WHERE id = ?", (_fatti_json(fatti), sondaggio_id)
            )

    # --- frasi di «Nessuna»

    def frasi_usate(self) -> set[str]:
        with self._connessione() as c:
            return {r["frase"] for r in c.execute("SELECT frase FROM frasi_usate")}

    def ultima_frase(self) -> str | None:
        """L'ultima frase usata nel giro di adesso."""
        with self._connessione() as c:
            riga = c.execute("SELECT frase FROM frasi_usate ORDER BY rowid DESC LIMIT 1").fetchone()
        return None if riga is None else riga["frase"]

    def usa_frase(self, frase: str, nuovo_giro: bool = False) -> None:
        """Con `nuovo_giro`, prima dimentica le frasi del giro finito."""
        with self._connessione() as c:
            if nuovo_giro:
                c.execute("DELETE FROM frasi_usate")
            c.execute("INSERT OR IGNORE INTO frasi_usate (frase) VALUES (?)", (frase,))

    # --- posta in uscita

    def accoda(
        self,
        chat_id: int,
        testo: str,
        entita: Sequence[dict],
        risposta_a: int | None,
        alle: datetime,
    ) -> int:
        with self._connessione() as c:
            [nuova] = _accoda(c, [LetteraNuova(chat_id, testo, tuple(entita), risposta_a)], alle)
        return nuova

    def posta(self) -> list[Lettera]:
        """In ordine di arrivo."""
        with self._connessione() as c:
            righe = c.execute("SELECT * FROM posta ORDER BY id").fetchall()
        return [
            Lettera(r["id"], r["chat_id"], r["testo"], tuple(json.loads(r["entita"])), r["risposta_a"])
            for r in righe
        ]

    def togli_lettera(self, lettera_id: int) -> None:
        with self._connessione() as c:
            c.execute("DELETE FROM posta WHERE id = ?", (lettera_id,))

    # --- valori

    def leggi_valore(self, chiave: str) -> str | None:
        with self._connessione() as c:
            return _leggi_valore(c, chiave)

    def scrivi_valore(self, chiave: str, valore: str) -> None:
        with self._connessione() as c:
            _scrivi_valore(c, chiave, valore)

    def messaggio_con_bottoni(self) -> tuple[int, int] | None:
        """(sondaggio, messaggio) dell'ultimo «impossibile» con i bottoni: i
        soli che valgono (§3.10)."""
        salvato = self.leggi_valore(CHIAVE_BOTTONI)
        if salvato is None:
            return None
        sondaggio, messaggio = salvato.split(":")
        return int(sondaggio), int(messaggio)

    def segna_messaggio_con_bottoni(self, sondaggio_id: int, messaggio: int) -> None:
        self.scrivi_valore(CHIAVE_BOTTONI, f"{sondaggio_id}:{messaggio}")

    def togli_messaggio_con_bottoni(self) -> None:
        with self._connessione() as c:
            _togli_valore(c, CHIAVE_BOTTONI)

    def offset(self) -> int | None:
        salvato = self.leggi_valore(CHIAVE_OFFSET)
        return None if salvato is None else int(salvato)

    def salva_offset(self, offset: int) -> None:
        self.scrivi_valore(CHIAVE_OFFSET, str(offset))

    def ultima_lettura(self) -> datetime | None:
        salvata = self.leggi_valore(CHIAVE_LETTURA)
        return None if salvata is None else datetime.fromisoformat(salvata)

    def segna_lettura(self, alle: datetime) -> None:
        self.scrivi_valore(CHIAVE_LETTURA, _iso(alle))
