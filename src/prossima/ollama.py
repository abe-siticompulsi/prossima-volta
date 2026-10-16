"""Il client di Ollama, per le risposte (spec 2026-10-17). Nessuna politica:
una domanda a `/api/chat`, e il testo che torna.

Ogni guasto (rete, tempo scaduto, errore HTTP, risposta illeggibile) è un
`OllamaError`: chi chiama ripiega su una frase fissa. Il modello resta in
memoria quanto vuole Ollama (il suo `keep_alive` di default, 5 minuti): a
freddo una chiamata prende fino a un minuto e passa.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

# Secondi: a freddo gemma3 ci mette 75 secondi a rispondere, e la CPU è condivisa con Paperless.
TEMPO_MASSIMO = 180.0


class OllamaError(RuntimeError):
    """Ollama non ha risposto, o non come doveva."""


@dataclass(frozen=True)
class Risposta:
    testo: str
    troncata: bool = False  # finita al limite di token: il testo è a metà


class Ollama:
    def __init__(
        self, url: str, http: httpx.Client | None = None, tempo_massimo: float = TEMPO_MASSIMO
    ) -> None:
        self._url = f"{url.rstrip('/')}/api/chat"
        self._http = http or httpx.Client()
        self._tempo_massimo = tempo_massimo

    def chiedi(
        self,
        modello: str,
        sistema: str,
        utente: str,
        *,
        temperatura: float,
        massimo_token: int,
        formato: dict | None = None,
    ) -> Risposta:
        """Una domanda, senza flusso. Con `formato` (uno schema JSON) Ollama
        costringe la risposta a seguirlo. Il campionamento è quello del
        prototipo, uguale per ogni modello."""
        corpo: dict = {
            "model": modello,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": utente},
            ],
            "stream": False,
            "options": {
                "temperature": temperatura,
                "num_predict": massimo_token,
                "top_k": 40,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }
        if formato is not None:
            corpo["format"] = formato
        try:
            risposta = self._http.post(self._url, json=corpo, timeout=self._tempo_massimo)
        except httpx.HTTPError as e:
            raise OllamaError(f"{modello}: errore di rete ({type(e).__name__})") from None
        if risposta.status_code != 200:
            raise OllamaError(f"{modello}: HTTP {risposta.status_code} {risposta.text[:200]}")
        try:
            dati = risposta.json()
            testo = dati["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise OllamaError(f"{modello}: risposta illeggibile") from None
        return Risposta(testo, troncata=dati.get("done_reason") == "length")
