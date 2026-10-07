"""Lo stato del bot, in SQLite: sondaggi, voti, annunci fatti, frasi usate,
posta in uscita, offset del bot e momento dell'ultima lettura.

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
from dataclasses import dataclass
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
    chiuso_da INTEGER
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


@dataclass(frozen=True)
class Sondaggio:
    id: int
    date: tuple[date, ...]
    poll_id: str  # il sondaggio di Telegram di adesso: cambia alla ripresa (§3.8)
    messaggio: int
    frase: str
    aperto_alle: datetime
    chiuso_alle: datetime | None = None


@dataclass(frozen=True)
class Lettera:
    """Un messaggio in attesa di partire."""

    id: int
    chat_id: int
    testo: str
    entita: tuple[dict, ...]
    risposta_a: int | None


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
            cursore = c.execute(
                "INSERT INTO sondaggi (date, poll_id, messaggio, frase, aperto_alle) "
                "VALUES (?, ?, ?, ?, ?)",
                (_giorni_json(date_), poll_id, messaggio, frase, _iso(alle)),
            )
            nuovo = cursore.lastrowid
        return self.sondaggio(nuovo)

    def chiudi_sondaggio(self, sondaggio_id: int, alle: datetime, comando: int | None = None) -> bool:
        """Vero se l'ha chiuso questa chiamata. `comando` è il messaggio del
        `/chiudi` che lo chiude: lo stesso comando letto due volte non chiude il
        sondaggio seguente."""
        with self._connessione() as c:
            cursore = c.execute(
                "UPDATE sondaggi SET chiuso_alle = ?, chiuso_da = ? "
                "WHERE id = ? AND chiuso_alle IS NULL",
                (_iso(alle), comando, sondaggio_id),
            )
        return cursore.rowcount == 1

    def chiuso_dal_comando(self, comando: int) -> bool:
        with self._connessione() as c:
            riga = c.execute("SELECT 1 FROM sondaggi WHERE chiuso_da = ?", (comando,)).fetchone()
        return riga is not None

    def riapri_sondaggio(
        self, sondaggio_id: int, date_: Sequence[date], poll_id: str, messaggio: int, frase: str
    ) -> Sondaggio:
        """Lo stesso sondaggio su un messaggio nuovo (§3.8): voti e annunci fatti restano."""
        with self._connessione() as c:
            c.execute(
                "UPDATE sondaggi SET date = ?, poll_id = ?, messaggio = ?, frase = ?, "
                "chiuso_alle = NULL, chiuso_da = NULL WHERE id = ?",
                (_giorni_json(date_), poll_id, messaggio, frase, sondaggio_id),
            )
        return self.sondaggio(sondaggio_id)

    # --- voti

    def registra_voto(
        self, sondaggio_id: int, utente_id: int, poll_id: str, voto: Voto, alle: datetime
    ) -> None:
        """Il voto più recente di una persona sostituisce il precedente, anche
        quando è vuoto (il voto tolto)."""
        with self._connessione() as c:
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

    def usa_frase(self, frase: str) -> None:
        with self._connessione() as c:
            c.execute("INSERT OR IGNORE INTO frasi_usate (frase) VALUES (?)", (frase,))

    def dimentica_frasi(self) -> None:
        with self._connessione() as c:
            c.execute("DELETE FROM frasi_usate")

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
            cursore = c.execute(
                "INSERT INTO posta (chat_id, testo, entita, risposta_a, creata_alle) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, testo, json.dumps(list(entita), ensure_ascii=False), risposta_a, _iso(alle)),
            )
            return cursore.lastrowid

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
            riga = c.execute("SELECT valore FROM valori WHERE chiave = ?", (chiave,)).fetchone()
        return None if riga is None else riga["valore"]

    def scrivi_valore(self, chiave: str, valore: str) -> None:
        with self._connessione() as c:
            c.execute(
                "INSERT INTO valori (chiave, valore) VALUES (?, ?) "
                "ON CONFLICT (chiave) DO UPDATE SET valore = excluded.valore",
                (chiave, valore),
            )

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
