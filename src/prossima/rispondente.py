"""Il rispondente: un thread che scrive le risposte con Ollama (spec
2026-10-17 §6), una alla volta: i 4 core del server sono condivisi con
Paperless. Non tocca né Telegram né il database: riceve una `Domanda` con la
foto dei fatti, e rende un `Esito`. Il bot, nel suo filo, prende le risposte
pronte a ogni giro.

Al massimo `MASSIMO` domande in lavoro, dall'arrivo a quando il bot prende la
risposta: oltre, `accetta` dice di no, e il bot risponde subito con la frase
fissa. Un riavvio perde le domande in lavoro.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

from . import testi
from .risposte import Domanda, Esito

log = logging.getLogger(__name__)

MASSIMO = 3


class Rispondente:
    def __init__(self, scrivi: Callable[[Domanda], Esito], massimo: int = MASSIMO) -> None:
        self._scrivi = scrivi
        self._massimo = massimo
        self._fila: queue.Queue[Domanda] = queue.Queue()
        self._pronte: queue.Queue[tuple[Domanda, Esito]] = queue.Queue()
        self._lucchetto = threading.Lock()
        self._in_lavoro: list[Domanda] = []
        threading.Thread(target=self._lavora, name="rispondente", daemon=True).start()

    def accetta(self, domanda: Domanda) -> bool:
        """Mette la domanda in fila, se c'è posto."""
        with self._lucchetto:
            if len(self._in_lavoro) >= self._massimo:
                return False
            self._in_lavoro.append(domanda)
        self._fila.put(domanda)
        return True

    def in_lavoro(self) -> tuple[Domanda, ...]:
        """Le domande accettate di cui il bot non ha ancora preso la risposta."""
        with self._lucchetto:
            return tuple(self._in_lavoro)

    def pronte(self) -> list[tuple[Domanda, Esito]]:
        """Le risposte pronte, nell'ordine in cui sono finite; dopo non sono più in lavoro."""
        pronte = []
        while True:
            try:
                pronte.append(self._pronte.get_nowait())
            except queue.Empty:
                break
        with self._lucchetto:
            for domanda, _ in pronte:
                self._in_lavoro.remove(domanda)
        return pronte

    def _lavora(self) -> None:
        while True:
            domanda = self._fila.get()
            try:
                esito = self._scrivi(domanda)
            except Exception:
                log.exception("risposta non scritta")
                esito = Esito(testi.non_riesco())
            self._pronte.put((domanda, esito))
