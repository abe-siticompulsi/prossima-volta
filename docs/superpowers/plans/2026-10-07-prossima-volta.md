# Prossima volta — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un bot Telegram che, nel gruppo del party dei Danni Radiosi, crea il sondaggio per la data della sessione seguente, ne segue i voti e dice nel gruppo quando una data va bene, quando ci si è vicini (e chi non ha ancora votato) e quando con le date proposte non ci si sta.

**Architecture:** Un solo processo Python, con un solo filo, in un container suo. Il ciclo di `principale.py` legge Telegram in long polling e passa ogni lotto a `Bot.ricevi` (`bot.py`), che smista comandi e voti, salva tutto in SQLite (`store.py`) e parla con Telegram attraverso un client sottile (`telegram.py`). Le regole (date, conteggi, annunci) sono pure (`regole.py`) e i testi per le persone stanno tutti in `testi.py`. Gli annunci si ricalcolano dallo stato a ogni giro e contano come fatti solo dopo che Telegram li ha accettati; ogni altro messaggio passa da una posta in uscita nel database, così un invio fallito riparte al giro seguente.

**Tech Stack:** Python 3.12 con uv, httpx, tzdata, sqlite3 e tomllib della libreria standard; pytest e ruff; Docker Compose sul server.

**Spec:** `docs/superpowers/specs/2026-10-07-prossima-volta-design.md` (commit `db92f7d`: comando `/sondaggio`, date in formato italiano). Modello per struttura, stile e tecniche: `~/git/python/radiant-selfie-machine` (sola lettura: niente codice condiviso).

## Global Constraints

Dalla spec, alla lettera (fra parentesi la sezione):

- (§5) Repo `~/git/python/prossima-volta`, pacchetto `prossima`, Python 3.12 con uv, httpx, `tzdata` (il fuso nel container). Nessuna parte web, nessuna porta.
- (§2) **Ogni messaggio afferma solo ciò che è verificato** — La regola di tutti i progetti di Alberto.
- (§3.5) Testo semplice, senza `parse_mode`. I nomi sono i soprannomi del roster. Le **menzioni** sono entità `text_mention` con l'identificativo Telegram della persona: notificano anche chi non ha un nome utente. Gli scostamenti delle entità si contano in unità UTF-16, come vuole Telegram (un'emoji come 📅 ne vale due). Le date nei messaggi hanno la forma delle opzioni («mar 14/10»).
- (§3.2) Opzioni: le date come «mar 14/10», nel formato italiano (giorno abbreviato: lun mar mer gio ven sab dom; giorno e mese senza zeri iniziali), più in fondo una frase di «Nessuna di queste» (§3.6).
- (§3.1) **Con date** (`g/m` o `g/m/aaaa`, e anche con il punto: `g.m`, `g.m.aaaa`): quelle date.
- (§3.1) «Settimana seguente» è la settimana di calendario dopo quella di oggi, nel fuso `Europe/Zurich` (di domenica è quella che comincia domani).
- (§3.4) Costanti: giocatori per giocare **4**; giocatori per «quasi» **3**; votanti perché «quasi» valga **4**.
- (§3.1) più di 10 date: «Troppe date: al massimo 10.»
- (§3.5) Un annuncio conta come fatto solo dopo che Telegram l'ha accettato. Quali annunci mandare si calcola dallo stato (voti) e dagli annunci già fatti, con una funzione pura: rifarlo non ripete niente, e un messaggio non partito riparte al giro seguente (§4).
- (§3.6) Una lista di frasi in `testi.py`, tutte di al massimo 100 caratteri (il limite di Telegram per un'opzione) e tutte comincianti con «Nessuna».
- (§3.8) Quando una lettura riesce più di **23 ore** dopo la precedente (un'ora di margine sulle 24), dopo aver gestito gli aggiornamenti ricevuti: […] (ore nel fuso `Europe/Zurich`).
- (§4) A ogni giro del ciclo (long polling di 25 secondi) il bot ricalcola gli annunci dei sondaggi aperti e manda quelli mancanti. Un 429 si rispetta: nessun invio prima di `retry_after`.
- (§4) **Il ciclo non si ferma** per un errore: lo registra e continua (come `cicli.py` di `radiant-selfie-machine`).
- (§4) **Il token non finisce mai nei log** (stessa tecnica del client dei selfie: niente testo delle eccezioni di httpx, niente concatenazione, logger `httpx` a WARNING).
- (§4) **Un solo processo, un solo filo**: niente gare.
- (§5) **Configurazione** (`config/prossima.env`, mai nel repo): `PV_BOT_TOKEN`, `PV_GRUPPO` (l'identificativo del gruppo del party), `PV_ROSTER=/config/roster.toml`, `PV_DB=/data/prossima.sqlite`, `PV_BATTITO=/data/battito`, `PV_FUSO=Europe/Zurich`. Per il piano reale: `PV_REALE_CHAT` (l'identificativo di Alberto).
- (§5) **Roster** (`config/roster.toml`, mai nel repo; nel repo solo `config.esempio/roster.toml` con identificativi finti). […] Esattamente un master; soprannomi e identificativi unici; un valore sbagliato ferma il servizio con un messaggio chiaro.
- (§5) **Container**: un servizio, `restart: unless-stopped`, volumi `./dati:/data` e `./config:/config:ro`. Controllo di salute: il battito (un file che il ciclo tocca a ogni giro) ha meno di 2 minuti.
- (§5) All'avvio registra i comandi (`setMyCommands`): `sondaggio` («Sondaggio per la prossima volta») e `chiudi` («Chiude il sondaggio»).
- (§6) **Piano reale** (`-m reale`), con il bot vero nella chat privata di Alberto (`PV_REALE_CHAT`), **a servizio fermo** (due lettori dello stesso bot si rubano gli aggiornamenti). **`docs/differenze-fra-test-e-realta.md`**, scritto prima dei finti.
- I testi dei messaggi (§3.1, §3.5, §3.7, §3.8) si copiano alla lettera: `testi.py` e le prove li riportano parola per parola.

Del progetto:

- **Italiano** nei testi per le persone, nei commenti, nelle docstring e nei nomi nuovi, come nel progetto dei selfie. I messaggi di commit sono **in inglese e brevi**, e finiscono con la riga `Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>`: chi esegue il task mette al posto di `<il modello che fa il commit>` il nome del proprio modello (per esempio `Claude Opus 5.5`).
- **Il repo sarà pubblico:** nessun dato personale vero. Identificativi Telegram finti (`100000001`…), gruppo finto (`-1000000000001`), nessun nome di server vero. I soprannomi del roster (gio, abe, emi, sem, sese, pippo) vanno bene.
- **Il tempo si inietta** (`adesso: Callable[[], datetime]`, e `oggi` nelle regole): nessuna prova dipende dall'orologio vero. Nel database i momenti sono stringhe ISO in UTC; giorni della settimana, «settimana seguente» e ore nei messaggi sono nel fuso `Europe/Zurich`.
- **TDD:** prima la prova che fallisce, poi il codice che la fa passare. La suite veloce resta veloce: niente rete, niente attese vere; il piano reale (`-m reale`) è escluso di default.
- **Ruff:** ogni task finisce con `uv run ruff check src tests` pulito.
- **Ramo:** `prima-versione` (esiste già, con la spec). Non si fonde senza l'assenso di Alberto. Niente sotto `.superpowers/` nei commit (è già in `.gitignore`).

## Verificato prima della consegna

Il codice di questo piano è stato estratto dal piano stesso ed eseguito task per task, in una copia usa e getta del repo, il 7/10/2026: ogni «Expected: FAIL» fallisce, ogni «Expected: PASS» passa con il numero di prove indicato, ruff è pulito alla fine di ogni task e ogni commit lascia l'albero pulito. Alla fine: 214 prove veloci verdi; il piano reale (7 prove) passa il controllo del fuso e salta le altre dicendo quale variabile manca; `prossima salute` risponde 0 con un battito fresco e 1 senza; `prossima` senza configurazione si ferma con «configurazione: PV_BOT_TOKEN manca». **Non** verificati qui: l'immagine Docker (Docker non c'era sulla macchina della verifica) e il piano reale contro il bot vero.

I fatti sull'API di Telegram usati qui vengono dalla documentazione della Bot API 10.3 (24/08/2026): `sendPoll` accetta da 1 a 12 opzioni di al massimo 100 caratteri; `allows_revoting` esiste ed è vero per default nei sondaggi normali; in `PollAnswer`, `option_ids` «May be empty if the vote was retracted»; gli scostamenti delle entità sono «in UTF-16 code units»; `getUpdates` non tiene gli aggiornamenti più di 24 ore. La descrizione dell'errore di `stopPoll` per un messaggio cancellato **non** è documentata: la verifica il piano reale.

## Scelte su punti che la spec lascia aperti

Da controllare con Alberto: la spec non le decide, il piano sì.

1. **Una data `g/m` senza anno già passata.** La spec dice «l'anno è quello della prossima volta che la data arriva, oggi compreso», ma dà anche il rifiuto «La data 3/10 è già passata.»: con la prima regola presa alla lettera una data senza anno non è mai passata (il 7/10, `3/10` diventerebbe il 3/10 dell'anno dopo, e il sondaggio avrebbe un'opzione lontana un anno, scritta come se fosse fra pochi giorni). Scelta: vale la data **più vicina a oggi** fra l'anno scorso, quest'anno e il prossimo (`regole._data_senza_anno`). In pratica è la prossima volta che la data arriva (il 28/12, `2/1` è il 2 gennaio dopo), salvo per una data passata da meno di sei mesi, che è rifiutata come passata. Con l'anno scritto (`3/10/2025`) il rifiuto ripete l'anno: «La data 3/10/2025 è già passata.».
2. **Prima il sondaggio, poi il messaggio che lo annuncia.** La spec scrive «scrive «🔁 Rimandiamo: …» e lancia un sondaggio nuovo»; il bot manda prima il sondaggio e scrive «🔁 Rimandiamo…» (e, alla ripresa, «Riapro il sondaggio…») solo dopo che Telegram l'ha accettato: se il sondaggio nuovo non parte, nessun messaggio dice che c'è. In quel caso il vecchio resta chiuso e nel gruppo non compare niente (l'errore va nel log). *Aggiornata nei giri di correzioni A e B:* con `rimanda` il bot chiude il vecchio e scrive «🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: …» con il comando da copiare; alla ripresa il vecchio resta chiuso, nel gruppo non compare niente (non «riprovate con /sondaggio», che farebbe buttare i voti tenuti) e il bot riprova a ogni lettura, finché il sondaggio parte, un `/sondaggio` lo sostituisce o le date passano.
3. **Il messaggio del sondaggio cancellato.** Con `/chiudi` il bot dice «Il messaggio del sondaggio non c'è più: lo considero chiuso.» e poi fa il resto del comando («🔒…», «🎲…», o il sondaggio nuovo di «rimanda»). Alla ripresa (§3.8) dice la stessa frase e si ferma: niente confronto dei conteggi, niente sondaggio riaperto.
4. **`/chiudi <argomento>`.** Una data si riconosce per giorno e mese fra le date del sondaggio (`14/10`, `14.10`, o `14/10/2025` con l'anno uguale); un giorno della settimana (`mar`) vale se nel sondaggio c'è una sola data con quel giorno, altrimenti «Non capisco «mar»: …»; un giorno assente dà «La data ven non era nel sondaggio.»; più di una parola dà «Non capisco «14/10 16/10»: …». Le date nei rifiuti sono scritte `g/m`; la parola non capita è riportata com'è stata scritta.
5. **«Impossibile» con più date in tre:** l'esempio «/chiudi@<bot> 14/10 per tenerla» usa la prima di quelle date.
6. **Chi «ha tolto il voto»:** le persone presenti quando il bot ha annunciato «possibile» e non presenti adesso. Dopo una ripresa il bot dimentica chi c'era (evento `Ripresa`), e un «non più possibile» usa la frase senza nomi; la usa anche se le persone mancanti non sono più nel roster.
7. **«Quasi» e «non più possibile» insieme.** Se una data possibile perde una sola persona torna con il master e tre giocatori: il bot dice «⚠️ … non va più bene: sem ha tolto il voto.» e, se per quella data non l'aveva mai detto, anche «📅 … manca un giocatore.» (il «quasi» resta uno per data). Nota: con il master e tre giocatori presenti hanno votato almeno quattro persone del roster, quindi la condizione dei 4 votanti non cambia mai l'esito.
8. **Posta in uscita.** Ogni messaggio che non è un annuncio (risposte ai comandi, chiusura, ripresa) passa da una tabella `posta` e parte in ordine; se non parte resta lì e riparte al giro seguente. Un rifiuto 4xx lo scarta con un errore nel log (ripeterlo darebbe lo stesso rifiuto). Gli annunci, se Telegram li rifiuta, si ritentano a ogni giro: per la spec contano come fatti solo dopo che Telegram li ha accettati.
9. **Risposte.** Rispondono al comando (`reply_parameters`) i rifiuti di `/sondaggio` e di `/chiudi` («Non capisco…», «La data…», «Troppe date…», «Il sondaggio lo chiudono…», «Non c'è nessun sondaggio aperto.»); «C'è già un sondaggio aperto…» risponde al sondaggio aperto. Gli annunci e gli altri messaggi sono messaggi semplici.
10. **Un `/chiudi` letto due volte** dopo un riavvio non chiude il sondaggio nato dal primo (`/chiudi rimanda` ne aprirebbe un terzo): il sondaggio ricorda il messaggio del comando che l'ha chiuso (`chiuso_da`).
11. **Conteggi alla ripresa:** i nostri si calcolano solo sui voti dati nel sondaggio di Telegram che si ferma (`poll_id`), compresi quelli di chi non è nel roster; i voti tenuti buoni da una ripresa precedente non sono nei conteggi di Telegram. Un voto che arriva per un sondaggio di Telegram che non è quello aperto si ignora.
12. **«Riapro il sondaggio…»:** «Non hanno ancora votato» elenca chiunque nel roster non abbia un voto, master compreso.
13. **Il roster:** `chiude` è facoltativo (falso se manca); una chiave sconosciuta (un refuso come `chuide`) ferma l'avvio; serve almeno una persona con `chiude = true`; `telegram_id` è un intero positivo. `PV_FUSO` vuoto vale `Europe/Zurich`; le altre variabili sono obbligatorie.
14. **`allows_revoting: true`** si passa esplicitamente a `sendPoll` (è il default dei sondaggi normali nella Bot API 10.x): togliere o cambiare il voto è parte delle regole.
15. **Il piano reale** legge `getUpdates` senza offset, per non confermare (e quindi rubare al servizio) gli aggiornamenti arrivati intanto; un test chiede ad Alberto di votare nella chat privata entro tre minuti. `getMyCommands` e `deleteMessage` servono solo al piano reale, che le chiama con il `_chiama` del client invece di aggiungere metodi che il bot non usa.

## Struttura dei file

| file | responsabilità |
|---|---|
| `pyproject.toml`, `.python-version`, `uv.lock` | il progetto, le dipendenze, pytest (piano reale escluso di default) e ruff |
| `docs/differenze-fra-test-e-realta.md` | le convinzioni sul vero che i finti mettono per iscritto, e dove si verificano. Si scrive **prima** dei finti |
| `src/prossima/regole.py` | puro: date di `/sondaggio` e di `/chiudi`, etichette, roster, voti, conteggi, possibile/quasi/fuori, impossibile, `annunci_da_fare`, i fatti, il buio |
| `src/prossima/testi.py` | tutti i testi per le persone, con le menzioni in UTF-16, e le frasi di «Nessuna» |
| `src/prossima/store.py` | SQLite: sondaggi (con gli annunci fatti), voti di tutti, frasi usate, posta in uscita, offset, ultima lettura |
| `src/prossima/config.py` | le variabili d'ambiente e il roster, con errori chiari |
| `src/prossima/telegram.py` | il client: `io`, `aggiornamenti`, `manda_sondaggio`, `scrivi`, `ferma_sondaggio`, `registra_comandi`; errori senza token |
| `src/prossima/bot.py` | smista comandi e voti, manda posta e annunci, `/chiudi`, la ripresa dopo il buio |
| `src/prossima/principale.py` | l'avvio, il ciclo, il battito, `prossima salute` |
| `config.esempio/roster.toml`, `config.esempio/prossima.env` | gli esempi, con identificativi finti |
| `tests/tavolo.py`, `tests/finti.py`, `tests/aggiornamenti.py`, `tests/conftest.py` | il tavolo delle prove, i finti, gli aggiornamenti di Telegram, le fixture |
| `tests/test_*.py` | la suite veloce |
| `tests/reale/` | il piano reale: bot vero, immagine e configurazione vere |
| `Dockerfile`, `.dockerignore`, `compose.yaml` | il container |
| `docs/messa-in-produzione.md`, `README.md` | come si mette in produzione, come si sviluppa |

## Come leggere i passi

- «Crea `x`:» e «Sostituisci l'intero `x` con:» danno il contenuto completo del file.
- «In `x`, sostituisci: … con: …» è una sostituzione esatta: il primo blocco compare una volta sola nel file.
- «In fondo a `x`, aggiungi:» accoda il blocco alla fine del file.
- Ogni comando si lancia dalla radice del repo, `~/git/python/prossima-volta`, sul ramo `prima-versione`.

## I task

1. Lo scheletro, le differenze fra test e realtà, le date (`regole.py`, prima metà).
2. Chi conta, le regole delle date, gli annunci (`regole.py`, seconda metà).
3. I testi, con le menzioni in UTF-16, e le frasi di «Nessuna» (`testi.py`).
4. Lo store SQLite (`store.py`).
5. La configurazione e il roster (`config.py`).
6. Il client di Telegram e il suo finto (`telegram.py`, `tests/finti.py`).
7. Il bot: `/sondaggio`, i voti, gli annunci, gli invii che non riescono.
8. Il bot: `/chiudi` nelle tre forme.
9. Il bot: la ripresa dopo il buio (§3.8).
10. L'avvio, il ciclo, il battito, il container, il piano reale, la guida.

Dieci invece di nove: il bot è diviso in tre task perché `/chiudi` (con `rimanda`, il messaggio cancellato e il comando letto due volte) e la ripresa sono unità che un revisore può respingere senza respingere il percorso `/sondaggio`, voti, annunci.

---

### Task 1: lo scheletro, le differenze fra test e realtà, le date

Il progetto nasce qui, con l'elenco delle convinzioni sul vero (prima dei finti, come vuole la spec §6) e con la prima metà di `regole.py`: le date di `/sondaggio` e di `/chiudi`, le etichette, i rifiuti. Tutto puro: il giorno di oggi arriva come argomento.

**Files:**
- Create: `pyproject.toml`, `.python-version`, `uv.lock`, `src/prossima/__init__.py`, `tests/__init__.py`
- Create: `docs/differenze-fra-test-e-realta.md`
- Create: `src/prossima/regole.py`
- Create: `tests/tavolo.py`
- Test: `tests/test_date.py`

**Interfaces:**
- Consumes: niente.
- Produces (`prossima.regole`): `GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")`, `GIORNI_INTERI`, `MASSIMO_DATE = 10`, `RIMANDA = "rimanda"`; eccezioni `Rifiuto(ValueError)`, `NonCapisco(parola: str)` con `.parola`, `DataPassata(scritta: str)` con `.scritta`, `TroppeDate()`, `NonNelSondaggio(scritta: str)` con `.scritta`; `breve(giorno: date) -> str` («14/10»); `etichetta(giorno: date) -> str` («mar 14/10»); `etichetta_intera(giorno: date) -> str` («martedì 14/10»); `lunedi_seguente(giorno: date) -> date`; `date_del_comando(parole: Sequence[str], oggi: date) -> list[date]`; `data_da_chiudere(parola: str, date_sondaggio: Sequence[date]) -> date`; `date_rimandate(date_sondaggio: Sequence[date]) -> list[date]`.
- Produces (`tests.tavolo`): `OGGI = date(2025, 10, 7)` (un martedì: la settimana seguente va dal 13 al 19/10, e il 14/10 è un martedì come negli esempi della spec); `d(scritta: str, anno: int = 2025) -> date` («14/10» → 14 ottobre 2025).

- [ ] **Step 1: lo scheletro del progetto**

```bash
mkdir -p src/prossima tests docs
touch src/prossima/__init__.py tests/__init__.py
uv python pin 3.12
```

`uv python pin` scrive `.python-version`: senza, uv sceglie il Python più recente installato, mentre il container usa il 3.12.

Crea `pyproject.toml`:

```toml
[project]
name = "prossima-volta"
version = "0.1.0"
description = "Il sondaggio per la data della prossima sessione dei Danni Radiosi, nel gruppo Telegram"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28,<1",
    # Il fuso Europe/Zurich anche nell'immagine slim, che non ha /usr/share/zoneinfo.
    "tzdata>=2025.2",
]

[project.scripts]
prossima = "prossima.principale:main"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.16"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/prossima"]

[tool.pytest.ini_options]
testpaths = ["tests"]
# Escluso di default: il piano reale parla con il bot vero e aspetta il voto di
# Alberto. La suite veloce deve restare veloce, altrimenti smette di essere
# lanciata.
#   uv run pytest -m reale -rs    il piano reale (v. tests/reale/)
addopts = "-m 'not reale'"
markers = [
    "reale: verifica un sistema esterno vero, non un suo finto (v. tests/reale/)",
]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
# La lunghezza delle righe la cura `ruff format`, non il linter.
ignore = ["E501"]
```

Poi:

```bash
uv sync
```

Expected: crea `.venv/` e `uv.lock` senza errori.

- [ ] **Step 2: le differenze fra test e realtà**

Si scrive adesso, prima di qualsiasi finto: ogni riga è una convinzione che i finti dei task 6–10 metteranno per iscritto, e dice dove il vero la mette alla prova.

Crea `docs/differenze-fra-test-e-realta.md`:

```markdown
# Differenze fra test e realtà

Ogni finto mette per iscritto una convinzione sul mondo vero, e un finto non
può smentire chi l'ha scritto: la conferma con un pallino verde. Questo elenco
dice quali convinzioni stanno nei finti e dove vengono messe alla prova contro
il vero. Si scrive prima dei finti, e si aggiorna ogni volta che il vero ne
smentisce una.

| Nei test | Nella realtà | Dove si verifica |
|---|---|---|
| Telegram risponde subito e con `ok: true` (`TelegramFinto`), salvo i guasti che la prova imposta. | Può fallire, rallentare, rifiutare (4xx) o chiedere di aspettare (429 con `retry_after`). | `tests/test_telegram.py` legge le risposte d'errore nella forma documentata dall'API. Un 429 vero non si provoca: vorrebbe dire inondare il bot. |
| Un sondaggio non anonimo, a risposta multipla, con fino a 11 opzioni (10 date e la frase di «Nessuna») parte, e il voto si può cambiare. | L'API ammette da 1 a 12 opzioni di al massimo 100 caratteri; `allows_revoting` è vero per default nei sondaggi normali, e il bot lo chiede comunque. Che un sondaggio non anonimo parta anche in una chat privata non è scritto da nessuna parte. | `tests/reale/test_telegram_vero.py::test_sondaggio_voto_ritiro_e_conteggi`: 10 date e la frase più lunga, nella chat privata di Alberto. |
| Un voto arriva come `poll_answer` con l'identificativo di chi vota (`user.id`) e le opzioni spuntate, contate da 0; il voto ritirato arriva con `option_ids` vuoto. | Telegram manda i voti a un bot solo per i sondaggi non anonimi creati da lui. | Il piano reale: Alberto vota, ritira il voto e vota di nuovo. |
| `stopPoll` restituisce i conteggi per opzione, nell'ordine delle opzioni. | L'API restituisce il `Poll` fermato, con `voter_count` per opzione («may be 0 if unknown»). | Il piano reale, dopo il voto di Alberto. |
| Un sondaggio cancellato fa rispondere a `stopPoll` «message to stop not found», che il client riconosce come `MessaggioSparito`. | La descrizione la sceglie Telegram, e non è documentata. | `tests/reale/test_telegram_vero.py::test_fermare_un_sondaggio_cancellato`: il bot manda un sondaggio, lo cancella e prova a fermarlo. |
| Le menzioni sono entità `text_mention` con il solo identificativo, e gli scostamenti contati in unità UTF-16 cadono sul nome. | Telegram rifiuta o sposta le entità con scostamenti sbagliati; se una menzione notifichi davvero lo vede solo una persona. | Il piano reale rilegge le entità nel messaggio che Telegram restituisce; a mano, nel gruppo: la notifica arriva. |
| Il bot riceve `/sondaggio` e `/sondaggio@<bot>` dal gruppo. | Con la privacy attiva il bot riceve solo i comandi rivolti a lui: con altri bot nel gruppo un `/sondaggio` nudo può non arrivare, e il menu dei comandi aggiunge `@<bot>` da solo. | A mano, nel gruppo: `/sondaggio@<bot>` dal menu. |
| Il bot legge gli aggiornamenti senza concorrenti. | Due lettori dello stesso bot si rubano gli aggiornamenti (409 Conflict). | Il piano reale si lancia a servizio fermo e legge `getUpdates` senza offset, così non conferma niente: v. `docs/messa-in-produzione.md`. |
| Il buio si prova spostando l'orologio finto di più di 23 ore. | Telegram tiene gli aggiornamenti per 24 ore e poi li perde; nessuna API dice chi ha votato cosa. | Non verificato contro il vero: servirebbe un giorno di buio. Lo dice la documentazione di `getUpdates`. |
| L'orologio è finto, e il fuso è `Europe/Zurich` di `tzdata`. | L'immagine `python:3.12-slim` non ha `/usr/share/zoneinfo`: senza il pacchetto `tzdata` il fuso non si trova. | `tests/reale/test_configurazione.py`, che gira nel container. |
| httpx non scrive log. | Al livello INFO httpx scrive l'URL di ogni richiesta, e l'URL di Telegram contiene il token. | `tests/test_principale.py` controlla che `configura_log` alzi il livello del logger `httpx`. |

## Da controllare a mano nel gruppo

- `/sondaggio@<bot>` scelto dal menu dei comandi arriva al bot con la privacy
  attiva, e il sondaggio compare nel gruppo.
- Una menzione («Non hanno ancora votato: …», «gio, abe: …») notifica la
  persona, anche chi non ha un nome utente.
```

- [ ] **Step 3: il tavolo delle prove e le prove delle date**

Crea `tests/tavolo.py`:

```python
"""Il tavolo delle prove: il giorno di oggi e, dal task 2, il roster della spec,
con identificativi Telegram finti."""

from __future__ import annotations

from datetime import date

# Martedì 7 ottobre 2025: la settimana seguente va da lunedì 13 a domenica 19, e
# il 14/10 è un martedì, come negli esempi della spec.
OGGI = date(2025, 10, 7)


def d(scritta: str, anno: int = 2025) -> date:
    """«14/10» → il 14 ottobre 2025."""
    giorno, mese = scritta.split("/")
    return date(anno, int(mese), int(giorno))
```

Crea `tests/test_date.py`:

```python
from datetime import date, timedelta

import pytest

from prossima import regole
from tests.tavolo import OGGI, d


def test_le_etichette_nel_formato_italiano():
    assert regole.breve(d("1/11")) == "1/11"
    assert regole.etichetta(d("14/10")) == "mar 14/10"
    assert regole.etichetta(d("5/1", 2026)) == "lun 5/1"
    assert regole.etichetta_intera(d("14/10")) == "martedì 14/10"


def test_ogni_giorno_ha_il_suo_nome():
    lunedi = d("13/10")
    settimana = [lunedi + timedelta(days=i) for i in range(7)]
    assert [regole.etichetta(g) for g in settimana] == [
        "lun 13/10", "mar 14/10", "mer 15/10", "gio 16/10", "ven 17/10", "sab 18/10", "dom 19/10",
    ]
    assert [regole.etichetta_intera(g) for g in settimana] == [
        "lunedì 13/10", "martedì 14/10", "mercoledì 15/10", "giovedì 16/10",
        "venerdì 17/10", "sabato 18/10", "domenica 19/10",
    ]


def test_senza_parole_i_sette_giorni_della_settimana_seguente():
    assert regole.date_del_comando([], OGGI) == [d("13/10") + timedelta(days=i) for i in range(7)]


@pytest.mark.parametrize(
    "oggi, lunedi",
    [
        (date(2025, 10, 13), date(2025, 10, 20)),  # di lunedì: non la settimana in corso
        (date(2025, 10, 12), date(2025, 10, 13)),  # di domenica: quella che comincia domani
        (date(2025, 12, 31), date(2026, 1, 5)),  # a cavallo dell'anno
        (date(2025, 12, 28), date(2025, 12, 29)),  # domenica 28/12: dal 29/12 al 4/1
    ],
)
def test_la_settimana_seguente(oggi, lunedi):
    date_ = regole.date_del_comando([], oggi)
    assert date_ == [lunedi + timedelta(days=i) for i in range(7)]


def test_i_giorni_della_settimana_seguente():
    assert regole.date_del_comando(["mar", "gio", "sab"], OGGI) == [d("14/10"), d("16/10"), d("18/10")]
    assert regole.date_del_comando(["Mar", "GIO"], OGGI) == [d("14/10"), d("16/10")]


@pytest.mark.parametrize("scritta", ["14/10", "14.10", "14/10/2025", "14.10.2025", "14/10.2025"])
def test_le_date_con_la_barra_o_con_il_punto(scritta):
    assert regole.date_del_comando([scritta], OGGI) == [d("14/10")]


def test_le_date_si_ordinano_e_i_doppioni_si_tolgono():
    assert regole.date_del_comando(["16/10", "14/10", "16.10"], OGGI) == [d("14/10"), d("16/10")]


def test_giorni_e_date_si_mescolano():
    assert regole.date_del_comando(["gio", "14/10", "16/10", "21/10"], OGGI) == [
        d("14/10"), d("16/10"), d("21/10"),
    ]


def test_senza_anno_la_prossima_volta_che_la_data_arriva_oggi_compreso():
    assert regole.date_del_comando(["7/10"], OGGI) == [d("7/10")]
    assert regole.date_del_comando(["5/1"], OGGI) == [d("5/1", 2026)]
    assert regole.date_del_comando(["1/4"], OGGI) == [d("1/4", 2026)]
    assert regole.date_del_comando(["2/1"], date(2025, 12, 28)) == [d("2/1", 2026)]


def test_una_data_passata_da_poco_e_passata_non_dell_anno_dopo():
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["3/10"], OGGI)
    assert rifiuto.value.scritta == "3/10"
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["28.12"], date(2026, 1, 5))
    assert rifiuto.value.scritta == "28/12"


def test_una_data_con_l_anno_passato():
    with pytest.raises(regole.DataPassata) as rifiuto:
        regole.date_del_comando(["14.10.2024"], OGGI)
    assert rifiuto.value.scritta == "14/10/2024"


def test_oggi_non_e_passata():
    assert regole.date_del_comando(["7/10/2025"], OGGI) == [OGGI]


@pytest.mark.parametrize(
    "parola", ["32/10", "31/11", "14-10", "domani", "14/10/25", "1/2/3/4", "lunedì", "29/2/2026"]
)
def test_una_parola_non_capita(parola):
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.date_del_comando([parola], OGGI)
    assert rifiuto.value.parola == parola


def test_la_prima_parola_sbagliata_ferma_tutto():
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.date_del_comando(["mar", "boh", "32/10"], OGGI)
    assert rifiuto.value.parola == "boh"


def test_al_massimo_10_date_contate_senza_doppioni():
    dieci = [f"{g}/10" for g in range(13, 23)]
    assert len(regole.date_del_comando(dieci, OGGI)) == 10
    assert len(regole.date_del_comando([*dieci, "13.10"], OGGI)) == 10
    with pytest.raises(regole.TroppeDate):
        regole.date_del_comando([*dieci, "23/10"], OGGI)


SONDAGGIO = [d("14/10"), d("16/10")]


@pytest.mark.parametrize("parola", ["14/10", "14.10", "14/10/2025", "mar", "MAR"])
def test_chiudere_tenendo_una_data_del_sondaggio(parola):
    assert regole.data_da_chiudere(parola, SONDAGGIO) == d("14/10")


@pytest.mark.parametrize(
    "parola, scritta", [("15/10", "15/10"), ("05.10", "5/10"), ("14/10/2026", "14/10/2026"), ("Ven", "ven")]
)
def test_chiudere_con_una_data_che_non_era_nel_sondaggio(parola, scritta):
    with pytest.raises(regole.NonNelSondaggio) as rifiuto:
        regole.data_da_chiudere(parola, SONDAGGIO)
    assert rifiuto.value.scritta == scritta


def test_chiudere_con_un_giorno_che_nel_sondaggio_compare_due_volte():
    with pytest.raises(regole.NonCapisco) as rifiuto:
        regole.data_da_chiudere("mar", [d("14/10"), d("21/10")])
    assert rifiuto.value.parola == "mar"


def test_chiudere_con_una_parola_strana():
    with pytest.raises(regole.NonCapisco):
        regole.data_da_chiudere("boh", SONDAGGIO)


def test_rimandare_tiene_i_giorni_della_settimana_nella_settimana_dopo():
    assert regole.date_rimandate([d("14/10"), d("16/10")]) == [d("21/10"), d("23/10")]
    settimana = regole.date_del_comando([], OGGI)
    assert regole.date_rimandate(settimana) == [d("20/10") + timedelta(days=i) for i in range(7)]
    # su due settimane: la settimana dopo quella dell'ultima data
    assert regole.date_rimandate([d("14/10"), d("23/10")]) == [d("28/10"), d("30/10")]
```

- [ ] **Step 4: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_date.py -q`
Expected: FAIL — errore di import: `regole` non esiste ancora.

- [ ] **Step 5: le date**

Crea `src/prossima/regole.py`:

```python
"""Le regole del sondaggio. Niente I/O: date, conteggi, annunci.

Tutto ciò che dipende dal giorno lo riceve come argomento (`oggi`, già nel fuso
del party): le prove non dipendono dall'orologio vero. I giorni della
settimana sono quelli di `date.weekday()`: lunedì 0, domenica 6. I testi per
le persone non stanno qui ma in `testi.py`: un rifiuto porta solo i dati che
servono a scriverlo.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, timedelta

GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
GIORNI_INTERI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MASSIMO_DATE = 10
RIMANDA = "rimanda"

# «14/10», «14/10/2025», e anche con il punto: «14.10», «14.10.2025».
_DATA = re.compile(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{4}))?")


class Rifiuto(ValueError):
    """Il comando non si esegue. Il testo per chi l'ha scritto lo dà `testi.rifiuto`."""


class NonCapisco(Rifiuto):
    def __init__(self, parola: str) -> None:
        super().__init__(parola)
        self.parola = parola  # come l'ha scritta la persona


class DataPassata(Rifiuto):
    def __init__(self, scritta: str) -> None:
        super().__init__(scritta)
        self.scritta = scritta  # «3/10», o «3/10/2024» se l'anno era scritto


class TroppeDate(Rifiuto):
    pass


class NonNelSondaggio(Rifiuto):
    def __init__(self, scritta: str) -> None:
        super().__init__(scritta)
        self.scritta = scritta  # «15/10», o il giorno della settimana: «ven»


def breve(giorno: date) -> str:
    """«14/10»: giorno e mese senza zeri iniziali, nel formato italiano."""
    return f"{giorno.day}/{giorno.month}"


def etichetta(giorno: date) -> str:
    """«mar 14/10»: l'opzione del sondaggio, e la data nei messaggi."""
    return f"{GIORNI[giorno.weekday()]} {breve(giorno)}"


def etichetta_intera(giorno: date) -> str:
    """«martedì 14/10»."""
    return f"{GIORNI_INTERI[giorno.weekday()]} {breve(giorno)}"


def lunedi_seguente(giorno: date) -> date:
    """Il lunedì della settimana di calendario dopo quella di `giorno`: di
    domenica è domani."""
    return giorno + timedelta(days=7 - giorno.weekday())


def _scritta(giorno: date, con_anno: bool) -> str:
    return f"{breve(giorno)}/{giorno.year}" if con_anno else breve(giorno)


def _data_senza_anno(giorno: int, mese: int, oggi: date) -> date | None:
    """La data `g/m` più vicina a oggi fra l'anno scorso, quest'anno e il
    prossimo; a pari distanza vince quella che viene.

    In pratica è «la prossima volta che la data arriva, oggi compreso» (il 28/12,
    «2/1» è il 2 gennaio dopo), salvo per una data passata da meno di sei mesi:
    quella resta nel passato, e il comando la rifiuta come passata (il 7/10,
    «3/10» è il 3 ottobre di quattro giorni prima, non quello dell'anno dopo).
    """
    candidate = []
    for anno in (oggi.year - 1, oggi.year, oggi.year + 1):
        try:
            candidate.append(date(anno, mese, giorno))
        except ValueError:
            continue
    if not candidate:
        return None
    return min(candidate, key=lambda d: (abs((d - oggi).days), d < oggi))


def _data_della_parola(parola: str, oggi: date) -> date:
    minuscola = parola.lower()
    if minuscola in GIORNI:
        return lunedi_seguente(oggi) + timedelta(days=GIORNI.index(minuscola))
    trovata = _DATA.fullmatch(parola)
    if trovata is None:
        raise NonCapisco(parola)
    g, m, a = trovata.groups()
    if a is None:
        giorno = _data_senza_anno(int(g), int(m), oggi)
    else:
        try:
            giorno = date(int(a), int(m), int(g))
        except ValueError:
            giorno = None
    if giorno is None:
        raise NonCapisco(parola)
    if giorno < oggi:
        raise DataPassata(_scritta(giorno, a is not None))
    return giorno


def date_del_comando(parole: Sequence[str], oggi: date) -> list[date]:
    """Le date di `/sondaggio`. Senza parole, i sette giorni della settimana
    seguente; con giorni (`lun` … `dom`) quei giorni della settimana seguente;
    con date, quelle date. Giorni e date si mescolano; il risultato è ordinato,
    senza doppioni. La prima parola che non va ferma tutto."""
    if not parole:
        lunedi = lunedi_seguente(oggi)
        return [lunedi + timedelta(days=i) for i in range(7)]
    scelte = {_data_della_parola(parola, oggi) for parola in parole}
    if len(scelte) > MASSIMO_DATE:
        raise TroppeDate()
    return sorted(scelte)


def data_da_chiudere(parola: str, date_sondaggio: Sequence[date]) -> date:
    """La data che `/chiudi <parola>` tiene: una data del sondaggio (`g/m`,
    `g/m/aaaa`, o con il punto), o il suo giorno della settimana, se nel
    sondaggio ce n'è uno solo."""
    minuscola = parola.lower()
    if minuscola in GIORNI:
        trovate = [d for d in date_sondaggio if GIORNI[d.weekday()] == minuscola]
        if not trovate:
            raise NonNelSondaggio(minuscola)
        if len(trovate) > 1:
            raise NonCapisco(parola)
        return trovate[0]
    trovata = _DATA.fullmatch(parola)
    if trovata is None:
        raise NonCapisco(parola)
    g, m = int(trovata[1]), int(trovata[2])
    a = None if trovata[3] is None else int(trovata[3])
    for giorno in date_sondaggio:
        if (giorno.day, giorno.month) == (g, m) and a in (None, giorno.year):
            return giorno
    raise NonNelSondaggio(f"{g}/{m}" if a is None else f"{g}/{m}/{a}")


def date_rimandate(date_sondaggio: Sequence[date]) -> list[date]:
    """Le date di `/chiudi rimanda`: gli stessi giorni della settimana, nella
    settimana dopo quella dell'ultima data."""
    lunedi = lunedi_seguente(max(date_sondaggio))
    giorni = sorted({d.weekday() for d in date_sondaggio})
    return [lunedi + timedelta(days=g) for g in giorni]

```

- [ ] **Step 6: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_date.py -q`
Expected: PASS — `41 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `41 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 7: commit**

```bash
git add .python-version pyproject.toml uv.lock src tests docs/differenze-fra-test-e-realta.md
git commit -m "scaffold: project, test/reality differences, poll dates

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 2: chi conta, le regole delle date, gli annunci

La seconda metà di `regole.py`, sempre pura: il roster, i voti, i conteggi, la classificazione (possibile, quasi, fuori), «impossibile», gli annunci da fare e i fatti che li ricordano. `annunci_da_fare` non manda niente: dice cosa manca, e `dopo` dice come cambiano i fatti quando Telegram ha accettato un annuncio. Così rifare il calcolo non ripete niente (spec §3.5).

**Files:**
- Modify: `src/prossima/regole.py` (gli import in cima; tutto il resto si accoda)
- Modify: `tests/tavolo.py` (sostituito per intero: aggiunge il roster)
- Test: `tests/test_regole.py`

**Interfaces:**
- Consumes: `prossima.regole` del task 1; `tests.tavolo.OGGI`, `d`.
- Produces (`prossima.regole`): `GIOCATORI_PER_GIOCARE = 4`, `GIOCATORI_PER_QUASI = 3`, `VOTANTI_PER_QUASI = 4`, `BUIO = timedelta(hours=23)`, `MASTER = "master"`, `GIOCATORE = "giocatore"`, `RUOLI`.
  - `@dataclass(frozen=True) Persona(soprannome: str, telegram_id: int, ruolo: str, chiude: bool = False)`.
  - `@dataclass(frozen=True) Roster(persone: tuple[Persona, ...])` con `.master -> Persona`, `.giocatori -> tuple[Persona, ...]`, `.chi_chiude -> tuple[Persona, ...]`, `.per_id(telegram_id: int | None) -> Persona | None`.
  - `@dataclass(frozen=True) Voto(date: frozenset[date] = frozenset(), nessuna: bool = False)` con `.dato -> bool` (ha votato).
  - `voto_da_opzioni(date_sondaggio: Sequence[date], opzioni: Iterable[int]) -> Voto`; `conteggi_per_opzione(date_sondaggio: Sequence[date], voti: Iterable[Voto]) -> list[int]` (la forma dei conteggi di `stopPoll`, «Nessuna» in fondo).
  - `@dataclass(frozen=True) Stato(roster: Roster, date: tuple[date, ...], voti: Mapping[int, Voto])` con `.voto(persona) -> Voto`, `.votanti`, `.senza_voto` (tuple di `Persona` nell'ordine del roster), `.presenti(giorno) -> tuple[Persona, ...]`.
  - `@dataclass(frozen=True) Conteggio(giorno, presenti, master_presente, master_ha_votato, giocatori_presenti, giocatori_senza_voto, votanti)` con `.possibile`, `.quasi`, `.fuori`, `.con_tre`; `conta(stato: Stato, giorno: date) -> Conteggio`; `possibili(stato) -> list[date]`; `impossibile(stato) -> bool`.
  - Gli annunci: `Quasi(giorno: date, presenti: tuple[Persona, ...], senza_voto: tuple[Persona, ...])`, `Possibile(giorno, presenti)`, `NonPiu(giorno, andati_via: tuple[Persona, ...])` (vuoto: non si sa chi), `Impossibile(con_tre: tuple[tuple[date, tuple[Persona, ...]], ...])`; `Annuncio = Quasi | Possibile | NonPiu | Impossibile`. Gli eventi muti: `Rientro()`, `Ripresa()`; `Evento = Annuncio | Rientro | Ripresa`.
  - `@dataclass(frozen=True) Fatti(quasi: frozenset[date] = frozenset(), possibili: Mapping[date, frozenset[int] | None] = {}, impossibile: bool = False)`; `dopo(fatti: Fatti, evento: Evento) -> Fatti`; `annunci_da_fare(stato: Stato, fatti: Fatti) -> list[Annuncio]`; `rientrato(stato, fatti) -> bool`; `al_buio(precedente: datetime | None, adesso: datetime) -> bool`.
- Produces (`tests.tavolo`): `GIO` (master, chiude), `ABE` (giocatore, chiude), `EMI`, `SEM`, `SESE`, `PIPPO` (identificativi `100000001`…`100000006`), `ROSTER`, `ESTRANEO = 100000099` (vota ma non è nel roster), `voto(scritto: str) -> Voto` («14/10 16/10», «nessuna», «» per il voto tolto), `stato(date_sondaggio: str = "14/10 16/10", estraneo: str | None = None, **voti: str) -> Stato`.

- [ ] **Step 1: il roster delle prove e le prove delle regole**

Sostituisci l'intero `tests/tavolo.py` con:

```python
"""Il tavolo delle prove: il giorno di oggi e il roster della spec, con
identificativi Telegram finti."""

from __future__ import annotations

from datetime import date

from prossima.regole import Persona, Roster, Stato, Voto

# Martedì 7 ottobre 2025: la settimana seguente va da lunedì 13 a domenica 19, e
# il 14/10 è un martedì, come negli esempi della spec.
OGGI = date(2025, 10, 7)


def d(scritta: str, anno: int = 2025) -> date:
    """«14/10» → il 14 ottobre 2025."""
    giorno, mese = scritta.split("/")
    return date(anno, int(mese), int(giorno))


GIO = Persona("gio", 100000001, "master", chiude=True)
ABE = Persona("abe", 100000002, "giocatore", chiude=True)
EMI = Persona("emi", 100000003, "giocatore")
SEM = Persona("sem", 100000004, "giocatore")
SESE = Persona("sese", 100000005, "giocatore")
PIPPO = Persona("pippo", 100000006, "giocatore")
ROSTER = Roster((GIO, ABE, EMI, SEM, SESE, PIPPO))
ESTRANEO = 100000099  # vota, ma non è nel roster


def voto(scritto: str) -> Voto:
    """«14/10 16/10»: le date spuntate; «nessuna» aggiunge «Nessuna di queste»;
    «» è il voto tolto."""
    parole = scritto.split()
    return Voto(
        date=frozenset(d(p) for p in parole if p != "nessuna"), nessuna="nessuna" in parole
    )


def stato(date_sondaggio: str = "14/10 16/10", estraneo: str | None = None, **voti: str) -> Stato:
    """Lo stato di un sondaggio sulle `date_sondaggio`, con i voti per soprannome."""
    per_id = {p.telegram_id: voto(voti[p.soprannome]) for p in ROSTER.persone if p.soprannome in voti}
    if estraneo is not None:
        per_id[ESTRANEO] = voto(estraneo)
    return Stato(ROSTER, tuple(d(g) for g in date_sondaggio.split()), per_id)
```

Crea `tests/test_regole.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from prossima import regole
from prossima.regole import Fatti, Impossibile, NonPiu, Possibile, Quasi, Voto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, PIPPO, ROSTER, SEM, SESE, d, stato


def ids(*persone):
    return frozenset(p.telegram_id for p in persone)


# --- chi conta


def test_il_roster():
    assert ROSTER.master == GIO
    assert ROSTER.giocatori == (ABE, EMI, SEM, SESE, PIPPO)
    assert ROSTER.chi_chiude == (GIO, ABE)
    assert ROSTER.per_id(SEM.telegram_id) == SEM
    assert ROSTER.per_id(ESTRANEO) is None
    assert ROSTER.per_id(None) is None


def test_ha_votato_chi_ha_una_risposta_non_vuota_anche_solo_nessuna():
    s = stato(gio="14/10", abe="nessuna", emi="")
    assert s.votanti == (GIO, ABE)
    assert s.senza_voto == (EMI, SEM, SESE, PIPPO)


def test_presenti_nell_ordine_del_roster_e_nessuna_non_toglie_le_date():
    s = stato(sem="14/10", gio="14/10 nessuna", abe="16/10")
    assert s.presenti(d("14/10")) == (GIO, SEM)


def test_chi_non_e_nel_roster_non_conta():
    s = stato(estraneo="14/10", gio="14/10")
    assert s.presenti(d("14/10")) == (GIO,)
    assert s.votanti == (GIO,)


def test_le_opzioni_di_telegram_come_voto():
    date_ = [d("14/10"), d("16/10")]
    assert regole.voto_da_opzioni(date_, [0]) == Voto(frozenset({d("14/10")}))
    assert regole.voto_da_opzioni(date_, [1, 2]) == Voto(frozenset({d("16/10")}), nessuna=True)
    assert regole.voto_da_opzioni(date_, [2]) == Voto(nessuna=True)
    assert regole.voto_da_opzioni(date_, [7]) == Voto()
    assert not regole.voto_da_opzioni(date_, []).dato


def test_i_conteggi_per_opzione_come_quelli_di_stop_poll():
    date_ = [d("14/10"), d("16/10")]
    voti = [Voto(frozenset(date_)), Voto(frozenset({d("16/10")}), nessuna=True), Voto()]
    assert regole.conteggi_per_opzione(date_, voti) == [1, 2, 1]
    assert regole.conteggi_per_opzione(date_, []) == [0, 0, 0]


# --- possibile, quasi, fuori: il 14/10 in ogni riga


@pytest.mark.parametrize(
    "voti, possibile, quasi, fuori",
    [
        # il master e quattro giocatori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), True, False, False),
        # quattro giocatori, il master non ha ancora votato
        (dict(abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, False),
        # il master e tre giocatori, pippo non ha votato: quasi, non fuori (3 + 1)
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="16/10"), False, True, False),
        # il master e tre giocatori, hanno votato tutti: quasi, e fuori (3 + 0)
        (
            dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="16/10", pippo="nessuna"),
            False, True, True,
        ),
        # il master ha votato un'altra data
        (dict(gio="16/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, True),
        # il master ha votato solo «Nessuna»
        (dict(gio="nessuna", abe="14/10", emi="14/10", sem="14/10", sese="14/10"), False, False, True),
        # due giocatori presenti e due senza voto: 2 + 2 non è fuori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="16/10"), False, False, False),
        # due giocatori presenti e uno senza voto: 2 + 1 è fuori
        (dict(gio="14/10", abe="14/10", emi="14/10", sem="16/10", sese="16/10"), False, False, True),
        # nessun voto
        ({}, False, False, False),
    ],
)
def test_possibile_quasi_fuori(voti, possibile, quasi, fuori):
    c = regole.conta(stato(**voti), d("14/10"))
    assert (c.possibile, c.quasi, c.fuori) == (possibile, quasi, fuori)


def test_il_conteggio_di_una_data():
    s = stato(gio="14/10", abe="14/10", emi="14/10", sem="16/10", estraneo="14/10")
    assert regole.conta(s, d("14/10")) == regole.Conteggio(
        giorno=d("14/10"),
        presenti=(GIO, ABE, EMI),
        master_presente=True,
        master_ha_votato=True,
        giocatori_presenti=2,
        giocatori_senza_voto=2,
        votanti=4,
    )


def test_le_date_possibili():
    s = stato(gio="14/10 16/10", abe="14/10 16/10", emi="14/10", sem="14/10", sese="14/10 16/10")
    assert regole.possibili(s) == [d("14/10")]


def test_impossibile():
    assert not regole.impossibile(stato())
    # il master ha votato senza scegliere una data: tutte fuori
    assert regole.impossibile(stato(gio="nessuna"))
    # in nessuna data i giocatori presenti più quelli senza voto arrivano a quattro
    assert regole.impossibile(
        stato(gio="14/10 16/10", abe="14/10", emi="16/10", sem="nessuna", sese="nessuna")
    )
    # una data ancora in gioco basta: il 14/10 ha il master e cinque giocatori senza voto
    assert not regole.impossibile(stato(gio="14/10"))


# --- gli annunci

QUASI_14 = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10")
POSSIBILE_14 = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="14/10")


def test_quasi_una_volta_con_chi_non_ha_ancora_votato():
    s = stato(**QUASI_14)
    annunci = regole.annunci_da_fare(s, Fatti())
    assert annunci == [Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO))]
    assert regole.annunci_da_fare(s, regole.dopo(Fatti(), annunci[0])) == []


def test_possibile_una_volta():
    s = stato(**POSSIBILE_14)
    annunci = regole.annunci_da_fare(s, Fatti())
    assert annunci == [Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE))]
    assert regole.annunci_da_fare(s, regole.dopo(Fatti(), annunci[0])) == []


def annunci_in_sequenza(*voti_uno_dopo_l_altro):
    """Gli annunci di un sondaggio i cui voti passano per questi stati, ognuno
    registrato come fatto prima del successivo."""
    fatti, annunciati = Fatti(), []
    for voti in voti_uno_dopo_l_altro:
        for annuncio in regole.annunci_da_fare(stato(**voti), fatti):
            annunciati.append(annuncio)
            fatti = regole.dopo(fatti, annuncio)
    return annunciati


def test_il_quasi_non_si_ripete_neanche_dopo_un_possibile():
    assert annunci_in_sequenza(QUASI_14, POSSIBILE_14, QUASI_14) == [
        Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO)),
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
        NonPiu(d("14/10"), (SESE,)),
    ]


def test_non_piu_possibile_con_chi_ha_tolto_il_voto():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    s = stato(**{**POSSIBILE_14, "sem": "", "sese": "nessuna"})
    assert regole.annunci_da_fare(s, fatti) == [NonPiu(d("14/10"), (SEM, SESE))]


def test_non_piu_possibile_e_poi_quasi_se_manca_uno_solo():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    s = stato(**{**POSSIBILE_14, "sem": "16/10"})
    assert regole.annunci_da_fare(s, fatti) == [
        NonPiu(d("14/10"), (SEM,)),
        Quasi(d("14/10"), (GIO, ABE, EMI, SESE), (PIPPO,)),
    ]


def test_non_piu_possibile_dopo_una_ripresa_non_sa_chi():
    fatti = regole.dopo(Fatti(), Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    fatti = regole.dopo(fatti, regole.Ripresa())
    assert fatti.possibili == {d("14/10"): None}
    s = stato(**{**POSSIBILE_14, "sem": "", "sese": ""})
    assert regole.annunci_da_fare(s, fatti) == [NonPiu(d("14/10"), ())]


def test_possibile_di_nuovo_dopo_un_non_piu():
    assert annunci_in_sequenza(POSSIBILE_14, {**POSSIBILE_14, "sem": ""}, POSSIBILE_14) == [
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
        NonPiu(d("14/10"), (SEM,)),
        Quasi(d("14/10"), (GIO, ABE, EMI, SESE), (SEM, PIPPO)),
        Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)),
    ]


# hanno votato tutti; il 14/10 ha il master e tre giocatori, il 16/10 non ha il master
CON_TRE = dict(gio="14/10", abe="14/10", emi="14/10", sem="14/10 16/10", sese="16/10", pippo="16/10")


def test_impossibile_con_le_date_in_cui_si_gioca_in_tre():
    annunci = regole.annunci_da_fare(stato(**CON_TRE), Fatti())
    assert annunci == [
        Quasi(d("14/10"), (GIO, ABE, EMI, SEM), ()),
        Impossibile(((d("14/10"), (GIO, ABE, EMI, SEM)),)),
    ]


def test_impossibile_senza_date_in_tre_compreso_il_master_che_vota_solo_nessuna():
    assert regole.annunci_da_fare(stato(gio="nessuna"), Fatti()) == [Impossibile(())]


def test_impossibile_di_nuovo_solo_dopo_un_rientro():
    s = stato(gio="nessuna")
    fatti = regole.dopo(Fatti(), Impossibile(()))
    assert regole.annunci_da_fare(s, fatti) == []
    assert not regole.rientrato(s, fatti)
    # il master toglie il voto: le date tornano in gioco
    tornato = stato(gio="")
    assert regole.rientrato(tornato, fatti)
    fatti = regole.dopo(fatti, regole.Rientro())
    assert not fatti.impossibile
    assert regole.annunci_da_fare(s, fatti) == [Impossibile(())]


def test_dopo_registra_ogni_evento():
    f = regole.dopo(Fatti(), Quasi(d("14/10"), (), ()))
    f = regole.dopo(f, Possibile(d("16/10"), (GIO, ABE)))
    assert f == Fatti(quasi=frozenset({d("14/10")}), possibili={d("16/10"): ids(GIO, ABE)})
    f = regole.dopo(f, NonPiu(d("16/10"), (ABE,)))
    assert f.possibili == {}
    assert regole.dopo(f, Impossibile(())).impossibile


def test_il_buio_comincia_dopo_23_ore():
    prima = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    assert not regole.al_buio(None, prima)
    assert not regole.al_buio(prima, prima + timedelta(hours=23))
    assert regole.al_buio(prima, prima + timedelta(hours=23, seconds=1))
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_regole.py -q`
Expected: FAIL — `ImportError: cannot import name 'Persona' from 'prossima.regole'`.

- [ ] **Step 3: le regole**

In `src/prossima/regole.py`, sostituisci:

```python
import re
from collections.abc import Sequence
from datetime import date, timedelta
```

con:

```python
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
```

In fondo a `src/prossima/regole.py`, aggiungi:

```python

# --- chi conta, e le regole delle date (§3.3 e §3.4 della spec)

GIOCATORI_PER_GIOCARE = 4
GIOCATORI_PER_QUASI = 3
VOTANTI_PER_QUASI = 4
# Telegram conserva gli aggiornamenti per 24 ore: un'ora di margine.
BUIO = timedelta(hours=23)

MASTER = "master"
GIOCATORE = "giocatore"
RUOLI = (MASTER, GIOCATORE)


@dataclass(frozen=True)
class Persona:
    soprannome: str
    telegram_id: int
    ruolo: str
    chiude: bool = False


@dataclass(frozen=True)
class Roster:
    """Le persone che contano, nell'ordine del file. `config.py` garantisce un
    solo master e soprannomi e identificativi unici."""

    persone: tuple[Persona, ...]

    @property
    def master(self) -> Persona:
        return next(p for p in self.persone if p.ruolo == MASTER)

    @property
    def giocatori(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.persone if p.ruolo == GIOCATORE)

    @property
    def chi_chiude(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.persone if p.chiude)

    def per_id(self, telegram_id: int | None) -> Persona | None:
        return next((p for p in self.persone if p.telegram_id == telegram_id), None)


@dataclass(frozen=True)
class Voto:
    """Le scelte di una persona: le date spuntate e «Nessuna di queste»."""

    date: frozenset[date] = frozenset()
    nessuna: bool = False

    @property
    def dato(self) -> bool:
        """Ha votato: una risposta non vuota, anche solo «Nessuna»."""
        return bool(self.date) or self.nessuna


def voto_da_opzioni(date_sondaggio: Sequence[date], opzioni: Iterable[int]) -> Voto:
    """Le opzioni di un `poll_answer` (indici da 0) come voto: prima le date,
    in fondo «Nessuna». Un indice fuori dal sondaggio non conta."""
    scelte = set(opzioni)
    return Voto(
        date=frozenset(g for i, g in enumerate(date_sondaggio) if i in scelte),
        nessuna=len(date_sondaggio) in scelte,
    )


def conteggi_per_opzione(date_sondaggio: Sequence[date], voti: Iterable[Voto]) -> list[int]:
    """Quanti hanno spuntato ogni opzione, nell'ordine del sondaggio e con
    «Nessuna» in fondo: la forma dei conteggi che restituisce `stopPoll`."""
    voti = list(voti)
    return [sum(g in v.date for v in voti) for g in date_sondaggio] + [
        sum(v.nessuna for v in voti)
    ]


@dataclass(frozen=True)
class Stato:
    """Un sondaggio come lo vedono le regole: le sue date e i voti registrati,
    per identificativo Telegram, anche di chi non è nel roster."""

    roster: Roster
    date: tuple[date, ...]
    voti: Mapping[int, Voto]

    def voto(self, persona: Persona) -> Voto:
        return self.voti.get(persona.telegram_id, Voto())

    @property
    def votanti(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if self.voto(p).dato)

    @property
    def senza_voto(self) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if not self.voto(p).dato)

    def presenti(self, giorno: date) -> tuple[Persona, ...]:
        return tuple(p for p in self.roster.persone if giorno in self.voto(p).date)


@dataclass(frozen=True)
class Conteggio:
    giorno: date
    presenti: tuple[Persona, ...]  # nell'ordine del roster
    master_presente: bool
    master_ha_votato: bool
    giocatori_presenti: int
    giocatori_senza_voto: int
    votanti: int  # persone del roster che hanno votato

    @property
    def possibile(self) -> bool:
        return self.master_presente and self.giocatori_presenti >= GIOCATORI_PER_GIOCARE

    @property
    def quasi(self) -> bool:
        return (
            self.votanti >= VOTANTI_PER_QUASI
            and self.master_presente
            and self.giocatori_presenti == GIOCATORI_PER_QUASI
        )

    @property
    def fuori(self) -> bool:
        return (self.master_ha_votato and not self.master_presente) or (
            self.giocatori_presenti + self.giocatori_senza_voto < GIOCATORI_PER_GIOCARE
        )

    @property
    def con_tre(self) -> bool:
        """Il master e almeno tre giocatori: la data che si terrebbe giocando in tre."""
        return self.master_presente and self.giocatori_presenti >= GIOCATORI_PER_QUASI


def conta(stato: Stato, giorno: date) -> Conteggio:
    presenti = stato.presenti(giorno)
    master = stato.roster.master
    giocatori = stato.roster.giocatori
    return Conteggio(
        giorno=giorno,
        presenti=presenti,
        master_presente=master in presenti,
        master_ha_votato=stato.voto(master).dato,
        giocatori_presenti=sum(p in presenti for p in giocatori),
        giocatori_senza_voto=sum(not stato.voto(p).dato for p in giocatori),
        votanti=len(stato.votanti),
    )


def possibili(stato: Stato) -> list[date]:
    return [g for g in stato.date if conta(stato, g).possibile]


def impossibile(stato: Stato) -> bool:
    """Nessuna data possibile: tutte le date sono fuori."""
    return bool(stato.date) and all(conta(stato, g).fuori for g in stato.date)


# --- gli annunci (§3.5)


@dataclass(frozen=True)
class Quasi:
    giorno: date
    presenti: tuple[Persona, ...]
    senza_voto: tuple[Persona, ...]


@dataclass(frozen=True)
class Possibile:
    giorno: date
    presenti: tuple[Persona, ...]


@dataclass(frozen=True)
class NonPiu:
    giorno: date
    andati_via: tuple[Persona, ...]  # vuoto: il bot non sa chi


@dataclass(frozen=True)
class Impossibile:
    con_tre: tuple[tuple[date, tuple[Persona, ...]], ...]  # le date con il master e tre giocatori


Annuncio = Quasi | Possibile | NonPiu | Impossibile


@dataclass(frozen=True)
class Rientro:
    """Dopo «impossibile» una data è tornata in gioco. Non si annuncia, ma si
    registra: il prossimo «impossibile» si potrà dire di nuovo."""


@dataclass(frozen=True)
class Ripresa:
    """Dopo il buio (§3.8) il bot non sa più chi c'era quando ha annunciato
    «possibile»: un «non più possibile» dirà che non ci sono più il master e
    quattro giocatori, senza nomi."""


Evento = Annuncio | Rientro | Ripresa


@dataclass(frozen=True)
class Fatti:
    """Gli annunci già fatti per un sondaggio, come contano per i prossimi."""

    quasi: frozenset[date] = frozenset()
    # Le date annunciate come possibili e non ancora come «non più»: chi c'era
    # al momento dell'annuncio, o None se il bot non lo sa più.
    possibili: Mapping[date, frozenset[int] | None] = field(default_factory=dict)
    impossibile: bool = False


def dopo(fatti: Fatti, evento: Evento) -> Fatti:
    """I fatti dopo un annuncio accettato da Telegram, o dopo un evento muto."""
    match evento:
        case Quasi():
            return replace(fatti, quasi=fatti.quasi | {evento.giorno})
        case Possibile():
            presenti = frozenset(p.telegram_id for p in evento.presenti)
            return replace(fatti, possibili={**fatti.possibili, evento.giorno: presenti})
        case NonPiu():
            restano = {g: p for g, p in fatti.possibili.items() if g != evento.giorno}
            return replace(fatti, possibili=restano)
        case Impossibile():
            return replace(fatti, impossibile=True)
        case Rientro():
            return replace(fatti, impossibile=False)
        case Ripresa():
            return replace(fatti, possibili=dict.fromkeys(fatti.possibili))
    raise TypeError(f"evento sconosciuto: {evento!r}")


def annunci_da_fare(stato: Stato, fatti: Fatti) -> list[Annuncio]:
    """Gli annunci che lo stato chiede e che non sono ancora stati fatti, data
    per data e con «impossibile» in fondo. Pura: rifarla non ripete niente."""
    annunci: list[Annuncio] = []
    for giorno in stato.date:
        c = conta(stato, giorno)
        if giorno in fatti.possibili and not c.possibile:
            annunci.append(NonPiu(giorno, _andati_via(stato, fatti.possibili[giorno], c)))
        if c.possibile and giorno not in fatti.possibili:
            annunci.append(Possibile(giorno, c.presenti))
        if c.quasi and giorno not in fatti.quasi:
            annunci.append(Quasi(giorno, c.presenti, stato.senza_voto))
    if impossibile(stato) and not fatti.impossibile:
        conteggi = [conta(stato, g) for g in stato.date]
        annunci.append(Impossibile(tuple((c.giorno, c.presenti) for c in conteggi if c.con_tre)))
    return annunci


def _andati_via(
    stato: Stato, prima: frozenset[int] | None, adesso: Conteggio
) -> tuple[Persona, ...]:
    if prima is None:
        return ()
    restano = {p.telegram_id for p in adesso.presenti}
    return tuple(
        p for p in stato.roster.persone if p.telegram_id in prima and p.telegram_id not in restano
    )


def rientrato(stato: Stato, fatti: Fatti) -> bool:
    """«Impossibile» è stato annunciato, e adesso una data è tornata in gioco."""
    return fatti.impossibile and not impossibile(stato)


def al_buio(precedente: datetime | None, adesso: datetime) -> bool:
    """La lettura di adesso arriva più di 23 ore dopo la precedente riuscita."""
    return precedente is not None and adesso - precedente > BUIO
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_regole.py -q`
Expected: PASS — `30 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `71 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/regole.py tests/tavolo.py tests/test_regole.py
git commit -m "rules: roster, votes, possible/almost/out, announcements

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 3: i testi, con le menzioni in UTF-16, e le frasi di «Nessuna»

Tutti i testi per le persone, copiati alla lettera dalla spec, e un solo modo di costruire le menzioni: `_Scrittura` conta la lunghezza in unità UTF-16 man mano che il testo cresce, così l'entità cade sul nome anche dopo un'emoji. La prova che lo dimostra ritaglia il testo come lo ritaglia Telegram.

**Files:**
- Create: `src/prossima/testi.py`
- Test: `tests/test_testi.py`

**Interfaces:**
- Consumes: `prossima.regole` (`etichetta`, `etichetta_intera`, `breve`, `MASSIMO_DATE`, `Persona`, `Roster`, gli annunci `Quasi`/`Possibile`/`NonPiu`/`Impossibile`, i rifiuti `NonCapisco`/`DataPassata`/`TroppeDate`/`NonNelSondaggio`); `tests.tavolo`.
- Produces (`prossima.testi`): `DOMANDA = "Prossima volta?"`, `LUNGHEZZA_OPZIONE = 100`, `FRASI_NESSUNA` (le 15 frasi della spec, in ordine); `@dataclass(frozen=True) Testo(testo: str, entita: tuple[dict, ...] = ())`, dove ogni entità è `{"type": "text_mention", "offset": int, "length": int, "user": {"id": int}}`; `utf16(testo: str) -> int`; `elenco(nomi: Sequence[str], congiunzione: str = "e") -> str`; `opzioni(date_sondaggio: Sequence[date], frase: str) -> list[str]`; `scegli_frase(usate: Collection[str], caso: Callable[[Sequence[str]], str]) -> str`; e, tutte `-> Testo`: `quasi(a)`, `possibile(a)`, `non_piu(a)`, `impossibile(a, chiude: Sequence[Persona], nome_bot: str)`, `annuncio(a: Annuncio, roster: Roster, nome_bot: str)`, `rifiuto(r: Rifiuto)`, `gia_aperto(nome_bot)`, `solo_chi_chiude(chiude)`, `nessun_sondaggio()`, `chiuso(possibili: Sequence[date])`, `si_gioca(giorno)`, `rimandiamo(lunedi)`, `sparito()`, `buio(dal: datetime, al: datetime, fuso: tzinfo)`, `conteggi(uguali: bool)`, `riapro(votanti, senza_voto)`, `date_passate()`.

- [ ] **Step 1: le prove dei testi**

Nelle prove `Testo` si scrive sempre `testi.Testo`: importato da solo, pytest proverebbe a raccoglierlo come classe di prove (comincia per «Test»).

Crea `tests/test_testi.py`:

```python
import random
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from prossima import regole, testi
from tests.tavolo import ABE, EMI, GIO, PIPPO, ROSTER, SEM, SESE, d

NOME = "ProssimaVoltaBot"
ZURIGO = ZoneInfo("Europe/Zurich")


def menzionati(t: testi.Testo) -> list[tuple[str, int]]:
    """Il pezzo di testo su cui cade ogni menzione, ritagliato come lo ritaglia
    Telegram (in unità UTF-16), e l'identificativo della persona."""
    unita = t.testo.encode("utf-16-le")
    return [
        (
            unita[2 * e["offset"] : 2 * (e["offset"] + e["length"])].decode("utf-16-le"),
            e["user"]["id"],
        )
        for e in t.entita
    ]


def test_utf16_conta_come_telegram():
    assert testi.utf16("abe") == 3
    assert testi.utf16("📅") == 2
    assert testi.utf16("⚠️") == 2
    assert testi.utf16("è") == 1


def test_le_opzioni_del_sondaggio():
    frase = testi.FRASI_NESSUNA[0]
    assert testi.opzioni([d("14/10"), d("16/10")], frase) == ["mar 14/10", "gio 16/10", frase]
    assert testi.DOMANDA == "Prossima volta?"


def test_quasi_con_le_menzioni_dopo_un_emoji():
    t = testi.quasi(regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (SESE, PIPPO)))
    assert t.testo == (
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(t) == [("sese", SESE.telegram_id), ("pippo", PIPPO.telegram_id)]
    assert all(e["type"] == "text_mention" for e in t.entita)
    # 📅 vale due unità: contando i caratteri la menzione cadrebbe una lettera prima
    assert t.entita[0]["offset"] == t.testo.index("sese") + 1


def test_quasi_quando_hanno_votato_tutti():
    t = testi.quasi(regole.Quasi(d("14/10"), (GIO, ABE, EMI, SEM), ()))
    assert t == testi.Testo("📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore.")


def test_possibile():
    t = testi.possibile(regole.Possibile(d("14/10"), (GIO, ABE, EMI, SEM, SESE)))
    assert t == testi.Testo("✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese.")


def test_non_piu_possibile():
    assert testi.non_piu(regole.NonPiu(d("14/10"), (SEM,))) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: sem ha tolto il voto."
    )
    assert testi.non_piu(regole.NonPiu(d("14/10"), (SEM, SESE))) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: sem e sese hanno tolto il voto."
    )
    assert testi.non_piu(regole.NonPiu(d("14/10"), ())) == testi.Testo(
        "⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro giocatori."
    )


def test_impossibile_con_una_data_in_tre():
    a = regole.Impossibile(((d("14/10"), (GIO, ABE, EMI, SEM)),))
    t = testi.impossibile(a, (GIO, ABE), NOME)
    assert t.testo == (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date. "
        "Con tre: mar 14/10 (gio, abe, emi, sem). "
        "gio, abe: /chiudi@ProssimaVoltaBot 14/10 per tenerla, "
        "/chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_impossibile_con_piu_date_in_tre():
    a = regole.Impossibile(
        ((d("14/10"), (GIO, ABE, EMI, SEM)), (d("16/10"), (GIO, ABE, SEM, SESE)))
    )
    t = testi.impossibile(a, (GIO, ABE), NOME)
    assert "Con tre: mar 14/10 (gio, abe, emi, sem); gio 16/10 (gio, abe, sem, sese). " in t.testo
    assert "/chiudi@ProssimaVoltaBot 14/10 per tenerla" in t.testo
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_impossibile_senza_date_in_tre():
    t = testi.impossibile(regole.Impossibile(()), (GIO, ABE), NOME)
    assert t.testo == (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date, e nemmeno con tre. "
        "gio, abe: /chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


def test_annuncio_sceglie_il_testo_e_menziona_chi_chiude_dal_roster():
    assert testi.annuncio(regole.NonPiu(d("14/10"), (SEM,)), ROSTER, NOME) == testi.non_piu(
        regole.NonPiu(d("14/10"), (SEM,))
    )
    t = testi.annuncio(regole.Impossibile(()), ROSTER, NOME)
    assert menzionati(t) == [("gio", GIO.telegram_id), ("abe", ABE.telegram_id)]


@pytest.mark.parametrize(
    "rifiuto, testo",
    [
        (
            regole.NonCapisco("32/10"),
            "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
        ),
        (regole.DataPassata("3/10"), "La data 3/10 è già passata."),
        (regole.TroppeDate(), "Troppe date: al massimo 10."),
        (regole.NonNelSondaggio("15/10"), "La data 15/10 non era nel sondaggio."),
    ],
)
def test_i_rifiuti(rifiuto, testo):
    assert testi.rifiuto(rifiuto) == testi.Testo(testo)


def test_le_risposte_ai_comandi():
    assert testi.gia_aperto(NOME) == testi.Testo(
        "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot."
    )
    assert testi.solo_chi_chiude((GIO, ABE)) == testi.Testo("Il sondaggio lo chiudono gio o abe.")
    assert testi.solo_chi_chiude((GIO, ABE, EMI)) == testi.Testo(
        "Il sondaggio lo chiudono gio, abe o emi."
    )
    assert testi.nessun_sondaggio() == testi.Testo("Non c'è nessun sondaggio aperto.")
    assert testi.chiuso([d("14/10"), d("16/10")]) == testi.Testo(
        "🔒 Sondaggio chiuso. Date possibili: mar 14/10, gio 16/10."
    )
    assert testi.chiuso([]) == testi.Testo(
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    )
    assert testi.si_gioca(d("14/10")) == testi.Testo("🎲 Si gioca martedì 14/10.")
    assert testi.rimandiamo(d("20/10")) == testi.Testo(
        "🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."
    )
    assert testi.sparito() == testi.Testo("Il messaggio del sondaggio non c'è più: lo considero chiuso.")


def test_il_buio_con_le_ore_di_zurigo():
    # ora legale: UTC+2
    dal = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    al = datetime(2025, 10, 14, 7, 30, tzinfo=UTC)
    assert testi.buio(dal, al, ZURIGO) == testi.Testo(
        "🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10 alle 9:30. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    )
    # ora solare: UTC+1
    t = testi.buio(datetime(2025, 11, 2, 23, 5, tzinfo=UTC), datetime(2025, 11, 4, 8, 0, tzinfo=UTC), ZURIGO)
    assert "dal 3/11 alle 0:05 al 4/11 alle 9:00." in t.testo


def test_i_conteggi_dopo_il_buio():
    assert testi.conteggi(True) == testi.Testo("I conteggi del sondaggio sono gli stessi che avevo io.")
    assert testi.conteggi(False) == testi.Testo(
        "I conteggi del sondaggio sono diversi dai miei: "
        "mentre ero spento qualcuno ha votato o cambiato voto."
    )


def test_riapro():
    t = testi.riapro((ABE, EMI, SEM), (SESE, PIPPO))
    assert t.testo == (
        "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(t) == [("sese", SESE.telegram_id), ("pippo", PIPPO.telegram_id)]


def test_riapro_senza_le_parti_vuote():
    assert testi.riapro((), (GIO, ABE)).testo == "Riapro il sondaggio. Non hanno ancora votato: gio, abe."
    assert testi.riapro((ABE,), ()) == testi.Testo(
        "Riapro il sondaggio. Ho già i voti di abe: se non avete cambiato idea, non serve rivotare."
    )
    assert testi.date_passate() == testi.Testo("Le date del sondaggio sono passate: lo chiudo.")


def test_le_frasi_di_nessuna():
    assert len(testi.FRASI_NESSUNA) == 15
    assert len(set(testi.FRASI_NESSUNA)) == 15
    for frase in testi.FRASI_NESSUNA:
        assert frase.startswith("Nessuna"), frase
        assert len(frase) <= testi.LUNGHEZZA_OPZIONE, frase
        assert testi.utf16(frase) <= testi.LUNGHEZZA_OPZIONE, frase


def test_le_frasi_ruotano_senza_ripetersi_e_poi_ricominciano():
    caso = random.Random(7).choice
    usate: set[str] = set()
    for _ in testi.FRASI_NESSUNA:
        frase = testi.scegli_frase(usate, caso)
        assert frase not in usate
        usate.add(frase)
    assert usate == set(testi.FRASI_NESSUNA)
    # finite tutte: una qualsiasi, e chi la sceglie ricomincia il giro
    assert testi.scegli_frase(usate, caso) in testi.FRASI_NESSUNA


def test_scegli_frase_sceglie_fra_le_restanti():
    usate = set(testi.FRASI_NESSUNA[1:])
    assert testi.scegli_frase(usate, lambda restanti: restanti[0]) == testi.FRASI_NESSUNA[0]
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_testi.py -q`
Expected: FAIL — errore di import: `testi` non esiste ancora.

- [ ] **Step 3: i testi**

Crea `src/prossima/testi.py`:

```python
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
    match r:
        case regole.NonCapisco():
            return Testo(
                f"Non capisco «{r.parola}»: scrivi i giorni (lun, mar, …) o le date (14/10)."
            )
        case regole.DataPassata():
            return Testo(f"La data {r.scritta} è già passata.")
        case regole.TroppeDate():
            return Testo(f"Troppe date: al massimo {regole.MASSIMO_DATE}.")
        case regole.NonNelSondaggio():
            return Testo(f"La data {r.scritta} non era nel sondaggio.")
    raise TypeError(f"rifiuto sconosciuto: {r!r}")


def gia_aperto(nome_bot: str) -> Testo:
    return Testo(f"C'è già un sondaggio aperto: chiudilo prima con /chiudi@{nome_bot}.")


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


def si_gioca(giorno: date) -> Testo:
    return Testo(f"🎲 Si gioca {regole.etichetta_intera(giorno)}.")


def rimandiamo(lunedi: date) -> Testo:
    return Testo(f"🔁 Rimandiamo: nuovo sondaggio sulla settimana del {regole.breve(lunedi)}.")


def sparito() -> Testo:
    return Testo("Il messaggio del sondaggio non c'è più: lo considero chiuso.")


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
        "mentre ero spento qualcuno ha votato o cambiato voto."
    )


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
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_testi.py -q`
Expected: PASS — `22 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `93 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/testi.py tests/test_testi.py
git commit -m "texts: messages with UTF-16 mentions, None-of-these phrases

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 4: lo store SQLite

Una connessione per operazione e WAL, come lo store dei selfie. Gli annunci fatti stanno nel sondaggio come un'istantanea JSON di `Fatti`: la logica è in `regole.dopo`, lo store la conserva soltanto. Il database tiene anche la regola «un sondaggio aperto alla volta», con un indice unico parziale.

**Files:**
- Create: `src/prossima/store.py`
- Create: `tests/conftest.py` (la fixture `store`; il task 7 la estende)
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `prossima.regole.Fatti`, `Voto`; `tests.tavolo`.
- Produces (`prossima.store`): `CHIAVE_OFFSET`, `CHIAVE_LETTURA`; `@dataclass(frozen=True) Sondaggio(id: int, date: tuple[date, ...], poll_id: str, messaggio: int, frase: str, aperto_alle: datetime, chiuso_alle: datetime | None = None)`; `@dataclass(frozen=True) Lettera(id: int, chat_id: int, testo: str, entita: tuple[dict, ...], risposta_a: int | None)`; `Store(percorso: Path | str)` con:
  - `crea_schema() -> None`;
  - `sondaggio_aperto() -> Sondaggio | None`, `sondaggio(sondaggio_id: int) -> Sondaggio | None`, `apri_sondaggio(date_: Sequence[date], poll_id: str, messaggio: int, frase: str, alle: datetime) -> Sondaggio` (con un sondaggio già aperto: `sqlite3.IntegrityError`), `chiudi_sondaggio(sondaggio_id: int, alle: datetime, comando: int | None = None) -> bool`, `chiuso_dal_comando(comando: int) -> bool`, `riapri_sondaggio(sondaggio_id: int, date_: Sequence[date], poll_id: str, messaggio: int, frase: str) -> Sondaggio`;
  - `registra_voto(sondaggio_id: int, utente_id: int, poll_id: str, voto: Voto, alle: datetime) -> None`, `voti(sondaggio_id: int) -> dict[int, Voto]`, `voti_del_poll(sondaggio_id: int, poll_id: str) -> list[Voto]`;
  - `fatti(sondaggio_id: int) -> Fatti`, `salva_fatti(sondaggio_id: int, fatti: Fatti) -> None`;
  - `frasi_usate() -> set[str]`, `usa_frase(frase: str) -> None`, `dimentica_frasi() -> None`;
  - `accoda(chat_id: int, testo: str, entita: Sequence[dict], risposta_a: int | None, alle: datetime) -> int`, `posta() -> list[Lettera]` (in ordine di arrivo), `togli_lettera(lettera_id: int) -> None`;
  - `leggi_valore(chiave) -> str | None`, `scrivi_valore(chiave, valore) -> None`, `offset() -> int | None`, `salva_offset(offset: int) -> None`, `ultima_lettura() -> datetime | None`, `segna_lettura(alle: datetime) -> None`.
- Produces (`tests/conftest.py`): la fixture `store` (uno `Store` con lo schema, in `tmp_path`).

- [ ] **Step 1: la fixture e le prove dello store**

Crea `tests/conftest.py`:

```python
import pytest

from prossima.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "prossima.sqlite")
    s.crea_schema()
    return s
```

Crea `tests/test_store.py`:

```python
import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima.regole import Fatti, Voto
from prossima.store import Lettera, Sondaggio, Store
from tests.tavolo import ESTRANEO, GIO, d

ALLE = datetime(2025, 10, 7, 18, 0, tzinfo=UTC)
DATE = (d("14/10"), d("16/10"))


def apri(store, poll_id="poll-1", messaggio=501, date_=DATE):
    return store.apri_sondaggio(date_, poll_id, messaggio, "Nessuna: riposo lungo. Molto lungo.", ALLE)


def test_lo_schema_si_crea_due_volte_e_usa_wal(tmp_path):
    s = Store(tmp_path / "x.sqlite")
    s.crea_schema()
    s.crea_schema()
    with sqlite3.connect(tmp_path / "x.sqlite") as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_aprire_e_ritrovare_il_sondaggio_aperto(store):
    assert store.sondaggio_aperto() is None
    s = apri(store)
    assert s == Sondaggio(
        id=s.id,
        date=DATE,
        poll_id="poll-1",
        messaggio=501,
        frase="Nessuna: riposo lungo. Molto lungo.",
        aperto_alle=ALLE,
    )
    assert store.sondaggio_aperto() == s


def test_un_sondaggio_aperto_alla_volta(store):
    apri(store)
    with pytest.raises(sqlite3.IntegrityError):
        apri(store, poll_id="poll-2", messaggio=502)


def test_chiudere_una_volta_sola_e_ricordare_il_comando(store):
    s = apri(store)
    assert store.chiudi_sondaggio(s.id, ALLE + timedelta(hours=1), comando=777)
    assert not store.chiudi_sondaggio(s.id, ALLE + timedelta(hours=2), comando=778)
    assert store.sondaggio_aperto() is None
    assert store.sondaggio(s.id).chiuso_alle == ALLE + timedelta(hours=1)
    assert store.chiuso_dal_comando(777)
    assert not store.chiuso_dal_comando(778)
    # chiuso, se ne apre un altro
    assert apri(store, poll_id="poll-2", messaggio=502).id != s.id


def test_riaprire_cambia_il_messaggio_e_tiene_voti_e_fatti(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset(DATE)), ALLE)
    store.salva_fatti(s.id, Fatti(quasi=frozenset({d("14/10")})))
    store.chiudi_sondaggio(s.id, ALLE)
    riaperto = store.riapri_sondaggio(s.id, (d("16/10"),), "poll-9", 909, "Nessuna: ho tirato 1 sul calendario")
    assert riaperto == Sondaggio(
        id=s.id,
        date=(d("16/10"),),
        poll_id="poll-9",
        messaggio=909,
        frase="Nessuna: ho tirato 1 sul calendario",
        aperto_alle=ALLE,
    )
    assert store.sondaggio_aperto() == riaperto
    assert store.voti(s.id) == {GIO.telegram_id: Voto(frozenset(DATE))}
    assert store.fatti(s.id).quasi == {d("14/10")}


def test_il_voto_piu_recente_sostituisce_il_precedente_anche_vuoto(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset({d("14/10")})), ALLE)
    store.registra_voto(s.id, ESTRANEO, "poll-1", Voto(nessuna=True), ALLE)
    assert store.voti(s.id) == {
        GIO.telegram_id: Voto(frozenset({d("14/10")})),
        ESTRANEO: Voto(nessuna=True),
    }
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(), ALLE)
    assert store.voti(s.id)[GIO.telegram_id] == Voto()


def test_i_voti_di_un_sondaggio_di_telegram(store):
    s = apri(store)
    store.registra_voto(s.id, GIO.telegram_id, "poll-1", Voto(frozenset({d("14/10")})), ALLE)
    store.registra_voto(s.id, ESTRANEO, "poll-2", Voto(nessuna=True), ALLE)
    assert store.voti_del_poll(s.id, "poll-1") == [Voto(frozenset({d("14/10")}))]
    assert store.voti_del_poll(s.id, "poll-2") == [Voto(nessuna=True)]


def test_i_fatti_tornano_come_sono_stati_salvati(store):
    s = apri(store)
    assert store.fatti(s.id) == Fatti()
    fatti = Fatti(
        quasi=frozenset({d("14/10")}),
        possibili={d("14/10"): frozenset({1, 2}), d("16/10"): None},
        impossibile=True,
    )
    store.salva_fatti(s.id, fatti)
    assert store.fatti(s.id) == fatti


def test_le_frasi_usate(store):
    assert store.frasi_usate() == set()
    store.usa_frase("Nessuna: a")
    store.usa_frase("Nessuna: a")
    store.usa_frase("Nessuna: b")
    assert store.frasi_usate() == {"Nessuna: a", "Nessuna: b"}
    store.dimentica_frasi()
    assert store.frasi_usate() == set()


def test_la_posta_in_ordine_di_arrivo(store):
    menzione = {"type": "text_mention", "offset": 3, "length": 4, "user": {"id": 100000005}}
    primo = store.accoda(-100, "📅 sese", [menzione], None, ALLE)
    secondo = store.accoda(-100, "Troppe date: al massimo 10.", [], 42, ALLE)
    assert store.posta() == [
        Lettera(primo, -100, "📅 sese", (menzione,), None),
        Lettera(secondo, -100, "Troppe date: al massimo 10.", (), 42),
    ]
    store.togli_lettera(primo)
    assert [lettera.id for lettera in store.posta()] == [secondo]


def test_offset_e_ultima_lettura(store):
    assert store.offset() is None
    assert store.ultima_lettura() is None
    store.salva_offset(42)
    zurigo = datetime(2025, 10, 12, 21, 5, tzinfo=ZoneInfo("Europe/Zurich"))
    store.segna_lettura(zurigo)
    assert store.offset() == 42
    assert store.ultima_lettura() == zurigo
    assert store.ultima_lettura().tzinfo == UTC


def test_un_momento_senza_fuso_e_rifiutato(store):
    with pytest.raises(ValueError, match="senza fuso"):
        store.segna_lettura(datetime(2025, 10, 12, 21, 5))
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'prossima.store'` (nel conftest).

- [ ] **Step 3: lo store**

Crea `src/prossima/store.py`:

```python
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
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_store.py -q`
Expected: PASS — `12 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `105 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/store.py tests/conftest.py tests/test_store.py
git commit -m "SQLite store: polls, votes, outbox, one open poll at a time

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 5: la configurazione e il roster

Le variabili d'ambiente e il roster in TOML, con un errore che dice cosa correggere e dove. Il roster d'esempio nel repo ha identificativi finti, ed è proprio il roster delle prove: una prova lo carica, così l'esempio non può invecchiare.

**Files:**
- Create: `src/prossima/config.py`
- Create: `config.esempio/roster.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `prossima.regole` (`MASTER`, `RUOLI`, `Persona`, `Roster`); `tests.tavolo.ROSTER`.
- Produces (`prossima.config`): `FUSO_PREDEFINITO = "Europe/Zurich"`; `ConfigurazioneErrata(ValueError)`; `@dataclass(frozen=True) Impostazioni(token_bot: str, gruppo: int, roster: Roster, db: Path, battito: Path, fuso: ZoneInfo)`; `roster_da_toml(testo: str, origine: str = "roster") -> Roster`; `leggi_roster(percorso: Path) -> Roster`; `da_ambiente(env: Mapping[str, str]) -> Impostazioni` (legge `PV_BOT_TOKEN`, `PV_GRUPPO`, `PV_ROSTER`, `PV_DB`, `PV_BATTITO`, `PV_FUSO`).

- [ ] **Step 1: il roster d'esempio e le prove**

Crea `config.esempio/roster.toml`:

```toml
# Copia in config/roster.toml sul server e metti gli identificativi Telegram veri
# (i numeri, non i nomi utente: quelli si cambiano). Non va mai nel repository.
#
# Esattamente un master. «chiude = true» per chi può chiudere il sondaggio;
# senza, la persona non lo chiude. Il bot conta solo le persone di questo file.

[[persona]]
soprannome = "gio"
telegram_id = 100000001
ruolo = "master"
chiude = true

[[persona]]
soprannome = "abe"
telegram_id = 100000002
ruolo = "giocatore"
chiude = true

[[persona]]
soprannome = "emi"
telegram_id = 100000003
ruolo = "giocatore"

[[persona]]
soprannome = "sem"
telegram_id = 100000004
ruolo = "giocatore"

[[persona]]
soprannome = "sese"
telegram_id = 100000005
ruolo = "giocatore"

[[persona]]
soprannome = "pippo"
telegram_id = 100000006
ruolo = "giocatore"
```

Crea `tests/test_config.py`:

```python
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from prossima import config
from prossima.config import ConfigurazioneErrata
from tests.tavolo import ROSTER

RADICE = Path(__file__).resolve().parents[1]

PERSONA = """
[[persona]]
soprannome = "{soprannome}"
telegram_id = {telegram_id}
ruolo = "{ruolo}"
chiude = {chiude}
"""


def roster(*persone: dict) -> str:
    return "".join(PERSONA.format(**p) for p in persone)


def p(soprannome="gio", telegram_id=100000001, ruolo="master", chiude="true"):
    return {"soprannome": soprannome, "telegram_id": telegram_id, "ruolo": ruolo, "chiude": chiude}


def test_il_roster_d_esempio_e_quello_delle_prove():
    assert config.leggi_roster(RADICE / "config.esempio" / "roster.toml") == ROSTER


def test_chiude_e_falso_se_manca():
    testo = roster(p()) + '[[persona]]\nsoprannome = "emi"\ntelegram_id = 3\nruolo = "giocatore"\n'
    assert [x.chiude for x in config.roster_da_toml(testo).persone] == [True, False]


@pytest.mark.parametrize(
    "testo, messaggio",
    [
        ("[[persona]\n", "non è TOML valido"),
        ("", "nessuna persona"),
        ("[gruppi]\nparty = -1\n" + roster(p()), "sezioni sconosciute: gruppi"),
        (roster(p()).replace("chiude", "chuide"), "chiavi sconosciute: chuide"),
        (roster(p(soprannome=" gio")), "soprannome manca, o ha spazi intorno"),
        (roster(p(telegram_id='"100000001"')), "telegram_id deve essere un numero intero positivo"),
        (roster(p(telegram_id="true")), "telegram_id deve essere un numero intero positivo"),
        (roster(p(telegram_id=-5)), "telegram_id deve essere un numero intero positivo"),
        (roster(p(ruolo="admin")), "ruolo 'admin' sconosciuto"),
        (roster(p(chiude='"sì"')), "chiude deve essere true o false"),
        (roster(p(), p(telegram_id=2, ruolo="giocatore")), "il soprannome 'gio' compare due volte"),
        (roster(p(), p(soprannome="abe", ruolo="giocatore")), "il telegram_id 100000001 compare due volte"),
        (roster(p(ruolo="giocatore")), "serve esattamente un master, ce ne sono 0"),
        (roster(p(), p(soprannome="abe", telegram_id=2)), "serve esattamente un master, ce ne sono 2"),
        (roster(p(chiude="false")), "nessuno può chiudere il sondaggio"),
    ],
)
def test_un_roster_sbagliato_ferma_l_avvio_e_dice_perche(testo, messaggio):
    with pytest.raises(ConfigurazioneErrata, match=messaggio):
        config.roster_da_toml(testo, "config/roster.toml")


def test_l_errore_dice_quale_persona():
    testo = roster(p(), p(soprannome="emi", telegram_id=3, ruolo="cuoco"))
    with pytest.raises(ConfigurazioneErrata, match=r"config/roster.toml, persona 2 \(emi\)"):
        config.roster_da_toml(testo, "config/roster.toml")


def test_un_roster_che_non_c_e(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="non si legge"):
        config.leggi_roster(tmp_path / "manca.toml")


def ambiente(tmp_path, **cambi):
    env = {
        "PV_BOT_TOKEN": "123:SEGRETO",
        "PV_GRUPPO": "-1000000000001",
        "PV_ROSTER": str(RADICE / "config.esempio" / "roster.toml"),
        "PV_DB": str(tmp_path / "prossima.sqlite"),
        "PV_BATTITO": str(tmp_path / "battito"),
        "PV_FUSO": "Europe/Zurich",
    }
    env.update(cambi)
    return env


def test_le_impostazioni_dall_ambiente(tmp_path):
    imp = config.da_ambiente(ambiente(tmp_path))
    assert imp == config.Impostazioni(
        token_bot="123:SEGRETO",
        gruppo=-1000000000001,
        roster=ROSTER,
        db=tmp_path / "prossima.sqlite",
        battito=tmp_path / "battito",
        fuso=ZoneInfo("Europe/Zurich"),
    )


def test_il_fuso_predefinito_e_zurigo(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path, PV_FUSO="")).fuso == ZoneInfo("Europe/Zurich")


@pytest.mark.parametrize("nome", ["PV_BOT_TOKEN", "PV_GRUPPO", "PV_ROSTER", "PV_DB", "PV_BATTITO"])
def test_una_variabile_che_manca(tmp_path, nome):
    with pytest.raises(ConfigurazioneErrata, match=f"{nome} manca"):
        config.da_ambiente(ambiente(tmp_path, **{nome: "  "}))


def test_valori_malformati(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="PV_GRUPPO non è un numero intero: 'party'"):
        config.da_ambiente(ambiente(tmp_path, PV_GRUPPO="party"))
    with pytest.raises(ConfigurazioneErrata, match="PV_FUSO: fuso orario sconosciuto: 'Europe/Zurigo'"):
        config.da_ambiente(ambiente(tmp_path, PV_FUSO="Europe/Zurigo"))

```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL — errore di import: `config` non esiste ancora.

- [ ] **Step 3: la configurazione**

Crea `src/prossima/config.py`:

```python
"""La configurazione del bot, dall'ambiente, e il roster.

Sul server stanno in `config/prossima.env` (permessi 600) e in
`config/roster.toml`; nel repository ci sono solo gli esempi di
`config.esempio/`, con identificativi finti. Un valore mancante o sbagliato
ferma l'avvio con un messaggio che dice quale: mai un default silenzioso per
un segreto, per il gruppo o per una persona.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .regole import MASTER, RUOLI, Persona, Roster

FUSO_PREDEFINITO = "Europe/Zurich"
_CHIAVI_PERSONA = frozenset({"soprannome", "telegram_id", "ruolo", "chiude"})


class ConfigurazioneErrata(ValueError):
    """Una variabile d'ambiente o il roster non hanno la forma attesa."""


@dataclass(frozen=True)
class Impostazioni:
    token_bot: str
    gruppo: int
    roster: Roster
    db: Path
    battito: Path
    fuso: ZoneInfo


def _testo(env: Mapping[str, str], nome: str) -> str:
    valore = (env.get(nome) or "").strip()
    if not valore:
        raise ConfigurazioneErrata(f"{nome} manca")
    return valore


def _intero(env: Mapping[str, str], nome: str) -> int:
    grezzo = _testo(env, nome)
    try:
        return int(grezzo)
    except ValueError:
        raise ConfigurazioneErrata(f"{nome} non è un numero intero: {grezzo!r}") from None


def _fuso(env: Mapping[str, str]) -> ZoneInfo:
    nome = (env.get("PV_FUSO") or "").strip() or FUSO_PREDEFINITO
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigurazioneErrata(f"PV_FUSO: fuso orario sconosciuto: {nome!r}") from None


def _persona(voce: object, dove: str) -> Persona:
    if not isinstance(voce, dict):
        raise ConfigurazioneErrata(f"{dove}: non è una sezione [[persona]]")
    sconosciute = set(voce) - _CHIAVI_PERSONA
    if sconosciute:
        raise ConfigurazioneErrata(f"{dove}: chiavi sconosciute: {', '.join(sorted(sconosciute))}")
    soprannome = voce.get("soprannome")
    if not isinstance(soprannome, str) or not soprannome.strip() or soprannome != soprannome.strip():
        raise ConfigurazioneErrata(f"{dove}: soprannome manca, o ha spazi intorno")
    dove = f"{dove} ({soprannome})"
    telegram_id = voce.get("telegram_id")
    if isinstance(telegram_id, bool) or not isinstance(telegram_id, int) or telegram_id <= 0:
        raise ConfigurazioneErrata(f"{dove}: telegram_id deve essere un numero intero positivo")
    ruolo = voce.get("ruolo")
    if ruolo not in RUOLI:
        raise ConfigurazioneErrata(f"{dove}: ruolo {ruolo!r} sconosciuto: «master» o «giocatore»")
    chiude = voce.get("chiude", False)
    if not isinstance(chiude, bool):
        raise ConfigurazioneErrata(f"{dove}: chiude deve essere true o false")
    return Persona(soprannome, telegram_id, ruolo, chiude)


def roster_da_toml(testo: str, origine: str = "roster") -> Roster:
    try:
        dati = tomllib.loads(testo)
    except tomllib.TOMLDecodeError as e:
        raise ConfigurazioneErrata(f"{origine}: non è TOML valido ({e})") from None
    sconosciute = set(dati) - {"persona"}
    if sconosciute:
        raise ConfigurazioneErrata(f"{origine}: sezioni sconosciute: {', '.join(sorted(sconosciute))}")
    voci = dati.get("persona")
    if not isinstance(voci, list) or not voci:
        raise ConfigurazioneErrata(f"{origine}: nessuna persona: servono le sezioni [[persona]]")
    persone = tuple(_persona(voce, f"{origine}, persona {i}") for i, voce in enumerate(voci, 1))
    soprannomi = [p.soprannome for p in persone]
    for s in soprannomi:
        if soprannomi.count(s) > 1:
            raise ConfigurazioneErrata(f"{origine}: il soprannome {s!r} compare due volte")
    identificativi = [p.telegram_id for p in persone]
    for i in identificativi:
        if identificativi.count(i) > 1:
            raise ConfigurazioneErrata(f"{origine}: il telegram_id {i} compare due volte")
    master = [p for p in persone if p.ruolo == MASTER]
    if len(master) != 1:
        raise ConfigurazioneErrata(
            f"{origine}: serve esattamente un master, ce ne sono {len(master)}"
        )
    if not any(p.chiude for p in persone):
        raise ConfigurazioneErrata(
            f"{origine}: nessuno può chiudere il sondaggio: serve almeno una persona con chiude = true"
        )
    return Roster(persone)


def leggi_roster(percorso: Path) -> Roster:
    try:
        testo = percorso.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigurazioneErrata(f"il roster {percorso} non si legge: {e.strerror}") from None
    return roster_da_toml(testo, str(percorso))


def da_ambiente(env: Mapping[str, str]) -> Impostazioni:
    return Impostazioni(
        token_bot=_testo(env, "PV_BOT_TOKEN"),
        gruppo=_intero(env, "PV_GRUPPO"),
        roster=leggi_roster(Path(_testo(env, "PV_ROSTER"))),
        db=Path(_testo(env, "PV_DB")),
        battito=Path(_testo(env, "PV_BATTITO")),
        fuso=_fuso(env),
    )
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS — `27 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `132 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/config.py config.esempio/roster.toml tests/test_config.py
git commit -m "config: environment and roster with clear errors

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 6: il client di Telegram e il suo finto

Il client non ha politica: chiama l'API, restituisce quello che serve e dice, con il tipo dell'errore, se ripetere serve. Il token non esce mai: niente testo delle eccezioni di httpx, `from None`. Il finto mette per iscritto le convinzioni elencate in `docs/differenze-fra-test-e-realta.md`, e una prova controlla che abbia gli stessi metodi del client vero, con gli stessi argomenti.

**Files:**
- Create: `src/prossima/telegram.py`
- Create: `tests/finti.py`
- Test: `tests/test_telegram.py`, `tests/test_finti.py`

**Interfaces:**
- Consumes: niente dei task precedenti.
- Produces (`prossima.telegram`): `TelegramError(RuntimeError)` (rete, 5xx, risposta non JSON: si riprova al giro seguente); `TelegramRifiuto(TelegramError)` (4xx: ripetere non serve); `MessaggioSparito(TelegramRifiuto)`; `TelegramTroppeRichieste(TelegramError)` con `.retry_after: int` (non è un `TelegramRifiuto`); `@dataclass(frozen=True) SondaggioMandato(poll_id: str, messaggio: int)`; `BotTelegram(token: str, http: httpx.Client | None = None)` con `io() -> str` (il nome utente del bot), `aggiornamenti(offset: int | None, attesa: int) -> list[dict]`, `manda_sondaggio(chat_id: int, domanda: str, opzioni: Sequence[str]) -> SondaggioMandato`, `scrivi(chat_id: int, testo: str, entita: Sequence[dict] = (), risposta_a: int | None = None) -> dict` (il messaggio come l'ha registrato Telegram), `ferma_sondaggio(chat_id: int, messaggio: int) -> list[int]`, `registra_comandi(comandi: Sequence[tuple[str, str]]) -> None`.
- Produces (`tests.finti`): `TelegramFinto(nome: str = "ProssimaVoltaBot")`, con gli stessi metodi e, per le prove, `chiamate: list[tuple[str, dict]]` (solo quello che Telegram ha accettato), `guasto: Exception | None` (per ogni chiamata), `guasti: dict[str, Exception]` (per metodo), `aggiornamenti_da_dare`, `sondaggi: list[dict]` (`poll_id`, `messaggio`, `opzioni`), `conteggi: dict[int, list[int]]` (quello che darà `stopPoll`, per messaggio; di default tutti zero), `cancellati: set[int]`, `di_tipo(nome) -> list[dict]`, `scritti() -> list[str]`, `ultimo_sondaggio -> dict`; `telegram_guasto() -> TelegramError`; `Orologio(inizio: datetime)`, chiamabile, con `.adesso` e `.avanza(**quanto)`.

- [ ] **Step 1: le prove del client e del finto**

Crea `tests/test_telegram.py`:

```python
import json

import httpx
import pytest

from prossima.telegram import (
    BotTelegram,
    MessaggioSparito,
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

TOKEN = "123:SEGRETO"


def bot_con(gestore):
    return BotTelegram(TOKEN, http=httpx.Client(transport=httpx.MockTransport(gestore)))


def ok(risultato):
    return httpx.Response(200, json={"ok": True, "result": risultato})


def rifiuto(codice, descrizione, **altro):
    return httpx.Response(
        codice, json={"ok": False, "error_code": codice, "description": descrizione, **altro}
    )


def registra(risultato):
    viste = []

    def gestore(richiesta):
        viste.append(richiesta)
        return ok(risultato)

    return viste, gestore


def corpo(richiesta):
    return json.loads(richiesta.content)


def test_io_restituisce_il_nome_del_bot():
    viste, gestore = registra({"id": 1, "is_bot": True, "username": "ProssimaVoltaBot"})
    assert bot_con(gestore).io() == "ProssimaVoltaBot"
    assert viste[0].url.path == f"/bot{TOKEN}/getMe"


def test_aggiornamenti_chiede_messaggi_e_voti():
    viste, gestore = registra([{"update_id": 5}])
    bot = bot_con(gestore)
    assert bot.aggiornamenti(7, 25) == [{"update_id": 5}]
    assert corpo(viste[0]) == {
        "timeout": 25,
        "allowed_updates": ["message", "poll_answer"],
        "offset": 7,
    }
    bot.aggiornamenti(None, 0)
    assert "offset" not in corpo(viste[1])


def test_manda_un_sondaggio_non_anonimo_a_risposta_multipla():
    viste, gestore = registra({"message_id": 501, "poll": {"id": "5432", "options": []}})
    mandato = bot_con(gestore).manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert mandato == SondaggioMandato(poll_id="5432", messaggio=501)
    assert viste[0].url.path.endswith("/sendPoll")
    assert corpo(viste[0]) == {
        "chat_id": -100,
        "question": "Prossima volta?",
        "options": [{"text": "mar 14/10"}, {"text": "Nessuna: x"}],
        "is_anonymous": False,
        "allows_multiple_answers": True,
        "allows_revoting": True,
    }


def test_scrivi_testo_semplice():
    viste, gestore = registra({"message_id": 42, "text": "ciao *non* markdown"})
    assert bot_con(gestore).scrivi(-100, "ciao *non* markdown") == {
        "message_id": 42,
        "text": "ciao *non* markdown",
    }
    assert viste[0].url.path.endswith("/sendMessage")
    # niente parse_mode, niente entità vuote, niente risposta
    assert corpo(viste[0]) == {"chat_id": -100, "text": "ciao *non* markdown"}


def test_scrivi_con_le_menzioni_in_risposta_a_un_messaggio():
    viste, gestore = registra({"message_id": 43})
    menzione = {"type": "text_mention", "offset": 3, "length": 4, "user": {"id": 100000005}}
    bot_con(gestore).scrivi(-100, "📅 sese", [menzione], risposta_a=501)
    assert corpo(viste[0]) == {
        "chat_id": -100,
        "text": "📅 sese",
        "entities": [menzione],
        "reply_parameters": {"message_id": 501, "allow_sending_without_reply": True},
    }


def test_ferma_sondaggio_restituisce_i_conteggi():
    viste, gestore = registra(
        {
            "id": "5432",
            "is_closed": True,
            "options": [
                {"text": "mar 14/10", "voter_count": 3},
                {"text": "gio 16/10", "voter_count": 0},
                {"text": "Nessuna: x", "voter_count": 1},
            ],
        }
    )
    assert bot_con(gestore).ferma_sondaggio(-100, 501) == [3, 0, 1]
    assert viste[0].url.path.endswith("/stopPoll")
    assert corpo(viste[0]) == {"chat_id": -100, "message_id": 501}


def test_ferma_sondaggio_di_un_messaggio_cancellato():
    bot = bot_con(lambda r: rifiuto(400, "Bad Request: message to stop not found"))
    with pytest.raises(MessaggioSparito):
        bot.ferma_sondaggio(-100, 501)


def test_ferma_sondaggio_rifiutato_per_un_altro_motivo_non_e_sparito():
    bot = bot_con(lambda r: rifiuto(400, "Bad Request: chat not found"))
    with pytest.raises(TelegramRifiuto) as errore:
        bot.ferma_sondaggio(-100, 501)
    assert not isinstance(errore.value, MessaggioSparito)


def test_registra_comandi():
    viste, gestore = registra(True)
    bot_con(gestore).registra_comandi(
        [("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio")]
    )
    assert viste[0].url.path.endswith("/setMyCommands")
    assert corpo(viste[0]) == {
        "commands": [
            {"command": "sondaggio", "description": "Sondaggio per la prossima volta"},
            {"command": "chiudi", "description": "Chiude il sondaggio"},
        ]
    }


def test_un_429_dice_quanto_aspettare():
    bot = bot_con(
        lambda r: rifiuto(429, "Too Many Requests: retry after 7", parameters={"retry_after": 7})
    )
    with pytest.raises(TelegramTroppeRichieste) as errore:
        bot.scrivi(-100, "x")
    assert errore.value.retry_after == 7
    assert not isinstance(errore.value, TelegramRifiuto)


def test_un_4xx_e_un_rifiuto():
    bot = bot_con(lambda r: rifiuto(403, "Forbidden: bot was kicked from the group chat"))
    with pytest.raises(TelegramRifiuto, match="sendMessage: Forbidden: bot was kicked"):
        bot.scrivi(-100, "x")


def test_un_5xx_non_e_un_rifiuto():
    bot = bot_con(lambda r: rifiuto(502, "Bad Gateway"))
    with pytest.raises(TelegramError) as errore:
        bot.scrivi(-100, "x")
    assert not isinstance(errore.value, TelegramRifiuto)


def test_un_errore_di_rete_non_rivela_il_token():
    def gestore(richiesta):
        raise httpx.ConnectError(f"impossibile raggiungere {richiesta.url}", request=richiesta)

    with pytest.raises(TelegramError) as errore:
        bot_con(gestore).scrivi(1, "x")
    assert "SEGRETO" not in str(errore.value)
    assert errore.value.__cause__ is None
    assert errore.value.__suppress_context__


def test_una_risposta_non_json():
    with pytest.raises(TelegramError, match="HTTP 502") as errore:
        bot_con(lambda r: httpx.Response(502, text="Bad gateway")).scrivi(1, "x")
    assert not isinstance(errore.value, TelegramRifiuto)
```

Crea `tests/test_finti.py`:

```python
import inspect

import pytest

from prossima.telegram import BotTelegram, MessaggioSparito
from tests.finti import TelegramFinto, telegram_guasto


def firma(funzione):
    return [(p.name, p.default) for p in inspect.signature(funzione).parameters.values()]


def test_il_finto_ha_i_metodi_del_client_vero_con_gli_stessi_argomenti():
    pubblici = [nome for nome in vars(BotTelegram) if not nome.startswith("_")]
    assert pubblici == [
        "io", "aggiornamenti", "manda_sondaggio", "scrivi", "ferma_sondaggio", "registra_comandi",
    ]
    for nome in pubblici:
        assert firma(getattr(TelegramFinto, nome)) == firma(getattr(BotTelegram, nome)), nome


def test_il_finto_registra_solo_quello_che_telegram_accetta():
    telegram = TelegramFinto()
    telegram.guasti["scrivi"] = telegram_guasto()
    with pytest.raises(type(telegram_guasto())):
        telegram.scrivi(-100, "x")
    mandato = telegram.manda_sondaggio(-100, "Prossima volta?", ["mar 14/10", "Nessuna: x"])
    assert telegram.chiamate == [
        ("manda_sondaggio", {"chat_id": -100, "domanda": "Prossima volta?", "opzioni": ["mar 14/10", "Nessuna: x"]})
    ]
    assert telegram.ferma_sondaggio(-100, mandato.messaggio) == [0, 0]
    telegram.cancellati.add(mandato.messaggio)
    with pytest.raises(MessaggioSparito):
        telegram.ferma_sondaggio(-100, mandato.messaggio)
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_telegram.py tests/test_finti.py -q`
Expected: FAIL — errore di import: `prossima.telegram` e `tests.finti` non esistono ancora.

- [ ] **Step 3: il client**

Crea `src/prossima/telegram.py`:

```python
"""Il client del bot Telegram. Nessuna politica: chiama l'API e restituisce
quello che serve.

Il token sta nell'URL di ogni chiamata. Per questo gli errori non riportano mai
il testo delle eccezioni di httpx, che può contenere l'URL, e non le
incatenano (`from None`): un `log.exception` le stamperebbe. Per lo stesso
motivo `principale.py` alza il livello del logger `httpx`, che al livello INFO
scriverebbe ogni URL, token compreso.

Gli errori dicono a chi li riceve se ripetere serve:
- `TelegramTroppeRichieste` (429): sì, ma non prima di `retry_after` secondi;
- `TelegramRifiuto` (gli altri 4xx): no, la stessa richiesta verrà rifiutata
  di nuovo; `MessaggioSparito` è il rifiuto di `stopPoll` per un messaggio
  cancellato;
- `TelegramError` (rete, 5xx, risposta non JSON): sì, al giro seguente.

Nessuna chiamata usa `parse_mode`: i testi sono semplici, e le menzioni sono
entità.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

# Telegram descrive un messaggio che non c'è più come «message to … not found».
_SPARITO = re.compile(r"message[^:]*not found|MESSAGE_ID_INVALID", re.IGNORECASE)


class TelegramError(RuntimeError):
    """Una chiamata all'API di Telegram non è andata a buon fine."""


class TelegramRifiuto(TelegramError):
    """Telegram ha rifiutato la richiesta (4xx): ripeterla non serve."""


class MessaggioSparito(TelegramRifiuto):
    """Il messaggio del sondaggio non c'è più: è stato cancellato."""


class TelegramTroppeRichieste(TelegramError):
    """429: niente richieste prima di `retry_after` secondi."""

    def __init__(self, messaggio: str, retry_after: int) -> None:
        super().__init__(messaggio)
        self.retry_after = retry_after


@dataclass(frozen=True)
class SondaggioMandato:
    poll_id: str
    messaggio: int


class BotTelegram:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._http = http or httpx.Client(timeout=httpx.Timeout(10.0))

    def _chiama(self, metodo: str, corpo: dict | None = None, timeout: float | None = None) -> Any:
        argomenti: dict[str, Any] = {"json": corpo or {}}
        if timeout is not None:
            argomenti["timeout"] = timeout
        try:
            risposta = self._http.post(self._base + metodo, **argomenti)
        except httpx.HTTPError as e:
            raise TelegramError(f"{metodo}: errore di rete ({type(e).__name__})") from None
        try:
            contenuto = risposta.json()
        except ValueError:
            raise TelegramError(
                f"{metodo}: risposta non JSON (HTTP {risposta.status_code})"
            ) from None
        if contenuto.get("ok"):
            return contenuto["result"]
        descrizione = f"{metodo}: {contenuto.get('description', 'errore senza descrizione')}"
        codice = contenuto.get("error_code", risposta.status_code)
        if codice == 429:
            attesa = (contenuto.get("parameters") or {}).get("retry_after", 1)
            raise TelegramTroppeRichieste(descrizione, int(attesa))
        if 400 <= codice < 500:
            raise TelegramRifiuto(descrizione)
        raise TelegramError(descrizione)

    def io(self) -> str:
        """Il nome utente del bot, senza la @."""
        return self._chiama("getMe")["username"]

    def aggiornamenti(self, offset: int | None, attesa: int) -> list[dict]:
        corpo: dict[str, Any] = {"timeout": attesa, "allowed_updates": ["message", "poll_answer"]}
        if offset is not None:
            corpo["offset"] = offset
        return self._chiama("getUpdates", corpo, timeout=attesa + 10.0)

    def manda_sondaggio(self, chat_id: int, domanda: str, opzioni: Sequence[str]) -> SondaggioMandato:
        """Non anonimo, a risposta multipla, con il voto che si può cambiare:
        Telegram manda al bot ogni voto, con chi l'ha dato."""
        messaggio = self._chiama(
            "sendPoll",
            {
                "chat_id": chat_id,
                "question": domanda,
                "options": [{"text": o} for o in opzioni],
                "is_anonymous": False,
                "allows_multiple_answers": True,
                "allows_revoting": True,
            },
        )
        return SondaggioMandato(poll_id=messaggio["poll"]["id"], messaggio=messaggio["message_id"])

    def scrivi(
        self,
        chat_id: int,
        testo: str,
        entita: Sequence[dict] = (),
        risposta_a: int | None = None,
    ) -> dict:
        """Il messaggio come l'ha registrato Telegram, entità comprese."""
        corpo: dict[str, Any] = {"chat_id": chat_id, "text": testo}
        if entita:
            corpo["entities"] = list(entita)
        if risposta_a is not None:
            # Se il messaggio a cui si risponde non c'è più, il messaggio parte lo stesso.
            corpo["reply_parameters"] = {
                "message_id": risposta_a,
                "allow_sending_without_reply": True,
            }
        return self._chiama("sendMessage", corpo)

    def ferma_sondaggio(self, chat_id: int, messaggio: int) -> list[int]:
        """Ferma il sondaggio e restituisce i conteggi per opzione, nell'ordine
        delle opzioni."""
        try:
            sondaggio = self._chiama("stopPoll", {"chat_id": chat_id, "message_id": messaggio})
        except TelegramRifiuto as e:
            if _SPARITO.search(str(e)):
                raise MessaggioSparito(str(e)) from None
            raise
        return [opzione["voter_count"] for opzione in sondaggio["options"]]

    def registra_comandi(self, comandi: Sequence[tuple[str, str]]) -> None:
        self._chiama(
            "setMyCommands",
            {"commands": [{"command": c, "description": d} for c, d in comandi]},
        )
```

- [ ] **Step 4: il finto**

Crea `tests/finti.py`:

```python
"""I finti dei sistemi esterni.

Ognuno mette per iscritto una convinzione sul vero: dove quella convinzione
viene messa alla prova lo dice docs/differenze-fra-test-e-realta.md. Prima di
aggiungere un comportamento qui, la domanda è: quale convinzione sto scrivendo,
e dove la verifica il piano reale?
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prossima.telegram import MessaggioSparito, SondaggioMandato, TelegramError


class TelegramFinto:
    """Risponde subito e con successo, salvo i guasti: `guasto` vale per ogni
    chiamata, `guasti[metodo]` per un metodo solo. Una chiamata fallita non
    lascia traccia in `chiamate`: lì c'è solo quello che Telegram ha accettato."""

    def __init__(self, nome: str = "ProssimaVoltaBot") -> None:
        self.nome = nome
        self.chiamate: list[tuple[str, dict]] = []
        self.guasto: Exception | None = None
        self.guasti: dict[str, Exception] = {}
        self.aggiornamenti_da_dare: list[dict] = []
        self.sondaggi: list[dict] = []  # i sondaggi mandati, il più recente in fondo
        self.conteggi: dict[int, list[int]] = {}  # per messaggio: quello che darà stopPoll
        self.cancellati: set[int] = set()  # messaggi cancellati da qualcuno nel gruppo
        self._ultimo_id = 500

    def _registra(self, nome: str, **argomenti) -> int:
        guasto = self.guasti.get(nome) or self.guasto
        if guasto is not None:
            raise guasto
        self.chiamate.append((nome, argomenti))
        self._ultimo_id += 1
        return self._ultimo_id

    def io(self) -> str:
        self._registra("io")
        return self.nome

    def aggiornamenti(self, offset, attesa):
        self._registra("aggiornamenti", offset=offset, attesa=attesa)
        dati, self.aggiornamenti_da_dare = self.aggiornamenti_da_dare, []
        return dati

    def manda_sondaggio(self, chat_id, domanda, opzioni):
        messaggio = self._registra(
            "manda_sondaggio", chat_id=chat_id, domanda=domanda, opzioni=list(opzioni)
        )
        mandato = SondaggioMandato(poll_id=f"poll-{messaggio}", messaggio=messaggio)
        self.sondaggi.append(
            {"poll_id": mandato.poll_id, "messaggio": messaggio, "opzioni": list(opzioni)}
        )
        return mandato

    def scrivi(self, chat_id, testo, entita=(), risposta_a=None):
        messaggio = self._registra(
            "scrivi", chat_id=chat_id, testo=testo, entita=list(entita), risposta_a=risposta_a
        )
        return {"message_id": messaggio, "chat": {"id": chat_id}, "text": testo}

    def ferma_sondaggio(self, chat_id, messaggio):
        if messaggio in self.cancellati:
            raise MessaggioSparito("stopPoll: Bad Request: message to stop not found")
        self._registra("ferma_sondaggio", chat_id=chat_id, messaggio=messaggio)
        sondaggio = next(s for s in self.sondaggi if s["messaggio"] == messaggio)
        return list(self.conteggi.get(messaggio, [0] * len(sondaggio["opzioni"])))

    def registra_comandi(self, comandi):
        self._registra("registra_comandi", comandi=list(comandi))

    # --- per le prove

    def di_tipo(self, nome: str) -> list[dict]:
        return [argomenti for n, argomenti in self.chiamate if n == nome]

    def scritti(self) -> list[str]:
        return [a["testo"] for a in self.di_tipo("scrivi")]

    @property
    def ultimo_sondaggio(self) -> dict:
        return self.sondaggi[-1]


def telegram_guasto() -> TelegramError:
    return TelegramError("sendMessage: errore di rete (ConnectError)")


class Orologio:
    def __init__(self, inizio: datetime) -> None:
        self.adesso = inizio

    def __call__(self) -> datetime:
        return self.adesso

    def avanza(self, **quanto) -> None:
        self.adesso += timedelta(**quanto)
```

- [ ] **Step 5: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_telegram.py tests/test_finti.py -q`
Expected: PASS — `16 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `148 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 6: commit**

```bash
git add src/prossima/telegram.py tests/finti.py tests/test_telegram.py tests/test_finti.py
git commit -m "Telegram client that never leaks the token, and its fake

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 7: il bot — `/sondaggio`, i voti, gli annunci, gli invii che non riescono

Il cuore: `Bot.ricevi` gestisce un lotto, salva l'offset dopo ogni aggiornamento (un aggiornamento gestito due volte è innocuo) e poi manda. `manda` svuota la posta in uscita, in ordine, e poi manda gli annunci che lo stato chiede; quello che non parte resta, e riparte al giro seguente. Ogni chiamata che scrive su Telegram passa da `_invia`, che dopo un 429 non lascia partire niente prima di `retry_after`. `/chiudi` arriva nel task 8, la ripresa nel task 9.

**Files:**
- Create: `src/prossima/bot.py`
- Create: `tests/aggiornamenti.py`
- Modify: `tests/conftest.py` (sostituito per intero: aggiunge orologio, Telegram finto e bot)
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `prossima.regole` (date, `Stato`, `annunci_da_fare`, `dopo`, `rientrato`, `Rientro`, `voto_da_opzioni`, `Rifiuto`), `prossima.testi` (`DOMANDA`, `opzioni`, `scegli_frase`, `FRASI_NESSUNA`, `annuncio`, `rifiuto`, `gia_aperto`, `Testo`), `prossima.store.Store` e `Sondaggio`, `prossima.telegram` (`SondaggioMandato`, `TelegramError`, `TelegramRifiuto`, `TelegramTroppeRichieste`); `tests.finti`, `tests.tavolo`.
- Produces (`prossima.bot`): `COMANDI = (("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio"))`; `Bot(*, telegram, store: Store, roster: Roster, gruppo: int, nome: str, fuso: tzinfo, adesso: Callable[[], datetime], caso: Callable[[Sequence[str]], str] = random.choice)` con `ricevi(aggiornamenti: list[dict]) -> None`, `gestisci(aggiornamento: dict) -> None`, `manda() -> None`. I pezzi interni che i task 8 e 9 usano: `_nuovo_sondaggio(date_) -> tuple[SondaggioMandato, str]` (manda prima la posta in attesa; la frase conta come usata solo se il sondaggio parte), `_accoda(testo: testi.Testo, risposta_a: int | None = None)`, `_invia(chiamata, *argomenti)`, `_stato(sondaggio) -> regole.Stato`, `_oggi() -> date`, `_manda_posta()`, e la riga `    # --- i pezzi` che separa i comandi dai pezzi.
- Produces (`tests.aggiornamenti`): `GRUPPO = -1000000000001`, `NOME = "ProssimaVoltaBot"`, `comando(testo: str, da: int = GIO.telegram_id, chat: int = GRUPPO) -> dict`, `risposta(poll_id: str, da: int, *opzioni: int) -> dict`, `vota(bot, telegram, chi: Persona | int, scritto: str = "") -> None` (vota nell'ultimo sondaggio mandato).
- Produces (`tests/conftest.py`): `ZURIGO`, `INIZIO` (martedì 7/10/2025 alle 20:00 a Zurigo); le fixture `store`, `orologio`, `telegram`, `bot` (con `caso` che sceglie sempre la prima frase restante).

- [ ] **Step 1: gli aggiornamenti, le fixture e le prove del bot**

Crea `tests/aggiornamenti.py`:

```python
"""Gli aggiornamenti di Telegram come li riceve il bot: comandi e voti."""

from __future__ import annotations

from itertools import count

from prossima import regole
from prossima.regole import Persona
from tests.tavolo import GIO, d

GRUPPO = -1000000000001  # il gruppo del party, finto
NOME = "ProssimaVoltaBot"

_numeri = count(1)


def comando(testo: str, da: int = GIO.telegram_id, chat: int = GRUPPO) -> dict:
    """Un messaggio nel gruppo: con la privacy attiva, al bot arrivano solo i comandi."""
    n = next(_numeri)
    return {
        "update_id": 1000 + n,
        "message": {
            "message_id": 9000 + n,
            "from": {"id": da, "is_bot": False, "first_name": "x"},
            "chat": {"id": chat, "type": "supergroup" if chat < 0 else "private"},
            "date": 1760000000,
            "text": testo,
        },
    }


def risposta(poll_id: str, da: int, *opzioni: int) -> dict:
    """Un voto: le opzioni spuntate, da 0; nessuna opzione è il voto tolto."""
    n = next(_numeri)
    return {
        "update_id": 1000 + n,
        "poll_answer": {
            "poll_id": poll_id,
            "user": {"id": da, "is_bot": False, "first_name": "x"},
            "option_ids": list(opzioni),
        },
    }


def vota(bot, telegram, chi: Persona | int, scritto: str = "") -> None:
    """`chi` (una persona, o un identificativo Telegram) vota nell'ultimo
    sondaggio mandato: «14/10 16/10», «nessuna», oppure «» per togliere il voto."""
    sondaggio = telegram.ultimo_sondaggio
    opzioni = []
    for parola in scritto.split():
        if parola == "nessuna":
            opzioni.append(len(sondaggio["opzioni"]) - 1)
        else:
            opzioni.append(sondaggio["opzioni"].index(regole.etichetta(d(parola))))
    utente = chi if isinstance(chi, int) else chi.telegram_id
    bot.ricevi([risposta(sondaggio["poll_id"], utente, *opzioni)])
```

Sostituisci l'intero `tests/conftest.py` con:

```python
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from prossima.bot import Bot
from prossima.store import Store
from tests.aggiornamenti import GRUPPO, NOME
from tests.finti import Orologio, TelegramFinto
from tests.tavolo import ROSTER

ZURIGO = ZoneInfo("Europe/Zurich")
# Martedì 7/10/2025 alle 20:00 a Zurigo: la settimana seguente va dal 13 al 19.
INIZIO = datetime(2025, 10, 7, 18, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "prossima.sqlite")
    s.crea_schema()
    return s


@pytest.fixture
def orologio():
    return Orologio(INIZIO)


@pytest.fixture
def telegram():
    return TelegramFinto(NOME)


@pytest.fixture
def bot(telegram, store, orologio):
    # `caso` sceglie sempre la prima frase restante: le prove sanno quale arriva.
    return Bot(
        telegram=telegram,
        store=store,
        roster=ROSTER,
        gruppo=GRUPPO,
        nome=NOME,
        fuso=ZURIGO,
        adesso=orologio,
        caso=lambda restanti: restanti[0],
    )
```

Crea `tests/test_bot.py`:

```python
import logging

from prossima import testi
from prossima.regole import Voto
from prossima.telegram import TelegramRifiuto, TelegramTroppeRichieste
from tests.aggiornamenti import GRUPPO, comando, risposta, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, PIPPO, SEM, SESE, d

FRASE = testi.FRASI_NESSUNA[0]  # `caso` sceglie la prima restante
SETTIMANA = ["lun 13/10", "mar 14/10", "mer 15/10", "gio 16/10", "ven 17/10", "sab 18/10", "dom 19/10"]


def menzionati(chiamata):
    unita = chiamata["testo"].encode("utf-16-le")
    return [
        unita[2 * e["offset"] : 2 * (e["offset"] + e["length"])].decode("utf-16-le")
        for e in chiamata["entita"]
    ]


# --- /sondaggio


def test_senza_parole_la_settimana_seguente(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio@ProssimaVoltaBot")])
    assert telegram.di_tipo("manda_sondaggio") == [
        {"chat_id": GRUPPO, "domanda": "Prossima volta?", "opzioni": [*SETTIMANA, FRASE]}
    ]
    aperto = store.sondaggio_aperto()
    assert aperto.date == tuple(d(f"{g}/10") for g in range(13, 20))
    assert (aperto.poll_id, aperto.messaggio) == (
        telegram.ultimo_sondaggio["poll_id"],
        telegram.ultimo_sondaggio["messaggio"],
    )
    assert aperto.frase == FRASE
    assert aperto.aperto_alle == orologio.adesso
    assert telegram.scritti() == []


def test_la_settimana_seguente_e_quella_di_zurigo(bot, telegram, orologio):
    # domenica 12/10 alle 22:30 UTC è già lunedì 13/10 a Zurigo
    orologio.adesso = orologio.adesso.replace(day=12, hour=22, minute=30)
    bot.ricevi([comando("/sondaggio")])
    assert telegram.ultimo_sondaggio["opzioni"][0] == "lun 20/10"


def test_il_comando_per_un_altro_bot_si_ignora(bot, telegram, store):
    bot.ricevi([comando("/sondaggio@AltroBot"), comando("/sondaggio@altrobot 32/10")])
    assert telegram.chiamate == []
    assert store.sondaggio_aperto() is None


def test_il_nome_del_bot_non_conta_le_maiuscole(bot, telegram):
    bot.ricevi([comando("/sondaggio@prossimavoltabot mar")])
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", FRASE]


def test_fuori_dal_gruppo_non_risponde_a_niente(bot, telegram, store):
    privata = GIO.telegram_id
    bot.ricevi([comando("/sondaggio", chat=privata), comando("/sondaggio 32/10", chat=privata)])
    assert telegram.chiamate == []
    assert store.sondaggio_aperto() is None


def test_un_messaggio_che_non_e_un_comando_si_ignora(bot, telegram):
    bot.ricevi([comando("ciao"), comando(""), comando("/aiuto")])
    assert telegram.chiamate == []


def test_giorni_e_date(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio sab")])
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", "gio 16/10", "sab 18/10", FRASE]
    store.chiudi_sondaggio(store.sondaggio_aperto().id, store.sondaggio_aperto().aperto_alle)
    bot.ricevi([comando("/sondaggio 16.10 14/10 gio")])
    assert telegram.ultimo_sondaggio["opzioni"][:2] == ["mar 14/10", "gio 16/10"]


def test_i_rifiuti_rispondono_al_comando_e_non_aprono_niente(bot, telegram, store):
    sbagliati = [
        comando("/sondaggio 32/10"),
        comando("/sondaggio 3/10"),
        comando("/sondaggio " + " ".join(f"{g}/10" for g in range(13, 24))),
    ]
    bot.ricevi(sbagliati)
    assert telegram.di_tipo("scrivi") == [
        {
            "chat_id": GRUPPO,
            "testo": "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
            "entita": [],
            "risposta_a": sbagliati[0]["message"]["message_id"],
        },
        {
            "chat_id": GRUPPO,
            "testo": "La data 3/10 è già passata.",
            "entita": [],
            "risposta_a": sbagliati[1]["message"]["message_id"],
        },
        {
            "chat_id": GRUPPO,
            "testo": "Troppe date: al massimo 10.",
            "entita": [],
            "risposta_a": sbagliati[2]["message"]["message_id"],
        },
    ]
    assert telegram.di_tipo("manda_sondaggio") == []
    assert store.sondaggio_aperto() is None


def test_con_un_sondaggio_aperto_risponde_al_sondaggio(bot, telegram):
    bot.ricevi([comando("/sondaggio")])
    messaggio = telegram.ultimo_sondaggio["messaggio"]
    bot.ricevi([comando("/sondaggio mar"), comando("/sondaggio 32/10")])
    gia_aperto = {
        "chat_id": GRUPPO,
        "testo": "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot.",
        "entita": [],
        "risposta_a": messaggio,
    }
    assert telegram.di_tipo("scrivi") == [gia_aperto, gia_aperto]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_le_frasi_di_nessuna_ruotano(bot, telegram, store):
    for _ in range(3):
        bot.ricevi([comando("/sondaggio mar")])
        aperto = store.sondaggio_aperto()
        store.chiudi_sondaggio(aperto.id, aperto.aperto_alle)
    usate = [s["opzioni"][-1] for s in telegram.sondaggi]
    assert usate == list(testi.FRASI_NESSUNA[:3])
    assert store.frasi_usate() == set(testi.FRASI_NESSUNA[:3])


def test_finite_le_frasi_si_ricomincia(bot, telegram, store):
    for frase in testi.FRASI_NESSUNA:
        store.usa_frase(frase)
    bot.ricevi([comando("/sondaggio mar")])
    assert telegram.ultimo_sondaggio["opzioni"][-1] == FRASE
    assert store.frasi_usate() == {FRASE}


def test_un_sondaggio_che_non_parte_non_apre_niente(bot, telegram, store, caplog):
    telegram.guasti["manda_sondaggio"] = telegram_guasto()
    with caplog.at_level(logging.ERROR):
        bot.ricevi([comando("/sondaggio")])
    assert store.sondaggio_aperto() is None
    assert store.frasi_usate() == set()
    assert "non gestito" in caplog.text


# --- i voti


def test_un_voto_si_registra_e_il_piu_recente_vale(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, ABE, "14/10 nessuna")
    vota(bot, telegram, ESTRANEO, "16/10")
    aperto = store.sondaggio_aperto()
    assert store.voti(aperto.id) == {
        ABE.telegram_id: Voto(frozenset({d("14/10")}), nessuna=True),
        ESTRANEO: Voto(frozenset({d("16/10")})),
    }
    vota(bot, telegram, ABE, "")
    assert store.voti(aperto.id)[ABE.telegram_id] == Voto()


def test_un_voto_per_un_altro_sondaggio_si_ignora(bot, store):
    bot.ricevi([comando("/sondaggio mar")])
    bot.ricevi([risposta("poll-di-qualcun-altro", ABE.telegram_id, 0)])
    assert store.voti(store.sondaggio_aperto().id) == {}


def test_un_voto_senza_sondaggio_aperto_si_ignora(bot, telegram):
    bot.ricevi([risposta("poll-1", ABE.telegram_id, 0)])
    assert telegram.chiamate == []


# --- gli annunci


def test_quasi_con_le_menzioni_di_chi_non_ha_votato(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    assert telegram.scritti() == []
    vota(bot, telegram, SEM, "14/10")
    [quasi] = telegram.di_tipo("scrivi")
    assert quasi["testo"] == (
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo."
    )
    assert menzionati(quasi) == ["sese", "pippo"]
    assert [e["user"]["id"] for e in quasi["entita"]] == [SESE.telegram_id, PIPPO.telegram_id]
    assert (quasi["chat_id"], quasi["risposta_a"]) == (GRUPPO, None)
    bot.ricevi([])
    assert len(telegram.scritti()) == 1


def test_possibile_non_piu_e_di_nuovo_possibile(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    vota(bot, telegram, SEM, "16/10")
    vota(bot, telegram, PIPPO, "14/10")
    assert telegram.scritti() == [
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo.",
        "✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese.",
        "⚠️ mar 14/10 non va più bene: sem ha tolto il voto.",
        "✅ mar 14/10 va bene: ci sono gio, abe, emi, sese e pippo.",
    ]


def test_impossibile_e_di_nuovo_dopo_che_una_data_e_tornata_in_gioco(bot, telegram):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, GIO, "nessuna")
    vota(bot, telegram, GIO, "")  # le date tornano in gioco: niente da dire
    vota(bot, telegram, GIO, "nessuna")
    impossibile = (
        "😬 Con quattro giocatori non ci si sta in nessuna di queste date, e nemmeno con tre. "
        "gio, abe: /chiudi@ProssimaVoltaBot rimanda per rifare il sondaggio sulla settimana dopo."
    )
    assert telegram.scritti() == [impossibile, impossibile]
    assert menzionati(telegram.di_tipo("scrivi")[0]) == ["gio", "abe"]


def test_chi_non_e_nel_roster_non_conta_negli_annunci(bot, telegram):
    bot.ricevi([comando("/sondaggio mar")])
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    vota(bot, telegram, ESTRANEO, "14/10")
    assert telegram.scritti() == []


# --- gli invii che non riescono


def test_un_annuncio_che_non_parte_riparte_al_giro_seguente(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    telegram.guasti["scrivi"] = telegram_guasto()
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "14/10")
    assert telegram.scritti() == []
    assert store.fatti(store.sondaggio_aperto().id).quasi == frozenset()
    del telegram.guasti["scrivi"]
    bot.ricevi([])
    bot.ricevi([])
    assert len(telegram.scritti()) == 1
    assert telegram.scritti()[0].startswith("📅 mar 14/10")


def test_dopo_un_429_niente_parte_prima_di_retry_after(bot, telegram, orologio):
    bot.ricevi([comando("/sondaggio mar gio")])
    telegram.guasti["scrivi"] = TelegramTroppeRichieste("sendMessage: Too Many Requests", 30)
    for persona in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, persona, "14/10")
    del telegram.guasti["scrivi"]
    orologio.avanza(seconds=29)
    bot.ricevi([])
    assert telegram.scritti() == []
    orologio.avanza(seconds=1)
    bot.ricevi([])
    assert len(telegram.scritti()) == 1


def test_la_posta_che_non_parte_resta_e_riparte_in_ordine(bot, telegram, store):
    telegram.guasto = telegram_guasto()
    primo, secondo = comando("/sondaggio 32/10"), comando("/sondaggio 3/10")
    bot.ricevi([primo, secondo])
    assert len(store.posta()) == 2
    telegram.guasto = None
    bot.ricevi([])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        (
            "Non capisco «32/10»: scrivi i giorni (lun, mar, …) o le date (14/10).",
            primo["message"]["message_id"],
        ),
        ("La data 3/10 è già passata.", secondo["message"]["message_id"]),
    ]
    assert store.posta() == []


def test_un_messaggio_rifiutato_da_telegram_si_scarta(bot, telegram, store, caplog):
    telegram.guasti["scrivi"] = TelegramRifiuto("sendMessage: Bad Request: chat not found")
    with caplog.at_level(logging.ERROR):
        bot.ricevi([comando("/sondaggio 32/10")])
    assert store.posta() == []
    assert "messaggio scartato" in caplog.text


def test_la_posta_parte_prima_del_sondaggio(bot, telegram):
    telegram.guasti["scrivi"] = telegram_guasto()
    bot.ricevi([comando("/sondaggio 32/10")])
    del telegram.guasti["scrivi"]
    bot.ricevi([comando("/sondaggio mar")])
    assert [nome for nome, _ in telegram.chiamate] == ["scrivi", "manda_sondaggio"]


# --- il lotto


def test_l_offset_si_salva_dopo_ogni_aggiornamento(bot, store):
    lotto = [comando("/sondaggio mar"), comando("ciao")]
    bot.ricevi(lotto)
    assert store.offset() == lotto[-1]["update_id"] + 1


def test_un_aggiornamento_che_esplode_non_ferma_gli_altri(bot, telegram, store, caplog):
    rotto = {"update_id": 77, "message": {"chat": {"id": GRUPPO}, "text": "/sondaggio 32/10"}}
    buono = comando("/sondaggio mar")
    with caplog.at_level(logging.ERROR):
        bot.ricevi([rotto, buono])
    assert "aggiornamento 77 non gestito" in caplog.text
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", FRASE]
    assert store.offset() == buono["update_id"] + 1


def test_un_aggiornamento_letto_due_volte_non_fa_doppioni(bot, telegram):
    lancio = comando("/sondaggio mar gio")
    bot.ricevi([lancio])
    voti = []
    for persona in (GIO, ABE, EMI, SEM):
        sondaggio = telegram.ultimo_sondaggio
        voti.append(risposta(sondaggio["poll_id"], persona.telegram_id, 0))
    bot.ricevi(voti)
    # dopo un riavvio, lo stesso lotto un'altra volta
    bot.ricevi([lancio, *voti])
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti() == [
        "📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. "
        "Non hanno ancora votato: sese, pippo.",
        "C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot.",
    ]

```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_bot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'prossima.bot'` (nel conftest).

- [ ] **Step 3: il bot**

Crea `src/prossima/bot.py`:

```python
"""Il bot: smista gli aggiornamenti di Telegram e manda gli annunci.

Un solo processo e un solo filo: nessuna gara fra un voto e un comando.

Che cosa parte verso Telegram, e quando:
- un sondaggio (`sendPoll`) e la sua chiusura (`stopPoll`) partono subito: se
  falliscono, il comando non ha effetto (resta nel log) e lo si riscrive;
- gli annunci (quasi, possibile, non più possibile, impossibile) si calcolano
  dallo stato a ogni giro (`manda`), e contano come fatti solo dopo che
  Telegram li ha accettati;
- ogni altro messaggio passa dalla posta in uscita del database, in ordine: se
  non parte resta lì, e riparte al giro seguente. Un rifiuto di Telegram (4xx)
  lo scarta, con un errore nel log: ripeterlo darebbe lo stesso rifiuto.
Dopo un 429 niente parte prima di `retry_after`.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, tzinfo

from . import regole, testi
from .regole import Roster
from .store import Sondaggio, Store
from .telegram import (
    SondaggioMandato,
    TelegramError,
    TelegramRifiuto,
    TelegramTroppeRichieste,
)

log = logging.getLogger(__name__)

COMANDI = (("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio"))


class Bot:
    def __init__(
        self,
        *,
        telegram,
        store: Store,
        roster: Roster,
        gruppo: int,
        nome: str,
        fuso: tzinfo,
        adesso: Callable[[], datetime],
        caso: Callable[[Sequence[str]], str] = random.choice,
    ) -> None:
        self._tg = telegram
        self._store = store
        self._roster = roster
        self._gruppo = gruppo
        self._nome = nome
        self._fuso = fuso
        self._adesso = adesso
        self._caso = caso
        self._pausa_fino_a: datetime | None = None

    # --- il giro

    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii."""
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        self.manda()

    def gestisci(self, aggiornamento: dict) -> None:
        if "poll_answer" in aggiornamento:
            self._voto(aggiornamento["poll_answer"])
        elif "message" in aggiornamento:
            self._messaggio(aggiornamento["message"])

    def manda(self) -> None:
        """La posta in uscita, in ordine, poi gli annunci del sondaggio aperto.
        Quello che non parte riparte al giro seguente."""
        try:
            self._manda_posta()
            self._manda_annunci()
        except TelegramError as e:
            log.warning("invio rimandato al giro seguente: %s", e)

    # --- i messaggi e i comandi

    def _messaggio(self, messaggio: dict) -> None:
        if messaggio.get("chat", {}).get("id") != self._gruppo:
            return  # fuori dal gruppo del party il bot non risponde a niente
        parole = (messaggio.get("text") or "").split()
        if not parole:
            return
        comando = self._comando(parole[0])
        if comando == "sondaggio":
            self._sondaggio(messaggio, parole[1:])

    def _comando(self, parola: str) -> str | None:
        """«/sondaggio» o «/sondaggio@<nome del bot>» → «sondaggio»; un comando
        rivolto a un altro bot → None."""
        if not parola.startswith("/"):
            return None
        comando, _, destinatario = parola[1:].partition("@")
        if destinatario and destinatario.lower() != self._nome.lower():
            return None
        return comando.lower()

    def _sondaggio(self, messaggio: dict, parole: list[str]) -> None:
        aperto = self._store.sondaggio_aperto()
        if aperto is not None:
            self._accoda(testi.gia_aperto(self._nome), risposta_a=aperto.messaggio)
            return
        try:
            date_ = regole.date_del_comando(parole, self._oggi())
        except regole.Rifiuto as r:
            self._accoda(testi.rifiuto(r), risposta_a=messaggio["message_id"])
            return
        mandato, frase = self._nuovo_sondaggio(date_)
        self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())

    def _voto(self, risposta: dict) -> None:
        sondaggio = self._store.sondaggio_aperto()
        utente = risposta.get("user")
        if sondaggio is None or utente is None or risposta.get("poll_id") != sondaggio.poll_id:
            return
        voto = regole.voto_da_opzioni(sondaggio.date, risposta.get("option_ids", []))
        self._store.registra_voto(sondaggio.id, utente["id"], sondaggio.poll_id, voto, self._adesso())

    # --- i pezzi

    def _oggi(self) -> date:
        return self._adesso().astimezone(self._fuso).date()

    def _stato(self, sondaggio: Sondaggio) -> regole.Stato:
        return regole.Stato(self._roster, sondaggio.date, self._store.voti(sondaggio.id))

    def _frase(self) -> str:
        usate = self._store.frasi_usate()
        if usate >= set(testi.FRASI_NESSUNA):
            self._store.dimentica_frasi()  # finite tutte: si ricomincia
            usate = set()
        return testi.scegli_frase(usate, self._caso)

    def _nuovo_sondaggio(self, date_: Sequence[date]) -> tuple[SondaggioMandato, str]:
        """Manda un sondaggio sulle `date_`. Prima la posta in attesa, che viene
        prima nella chat; la frase conta come usata solo se il sondaggio parte."""
        try:
            self._manda_posta()
        except TelegramError as e:
            log.warning("posta rimandata: %s", e)
        frase = self._frase()
        mandato = self._invia(
            self._tg.manda_sondaggio, self._gruppo, testi.DOMANDA, testi.opzioni(date_, frase)
        )
        self._store.usa_frase(frase)
        return mandato, frase

    def _accoda(self, testo: testi.Testo, risposta_a: int | None = None) -> None:
        self._store.accoda(self._gruppo, testo.testo, testo.entita, risposta_a, self._adesso())

    def _invia(self, chiamata, *argomenti):
        """Ogni chiamata che scrive su Telegram passa di qui: dopo un 429, niente
        parte prima di `retry_after`."""
        ora = self._adesso()
        if self._pausa_fino_a is not None and ora < self._pausa_fino_a:
            raise TelegramError(
                f"Telegram ha chiesto di aspettare fino alle {self._pausa_fino_a.isoformat(timespec='seconds')}"
            )
        try:
            return chiamata(*argomenti)
        except TelegramTroppeRichieste as e:
            self._pausa_fino_a = ora + timedelta(seconds=e.retry_after)
            raise

    def _manda_posta(self) -> None:
        for lettera in self._store.posta():
            try:
                self._invia(
                    self._tg.scrivi, lettera.chat_id, lettera.testo, lettera.entita, lettera.risposta_a
                )
            except TelegramRifiuto as e:
                log.error("messaggio scartato, Telegram lo rifiuta: %s (%r)", e, lettera.testo)
            self._store.togli_lettera(lettera.id)

    def _manda_annunci(self) -> None:
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            return
        stato = self._stato(sondaggio)
        fatti = self._store.fatti(sondaggio.id)
        if regole.rientrato(stato, fatti):
            fatti = regole.dopo(fatti, regole.Rientro())
            self._store.salva_fatti(sondaggio.id, fatti)
        for annuncio in regole.annunci_da_fare(stato, fatti):
            testo = testi.annuncio(annuncio, self._roster, self._nome)
            self._invia(self._tg.scrivi, self._gruppo, testo.testo, testo.entita)
            fatti = regole.dopo(fatti, annuncio)
            self._store.salva_fatti(sondaggio.id, fatti)
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_bot.py -q`
Expected: PASS — `27 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `175 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/bot.py tests/aggiornamenti.py tests/conftest.py tests/test_bot.py
git commit -m "bot: /sondaggio, votes, announcements, outbox and retries

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 8: il bot — `/chiudi` nelle tre forme

`/chiudi` è un'unità a sé: chi può chiudere, le tre forme (date possibili, una data tenuta, `rimanda`), il messaggio del sondaggio cancellato, il comando letto due volte. `_ferma` restituisce i conteggi di `stopPoll`: qui non servono, li userà la ripresa (task 9).

**Files:**
- Modify: `src/prossima/bot.py` (l'import di `MessaggioSparito`, lo smistamento di `/chiudi`, la sezione `# --- /chiudi` prima di `# --- i pezzi`)
- Test: `tests/test_chiudi.py`

**Interfaces:**
- Consumes: dal task 7 `Bot._accoda`, `_invia`, `_stato`, `_nuovo_sondaggio`; `Store.chiudi_sondaggio(sondaggio_id, alle, comando)`, `chiuso_dal_comando(comando)`, `apri_sondaggio(...)`; `regole.data_da_chiudere`, `date_rimandate`, `lunedi_seguente`, `possibili`, `NonCapisco`, `RIMANDA`; `testi.solo_chi_chiude`, `nessun_sondaggio`, `chiuso`, `si_gioca`, `rimandiamo`, `sparito`, `rifiuto`; `telegram.MessaggioSparito`; il finto con `cancellati`.
- Produces (`prossima.bot`): `Bot._chiudi(messaggio: dict, parole: list[str]) -> None`; `Bot._ferma(sondaggio: Sondaggio, comando: int | None = None) -> list[int] | None` (i conteggi di Telegram, o `None` se il messaggio non c'era più: in quel caso il sondaggio è chiuso lo stesso, e il bot lo dice).

- [ ] **Step 1: le prove di `/chiudi`**

Crea `tests/test_chiudi.py`:

```python
import pytest

from prossima import testi
from tests.aggiornamenti import GRUPPO, comando, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, GIO, SEM, SESE, d


@pytest.fixture
def aperto(bot, telegram, store):
    """Un sondaggio su martedì 14/10 e giovedì 16/10."""
    bot.ricevi([comando("/sondaggio mar gio")])
    return store.sondaggio_aperto()


def possibile_il_14(bot, telegram):
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")


def test_solo_chi_chiude(bot, telegram, store, aperto):
    da_emi = comando("/chiudi", da=EMI.telegram_id)
    bot.ricevi([da_emi])
    assert telegram.di_tipo("scrivi") == [
        {
            "chat_id": GRUPPO,
            "testo": "Il sondaggio lo chiudono gio o abe.",
            "entita": [],
            "risposta_a": da_emi["message"]["message_id"],
        }
    ]
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto


def test_senza_sondaggio_aperto(bot, telegram):
    da_gio = comando("/chiudi")
    bot.ricevi([da_gio])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        ("Non c'è nessun sondaggio aperto.", da_gio["message"]["message_id"])
    ]


def test_chiudi_dice_le_date_possibili(bot, telegram, store, aperto):
    possibile_il_14(bot, telegram)
    bot.ricevi([comando("/chiudi@ProssimaVoltaBot", da=ABE.telegram_id)])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert store.sondaggio_aperto() is None
    assert telegram.scritti()[-1] == "🔒 Sondaggio chiuso. Date possibili: mar 14/10."


def test_chiudi_senza_date_possibili(bot, telegram, aperto):
    bot.ricevi([comando("/chiudi")])
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]


@pytest.mark.parametrize("parola", ["14/10", "14.10", "mar", "MAR"])
def test_chiudi_tenendo_una_data(bot, telegram, store, aperto, parola):
    bot.ricevi([comando(f"/chiudi {parola}")])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == ["🎲 Si gioca martedì 14/10."]


@pytest.mark.parametrize(
    "argomento, testo",
    [
        ("15/10", "La data 15/10 non era nel sondaggio."),
        ("ven", "La data ven non era nel sondaggio."),
        ("boh", "Non capisco «boh»: scrivi i giorni (lun, mar, …) o le date (14/10)."),
        ("14/10 16/10", "Non capisco «14/10 16/10»: scrivi i giorni (lun, mar, …) o le date (14/10)."),
    ],
)
def test_chiudi_con_una_data_sbagliata_lascia_il_sondaggio_aperto(
    bot, telegram, store, aperto, argomento, testo
):
    chiudi = comando(f"/chiudi {argomento}")
    bot.ricevi([chiudi])
    assert [(a["testo"], a["risposta_a"]) for a in telegram.di_tipo("scrivi")] == [
        (testo, chiudi["message"]["message_id"])
    ]
    assert telegram.di_tipo("ferma_sondaggio") == []
    assert store.sondaggio_aperto() == aperto


def test_rimanda_rifa_il_sondaggio_sulla_settimana_dopo(bot, telegram, store, aperto):
    bot.ricevi([comando("/chiudi rimanda")])
    assert telegram.di_tipo("ferma_sondaggio") == [{"chat_id": GRUPPO, "messaggio": aperto.messaggio}]
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 21/10", "gio 23/10", testi.FRASI_NESSUNA[1]]
    nuovo = store.sondaggio_aperto()
    assert nuovo.id != aperto.id
    assert nuovo.date == (d("21/10"), d("23/10"))
    assert telegram.scritti() == ["🔁 Rimandiamo: nuovo sondaggio sulla settimana del 20/10."]
    # il messaggio dice del sondaggio nuovo solo dopo che è partito
    assert [nome for nome, _ in telegram.chiamate][-3:] == ["ferma_sondaggio", "manda_sondaggio", "scrivi"]


def test_rimanda_letto_due_volte_non_chiude_il_sondaggio_nuovo(bot, telegram, store, aperto):
    rimanda = comando("/chiudi rimanda")
    bot.ricevi([rimanda])
    nuovo = store.sondaggio_aperto()
    bot.ricevi([rimanda])  # dopo un riavvio, lo stesso aggiornamento
    assert store.sondaggio_aperto() == nuovo
    assert len(telegram.di_tipo("ferma_sondaggio")) == 1
    assert len(telegram.di_tipo("manda_sondaggio")) == 2


def test_rimanda_se_il_sondaggio_nuovo_non_parte(bot, telegram, store, aperto):
    telegram.guasti["manda_sondaggio"] = telegram_guasto()
    bot.ricevi([comando("/chiudi rimanda")])
    # il vecchio è chiuso; del nuovo nessuno scrive niente, perché non c'è
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == []


def test_il_messaggio_del_sondaggio_cancellato(bot, telegram, store, aperto):
    telegram.cancellati.add(aperto.messaggio)
    bot.ricevi([comando("/chiudi 14/10")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [
        "Il messaggio del sondaggio non c'è più: lo considero chiuso.",
        "🎲 Si gioca martedì 14/10.",
    ]


def test_uno_stop_che_non_riesce_lascia_il_sondaggio_aperto(bot, telegram, store, aperto):
    telegram.guasti["ferma_sondaggio"] = telegram_guasto()
    bot.ricevi([comando("/chiudi")])
    assert store.sondaggio_aperto() == aperto
    assert telegram.scritti() == []
    del telegram.guasti["ferma_sondaggio"]
    bot.ricevi([comando("/chiudi")])
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]


def test_dopo_la_chiusura_niente_annunci(bot, telegram, aperto):
    for persona in (GIO, ABE, EMI):
        vota(bot, telegram, persona, "14/10")
    bot.ricevi([comando("/chiudi")])
    vota(bot, telegram, SEM, "14/10")  # un voto arrivato tardi: il sondaggio è chiuso
    assert telegram.scritti() == [
        "🔒 Sondaggio chiuso. Nessuna data con il master e quattro giocatori."
    ]
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_chiudi.py -q`
Expected: FAIL — il bot ignora ancora `/chiudi`: niente `stopPoll`, niente messaggi.

- [ ] **Step 3: `/chiudi`**

In `src/prossima/bot.py`, sostituisci:

```python
from .telegram import (
    SondaggioMandato,
```

con:

```python
from .telegram import (
    MessaggioSparito,
    SondaggioMandato,
```

In `src/prossima/bot.py`, sostituisci:

```python
        if comando == "sondaggio":
            self._sondaggio(messaggio, parole[1:])
```

con:

```python
        if comando == "sondaggio":
            self._sondaggio(messaggio, parole[1:])
        elif comando == "chiudi":
            self._chiudi(messaggio, parole[1:])
```

In `src/prossima/bot.py`, sostituisci:

```python
    # --- i pezzi
```

con:

```python
    # --- /chiudi

    def _chiudi(self, messaggio: dict, parole: list[str]) -> None:
        comando = messaggio["message_id"]
        if self._store.chiuso_dal_comando(comando):
            return  # lo stesso /chiudi letto una seconda volta dopo un riavvio
        chi = self._roster.per_id(messaggio.get("from", {}).get("id"))
        if chi is None or not chi.chiude:
            self._accoda(testi.solo_chi_chiude(self._roster.chi_chiude), risposta_a=comando)
            return
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            self._accoda(testi.nessun_sondaggio(), risposta_a=comando)
            return
        if len(parole) > 1:
            self._accoda(testi.rifiuto(regole.NonCapisco(" ".join(parole))), risposta_a=comando)
            return
        argomento = parole[0] if parole else None
        rimanda = argomento is not None and argomento.lower() == regole.RIMANDA
        tenuta = None
        if argomento is not None and not rimanda:
            try:
                tenuta = regole.data_da_chiudere(argomento, sondaggio.date)
            except regole.Rifiuto as r:
                self._accoda(testi.rifiuto(r), risposta_a=comando)
                return
        stato = self._stato(sondaggio)
        self._ferma(sondaggio, comando)
        if rimanda:
            date_ = regole.date_rimandate(sondaggio.date)
            mandato, frase = self._nuovo_sondaggio(date_)
            self._store.apri_sondaggio(date_, mandato.poll_id, mandato.messaggio, frase, self._adesso())
            self._accoda(testi.rimandiamo(regole.lunedi_seguente(max(sondaggio.date))))
        elif tenuta is not None:
            self._accoda(testi.si_gioca(tenuta))
        else:
            self._accoda(testi.chiuso(regole.possibili(stato)))

    def _ferma(self, sondaggio: Sondaggio, comando: int | None = None) -> list[int] | None:
        """Ferma il sondaggio su Telegram e lo chiude nel database; restituisce i
        conteggi di Telegram. Se il messaggio non c'è più, lo chiude lo stesso, lo
        dice, e restituisce None."""
        try:
            conteggi = self._invia(self._tg.ferma_sondaggio, self._gruppo, sondaggio.messaggio)
        except MessaggioSparito:
            conteggi = None
        self._store.chiudi_sondaggio(sondaggio.id, self._adesso(), comando)
        if conteggi is None:
            self._accoda(testi.sparito())
        return conteggi

    # --- i pezzi
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_chiudi.py -q`
Expected: PASS — `18 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `193 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/bot.py tests/test_chiudi.py
git commit -m "bot: /chiudi with possible dates, a kept date, or rimanda

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 9: la ripresa dopo il buio (§3.8)

`ricevi` ricorda il momento dell'ultima lettura riuscita. Quando una lettura arriva più di 23 ore dopo la precedente, dopo aver gestito il lotto il bot lo dice, ferma il sondaggio aperto, confronta i conteggi di Telegram con i suoi, e lo riapre sulle date non ancora passate tenendo buoni i voti registrati (o lo chiude, se le date sono tutte passate). Una ripresa che fallisce a metà finisce nel log e non si ripete alla lettura seguente: il buio è finito.

**Files:**
- Modify: `src/prossima/bot.py` (la prima riga della docstring, il metodo `ricevi`, la sezione `# --- la ripresa dopo il buio (§3.8)` prima di `# --- i pezzi`)
- Test: `tests/test_ripresa.py`

**Interfaces:**
- Consumes: dal task 8 `Bot._ferma(sondaggio, comando=None) -> list[int] | None`; dal task 7 `_accoda`, `_nuovo_sondaggio`, `_stato`, `_oggi`; `Store.ultima_lettura()`, `segna_lettura(alle)`, `voti_del_poll(sondaggio_id, poll_id)`, `riapri_sondaggio(...)`, `fatti`, `salva_fatti`; `regole.al_buio`, `conteggi_per_opzione`, `dopo`, `Ripresa`; `testi.buio`, `conteggi`, `date_passate`, `riapro`; il finto con `conteggi` e `cancellati`.
- Produces (`prossima.bot`): `Bot.riprendi(dal: datetime, al: datetime) -> None`; `Bot.ricevi` che fa la ripresa quando `regole.al_buio(precedente, ora)`.

- [ ] **Step 1: le prove della ripresa**

Crea `tests/test_ripresa.py`:

```python
import logging
from datetime import UTC, datetime

from prossima import testi
from prossima.regole import Voto
from tests.aggiornamenti import comando, vota
from tests.finti import telegram_guasto
from tests.tavolo import ABE, EMI, ESTRANEO, GIO, SEM, SESE, d

BUIO = (
    "🔌 Sono rimasto senza Telegram dal 7/10 alle 20:00 al 9/10 alle 2:00. "
    "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
)
UGUALI = "I conteggi del sondaggio sono gli stessi che avevo io."
DIVERSI = (
    "I conteggi del sondaggio sono diversi dai miei: "
    "mentre ero spento qualcuno ha votato o cambiato voto."
)


def dopo_il_buio(bot, orologio, ore=30):
    """L'ultima lettura riuscita è di adesso; la prossima arriva `ore` dopo."""
    orologio.avanza(hours=ore)
    bot.ricevi([])


def test_la_prima_lettura_non_e_buio(bot, telegram):
    bot.ricevi([])
    assert telegram.chiamate == []


def test_23_ore_non_sono_buio(bot, telegram, orologio):
    bot.ricevi([])
    dopo_il_buio(bot, orologio, ore=23)
    assert telegram.chiamate == []


def test_senza_sondaggio_solo_il_messaggio_del_buio(bot, telegram, orologio):
    orologio.adesso = datetime(2025, 10, 12, 19, 5, tzinfo=UTC)
    bot.ricevi([])
    orologio.adesso = datetime(2025, 10, 14, 7, 30, tzinfo=UTC)
    bot.ricevi([])
    assert telegram.scritti() == [
        "🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10 alle 9:30. "
        "I comandi e i voti di quel periodo potrebbero non essermi arrivati."
    ]


def sondaggio_con_tre_voti(bot, telegram, store):
    bot.ricevi([comando("/sondaggio mar gio")])
    vota(bot, telegram, ABE, "14/10")
    vota(bot, telegram, EMI, "14/10 16/10")
    vota(bot, telegram, SEM, "nessuna")
    return store.sondaggio_aperto()


def test_conteggi_uguali_riapre_e_tiene_i_voti(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.di_tipo("ferma_sondaggio")[-1]["messaggio"] == vecchio.messaggio
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", "gio 16/10", testi.FRASI_NESSUNA[1]]
    assert telegram.scritti() == [
        BUIO,
        UGUALI,
        "Riapro il sondaggio. Ho già i voti di abe, emi e sem: se non avete cambiato idea, "
        "non serve rivotare. Non hanno ancora votato: gio, sese, pippo.",
    ]
    # il buio e i conteggi prima del sondaggio nuovo, «Riapro» dopo
    nomi = [nome for nome, _ in telegram.chiamate if nome != "aggiornamenti"]
    assert nomi[-5:] == ["ferma_sondaggio", "scrivi", "scrivi", "manda_sondaggio", "scrivi"]
    riaperto = store.sondaggio_aperto()
    assert riaperto.id == vecchio.id
    assert riaperto.poll_id == telegram.ultimo_sondaggio["poll_id"] != vecchio.poll_id
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("14/10"), d("16/10")}))
    # nel sondaggio nuovo il voto nuovo sostituisce quello tenuto buono
    vota(bot, telegram, EMI, "16/10")
    assert store.voti(riaperto.id)[EMI.telegram_id] == Voto(frozenset({d("16/10")}))


def test_conteggi_diversi(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]  # qualcuno ha votato al buio
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[:2] == [BUIO, DIVERSI]


def test_i_conteggi_comprendono_chi_non_e_nel_roster(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    vota(bot, telegram, ESTRANEO, "16/10")
    telegram.conteggi[vecchio.messaggio] = [2, 2, 1]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti()[1] == UGUALI


def test_dopo_una_seconda_ripresa_contano_solo_i_voti_del_sondaggio_nuovo(
    bot, telegram, store, orologio
):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [2, 1, 1]
    dopo_il_buio(bot, orologio, ore=24)
    vota(bot, telegram, GIO, "16/10")  # l'unico voto dato nel sondaggio riaperto
    riaperto = store.sondaggio_aperto()
    telegram.conteggi[riaperto.messaggio] = [0, 1, 0]
    dopo_il_buio(bot, orologio, ore=24)
    assert telegram.scritti().count(UGUALI) == 2


def test_le_date_passate_non_si_riaprono(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 14/10")])
    dopo_il_buio(bot, orologio, ore=30)  # giovedì 9/10 alle 2:00
    assert telegram.ultimo_sondaggio["opzioni"] == ["mar 14/10", testi.FRASI_NESSUNA[1]]
    assert store.sondaggio_aperto().date == (d("14/10"),)
    # le opzioni sono quelle nuove: la prima ora è il 14/10
    vota(bot, telegram, ABE, "14/10")
    assert store.voti(store.sondaggio_aperto().id)[ABE.telegram_id] == Voto(frozenset({d("14/10")}))


def test_tutte_le_date_passate_chiude_e_basta(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio 8/10 9/10")])
    dopo_il_buio(bot, orologio, ore=80)
    assert store.sondaggio_aperto() is None
    assert len(telegram.di_tipo("manda_sondaggio")) == 1
    assert telegram.scritti()[1:] == [UGUALI, "Le date del sondaggio sono passate: lo chiudo."]


def test_il_sondaggio_cancellato_durante_il_buio(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.cancellati.add(vecchio.messaggio)
    dopo_il_buio(bot, orologio)
    assert store.sondaggio_aperto() is None
    assert telegram.scritti() == [BUIO, "Il messaggio del sondaggio non c'è più: lo considero chiuso."]
    assert len(telegram.di_tipo("manda_sondaggio")) == 1


def test_gli_annunci_fatti_restano_e_dopo_la_ripresa_non_si_sa_chi(bot, telegram, store, orologio):
    bot.ricevi([comando("/sondaggio mar gio")])
    for persona in (GIO, ABE, EMI, SEM, SESE):
        vota(bot, telegram, persona, "14/10")
    possibile = "✅ mar 14/10 va bene: ci sono gio, abe, emi, sem e sese."
    assert possibile in telegram.scritti()
    telegram.conteggi[store.sondaggio_aperto().messaggio] = [5, 0, 0]
    dopo_il_buio(bot, orologio)
    assert telegram.scritti().count(possibile) == 1
    vota(bot, telegram, SEM, "nessuna")
    # il «quasi» del 14/10 era già stato detto prima del «possibile»: non si ripete
    assert telegram.scritti()[-1] == (
        "⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro giocatori."
    )


def test_se_lo_stop_non_riesce_la_ripresa_si_ferma_al_messaggio(bot, telegram, store, orologio, caplog):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.guasti["ferma_sondaggio"] = telegram_guasto()
    with caplog.at_level(logging.ERROR):
        dopo_il_buio(bot, orologio)
    assert "ripresa dopo il buio non riuscita" in caplog.text
    assert store.sondaggio_aperto() == vecchio
    assert telegram.scritti() == [BUIO]
    # alla lettura seguente il buio è finito: niente ripresa doppia
    del telegram.guasti["ferma_sondaggio"]
    orologio.avanza(seconds=25)
    bot.ricevi([])
    assert telegram.scritti() == [BUIO]


def test_la_ripresa_arriva_dopo_gli_aggiornamenti_del_lotto(bot, telegram, store, orologio):
    vecchio = sondaggio_con_tre_voti(bot, telegram, store)
    telegram.conteggi[vecchio.messaggio] = [3, 1, 1]
    orologio.avanza(hours=30)
    voto_di_gio = {
        "update_id": 5000,
        "poll_answer": {"poll_id": vecchio.poll_id, "user": {"id": GIO.telegram_id}, "option_ids": [0]},
    }
    bot.ricevi([voto_di_gio])
    # il voto di gio, arrivato nel lotto, conta: i conteggi tornano
    assert telegram.scritti()[:2] == [BUIO, UGUALI]
    assert store.voti(vecchio.id)[GIO.telegram_id] == Voto(frozenset({d("14/10")}))
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_ripresa.py -q`
Expected: FAIL — il bot non registra le letture e non fa la ripresa: niente «🔌 Sono rimasto senza Telegram…». Due prove passano già (la prima lettura e 23 ore non sono buio): il riepilogo dice `11 failed, 2 passed`.

- [ ] **Step 3: la ripresa**

In `src/prossima/bot.py`, sostituisci:

```python
"""Il bot: smista gli aggiornamenti di Telegram e manda gli annunci.
```

con:

```python
"""Il bot: smista gli aggiornamenti di Telegram, manda gli annunci, fa la ripresa.
```

In `src/prossima/bot.py`, sostituisci:

```python
    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii."""
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        self.manda()

```

con:

```python
    def ricevi(self, aggiornamenti: list[dict]) -> None:
        """Un lotto letto da `getUpdates`. Ogni aggiornamento, poi il suo offset
        (dopo, non prima: un aggiornamento gestito due volte è innocuo), poi gli
        invii. Dopo più di 23 ore senza letture, la ripresa (§3.8)."""
        ora = self._adesso()
        precedente = self._store.ultima_lettura()
        for aggiornamento in aggiornamenti:
            try:
                self.gestisci(aggiornamento)
            except Exception:
                log.exception("aggiornamento %s non gestito", aggiornamento.get("update_id"))
            self._store.salva_offset(int(aggiornamento["update_id"]) + 1)
            self.manda()
        self._store.segna_lettura(ora)
        if regole.al_buio(precedente, ora):
            try:
                self.riprendi(precedente, ora)
            except Exception:
                log.exception("ripresa dopo il buio non riuscita")
        self.manda()

```

In `src/prossima/bot.py`, sostituisci:

```python
    # --- i pezzi
```

con:

```python
    # --- la ripresa dopo il buio (§3.8)

    def riprendi(self, dal: datetime, al: datetime) -> None:
        self._accoda(testi.buio(dal, al, self._fuso))
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None:
            return
        conteggi = self._ferma(sondaggio)
        if conteggi is None:
            return  # il messaggio non c'è più: chiuso, e detto
        nostri = regole.conteggi_per_opzione(
            sondaggio.date, self._store.voti_del_poll(sondaggio.id, sondaggio.poll_id)
        )
        self._accoda(testi.conteggi(conteggi == nostri))
        future = [g for g in sondaggio.date if g >= self._oggi()]
        if not future:
            self._accoda(testi.date_passate())
            return
        mandato, frase = self._nuovo_sondaggio(future)
        riaperto = self._store.riapri_sondaggio(
            sondaggio.id, future, mandato.poll_id, mandato.messaggio, frase
        )
        fatti = regole.dopo(self._store.fatti(riaperto.id), regole.Ripresa())
        self._store.salva_fatti(riaperto.id, fatti)
        stato = self._stato(riaperto)
        self._accoda(testi.riapro(stato.votanti, stato.senza_voto))

    # --- i pezzi
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_ripresa.py -q`
Expected: PASS — `13 passed`.

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `206 passed` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

- [ ] **Step 5: commit**

```bash
git add src/prossima/bot.py tests/test_ripresa.py
git commit -m "bot: resume after more than 23 hours without Telegram

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

### Task 10: l'avvio, il ciclo, il battito, il container, il piano reale, la guida

Il punto d'ingresso (`prossima`, e `prossima salute` per il controllo di salute), il ciclo che non muore per un errore e tocca il battito a ogni giro, il container, il piano reale e le due guide. Le prove veloci coprono il ciclo, il battito, l'avvio con il finto (nome del bot e comandi registrati) e il livello del logger `httpx`; il piano reale si lancia sul server (guida, punto 6).

**Files:**
- Create: `src/prossima/principale.py`
- Test: `tests/test_principale.py`
- Create: `tests/reale/__init__.py`, `tests/reale/ambiente.py`, `tests/reale/test_telegram_vero.py`, `tests/reale/test_configurazione.py`
- Create: `Dockerfile`, `.dockerignore`, `compose.yaml`, `config.esempio/prossima.env`
- Create: `docs/messa-in-produzione.md`, `README.md`

**Interfaces:**
- Consumes: `config.da_ambiente`, `ConfigurazioneErrata`; `Store`; `BotTelegram`, `TelegramError`, `MessaggioSparito`; `Bot`, `COMANDI`; `regole`, `testi` (nel piano reale); `tests.finti.TelegramFinto`; la fixture `store`.
- Produces (`prossima.principale`): `ATTESA = 25`, `BATTITO_MASSIMO = 120`; `configura_log() -> None`; `ciclo(telegram, bot: Bot, store: Store, battito: Path, fermo: threading.Event, *, attesa: int = 25, pausa_errore: float = 5.0) -> None`; `in_salute(battito: Path, adesso: float | None = None) -> bool`; `avvia(env: Mapping[str, str], *, telegram=None, fermo: threading.Event | None = None) -> None`; `main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int` (0, 1 se Telegram non risponde all'avvio o il battito è vecchio, 2 per una configurazione sbagliata o un argomento sconosciuto). Lo script `prossima` è in `pyproject.toml` dal task 1.

- [ ] **Step 1: le prove dell'avvio e del ciclo**

Crea `tests/test_principale.py`:

```python
import logging
import os
import threading
import time
from pathlib import Path

from prossima import principale
from prossima.telegram import TelegramError
from tests.finti import TelegramFinto

RADICE = Path(__file__).resolve().parents[1]


class TelegramACicli(TelegramFinto):
    """Dà un lotto di aggiornamenti per chiamata; finiti i lotti, ferma il ciclo."""

    def __init__(self, fermo, lotti):
        super().__init__()
        self._fermo = fermo
        self._lotti = list(lotti)

    def aggiornamenti(self, offset, attesa):
        self.chiamate.append(("aggiornamenti", {"offset": offset, "attesa": attesa}))
        if not self._lotti:
            self._fermo.set()
            return []
        lotto = self._lotti.pop(0)
        if isinstance(lotto, Exception):
            raise lotto
        return lotto


class BotFinto:
    def __init__(self, store, esplodi=False):
        self.lotti = []
        self._store = store
        self._esplodi = esplodi

    def ricevi(self, aggiornamenti):
        self.lotti.append([a["update_id"] for a in aggiornamenti])
        if self._esplodi:
            self._esplodi = False
            raise RuntimeError("boom")
        if aggiornamenti:
            self._store.salva_offset(aggiornamenti[-1]["update_id"] + 1)


def offset_chiesti(telegram):
    return [a["offset"] for nome, a in telegram.chiamate if nome == "aggiornamenti"]


def test_il_ciclo_passa_i_lotti_al_bot_con_l_offset_salvato(store, tmp_path):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [[{"update_id": 5}, {"update_id": 6}], [{"update_id": 7}]])
    bot = BotFinto(store)
    principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=0)
    assert bot.lotti == [[5, 6], [7], []]
    assert offset_chiesti(telegram) == [None, 7, 8]
    assert (tmp_path / "battito").exists()


def test_un_errore_di_telegram_o_del_bot_non_ferma_il_ciclo(store, tmp_path, caplog):
    fermo = threading.Event()
    telegram = TelegramACicli(fermo, [TelegramError("getUpdates: errore di rete"), [{"update_id": 1}], [{"update_id": 2}]])
    bot = BotFinto(store, esplodi=True)
    with caplog.at_level(logging.WARNING):
        principale.ciclo(telegram, bot, store, tmp_path / "battito", fermo, attesa=0, pausa_errore=0)
    assert bot.lotti == [[1], [2], []]
    assert "lettura del bot non riuscita: getUpdates: errore di rete" in caplog.text
    assert "errore inatteso" in caplog.text


def test_il_battito(tmp_path):
    battito = tmp_path / "battito"
    assert not principale.in_salute(battito)
    battito.touch()
    assert principale.in_salute(battito)
    vecchio = time.time() - 121
    os.utime(battito, (vecchio, vecchio))
    assert not principale.in_salute(battito)


def test_prossima_salute(tmp_path):
    battito = tmp_path / "battito"
    assert principale.main(["salute"], {"PV_BATTITO": str(battito)}) == 1
    battito.touch()
    assert principale.main(["salute"], {"PV_BATTITO": str(battito)}) == 0
    assert principale.main(["salute"], {}) == 1


def test_i_log_di_httpx_non_scrivono_gli_url_col_token():
    principale.configura_log()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def ambiente(tmp_path):
    return {
        "PV_BOT_TOKEN": "123:SEGRETO",
        "PV_GRUPPO": "-1000000000001",
        "PV_ROSTER": str(RADICE / "config.esempio" / "roster.toml"),
        "PV_DB": str(tmp_path / "prossima.sqlite"),
        "PV_BATTITO": str(tmp_path / "battito"),
    }


def test_all_avvio_chiede_il_nome_e_registra_i_comandi(tmp_path):
    telegram = TelegramFinto("ProssimaVoltaBot")
    fermo = threading.Event()
    fermo.set()
    principale.avvia(ambiente(tmp_path), telegram=telegram, fermo=fermo)
    assert telegram.di_tipo("io") == [{}]
    assert telegram.di_tipo("registra_comandi") == [
        {"comandi": [("sondaggio", "Sondaggio per la prossima volta"), ("chiudi", "Chiude il sondaggio")]}
    ]
    assert (tmp_path / "prossima.sqlite").exists()


def test_una_configurazione_sbagliata_ferma_l_avvio(tmp_path, caplog):
    env = {**ambiente(tmp_path), "PV_GRUPPO": "party"}
    with caplog.at_level(logging.ERROR):
        assert principale.main([], env) == 2
    assert "PV_GRUPPO non è un numero intero" in caplog.text
    assert "SEGRETO" not in caplog.text


def test_un_argomento_sconosciuto(caplog):
    with caplog.at_level(logging.ERROR):
        assert principale.main(["boh"], {}) == 2
    assert "uso: prossima [salute]" in caplog.text
```

- [ ] **Step 2: lancia le prove e verifica che falliscano**

Run: `uv run pytest tests/test_principale.py -q`
Expected: FAIL — errore di import: `principale` non esiste ancora.

- [ ] **Step 3: l'avvio e il ciclo**

Crea `src/prossima/principale.py`:

```python
"""Il punto d'ingresso: `prossima` avvia il bot, `prossima salute` controlla il
battito (il controllo di salute del container).

Il logger `httpx` sta a WARNING: al livello INFO scriverebbe l'URL di ogni
chiamata a Telegram, e l'URL contiene il token.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from . import config
from .bot import COMANDI, Bot
from .store import Store
from .telegram import BotTelegram, TelegramError

log = logging.getLogger(__name__)

ATTESA = 25  # secondi di long polling
BATTITO_MASSIMO = 120  # secondi: oltre, il container è malato


def configura_log() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def ciclo(
    telegram,
    bot: Bot,
    store: Store,
    battito: Path,
    fermo: threading.Event,
    *,
    attesa: int = ATTESA,
    pausa_errore: float = 5.0,
) -> None:
    """Legge il bot in long polling finché `fermo` non è impostato, e tocca il
    battito a ogni giro. Non si ferma per un errore: lo registra e riprova."""
    while not fermo.is_set():
        try:
            bot.ricevi(telegram.aggiornamenti(store.offset(), attesa))
        except TelegramError as e:
            log.warning("lettura del bot non riuscita: %s", e)
            fermo.wait(pausa_errore)
        except Exception:
            log.exception("ciclo del bot: errore inatteso, riprovo")
            fermo.wait(pausa_errore)
        _batti(battito)


def _batti(battito: Path) -> None:
    try:
        battito.touch()
    except OSError:
        log.exception("battito non scritto: %s", battito)


def in_salute(battito: Path, adesso: float | None = None) -> bool:
    """Il battito ha meno di due minuti."""
    try:
        eta = (time.time() if adesso is None else adesso) - battito.stat().st_mtime
    except OSError:
        return False
    return eta < BATTITO_MASSIMO


def avvia(env: Mapping[str, str], *, telegram=None, fermo: threading.Event | None = None) -> None:
    """Costruisce il bot vero e gira finché `fermo` non è impostato (in esercizio,
    mai: il container lo ferma con un segnale)."""
    imp = config.da_ambiente(env)
    store = Store(imp.db)
    store.crea_schema()
    telegram = telegram or BotTelegram(imp.token_bot)
    nome = telegram.io()
    telegram.registra_comandi(COMANDI)
    bot = Bot(
        telegram=telegram,
        store=store,
        roster=imp.roster,
        gruppo=imp.gruppo,
        nome=nome,
        fuso=imp.fuso,
        adesso=lambda: datetime.now(UTC),
    )
    log.info(
        "Prossima volta: @%s nel gruppo %s, %d persone nel roster",
        nome,
        imp.gruppo,
        len(imp.roster.persone),
    )
    ciclo(telegram, bot, store, imp.battito, fermo or threading.Event())


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    env = os.environ if env is None else env
    configura_log()
    if argv == ["salute"]:
        battito = (env.get("PV_BATTITO") or "").strip()
        return 0 if battito and in_salute(Path(battito)) else 1
    if argv:
        log.error("uso: prossima [salute]")
        return 2
    try:
        avvia(env)
    except config.ConfigurazioneErrata as e:
        log.error("configurazione: %s", e)
        return 2
    except TelegramError as e:
        log.error("Telegram non risponde all'avvio: %s", e)
        return 1
    return 0
```

- [ ] **Step 4: lancia le prove e verifica che passino**

Run: `uv run pytest tests/test_principale.py -q`
Expected: PASS — `8 passed`.

- [ ] **Step 5: il piano reale**

```bash
mkdir -p tests/reale
touch tests/reale/__init__.py
```

Crea `tests/reale/ambiente.py`:

```python
"""Le variabili del piano reale.

Una variabile mancante fa saltare il test, e il messaggio dice quale contratto
resta non verificato. Un salto non è un successo: il piano reale è verde solo
quando non salta niente (`pytest -rs` elenca i salti con il loro motivo).
"""

import os

import pytest


def richiesta(nome: str) -> str:
    valore = os.environ.get(nome, "").strip()
    if not valore:
        pytest.skip(f"{nome} non impostata: questo contratto NON è stato verificato")
    return valore
```

Crea `tests/reale/test_telegram_vero.py`:

```python
"""Il bot vero, nella chat privata di Alberto (`PV_REALE_CHAT`).

Si lancia **a servizio fermo** (`docker compose stop prossima`): due lettori
dello stesso bot si rubano gli aggiornamenti. Questi test leggono `getUpdates`
senza offset, quindi non confermano niente a Telegram: alla ripartenza il
servizio ritrova quello che è arrivato nel frattempo, e ignora i voti di prova
(sono di sondaggi che non conosce).

Un test chiede ad Alberto di votare: la domanda del sondaggio dice cosa fare,
e il test aspetta fino a tre minuti.
"""

import time
from datetime import date, timedelta

import pytest

from prossima import regole, testi
from prossima.bot import COMANDI
from prossima.regole import Persona
from prossima.telegram import BotTelegram, MessaggioSparito
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale

ATTESA_VOTI = 180  # secondi


def bot() -> BotTelegram:
    return BotTelegram(richiesta("PV_BOT_TOKEN"))


def chat() -> int:
    return int(richiesta("PV_REALE_CHAT"))


def risposte(b: BotTelegram, poll_id: str, quante: int) -> list[dict]:
    """Le prime `quante` risposte al sondaggio `poll_id`, lette senza offset."""
    trovate: list[dict] = []
    fine = time.monotonic() + ATTESA_VOTI
    while time.monotonic() < fine:
        trovate = [
            a["poll_answer"]
            for a in b.aggiornamenti(None, 5)
            if a.get("poll_answer", {}).get("poll_id") == poll_id
        ]
        if len(trovate) >= quante:
            return trovate[:quante]
        time.sleep(1)
    pytest.fail(f"in {ATTESA_VOTI} secondi sono arrivate {len(trovate)} risposte su {quante}")


def test_il_nome_del_bot():
    assert bot().io().lower().endswith("bot")


def test_i_comandi_del_menu():
    b = bot()
    b.registra_comandi(COMANDI)
    # getMyCommands al bot non serve: lo si chiama qui solo per rileggere.
    letti = b._chiama("getMyCommands")
    assert [(c["command"], c["description"]) for c in letti] == list(COMANDI)


def test_una_menzione_dopo_un_emoji_cade_sul_nome():
    """Contratto: Telegram conta gli scostamenti delle entità in UTF-16, come
    `testi.py`, e accetta una `text_mention` con il solo identificativo."""
    alberto = Persona("abe", chat(), "giocatore")
    altri = tuple(Persona(n, 100000001 + i, "giocatore") for i, n in enumerate(("gio", "emi", "sem", "sese")))
    t = testi.quasi(regole.Quasi(date.today() + timedelta(days=7), altri, (alberto,)))
    messaggio = bot().scrivi(chat(), t.testo, t.entita)
    [entita] = messaggio["entities"]
    assert entita["type"] == "text_mention"
    assert (entita["offset"], entita["length"]) == (t.entita[0]["offset"], 3)
    assert entita["user"]["id"] == chat()


def test_sondaggio_voto_ritiro_e_conteggi():
    """Contratti: un sondaggio non anonimo a risposta multipla con 11 opzioni
    (10 date e la frase più lunga) parte; ogni voto arriva come `poll_answer`
    con l'identificativo di chi vota e le opzioni da 0; il voto ritirato arriva
    con le opzioni vuote; `stopPoll` dà i conteggi per opzione, in ordine."""
    b = bot()
    date_ = [date.today() + timedelta(days=i) for i in range(1, regole.MASSIMO_DATE + 1)]
    frase = max(testi.FRASI_NESSUNA, key=len)
    mandato = b.manda_sondaggio(
        chat(),
        "🧪 Prova di Prossima volta: spunta la prima e la terza data e vota; "
        "poi ritira il voto; poi spunta la seconda e vota.",
        testi.opzioni(date_, frase),
    )
    primo, ritiro, secondo = risposte(b, mandato.poll_id, 3)
    assert primo["user"]["id"] == chat()
    assert primo["option_ids"] == [0, 2]
    assert ritiro["option_ids"] == []
    assert secondo["option_ids"] == [1]
    assert b.ferma_sondaggio(chat(), mandato.messaggio) == [0, 1] + [0] * 9


def test_fermare_un_sondaggio_cancellato():
    """Contratto: per un messaggio cancellato `stopPoll` risponde con una
    descrizione che `MessaggioSparito` riconosce."""
    b = bot()
    mandato = b.manda_sondaggio(chat(), "🧪 Prova di Prossima volta: sparisco da solo.", ["sì", "no"])
    # deleteMessage al bot non serve: qui fa la parte di chi cancella il sondaggio.
    b._chiama("deleteMessage", {"chat_id": chat(), "message_id": mandato.messaggio})
    with pytest.raises(MessaggioSparito):
        b.ferma_sondaggio(chat(), mandato.messaggio)
```

Crea `tests/reale/test_configurazione.py`:

```python
"""L'immagine e la configurazione vere. Nel container (`docker compose
--profile prova run --rm prova`) l'ambiente è quello di `config/prossima.env`."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from prossima import config
from tests.reale.ambiente import richiesta

pytestmark = pytest.mark.reale


def test_il_fuso_di_zurigo_c_e_anche_nell_immagine_slim():
    zurigo = ZoneInfo("Europe/Zurich")
    assert datetime(2025, 7, 1, 12, tzinfo=zurigo).utcoffset() == timedelta(hours=2)
    assert datetime(2025, 12, 1, 12, tzinfo=zurigo).utcoffset() == timedelta(hours=1)


def test_la_configurazione_vera_e_il_roster_vero_si_leggono():
    richiesta("PV_ROSTER")
    imp = config.da_ambiente(os.environ)
    assert imp.gruppo < 0, "PV_GRUPPO deve essere il gruppo del party: un numero negativo"
```

Run: `uv run pytest -m reale -rs -q`
Expected: PASS — `1 passed, 6 skipped`: il fuso c'è; ogni salto dice quale variabile manca («PV_BOT_TOKEN non impostata: questo contratto NON è stato verificato», e così per `PV_REALE_CHAT` e `PV_ROSTER`). Il piano reale vero si lancia sul server, a servizio fermo (guida, punto 6).

- [ ] **Step 6: il container e la configurazione d'esempio**

Crea `Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

FROM base AS servizio
# Il battito: il ciclo tocca il file a ogni giro (long polling di 25 secondi).
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s CMD ["prossima", "salute"]
CMD ["prossima"]

FROM base AS prova
COPY tests ./tests
RUN uv sync --frozen
CMD ["pytest", "-m", "reale", "-rs", "tests/reale"]
```

Crea `.dockerignore`:

```text
.git
.venv
__pycache__
.pytest_cache
.ruff_cache
.superpowers
dati
config
docs
```

Crea `compose.yaml`:

```yaml
services:
  prossima:
    build:
      context: .
      target: servizio
    restart: unless-stopped
    env_file: ./config/prossima.env
    volumes:
      - ./dati:/data
      - ./config:/config:ro
    # Nessuna porta: il bot chiama Telegram, nessuno chiama il bot.

  prova:
    profiles: ["prova"]
    build:
      context: .
      target: prova
    env_file: ./config/prossima.env
    volumes:
      - ./dati:/data
      - ./config:/config:ro
```

Crea `config.esempio/prossima.env`:

```bash
# Copia in config/prossima.env sul server, poi: chmod 600 config/prossima.env
# Contiene il token del bot: non va mai nel repository.

# Il bot di Prossima volta (nuovo, separato da quelli dei selfie e di ctc), da @BotFather.
PV_BOT_TOKEN=

# L'identificativo del gruppo del party: un numero negativo
# (v. docs/messa-in-produzione.md, punto 3).
PV_GRUPPO=

PV_ROSTER=/config/roster.toml
PV_DB=/data/prossima.sqlite
PV_BATTITO=/data/battito
PV_FUSO=Europe/Zurich

# Per il piano reale, a servizio fermo (v. docs/messa-in-produzione.md, punto 6):
# PV_REALE_CHAT=      il tuo identificativo Telegram: il piano reale ti scrive in privato
```

- [ ] **Step 7: la guida e il README**

Crea `docs/messa-in-produzione.md`:

````markdown
# Messa in produzione

Sulla stessa macchina dei selfie, in un container suo: niente porte, niente
proxy, niente certificati. Il bot chiama Telegram, nessuno chiama il bot. Una
volta sola, in quest'ordine. I comandi che leggono il token lo prendono dal
file, senza mai scriverlo nella riga di comando.

## 1. Il bot

1. Su Telegram, da **@BotFather**: `/newbot`, nome «Prossima volta». Il token
   va in `config/prossima.env` (punto 3), da nessun'altra parte.
2. **Non** toccare la privacy (`/setprivacy`): attiva, com'è per default, il bot
   riceve solo i comandi rivolti a lui e i voti dei suoi sondaggi.
3. Aggiungi il bot al gruppo del party.
4. Scrivi `/start` al bot **in privato**: senza, il bot non può scriverti, e il
   piano reale (punto 6) non funziona.

## 2. Il codice

Porta il repository sul server (un `git clone`, o una copia della cartella senza
`.venv`, `dati` e `config`), entra nella cartella e:

```bash
mkdir -p config dati
```

## 3. La configurazione

```bash
cp config.esempio/prossima.env config/prossima.env
cp config.esempio/roster.toml config/roster.toml
chmod 600 config/prossima.env config/roster.toml
```

In `config/prossima.env` metti il token. In `config/roster.toml` metti gli
identificativi Telegram veri delle sei persone (i numeri: li ha già il roster di
`ctc`, sul Mac in `~/.config/close-the-circle/roster.toml`, chiave
`telegram_id`).

L'identificativo del gruppo è nello stesso roster di `ctc`, chiave `party` in
`[gruppi]`. Se preferisci leggerlo da Telegram: scrivi nel gruppo
`/start@<nome_del_bot>` (il nome utente del bot, quello che finisce in `bot`) e,
sul server, prima di avviare il servizio (acceso, si prenderebbe lui gli
aggiornamenti):

```bash
TOKEN=$(grep -oP '^PV_BOT_TOKEN=\K.*' config/prossima.env)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*' | sort -u
unset TOKEN
```

Il numero negativo è il gruppo e va in `PV_GRUPPO`; quello positivo sei tu, in
privato, e servirà per il piano reale (`PV_REALE_CHAT`).

## 4. Avvio

```bash
docker compose up -d --build
docker compose logs prossima
```

Nel log, entro qualche secondo: «Prossima volta: @<nome_del_bot> nel gruppo
<PV_GRUPPO>, 6 persone nel roster». Un roster sbagliato ferma l'avvio con una
riga «configurazione: …» che dice cosa correggere.

Dopo un paio di minuti `docker compose ps` mostra il servizio `healthy`: il
controllo di salute guarda il battito, un file che il ciclo del bot tocca a ogni
giro (`/data/battito`, deve avere meno di 2 minuti).

## 5. A mano, nel gruppo

- Dal menu dei comandi (il tasto `/` accanto al campo di testo) scegli
  `/sondaggio`: il menu scrive `/sondaggio@<nome_del_bot>`, e il sondaggio della
  settimana seguente compare nel gruppo.
- Quando arriva il primo annuncio con dei nomi («Non hanno ancora votato: …»),
  chiedi alle persone nominate se hanno ricevuto la notifica.
- Chiudi il sondaggio di prova con `/chiudi`.

## 6. Il piano reale

Si lancia **a servizio fermo**: due lettori dello stesso bot si rubano gli
aggiornamenti. Il piano reale legge `getUpdates` senza offset e non conferma
niente, quindi alla ripartenza il servizio ritrova tutto quello che è arrivato
nel frattempo.

Metti il tuo identificativo in `PV_REALE_CHAT` dentro `config/prossima.env`
(punto 3), poi:

```bash
docker compose stop prossima
docker compose --profile prova run --rm prova
docker compose start prossima
```

Un test manda nella chat privata un sondaggio di prova e aspetta fino a tre
minuti: fai quello che dice la domanda (spunta la prima e la terza data e vota,
ritira il voto, spunta la seconda e vota). Il piano reale è verde solo se **non
salta niente**: un test saltato non è un test superato, e `-rs` dice quale
variabile mancava.

## Aggiornare

```bash
git pull && docker compose up -d --build
```
````

Crea `README.md`:

````markdown
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
````

- [ ] **Step 8: l'ultimo giro**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: PASS — `214 passed, 7 deselected` e `All checks passed!`. Se ruff segnala solo l'ordine degli import (I001), `uv run ruff check --fix src tests` lo sistema.

Run: `uv run prossima salute`
Expected: FAIL — esce con 1: `PV_BATTITO` non è impostata.

Run: `uv run prossima`
Expected: FAIL — esce con 2 e scrive «configurazione: PV_BOT_TOKEN manca» (o la prima variabile che manca nell'ambiente).

- [ ] **Step 9: commit**

```bash
git add src/prossima/principale.py tests/test_principale.py tests/reale Dockerfile .dockerignore compose.yaml config.esempio/prossima.env docs/messa-in-produzione.md README.md
git commit -m "entry point, heartbeat, container, real test plan, docs

Co-Authored-By: <il modello che fa il commit> <noreply@anthropic.com>"
```

---

## Dopo l'ultimo task

- La suite intera e ruff, come nell'ultimo giro del task 10.
- Il piano reale, l'immagine Docker e i controlli a mano nel gruppo li fa Alberto, sul server, seguendo `docs/messa-in-produzione.md`: il piano reale è verde solo se non salta niente.
- Il ramo `prima-versione` non si fonde senza l'assenso di Alberto.

---

## Deviazioni durante l'esecuzione

### Giro di correzioni A: gli errori di Telegram nel bot (dopo le revisioni dei task 7 e 8)

Decisioni prese su delega di Alberto, poi corrette dopo la revisione del giro A; la spec è aggiornata (§3.1, §3.6, §3.7, §4). Qui lo stato finale.

- **`sendPoll` non confermato da `/sondaggio`** (rete, 5xx, 4xx, la pausa di un 429): non più un ERROR con traceback e il silenzio nel gruppo, ma un avviso nel log (un ERROR per un rifiuto) e la risposta «Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:» seguita, sull'ultima riga, dal comando da copiare con gli argomenti originali (`testi.sondaggio_non_confermato`). Lo store ricorda il momento del tentativo (`segna_non_confermato`, `ultimo_non_confermato`) solo se il sondaggio può essere partito: non durante la pausa (`bot.TelegramInPausa`, sollevata da `_invia` prima della chiamata), non dopo un 4xx o un 429.
- **Voti per un sondaggio sconosciuto** (cambia la scelta 11): non più ignorati in silenzio. Sempre un WARNING con il `poll_id`; nel gruppo, una volta per sondaggio e solo con un tentativo non confermato negli ultimi 7 giorni: senza sondaggio aperto «… Rilanciate /sondaggio@<bot> e votate lì.», con un sondaggio aperto (e non in chiusura) in risposta al suo messaggio «… Il sondaggio che conto è questo: votate qui.». Anche il sondaggio nuovo non confermato di `/chiudi rimanda` conta come tentativo. Un voto per un sondaggio conosciuto ma chiuso si ignora ancora.
- **`stopPoll` su un sondaggio già chiuso**: `telegram.SondaggioGiaChiuso` («poll has already been closed», da confermare con la nuova prova reale `test_fermare_due_volte`). `Bot._ferma` restituisce `Fermato(conteggi, sparito)` e non chiude più il sondaggio nel database: lo fa chi chiama, insieme alla lettera. Il finto ricorda i sondaggi fermati, controlla i guasti prima di tutto, e ha le risposte perse (`risposte_perse`; un lotto di `getUpdates` perso si riconsegna); `telegram_guasto(metodo)` porta il nome del metodo dell'API.
- **`stopPoll` non confermato: la chiusura in sospeso** (sostituisce il silenzio del piano; dopo la revisione sostituisce anche l'invito a riscrivere `/chiudi`): `Store.sospendi_chiusura` ricorda `ChiusuraSospesa(sondaggio, comando, argomento)` in `valori` con la risposta «Telegram non ha confermato la chiusura del sondaggio: riprovo da solo.»; `manda()` ritenta lo stop a ogni giro, fuori dalla pausa (`_riprova_chiusura`), e quando Telegram risponde chiude come il comando (`_completa`). Chiudere il sondaggio toglie la chiave nella stessa transazione. Nel frattempo `/sondaggio` risponde «Il sondaggio di prima non è ancora chiuso: …» e un altro `/chiudi` sostituisce l'argomento senza un altro stop. Un rifiuto dello stop: ERROR una volta per processo, e si ritenta.
- **`/chiudi rimanda`** (cambia la scelta 2): stop, poi `sendPoll`, poi `Store.rimanda`, che chiude il vecchio (e solleva se non era aperto), apre il nuovo e accoda «🔁» in una transazione. Se il sondaggio nuovo non parte, il vecchio si chiude con «🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: se non lo vedete, lanciatelo con:» e il comando con le date sull'ultima riga, nella stessa transazione del tentativo (`chiudi_sondaggio(..., non_confermato=...)`). Le date passate si tolgono; se non ne resta nessuna, «Le date del sondaggio sono passate: lo chiudo.» e niente sondaggio nuovo (scelta di chi ha eseguito il giro: il caso non era deciso). Il lunedì di «🔁» viene dalle date nuove (`regole.lunedi`).
- **La lettera di una chiusura** («🔒», «🎲», «non c'è più») si accoda nella transazione della chiusura (`chiudi_sondaggio(..., lettere=...)`, `store.LetteraNuova`). Con `rimanda`, «non c'è più» parte da sola, prima del sondaggio nuovo (un'interruzione prima del salvataggio la fa ripetere).
- **Rifiuti di `/chiudi`** (cambia la scelta 4): «Non capisco «…»: scrivi una data del sondaggio (14/10), il suo giorno (mar) o rimanda.»; `regole.GiornoAmbiguo` («Nel sondaggio c'è più di un martedì: scrivi la data (14/10).») e `regole.GiornoAssente` («Nel sondaggio non c'è nessun venerdì.») al posto di «Non capisco «mar»…» e di «La data ven non era nel sondaggio.». I testi stanno in `testi.rifiuto_di_chiudi`; `testi.rifiuto` resta per `/sondaggio`.
- **Minori del task 7**: la pausa del 429 si conta dalla risposta; durante la pausa `manda()` non prova (un solo avviso nel log); un annuncio rifiutato (4xx) non ferma i seguenti, va nel log una volta e si salta fino al prossimo avvio (cambia la scelta 8 per gli annunci); il giro nuovo di frasi non comincia con l'ultima usata, e comincia solo se il sondaggio parte (`Store.usa_frase(frase, nuovo_giro)`, `Store.ultima_frase`; `dimentica_frasi` non c'è più); le opzioni sono sempre in ordine di data.
- **Prove**: le fixture `riavvia` (il bot ripartito) e `uccidi` (il processo fermato a metà; `uccidi.basta()` rimette solo i metodi uccisi) in `tests/conftest.py`. `docs/differenze-fra-test-e-realta.md` dice anche dei messaggi che, con la risposta persa o il processo fermato dopo l'invio, arrivano due volte. Alla fine del giro: 298 prove veloci, 8 del piano reale.
- **Da fare nel giro B** (la ripresa):
  - `riprendi` usa il nuovo `_ferma` e, con un sondaggio già chiuso, per ora riapre senza la frase sui conteggi. Da fare: «già chiuso» con una chiusura in sospeso → si completa la chiusura del comando, non si riapre; «già chiuso» senza la chiave `ripresa` in fase «fermare» salvata prima dello stop e senza chiusura in sospeso → si chiude e lo si dice, non si riapre.
  - Oggi la ripresa chiude il sondaggio e così toglie anche la sua chiusura in sospeso (`store._chiudi`), poi lo riapre: la decisione di chi l'aveva chiuso si perde. È il caso del punto sopra.
  - Quando la ripresa ricorderà i `poll_id` di prima, `Store.poll_conosciuto` dovrà conoscerli (oggi li trova solo nei voti).

### Giro di correzioni B: la ripresa che riprende (dopo la revisione del task 9)

Decisioni prese su delega di Alberto, che per la ripresa ha chiesto che il bot «deve fare il possibile per recuperare»; la spec è aggiornata (§3.1, §3.7, §3.8, §4). I tre punti «Da fare nel giro B» qui sopra sono fatti.

- **Residui del giro A.** Un completamento della chiusura in sospeso che fallisce per un errore che non viene da Telegram va nel log con il traceback e non si ritenta fino al prossimo avvio (`Bot._chiusure_guaste`, per comando): con `rimanda` partiva un sondaggio nuovo a ogni giro. La chiave resta, e un `/chiudi` nuovo la ritenta. `/sondaggio` con una chiusura in sospeso risponde «Telegram non ha ancora confermato la chiusura del sondaggio di prima: riprovate fra poco.». L'avviso dei voti sconosciuti senza sondaggio aperto finisce con il comando da copiare, sull'ultima riga, con gli argomenti del tentativo: `segna_non_confermato(alle, argomenti, lettere)`, `ultimo_non_confermato() -> NonConfermato(alle, argomenti)`, `chiudi_sondaggio(..., non_confermato=argomenti)`.
- **La ripresa riprendibile** (aggiorna la scelta 2). `Bot.riprendi` non c'è più: `ricevi` chiama `_inizia_ripresa` dopo il buio, e `_continua_ripresa` a ogni lettura. Lo store tiene la chiave `ripresa` in `valori` (`RipresaInCorso(sondaggio, fase, stop_provato)`, fasi `FERMARE` e `RIAPRIRE`), con un'operazione per passo, in una transazione ciascuna: `inizia_ripresa` (la lettura, il messaggio del buio, la chiave; una ripresa dello stesso sondaggio già in corso resta com'è), `prova_stop_di_ripresa` (prima del primo stop), `fermato_per_riprendere` (la chiusura, la frase sui conteggi, la fase «riaprire»), `riapri_sondaggio` (la riga, i fatti dopo `Ripresa`, «Riapro…», via la chiave) e `fine_ripresa` (il messaggio sparito, il sondaggio già chiuso da chi non si sa, le date passate, un sondaggio aperto nel frattempo, un errore). Un errore di Telegram lascia la chiave, e durante la pausa di un 429 la ripresa non prova; un altro errore la toglie, con il traceback.
- **Già chiuso nella ripresa.** Con una chiusura in sospeso la ripresa finisce subito e lascia lo stop a `manda`, che completa il comando: vale qualunque cosa risponda Telegram, anche i conteggi (scelta di chi ha eseguito il giro: il brief decideva solo il «già chiuso», ma riaprire un sondaggio che chi può chiudere ha chiuso perderebbe la sua decisione). Senza: se uno stop della ripresa è già partito (`stop_provato`), «Il sondaggio risultava già chiuso: non posso confrontare i conteggi.» e si riapre; altrimenti «Il sondaggio risultava già chiuso.», chiuso e non riaperto. `stop_provato` è il modo, scelto da chi ha eseguito il giro, di sapere che la chiave in fase «fermare» era stata salvata prima di uno stop già partito.
- **Conteggi diversi**: «I conteggi del sondaggio sono diversi dai miei: qualcuno ha votato o cambiato voto senza che lo sapessi.».
- **Minori del task 9.** Un sondaggio nato nel lotto del buio (`aperto_alle` non prima della lettura) non si ferma e non si rifà. Un voto al sondaggio di Telegram di prima della ripresa, arrivato dopo la riapertura, vale se la persona non ha votato nel sondaggio di adesso, con le opzioni di prima (cambia di nuovo la scelta 11): `Sondaggio.poll_prima` e `date_prima`, `Store.registra_voto_tardivo`; `poll_conosciuto` conosce anche `poll_prima`. `rimanda` usa i giorni della settimana delle date con cui il sondaggio è nato (`Sondaggio.date_iniziali`). Docstring di `ricevi`, `_inizia_ripresa` e `_continua_ripresa`; `oggi` calcolato una volta. Un `/chiudi` nel lotto del buio chiude con i voti che il bot ha visto: scritto in `docs/differenze-fra-test-e-realta.md`, non corretto.
- **Dal giro A.** Con una chiusura in sospeso niente annunci per quel sondaggio. Lo stop ritentato con la rete giù va nel log la prima volta e poi al massimo ogni 10 minuti per la stessa chiusura (`Bot._da_avvisare`, `AVVISO_RIPETUTO`); con la stessa regola gli errori di Telegram della ripresa (scelta di chi ha eseguito il giro: la ripresa si ritenta a ogni lettura). Uno stop rifiutato resta ritentato a ogni giro, con un ERROR una volta per processo.
- **Database**: tre colonne nuove in `sondaggi` (`date_iniziali`, `poll_prima`, `date_prima`), scritte nel `CREATE TABLE`: nessun database è ancora in esercizio, quindi nessuna migrazione.
- **Prove**: una per ogni passo della ripresa con il processo ucciso, e per lo stop e il `sendPoll` guasti nella ripresa. Alla fine del giro: 332 prove veloci, 8 del piano reale.

#### Correzioni dopo la revisione del giro B

Decisioni del controllore; la spec è aggiornata (§3.7, §3.8, §4). Qui lo stato finale, che corregge i punti sopra dove dicono altro.

- **`/chiudi` mentre la riapertura aspetta.** Il sondaggio che la ripresa ha fermato conta come aperto per `/chiudi` (`Bot._in_riapertura`): si chiude come il comando chiede, con i voti tenuti, senza stop («🔒…», «🎲…», `rimanda`), con `chiuso_da`. `store._chiudi` accetta quel sondaggio (chiuso, senza `chiuso_da`, con la ripresa in fase «riaprire») e, chiudendo un sondaggio, toglie anche la sua ripresa, nella stessa transazione della lettera.
- **Un errore che non viene da Telegram nella ripresa** non la abbandona più: la ripresa resta, e `Bot._riprese_guaste` (per sondaggio) la ferma fino al prossimo avvio, che la riprova una volta, come `_chiusure_guaste` per le chiusure.
- **Dopo un completamento fallito** (la chiusura fra `_chiusure_guaste`): `/sondaggio` riceve «Non sono riuscito a completare la chiusura del sondaggio di prima. Chi può chiudere la riprovi con:» e, sull'ultima riga, `/chiudi@<bot>` con l'argomento in sospeso (`testi.chiusura_non_completata`); un `/chiudi` nuovo riceve «Riprovo a completare la chiusura del sondaggio.» (`testi.riprovo_a_completare`) e, con il comando nuovo, il bot riprova.
- **Minori.** Un invio che non parte (la posta, anche quella prima di un sondaggio) va nel log la prima volta e poi al massimo ogni 10 minuti, un 429 sempre (`Bot._avvisa_invio`). `Bot._in_chiusura` vale anche per la ripresa in fase «fermare» con `stop_provato`; la chiusura in sospeso da sola è `_in_sospeso`, che usano `/chiudi` e la ripresa. Mentre la riapertura aspetta, un voto al sondaggio fermato si registra su quello, e l'avviso dei voti sconosciuti va solo nel log. Una prova del 429 dentro la ripresa. La spec §3.8 dice del sondaggio doppio della riapertura.
- **La suddivisione di `bot.py`** non si fa qui: sarà un giro a sé (D), dopo il C.
- **Prove**: alla fine delle correzioni, 345 prove veloci, 8 del piano reale.

#### Secondo riesame del giro B

Decisioni del controllore; la spec è aggiornata (§3.7, §3.8).

- **Un `/sondaggio` vale al posto della riapertura, in modo atomico**: `store._apri` toglie una ripresa in fase «riaprire» nella stessa transazione dell'apertura (per `apri_sondaggio` e per `rimanda`); il controllo in `Bot._riapri` resta come rete. Prima, con la ripresa ferma per un errore, la chiave sopravviveva al sondaggio nuovo: un secondo `/chiudi` chiudeva anche il sondaggio fermato, e il riavvio lo riapriva.
- **Una ripresa ferma per un errore, dopo il suo stop**: `/sondaggio` risponde «Non sono riuscito a completare la chiusura del sondaggio di prima. Chi può chiudere la riprovi con:» e `/chiudi@<bot>` sull'ultima riga (`testi.chiusura_non_completata(nome, [])`, `Bot._ripresa_guasta`).
- **Un `/chiudi` che fallisce sul sondaggio in riapertura** (un errore che non viene da Telegram): il sondaggio va fra le `_riprese_guaste`, con il traceback nel log, e la riapertura non riparte da sola (il prossimo avvio la riprova).
- **Il caso «chi l'ha chiuso non si sa» interrotto** dopo `prova_stop_di_ripresa`, o dopo uno stop rifiutato, si attribuisce alla ripresa e riapre: scritto nella spec §3.8.
- **Le date passate**: il riepilogo «🔒 Sondaggio chiuso. Date possibili: …» elenca solo le date da oggi in poi; `/chiudi <data>` (o il suo giorno) con una data passata risponde «La data 8/10 è già passata.» (`regole.DataPassata` in `testi.rifiuto_di_chiudi`) e non chiude. Vale per ogni chiusura.
- **Prove**: alla fine, 355 prove veloci, 8 del piano reale.

### Giro di correzioni C: avvio, container, guida, piano reale, prove mancanti (dopo la revisione del task 10 e i rilievi minori dei task 1, 3 e 4)

Decisioni del controllore su delega di Alberto; la spec è aggiornata (§3.1, §3.7, §3.8, §4, §5, §6).

- **Residui del giro B.** (1) L'avviso di un voto per un sondaggio sconosciuto va solo nel log in **tutta** la ripresa, non solo nella fase «riaprire»: `Bot._voto_sconosciuto` guarda `store.ripresa()` e non più `_in_riapertura()`. La prova dello stop non confermato che si aspettava il «Rilanciatelo» ora lo esclude. (2) Il riepilogo di chiusura con date possibili tutte passate dice «🔒 Sondaggio chiuso. Nessuna data possibile da oggi in poi.» (`testi.chiuso_con_le_date_possibili_passate`); senza date possibili resta «Nessuna data con il master e quattro giocatori.». (3) `regole.data_da_chiudere(parola, date, oggi)` conta per un giorno solo le date da oggi in poi; con solo date passate si segue il percorso di una data passata (una sola: la restituisce e il bot dice «è già passata»; più d'una: «più di un martedì», con la prima, come prima).
- **Le prove di `principale`** (le cinque del revisore, in `tests/test_principale.py`): il battito a ogni giro anche dopo un errore, un 409 e un 429 su `getUpdates` non fermano il ciclo, `main` configura i log di httpx, httpx non scrive il token, `avvia` collega ciclo, battito e gruppo. Il 429 usa un `FermoFinto` (un `threading.Event` che non aspetta e ricorda le attese) per non aspettare davvero.
- **Il ciclo** (`principale.ciclo`): la pausa dopo un errore parte da `pausa_errore` (5 secondi) e raddoppia a ogni errore di fila fino a `PAUSA_MASSIMA` (60), e torna normale al primo giro riuscito (lettura e bot); il raddoppio è iterativo (un esponente crescerebbe fino all'`OverflowError` dopo ore di rete giù). Dopo un 429 si aspetta `max(pausa, retry_after)`. Aggiunta di chi ha eseguito il giro (il brief non la chiedeva): l'attesa si fa a fette di `FETTA_DI_ATTESA` (60 secondi) e il battito si tocca prima di aspettare e a ogni fetta, perché un `retry_after` oltre i 2 minuti avrebbe fatto segnare il container come non in salute mentre il ciclo gira. Il battito resta quello di prima: dice che il ciclo gira, non che Telegram risponde.
- **Container e guida.** `init: true` nel servizio di `compose.yaml` (con Python come PID 1 SIGTERM è ignorato e `docker compose stop` aspetta 10 secondi); la docstring di `principale.avvia` ora dice come il container lo ferma. La guida dice «dopo aver corretto, `docker compose up -d`» (il riavvio automatico non rilegge `prossima.env`) e di togliere il `#` da `PV_REALE_CHAT=`; in `config.esempio/prossima.env` la descrizione di `PV_REALE_CHAT` sta sulla riga sopra e `# PV_REALE_CHAT=` da solo; `.dockerignore` ignora `**/__pycache__`. Docker non c'è sulla macchina di sviluppo: compose e Dockerfile si sono giudicati leggendoli, e che `docker compose stop` torni subito va controllato a mano (v. `docs/differenze-fra-test-e-realta.md`).
- **Il piano reale.** `tests/reale/ambiente.py`: `richiesta(nome, non_verificato)` salta con «NON verificato: …» (di default il nome del test, da `PYTEST_CURRENT_TEST`) e `richiedi_la_configurazione` salta per ognuna di `PV_BOT_TOKEN`, `PV_GRUPPO`, `PV_ROSTER`, `PV_DB`, `PV_BATTITO`; `tests/test_reale_ambiente.py` lo prova nella suite veloce, insieme al suggerimento del fallimento di `risposte()` («il servizio è davvero fermo? (due lettori si rubano i voti) hai votato entro 3 minuti?»). `test_fermare_due_volte` (c'era già dal giro A) ora riporta il testo ricevuto se la descrizione di «già chiuso» è un'altra; nuova `test_un_sondaggio_con_undici_opzioni_parte`. Nessuna delle due è stata lanciata contro Telegram vero: la descrizione di «già chiuso» e il limite delle opzioni restano **da confermare** nelle differenze finché Alberto non lancia il piano reale.
- **Minori del task 1.** `_DATA` con `re.ASCII` (le cifre arabo-indiche o a larghezza piena non sono date). Una data oltre un anno da oggi (lo stesso giorno dell'anno dopo, il 28/2 per il 29/2) è «La data 14/10/2052 è troppo lontana.» (`regole.DataTroppoLontana`, con l'anno scritto): chiude anche l'`OverflowError` di `date_rimandate` con l'anno 9999. Il `29/2` senza anno, fuori da un anno bisestile, è il prossimo 29 febbraio (con `calendar.isleap`; il secolo non bisestile compreso), e se è oltre un anno è «troppo lontana»; in un anno bisestile resta la regola di tutte le date (il 10/3/2028 «29/2» è «già passata»).
- **Minori dei task 3 e 4** (solo prove, il codice non cambia): la lunghezza UTF-16 di una menzione con un soprannome non ASCII (`sèsè🎲`) e dell'offset della seguente; `testi.annuncio` anche su `Quasi` e `Possibile`; `riapri_sondaggio` con un altro sondaggio aperto (`IntegrityError`, il primo com'era, niente in posta); un voto rifatto in un altro `poll_id` esce da `voti_del_poll` del vecchio ed entra in quello nuovo. Provate con mutanti: ognuna fallisce senza la correzione che la riguarda.
- **Prove**: alla fine, 409 prove veloci, 9 del piano reale (tutte saltate senza le variabili: `uv run pytest -m reale -q -rs` dice per ognuna quale e che cosa non è verificato).

### Giro D: `bot.py` diviso in parti (dopo il giro C)

Decisione del controllore su delega di Alberto, dalla revisione del giro B (M7): `bot.py` era cresciuto oltre le 760 righe, con tre macchine a stati intrecciate e le dipendenze fra le parti implicite in `self`. Un rifacimento puro: nessun comportamento, testo o significato di prova cambia; la spec cambia solo in §5.

La struttura dei file del bot, al posto della riga di `bot.py` nella tabella «Struttura dei file»:

| file | responsabilità |
|---|---|
| `src/prossima/bot.py` | collega le parti: il giro (`ricevi`, `manda`), lo smistamento, `/sondaggio`, i voti (anche per un sondaggio sconosciuto), gli annunci (con gli annunci rifiutati, in memoria); `COMANDI` |
| `src/prossima/chiusura.py` | `Chiusure`: `/chiudi`, la chiusura in sospeso e i suoi tentativi (`riprova`), il completamento, `rimanda`; in memoria gli stop rifiutati e le chiusure guaste |
| `src/prossima/ripresa.py` | `Ripresa`: la ripresa dopo il buio (`inizia`, `continua`, lo stop e la riapertura); in memoria le riprese guaste |
| `src/prossima/invio.py` | `Invio`: ogni chiamata che scrive su Telegram, la pausa del 429, la posta in uscita, il sondaggio nuovo con la frase di «Nessuna», lo stop (`Fermato`); `TelegramInPausa`, `forse_arrivata`, `livello`, e `Avvisi` (nel log la prima volta, poi al massimo ogni 10 minuti) |

Le dipendenze vanno in un senso solo, `bot` → `chiusura` → `ripresa` → `invio` (il bot usa anche la ripresa e l'invio), senza import circolari. Nessuna parte tocca le strutture in memoria di un'altra se non con un suo metodo. Rispetto alla proposta del revisore:

- **La chiusura sopra la ripresa**, non sotto: `/chiudi` chiude anche il sondaggio che la ripresa aspetta di riaprire (`Ripresa.in_riapertura`), e se quella chiusura fallisce ferma la ripresa fino al riavvio (`Ripresa.ferma_fino_al_riavvio`, una struttura in memoria della ripresa). Alla ripresa delle chiusure basta sapere se ce n'è una in sospeso: è un fatto del database, e la ripresa lo legge dallo store.
- **Il sondaggio nuovo e la frase di «Nessuna» in `invio.py`**, non in `bot.py`: li usano `/sondaggio`, `rimanda` (le chiusure) e la riapertura (la ripresa); nel bot, le parti di sotto dovrebbero richiamare quella di sopra. Anche le lettere per il gruppo (`lettera`, `lettere`, `accoda`) sono dell'invio.
- **Gli avvisi che si ripetono**: ogni parte ha i suoi `Avvisi` (prima un solo dizionario, con chiavi diverse per invio, chiusura e ripresa: la regola è la stessa).
- **`store.py` resta com'è**, e i suoi tipi restano lì: sono una settantina di righe su quasi settecento, e spostarli non alleggerirebbe la lettura.
- Ogni parte scrive nel log con il proprio logger (`prossima.chiusura`, `prossima.ripresa`, `prossima.invio`): i messaggi sono gli stessi, cambia il nome del logger nella riga.

Prove: le stesse 409 prove veloci, tutte verdi a ogni passo; una sola cambia il punto in cui chiama, non che cosa verifica (`bot._nuovo_sondaggio` è ora `bot._invio.nuovo_sondaggio`).

### Giro E: la rifinitura dopo la revisione dell'intero ramo

Decisioni del controllore su delega di Alberto, dopo la revisione finale del ramo; la spec è aggiornata (§3.1, §3.5, §3.7, §3.8, §4, §5, §6), con la guida e le differenze fra test e realtà.

- **Gli annunci solo sulle date da oggi in poi** (I1). `Bot._stato` toglie le date passate: una data passata non si annuncia più come «quasi» o «possibile» e non entra in «impossibile» (né fra le date «Con tre», che `/chiudi` rifiuterebbe). Un «non più possibile» falso non c'è: `regole.annunci_da_fare` guarda solo le date dello stato, e un «possibile» su una data passata resta nei fatti senza effetto (provato). `Chiusure._stato` resta con tutte le date: il riepilogo le filtra già, e gli servono quelle passate per dire «Nessuna data possibile da oggi in poi». Conseguenza, scritta nella spec: quando passa l'ultima data ancora in gioco e le altre sono fuori, il sondaggio diventa «impossibile» senza un voto nuovo.
- **La riapertura non manda sondaggi a raffica** (I2). Dopo un errore che forse è arrivato a Telegram (`forse_arrivata`), la ripresa ricorda il momento del tentativo per sondaggio (`Ripresa._forse_partite`, in memoria) e non manda un altro sondaggio prima di `AVVISO_RIPETUTO`; la pausa di un 429 e un rifiuto non cambiano. Due prove di prima usavano un errore di rete e si aspettavano il sondaggio alla lettura seguente: ora lo aspettano dieci minuti dopo. «Riapro il sondaggio…» risponde al sondaggio riaperto. Il client aspetta la risposta di `sendPoll`, `sendMessage` e `stopPoll` fino a 30 secondi (`telegram.SCRITTURA = httpx.Timeout(10.0, read=30.0)`); `getUpdates` resta all'attesa più 10, `getMe` e `setMyCommands` ai 10 del client.
- **Le menzioni verso chi non ha mai scritto al bot** (I3), solo documenti: una riga nelle differenze, e nella guida le sei persone che scrivono `/start` al bot (punto 1) e la prova a mano di una menzione verso chi non l'ha fatto (punto 5).
- **`prossima sblocca`** (minore 1): `src/prossima/sblocco.py` (scelta di chi ha eseguito il giro: un modulo a sé al posto di un `python -c`), chiamato da `principale.main`. Toglie la chiusura in sospeso e la ripresa, chiude nel database il sondaggio aperto, e scrive nel log una riga per ogni cosa tolta; legge solo `PV_DB` e non crea un database che non c'è. Nel gruppo non scrive niente. La guida ha la sezione «Se il bot resta bloccato».
- **Minori 2-5 e 10**: la regola vera delle date senza anno nella spec §3.1; la docstring di `principale.avvia`; `.gitignore` (`*.sqlite*`, `battito`, `/.env`); `docker compose run --rm --build prova` nella guida e nella docstring di `tests/reale/test_configurazione.py`; la rotazione del log in `compose.yaml` (`json-file`, `10m`, `3`).
- **`/chiudi <data>` dopo una riapertura** (minore 6) cerca anche in `date_iniziali`: «La data 8/10 è già passata.», anche con il giorno (`/chiudi mer`), al posto di «non era nel sondaggio» o «nessun mercoledì».
- **I conteggi diversi alla chiusura** (minore 7): in `Chiusure._completa`, se i conteggi di `stopPoll` sono diversi da quelli del bot (contati come alla ripresa, sui voti del sondaggio di Telegram di adesso), prima del riepilogo «🔒…» la frase dei conteggi diversi. Solo prima del riepilogo, come dice il brief: «🎲 Si gioca…» e `rimanda` non contano le date possibili. Il finto dà zero voti per opzione se la prova non dice i conteggi: quattro prove con dei voti che arrivano a uno stop ora li dicono.
- **Il lotto pieno dopo il buio** (minore 8): con 100 aggiornamenti (`telegram.MASSIMO_AGGIORNAMENTI`, il default di `limit`) la ripresa aspetta il primo lotto che non è pieno, e la lettura non si segna. Aggiunta di chi ha eseguito il giro: il bot ricorda in memoria la prima lettura dopo il buio (`Bot._fine_del_buio`) e la passa alla ripresa come fine del buio. Senza, un sondaggio nato in un lotto pieno sarebbe sembrato aperto da prima, e la ripresa l'avrebbe fermato e riaperto; e il messaggio del buio avrebbe detto l'ora di un lotto seguente.
- **L'errore del ciclo** (minore 9): quando la pausa arriva al massimo, un errore nel log, una volta sola fino alla prossima lettura riuscita. Il testo non è quello del brief («Telegram non risponde da N tentativi»): un 409 o un 429 sono risposte di Telegram. È «lettura del bot non riuscita da N tentativi di fila, l'ultimo: …», e conta solo le letture fallite: gli errori del bot hanno già il loro errore con il traceback.
- **Prove**: `fino_al` è passato da `tests/test_chiudi.py` a `tests/aggiornamenti.py`. Alla fine, 432 prove veloci; il piano reale, 9 prove, senza le variabili ne salta 8 dicendo quale manca (la nona, il fuso di Zurigo, non ne ha bisogno).

#### Correzioni dopo i dubbi del giro E

Decisioni del controllore; la spec è aggiornata (§3.5), con la guida e le differenze. Qui lo stato finale, che corregge i punti sopra dove dicono altro.

- **Niente «impossibile» dopo un possibile passato.** Se una data passata era stata annunciata come possibile e nessuno l'ha ritirata (è ancora fra i `possibili` dei fatti, senza un «non più possibile»), «impossibile» non si annuncia: probabilmente quel giorno si è giocato, e «nessuna di queste date» il giorno dopo sarebbe falso nei fatti. La regola sta in `regole.annunci_da_fare` (`_possibile_passata`): lo stato che riceve ha solo le date ancora in gioco, quindi una data dei `possibili` che non c'è è passata. Senza una data così, «impossibile» per il solo passare del tempo resta.
- **Le menzioni nella guida.** Nella guida (§1 e §5) non c'è più «dopo, le menzioni sono garantite»: le sei persone scrivono `/start` al bot perché le menzioni verso chi non l'ha fatto non sono verificate, e il controllo a mano nel gruppo prova i due casi (chi l'ha scritto e chi non ancora).
- **Prove**: 434 prove veloci.

#### Correzioni dopo la revisione finale

Decisioni del controllore; la spec è aggiornata (§4, §5), con la guida e le differenze.

- **`prossima sblocca` non chiude un sondaggio sano.** Chiude il sondaggio aperto solo se la chiusura in sospeso o la ripresa che ha tolto erano sue; altrimenti non cambia niente e dice «niente da sbloccare: nessuna chiusura in sospeso, nessuna ripresa» (il testo di prima diceva anche «nessun sondaggio aperto», che con un sondaggio sano aperto sarebbe falso). Così il comando si può provare senza rischi.
- **Guida §6**: torna `--profile prova`, `docker compose --profile prova run --rm --build prova` (anche nella docstring di `tests/reale/test_configurazione.py` e nelle differenze).
- **Prove**: 438 prove veloci.

### Dopo la fusione: le frasi di «Nessuna» in un file sul server

Richiesta di Alberto prima di pubblicare il repository: via dal codice e dalla
storia (riscritta prima del primo push) le sette frasi con le battute sulle
persone del gruppo, e le frasi in un file di configurazione. `PV_FRASI`
(facoltativa) indica il file, `config/frasi.txt` sul server; senza, le 15 frasi
predefinite di `testi.FRASI_NESSUNA`, le stesse di `config.esempio/frasi.txt`.
`config.leggi_frasi` rifiuta le frasi oltre 100 caratteri (in UTF-16), i doppioni,
un file senza frasi e le righe «NOME=valore» (`PV_FRASI` che indica per sbaglio
`prossima.env` metterebbe il token in un sondaggio), dicendo la riga, contata
solo sugli a capo; il bot passa le frasi a `Invio`, e `testi.scegli_frase`
sceglie nella lista che riceve. Il piano reale manda, fra le frasi che il
servizio usa, quella con più byte. La revisione del commit ha portato la guardia
sulle righe di configurazione, il conto delle righe e tre prove che uccidono
mutazioni sopravvissute. Il nome del gruppo e i soprannomi restano nel
repository, come in quello dei selfie: i soprannomi si cambiano nel roster, e il
nome del gruppo il bot lo scrive solo in una frase, che ora sta nel file.

### Dopo la pubblicazione: il container senza privilegi

Dalla revisione di sicurezza del servizio dei selfie, lo stesso rinforzo anche
qui: utente 10001 nel `Dockerfile` (servizio e prova), e in `compose.yaml`
`read_only`, `tmpfs` per `/tmp`, `cap_drop: ALL`, `no-new-privileges`, 256 MB e
64 processi. La guida fa di `dati` una cartella dell'utente 10001 e rende roster
e frasi leggibili dal suo gruppo (640). Docker non c'è sul Mac:
`tests/test_container.py` controlla solo il testo, l'avvio vero è fra i controlli
a mano sul server.

### Il primo piano reale (2026-10-08)

Otto contratti su nove confermati, nessuno saltato. Fra questi: le 11 opzioni,
la descrizione di un messaggio cancellato, le menzioni, i voti. Il nono era
sbagliato: un secondo `stopPoll` sullo stesso sondaggio risponde «Bad Request:
poll can't be stopped», non «poll has already been closed». `_GIA_CHIUSO`
riconosce adesso tutte e due, e il finto usa la descrizione vera.

Al secondo giro del piano reale Alberto ha tolto una data alla volta invece di
ritirare il voto intero: Telegram ha mandato le opzioni rimaste (`[0]`), un voto
cambiato che il bot sostituisce al precedente come ogni altro. Il codice era già
giusto; la prova adesso chiede anche questo passo (togli solo la terza, poi
ritira il voto).

### La domanda nella configurazione (2026-10-09)

Richiesta di Alberto: la domanda del sondaggio si cambia senza toccare il
codice. `PV_DOMANDA` in `prossima.env` (facoltativa; senza, «Prossima volta?»),
al massimo 300 caratteri in UTF-16, controllata all'avvio senza ripeterne il
valore nel messaggio d'errore; il bot la passa a `Invio`, che la usa per ogni
sondaggio nuovo, anche nella ripresa e in `/chiudi rimanda`. La domanda come
opzione di `/sondaggio`, per un sondaggio speciale, è rimandata a più avanti.

### Annunci brevi, il sabato e /aiuto (2026-10-10)

Dopo il primo sondaggio vero il gruppo ha trovato gli annunci prolissi: cinque
messaggi per un voto. Il piano è `docs/superpowers/plans/2026-10-10-annunci-e-sabato.md`, la spec
§2, §3.1, §3.5, §3.7, §3.9. Riassunto:

- testi brevi, con i nomi con la maiuscola e le date dette per giorno;
- «quasi» solo se qualcuno non ha votato e nessuna data è possibile;
- l'attesa di 2 minuti dall'ultimo voto, in memoria;
- un messaggio per tipo;
- il sabato fuori dai giorni di sempre (`PV_GIORNI`, `con sabato`, giorni per intero);
- `/aiuto`.

Durante l'esecuzione:

- I Task 2-5 sono andati in un commit solo. I nomi con la maiuscola rompevano le
  stesse prove che i testi nuovi degli annunci avrebbero riscritto: due giri sulle
  stesse prove non servivano.
- Il codice dell'attesa è stato scritto prima delle sue prove. Le prove sono
  arrivate subito dopo, e nove mutazioni (l'attesa tolta, l'attesa che non
  riparte a un voto nuovo, niente raggruppamento, le regole di «quasi», l'ordine
  per tipo, i nomi solo se noti per tutte le date, la settimana sola, chi si
  menziona) le fanno fallire tutte.
- `conftest.riavvia` crea il bot con `attesa_annunci=0`, così le prove degli
  annunci restano immediate; quelle dell'attesa la chiedono.
- In «impossibile», «per tenerla» con una sola data e «per tenerne una» con più
  date (aggiunto alla spec).
- La prova del messaggio che non è un comando usava `/aiuto` come comando
  sconosciuto: adesso usa `/start`.
- La revisione del ramo ha portato:
  - le prove che mancavano (l'attesa vera di 2 minuti in esercizio, `PV_GIORNI`
    che arriva al bot, `/aiuto` dai giorni della configurazione, l'attesa nei
    percorsi della ripresa, un errore di rete sul secondo messaggio, l'ordine
    «non più» prima di «possibile», sabato e domenica al maschile, i nomi
    nell'ordine del roster, le date dette guardando tutto il sondaggio);
  - l'attesa che riparte solo per i voti registrati di persone del roster (non
    per un voto tardivo scartato, non per chi non è nel roster);
  - i giorni con l'accento scomposto (NFD);
  - l'esempio del rifiuto di «con», che usa il primo giorno escluso;
  - «lo chiude Abe» quando il master non può chiudere e può solo uno.
- Un tocco su un comando evidenziato manda solo il comando, senza gli argomenti
  (Alberto l'ha visto sul telefono). Così i comandi con argomenti nei messaggi
  del bot sono diventati codice (`_Scrittura.codice`): `/aiuto`, il rifiuto di
  «con», i «riprovate con:», «impossibile». I bottoni per «impossibile» vengono
  dopo, in un lavoro a parte.

### I bottoni di «impossibile» (2026-10-10)

Il piano è `docs/superpowers/plans/2026-10-10-bottoni.md`, la spec §3.5 (punto 4) e §3.10.

- Sotto «impossibile» ci sono i bottoni «Tieni <giorno>» e «Rimanda alla prossima settimana».
- Per chi può chiudere, un tocco vale come `/chiudi <argomento>` della stessa persona.
- Il «comando» di `Chiusure.chiudi` è il messaggio con i bottoni: un tocco riletto, o un secondo bottone
  dopo il primo, non chiude due volte.
- Con più persone che possono chiudere e un master che non può, il testo dice «Abe e Emi, decidete voi:».
- Il piano reale chiede ad Alberto di toccare un bottone nella chat privata.
- Il piano reale gli chiede anche di toccare un comando di `/aiuto` e di incollarlo nella chat: un codice,
  toccato, si copia intero (prima era un controllo a mano nel gruppo).
- La revisione del ramo ha portato:
  - con la chiusura in sospeso, un altro bottone sullo stesso messaggio cambia la decisione (il messaggio
    costruito dal tocco ha `"tocco": True`, e `Chiusure.chiudi` scarta solo lo stesso bottone);
  - il bot ricorda il messaggio con i bottoni validi (`store.messaggio_con_bottoni`): i bottoni di un
    «impossibile» superato rispondono «Questi bottoni non valgono più.»;
  - i bottoni si tolgono in `manda` appena il sondaggio non è più aperto, quindi anche dopo una chiusura in
    sospeso completata più tardi, e quando una data torna in gioco o arriva un «impossibile» nuovo;
  - «message is not modified» su `editMessageReplyMarkup` non è un errore;
  - l'identificativo del sondaggio nel dato del bottone solo con cifre ASCII;
  - `testi.annunci` senza il sondaggio, per «impossibile», è un errore;
  - le prove che mancavano: il tocco con la ripresa che aspetta di riaprire, la pausa di un 429, il
    «Rimanda» vecchio dopo un rimanda scritto, l'argomento vuoto.

### Il piano reale dopo gli annunci brevi (2026-10-10)

Il primo giro sul server dopo annunci e bottoni: 10 prove su 11. `test_una_menzione_dopo_un_emoji_cade_sul_nome`
usava ancora `testi.quasi`, tolta con gli annunci brevi; le prove veloci non importano il piano reale e non se ne
sono accorte. Il «quasi» nuovo non ha più emoji, quindi la prova ora menziona Alberto nel testo di «impossibile»,
che comincia con 😬 (due unità UTF-16). `tests/test_piano_reale.py`, fra le prove veloci, controlla che i nomi dei
moduli di `prossima` usati dal piano reale esistano ancora.
