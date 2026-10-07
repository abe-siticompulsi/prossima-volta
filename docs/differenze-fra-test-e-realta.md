# Differenze fra test e realtà

Ogni finto mette per iscritto una convinzione sul mondo vero, e un finto non
può smentire chi l'ha scritto: la conferma con un pallino verde. Questo elenco
dice quali convinzioni stanno nei finti e dove vengono messe alla prova contro
il vero. Si scrive prima dei finti, e si aggiorna ogni volta che il vero ne
smentisce una.

| Nei test | Nella realtà | Dove si verifica |
|---|---|---|
| Telegram risponde subito e con `ok: true` (`TelegramFinto`), salvo i guasti che la prova imposta. | Può fallire, rallentare, rifiutare (4xx) o chiedere di aspettare (429 con `retry_after`). | `tests/test_telegram.py` legge le risposte d'errore nella forma documentata dall'API. Un 429 vero non si provoca: vorrebbe dire inondare il bot. |
| Un sondaggio non anonimo, a risposta multipla, con fino a 11 opzioni (10 date e la frase di «Nessuna») parte, e il voto si può cambiare. | L'API ammette da 1 a 12 opzioni (**da ricontrollare nel piano reale**) di al massimo 100 caratteri; `allows_revoting` è vero per default nei sondaggi normali, e il bot lo chiede comunque. Che un sondaggio non anonimo parta anche in una chat privata non è scritto da nessuna parte. | `tests/reale/test_telegram_vero.py::test_sondaggio_voto_ritiro_e_conteggi`: 10 date e la frase più lunga, nella chat privata di Alberto. |
| Un voto arriva come `poll_answer` con l'identificativo di chi vota (`user.id`) e le opzioni spuntate, contate da 0; il voto ritirato arriva con `option_ids` vuoto. | Telegram manda i voti a un bot solo per i sondaggi non anonimi creati da lui. | Il piano reale: Alberto vota, ritira il voto e vota di nuovo. |
| `stopPoll` restituisce i conteggi per opzione, nell'ordine delle opzioni. | L'API restituisce il `Poll` fermato, con `voter_count` per opzione («may be 0 if unknown»). | Il piano reale, dopo il voto di Alberto. |
| Un sondaggio cancellato fa rispondere a `stopPoll` «message to stop not found», che il client riconosce come `MessaggioSparito`. | La descrizione la sceglie Telegram, e non è documentata. | `tests/reale/test_telegram_vero.py::test_fermare_un_sondaggio_cancellato`: il bot manda un sondaggio, lo cancella e prova a fermarlo. |
| Le menzioni sono entità `text_mention` con il solo identificativo, e gli scostamenti contati in unità UTF-16 cadono sul nome. | Telegram rifiuta o sposta le entità con scostamenti sbagliati; se una menzione notifichi davvero lo vede solo una persona. | Il piano reale rilegge le entità nel messaggio che Telegram restituisce; a mano, nel gruppo: la notifica arriva. |
| Il bot riceve `/sondaggio` e `/sondaggio@<bot>` dal gruppo. | Con la privacy attiva il bot riceve solo i comandi rivolti a lui: con altri bot nel gruppo un `/sondaggio` nudo può non arrivare, e il menu dei comandi aggiunge `@<bot>` da solo. | A mano, nel gruppo: `/sondaggio@<bot>` dal menu. |
| Il bot legge gli aggiornamenti senza concorrenti. | Due lettori dello stesso bot si rubano gli aggiornamenti (409 Conflict). | Il piano reale si lancia a servizio fermo e legge `getUpdates` senza offset, così non conferma niente: v. `docs/messa-in-produzione.md`. |
| Il buio si prova spostando l'orologio finto di più di 23 ore. | Telegram tiene gli aggiornamenti per 24 ore e poi li perde; nessuna API dice chi ha votato cosa. | Non verificato contro il vero: servirebbe un giorno di buio. Lo dice la documentazione di `getUpdates`. |
| L'orologio è finto, e il fuso è `Europe/Zurich` di `tzdata`. | L'immagine `python:3.12-slim` non ha `/usr/share/zoneinfo`: senza il pacchetto `tzdata` il fuso non si trova. | `tests/reale/test_configurazione.py`, che gira nel container. |
| httpx non scrive log. | Al livello INFO httpx scrive l'URL di ogni richiesta, e l'URL di Telegram contiene il token. | `tests/test_principale.py` controlla che `configura_log` alzi il livello del logger `httpx`. |
| `stopPoll` nel finto si può ripetere e restituisce i conteggi di nuovo. | Su un sondaggio già chiuso il vero rifiuta con un 400 (probabilmente «poll has already been closed»), che il client trasforma in `TelegramRifiuto` senza conteggi. | Il piano reale, e la gestione del bot di un `/chiudi` o di una ripresa interrotta tra `stopPoll` e il salvataggio. |
| `getUpdates` nel finto consegna una volta sola e ignora `offset`. | Il vero consegna gli stessi aggiornamenti di nuovo fino a che l'offset li conferma. | Doppi aggiornamenti dopo un riavvio si provano rimettendoli a mano in `aggiornamenti_da_dare`. |

## Da controllare a mano nel gruppo

- `/sondaggio@<bot>` scelto dal menu dei comandi arriva al bot con la privacy
  attiva, e il sondaggio compare nel gruppo.
- Una menzione («Non hanno ancora votato: …», «gio, abe: …») notifica la
  persona, anche chi non ha un nome utente.
