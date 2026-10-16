# Le risposte con Ollama — design

Data: 2026-10-17. Ramo `risposte`, da `main` (5c28989). Viene dal prototipo (`prototipo-ollama`, piano
`docs/superpowers/plans/2026-10-11-prototipo-ollama.md`, «strada unita corretta» del 15/10) e dal brainstorming
con Alberto del 16-17/10.

## 1. Che cosa

Il bot risponde a chi gli scrive: nel gruppo a chi risponde a un suo messaggio, in privato a chi è nel roster.
Un modello veloce (`llama3`) dice di che tipo è il messaggio; il codice scrive la risposta con i fatti del
sondaggio; un modello che scrive meglio (`gemma3:12b`) la riscrive in modo naturale, controllata sui fatti.
Per una battuta, la battuta la scrive `gemma3`. Annunci, sondaggio e comandi non cambiano.

Fuori perimetro: annunci riscritti (forse dopo, a parte), frasi di «Nessuna» generate, l'annuncio «hanno
votato tutti» (idea in sospeso, dopo).

## 2. A che cosa risponde

- **Nel gruppo**: a un messaggio di testo che risponde a un messaggio del bot (con la privacy attiva le
  menzioni `@bot` non arrivano, le risposte ai suoi messaggi sì), di chiunque; non a un comando (`/…`).
- **In privato**: a ogni messaggio di testo di chi è nel roster, che non è un comando (`/aiuto` resta com'è).
  Serve anche al piano reale.
- Senza `PV_OLLAMA_URL` il bot non risponde (com'è oggi): le risposte sono spente.
- Il bot risponde citando il messaggio nel gruppo; in privato senza citarlo.

## 3. Il tipo e la risposta del codice

`llama3`, temperatura 0, risposta JSON costretta da uno schema: `{"tipo": …, "giorno": … | null}`. I tipi
sono quelli del prototipo (`chi_c_e`, `data`, `voto`, `chiusura`, `non_so`, `battuta`, `altro`). Il giorno
vale solo se il messaggio lo nomina davvero; `chi_c_e` senza un giorno nominato si risponde come `data`.

I fatti vengono **dall'ultimo sondaggio**: quello aperto oppure, se non c'è, l'ultimo chiuso.

| Tipo | Stato | Risposta del codice |
|---|---|---|
| `data` | nessun sondaggio, mai | «Non c'è ancora un sondaggio: lancialo con `/sondaggio`.» |
| `data` | aperto, senza giorno | «Il sondaggio è ancora aperto. Per ora si può fare martedì 14/10 o giovedì 16/10.» (o «…e nessuna data ha il master e quattro giocatori.») |
| `data` | aperto, con giorno | «Il sondaggio è ancora aperto.» + lo stato del giorno |
| `data` | chiuso, data scelta da oggi in poi | «Si gioca giovedì 16/10.» (con un giorno nominato: «Sì: …» / «No: …») |
| `data` | chiuso, data scelta passata | «Si è giocato giovedì 16/10. Per la prossima volta non c'è ancora un sondaggio.» |
| `data` | chiuso senza data, date possibili da oggi in poi | «Il sondaggio è chiuso: si può fare martedì 14/10 o giovedì 16/10. Gio, a te la scelta.» |
| `data` | chiuso senza data, nessuna data possibile (o tutte passate) | «Il sondaggio è chiuso senza una data. Per la prossima volta serve un sondaggio nuovo.» |
| `chi_c_e` | con un sondaggio | lo stato del giorno: «Giovedì 16/10: si può fare. L'hanno votata Gio, Abe, …», e, a sondaggio aperto e se la data non si può ancora fare, chi non ha ancora votato |
| `voto` | aperto | «Sem, conta solo il sondaggio: aggiorna lì il tuo voto.» |
| `voto` | chiuso | «Sese, il sondaggio è chiuso. Gio, non faccio valutazioni: lascio a te le decisioni (ehi, ho fatto la rima)!», con «Gio» menzione del master |
| `chiusura` | — | «Chiude Gio (o Abe, in emergenza), quando decide.» |
| `non_so` | — | «Questo non lo so: chiedi a Gio.» |
| `altro` | — | «Io conto i voti e basta.» |
| `battuta` | — | la scrive `gemma3` |

Senza sondaggio, `chi_c_e` e `voto` rispondono come `data`. Le date possibili sono quelle da oggi in poi. Il
nome di chi scrive è il soprannome del roster con la maiuscola o, per chi non è nel roster, il suo nome
Telegram.

## 4. La riscrittura e la battuta

- `gemma3` riscrive la risposta del codice (prompt e controlli del prototipo: stessi giorni, date e nomi,
  nessuno in più tranne chi scrive; una riga; niente emoji). Fino a 3 tentativi, con il motivo dello scarto;
  poi resta la risposta del codice.
- **Non si riscrive** una risposta che nomina più di una persona (l'elenco dei votanti: `gemma3` rimetteva i
  nomi dalla parte sbagliata) o che ha entità (una menzione, un comando in codice): resta com'è.
- La battuta: prompt e controlli del prototipo (niente fatti, nessuno del gruppo tranne chi scrive, al
  massimo 200 caratteri), fino a 3 tentativi. Se non passa: «Mi dispiace, non posso risponderti. Io sono
  bravo a contare i voti; per il resto, faccio quello che posso. 😉️»

## 5. I ripieghi

- Ollama non risponde (rete, errore HTTP, tempo scaduto, JSON del tipo illeggibile): «Ora non riesco a
  rispondere: riprova più tardi.» Se il tipo c'era e cade la riscrittura, resta la risposta del codice.
- Una chiusura in sospeso o una ripresa in corso (il sondaggio forse è già fermo): la stessa frase fissa,
  subito, senza Ollama.
- **Fila di 3**: al massimo 3 messaggi in lavoro (quello in corso compreso); il quarto riceve subito la frase
  fissa.
- Un riavvio perde i messaggi in lavoro: si scrive nel log, nessuna risposta.

## 6. Come gira: un thread nel bot (strada A)

- Il bot resta a un filo per Telegram e il database. Un **thread** fa le chiamate a Ollama, una alla volta
  (i 4 core del server sono condivisi con Paperless), e non tocca né Telegram né il database.
- Quando arriva un messaggio a cui rispondere, il bot fa la **foto dei fatti** (il sondaggio, i voti, la
  data scelta, oggi) e la passa al thread con il messaggio.
- Il thread rende il tipo, il giorno e il testo. Al giro seguente il bot prende le risposte pronte: se nel
  frattempo i fatti sono cambiati, manda la risposta del codice rifatta con i fatti di adesso (non
  riscritta); altrimenti quella del thread. La risposta va nella **posta** (`invio.accoda`), come ogni
  messaggio.
- Mentre il thread lavora, il bot manda «sta scrivendo…» (`sendChatAction`, al massimo ogni 4 secondi per
  chat, al meglio) e legge Telegram con un long polling di **2 secondi** invece di 25, per prendere la
  risposta appena è pronta.
- I modelli restano in memoria con il `keep_alive` di default di Ollama (5 minuti): a freddo una risposta
  prende fino a 75 secondi, e va bene. Una chiamata scade dopo 180 secondi.

## 7. La data scelta

La tabella `sondaggi` prende la colonna `scelta` (la data ISO, o vuota). All'avvio `crea_schema` la aggiunge
se manca (`ALTER TABLE … ADD COLUMN`): i sondaggi già chiusi restano senza data scelta. `/chiudi <data>` (e
il bottone che tiene una data) la scrive nella stessa transazione della chiusura; `/chiudi` senza data e
`rimanda` la lasciano vuota.

## 8. Configurazione e rete

- `PV_OLLAMA_URL` (facoltativo; senza, niente risposte), `PV_OLLAMA_TIPO` (default `llama3:latest`),
  `PV_OLLAMA_TESTO` (default `gemma3:12b`).
- Rete Docker dedicata `ollama` (esterna per il compose del bot): ci stanno solo Ollama e il bot. La porta
  11434 di Ollama si pubblica solo su `127.0.0.1` (per i prototipi, con un tunnel SSH). Le due righe nel
  compose di Paperless le fa Alberto. Dal bot: `PV_OLLAMA_URL=http://ollama:11434`.

## 9. Prove

- Veloci: controlli, prompt, risposte del codice per ogni stato, la riscrittura e la battuta con un Ollama
  finto (testi buoni, scartati, errori), il thread e la fila, il bot (gruppo, privato, fatti cambiati,
  «sta scrivendo…», long polling corto), la migrazione della colonna `scelta`.
- Piano reale: `sendChatAction` accettato da Telegram; Ollama vero, se `PV_OLLAMA_URL` c'è (i due modelli ci
  sono, il JSON del tipo segue lo schema).
- Dopo il rilascio, Alberto prova in privato: è il modo previsto per vedere le risposte senza scrivere nel
  gruppo.
