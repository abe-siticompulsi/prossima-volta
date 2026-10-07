# Prossima volta

Il bot Telegram che, nel gruppo dei *Danni Radiosi*, crea il sondaggio per la
data della sessione seguente (`/sondaggio`), ne segue i voti e dice nel gruppo
quando una data va bene, quando ci si è vicini e chi non ha ancora votato, e
quando con le date proposte non ci si sta. Lo chiudono gio o abe (`/chiudi`).

Il design sta in `docs/superpowers/specs/`, il piano in `docs/superpowers/plans/`.
Leggi la specifica prima di cambiare il comportamento: i testi dei messaggi
sono copiati da lì, e molte scelte hanno un motivo che il codice da solo non
spiega.

## Sviluppo

Richiede [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest -q                 # la suite veloce, con un Telegram finto
uv run ruff check src tests
```

Il piano reale (`-m reale`) parla con il bot vero, nella chat privata di
Alberto, a servizio fermo: v. `docs/messa-in-produzione.md`. Le convinzioni che
i finti mettono per iscritto, e dove vengono verificate, stanno in
`docs/differenze-fra-test-e-realta.md`.

## In produzione

In Docker, sulla stessa macchina dei selfie ma in un container suo:
`docs/messa-in-produzione.md`.
