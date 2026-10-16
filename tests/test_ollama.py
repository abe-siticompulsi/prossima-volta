import json
import re

import httpx
import pytest

from prossima.ollama import Ollama, OllamaError, Risposta

URL = "http://ollama:11434/"


def ollama(gestisci) -> Ollama:
    return Ollama(URL, httpx.Client(transport=httpx.MockTransport(gestisci)))


def test_chiedi_manda_la_chat_e_legge_il_testo():
    corpi = []

    def gestisci(richiesta: httpx.Request) -> httpx.Response:
        corpi.append((richiesta.url.path, json.loads(richiesta.content)))
        return httpx.Response(200, json={"message": {"content": "Ciao"}, "done_reason": "stop"})

    r = ollama(gestisci).chiedi(
        "llama3:latest", "sistema", "utente", temperatura=0.0, massimo_token=60, formato={"x": 1}
    )
    assert r == Risposta("Ciao")
    [(percorso, corpo)] = corpi
    assert percorso == "/api/chat"
    assert corpo["model"] == "llama3:latest"
    assert corpo["messages"] == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "utente"},
    ]
    assert corpo["stream"] is False and corpo["format"] == {"x": 1}
    assert corpo["options"]["temperature"] == 0.0 and corpo["options"]["num_predict"] == 60
    assert "keep_alive" not in corpo  # quello di default di Ollama


def test_una_risposta_al_limite_di_token_e_troncata():
    r = ollama(
        lambda _: httpx.Response(200, json={"message": {"content": "a"}, "done_reason": "length"})
    ).chiedi("m", "s", "u", temperatura=0.5, massimo_token=1)
    assert r.troncata


def test_senza_formato_non_lo_manda():
    corpi = []

    def gestisci(richiesta):
        corpi.append(json.loads(richiesta.content))
        return httpx.Response(200, json={"message": {"content": "x"}})

    ollama(gestisci).chiedi("m", "s", "u", temperatura=0.5, massimo_token=10)
    assert "format" not in corpi[0]


def _rete_giu(richiesta):
    raise httpx.ConnectError("giù", request=richiesta)


@pytest.mark.parametrize(
    "gestisci, messaggio",
    [
        (_rete_giu, "m: errore di rete (ConnectError)"),
        (lambda _: httpx.Response(404, text='{"error":"model not found"}'), "m: HTTP 404"),
        (lambda _: httpx.Response(200, text="non json"), "m: risposta illeggibile"),
        (lambda _: httpx.Response(200, json={"altro": 1}), "m: risposta illeggibile"),
    ],
)
def test_ogni_guasto_e_un_errore_di_ollama(gestisci, messaggio):
    with pytest.raises(OllamaError, match=re.escape(messaggio)):
        ollama(gestisci).chiedi("m", "s", "u", temperatura=0.5, massimo_token=10)
