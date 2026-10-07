# Prossima volta — il sondaggio della data per i Danni Radiosi

Data: 2026-10-07. Stato: approvata da Alberto in conversazione (tre parti più le
modifiche), da eseguire con subagenti. Aggiornata il 2026-10-08 con il giro di
correzioni A (gli errori di Telegram nel bot, decisi su delega di Alberto):
§3.1, §3.6, §3.7, §4.

## 1. Perché

Il party dei Danni Radiosi sceglie la data della sessione seguente in chat. Un
bot nel gruppo del party crea il sondaggio con le date, segue i voti e dice nel
gruppo quando una data va bene, quando ci si è vicini (e chi non ha ancora
votato), e quando con le date proposte non ci si sta.

Progetto a sé, accanto a `radiant-selfie-machine` (il servizio dei selfie) e a
`close-the-circle` (`ctc`). Non condivide codice né database con loro: un bot
suo, un container suo, sulla stessa macchina dei selfie.

## 2. Decisioni

| Decisione | Perché |
|---|---|
| **Il sondaggio lo crea il bot** | Telegram manda a un bot i voti (chi, quali opzioni) solo dei sondaggi non anonimi creati dal bot stesso. |
| **Chiunque nel gruppo lo lancia**, con `/sondaggio` | Richiesta di Alberto. |
| **Solo gio (master) e abe lo chiudono** | La decisione finale è loro; nessuno lo chiude per sbaglio. |
| **Bot nuovo, repo nuovo, container nuovo** | I selfie restano intoccati: un errore qui non ferma la validazione delle foto la sera della partita. |
| **Privacy del bot attiva** | Il bot riceve solo i comandi rivolti a lui e i voti dei suoi sondaggi: non legge la chat. |
| **Nessun gruppo di prova** | Richiesta di Alberto: «siamo tra amici, per testare servono le persone vere». Il piano reale gira nella chat privata di Alberto con il bot. |
| **Frasi di «Nessuna di queste» da una lista scritta a mano** | Prevedibili, lette da Alberto prima che arrivino nel gruppo. Ollama (nella rete locale) è una possibile aggiunta futura, fuori da questa spec. |
| **Ogni messaggio afferma solo ciò che è verificato** | La regola di tutti i progetti di Alberto. |

## 3. Il comportamento

### 3.1 Lanciare il sondaggio: `/sondaggio`

Nel gruppo del party, `/sondaggio@<bot>` (il menu dei comandi di Telegram aggiunge
`@<bot>` da solo; nel gruppo ci sono altri bot e, con la privacy attiva, un
`/sondaggio` nudo potrebbe non arrivare). Il bot accetta `/sondaggio` e `/sondaggio@<suo nome>`
e ignora i comandi rivolti ad altri bot.

- **Senza parametri**: i sette giorni della settimana seguente, da lunedì a
  domenica. «Settimana seguente» è la settimana di calendario dopo quella di
  oggi, nel fuso `Europe/Zurich` (di domenica è quella che comincia domani).
- **Con giorni della settimana** (`lun mar mer gio ven sab dom`): quei giorni
  della settimana seguente. `/sondaggio mar gio sab`.
- **Con date** (`g/m` o `g/m/aaaa`, e anche con il punto: `g.m`, `g.m.aaaa`):
  quelle date. Senza anno, l'anno è quello della prossima volta che la data
  arriva, oggi compreso. `/sondaggio 14/10 16/10`.
- Giorni e date si possono mescolare. Le date si ordinano e i doppioni si
  tolgono.
- **Rifiuti** (risposta al comando, nessun sondaggio):
  - parola non capita: «Non capisco «32/10»: scrivi i giorni (lun, mar, …) o
    le date (14/10).»;
  - data passata: «La data 3/10 è già passata.» (oggi non è passata);
  - più di 10 date: «Troppe date: al massimo 10.»;
  - un sondaggio già aperto: risposta al messaggio del sondaggio aperto, «C'è
    già un sondaggio aperto: chiudilo prima con /chiudi@<bot>.».
- **Telegram non conferma il sondaggio** (rete, 5xx, un rifiuto, la pausa
  dopo un 429): nessun sondaggio nel database, un avviso nel log (un errore,
  se Telegram l'ha rifiutato), e la risposta al comando, su due righe:

  ```
  Telegram non ha confermato il sondaggio: se non lo vedete, riprovate con:
  /sondaggio@<bot> mar gio
  ```

  Vera anche se il sondaggio è partito e la risposta si è persa. L'ultima riga
  è il comando da copiare, con gli argomenti come li ha scritti chi l'ha
  lanciato (nessuno, se non ce n'erano) e niente dopo: un punto finale si
  copierebbe con l'ultima data. Se il sondaggio può essere partito (rete, 5xx,
  una risposta illeggibile; non durante la pausa, non dopo un rifiuto), il bot
  ricorda il momento del tentativo: serve per i voti a un sondaggio
  sconosciuto (§4).
- **Fuori dal gruppo configurato** il bot non risponde a niente.

### 3.2 Il sondaggio

- Domanda: «Prossima volta?».
- Opzioni: le date come «mar 14/10», nel formato italiano (giorno abbreviato:
  lun mar mer gio ven sab dom; giorno e mese senza zeri iniziali), più in fondo una frase di «Nessuna di
  queste» (§3.6).
- Non anonimo, a risposta multipla: ognuno spunta tutte le date in cui c'è.
- Un sondaggio aperto alla volta nel gruppo.

### 3.3 Chi conta

Il roster (`config/roster.toml`, §5) elenca le sei persone: gio con ruolo
`master`, abe, emi, sem, sese e pippo con ruolo `giocatore`; gio e abe con
`chiude = true`. Il bot registra i voti di chiunque (servono per confrontare i
conteggi alla ripresa, §3.8), ma nelle regole contano solo le persone del
roster.

- **Ha votato**: chi ha una risposta non vuota (anche solo «Nessuna»). Chi
  toglie il voto (risposta vuota) torna fra chi non ha votato.
- **Presenti in una data**: chi l'ha spuntata. «Nessuna» insieme a delle date
  non toglie le date.
- Il voto più recente di una persona sostituisce il precedente.

### 3.4 Le regole delle date

Costanti: giocatori per giocare **4**; giocatori per «quasi» **3**; votanti
perché «quasi» valga **4**.

- **Possibile**: il master è presente e i giocatori presenti sono almeno 4.
- **Quasi**: hanno votato almeno 4 persone del roster, il master è presente e i
  giocatori presenti sono esattamente 3.
- **Fuori**: il master ha votato e non è presente; oppure i giocatori presenti
  più i giocatori che non hanno ancora votato sono meno di 4.
- **Nessuna data possibile** (il sondaggio è «impossibile»): tutte le date sono
  fuori.

### 3.5 I messaggi

Testo semplice, senza `parse_mode`. I nomi sono i soprannomi del roster. Le
**menzioni** sono entità `text_mention` con l'identificativo Telegram della
persona: notificano anche chi non ha un nome utente. Gli scostamenti delle
entità si contano in unità UTF-16, come vuole Telegram (un'emoji come 📅 ne
vale due). Le date nei messaggi hanno la forma delle opzioni («mar 14/10»).

1. **Quasi** — una volta per data, la prima volta che la data è quasi:
   «📅 mar 14/10: ci sono gio, abe, emi e sem, manca un giocatore. Non hanno
   ancora votato: sese, pippo.» I nomi dopo «Non hanno ancora votato» sono
   menzioni; se hanno votato tutti, la seconda frase non c'è.
2. **Possibile** — una volta per data, quando diventa possibile (di nuovo
   dopo un «non più possibile»): «✅ mar 14/10 va bene: ci sono gio, abe, emi,
   sem e sese.» Il sondaggio resta aperto.
3. **Non più possibile** — quando una data annunciata come possibile non lo è
   più: «⚠️ mar 14/10 non va più bene: sem ha tolto il voto.» (con più persone:
   «sem e sese hanno tolto il voto»). Se il bot non sa chi (dopo una ripresa,
   §3.8): «⚠️ mar 14/10 non va più bene: non ci sono più il master e quattro
   giocatori.»
4. **Impossibile** — quando tutte le date diventano fuori (di nuovo, se nel
   frattempo una era tornata in gioco):
   - con date in cui ci sono il master e almeno tre giocatori: «😬 Con quattro
     giocatori non ci si sta in nessuna di queste date. Con tre: mar 14/10
     (gio, abe, emi, sem). gio, abe: /chiudi@<bot> 14/10 per tenerla,
     /chiudi@<bot> rimanda per rifare il sondaggio sulla settimana dopo.»
     (più date: elenco separato da «; »);
   - senza: «😬 Con quattro giocatori non ci si sta in nessuna di queste date,
     e nemmeno con tre. gio, abe: /chiudi@<bot> rimanda per rifare il
     sondaggio sulla settimana dopo.»
   «gio, abe» sono menzioni delle persone con `chiude = true`.

Un annuncio conta come fatto solo dopo che Telegram l'ha accettato. Quali
annunci mandare si calcola dallo stato (voti) e dagli annunci già fatti, con una
funzione pura: rifarlo non ripete niente, e un messaggio non partito riparte al
giro seguente (§4).

### 3.6 «Nessuna di queste»

Una lista di frasi in `testi.py`, tutte di al massimo 100 caratteri (il limite
di Telegram per un'opzione) e tutte comincianti con «Nessuna». Il bot ne usa una
per sondaggio, a caso fra quelle non ancora usate; finite tutte, ricomincia, ma
non con l'ultima usata (e il giro nuovo comincia solo se il sondaggio parte). Le
frasi usate stanno nel database. La lista iniziale (Alberto la correggerà):

1. Nessuna: ho fallito il tiro salvezza contro la vita reale
2. Nessuna: ho tirato 1 sul calendario
3. Nessuna: il destino ha tirato con svantaggio
4. Nessuna: ho perso l'iniziativa contro la mia agenda
5. Nessuna: un mimic travestito da agenda si è mangiato la settimana
6. Nessuna: questa settimana i danni radiosi me li fa il lavoro
7. Nessuna: riposo lungo. Molto lungo.
8. Nessuna: ho perso la concentrazione, e con lei la settimana
9. Nessuna: il mio slot del martedì è esaurito
10. Nessuna: questa settimana sono un PNG
11. Nessuna: il mio personaggio è in un semipiano senza calendario
12. Nessuna: il master può dire che il mio personaggio dorme
13. Nessuna: lancio Velocità sulla settimana dopo
14. Nessuna: 20 naturale per trovare una scusa
15. Nessuna: il bardo scriverà comunque una canzone sulla mia assenza

### 3.7 Chiudere: `/chiudi`

Solo le persone con `chiude = true`. Altrimenti: «Il sondaggio lo chiudono gio o
abe.» (i nomi dal roster). Senza sondaggio aperto: «Non c'è nessun sondaggio
aperto.»

- **`/chiudi`**: il bot ferma il sondaggio (`stopPoll`) e scrive «🔒 Sondaggio
  chiuso. Date possibili: mar 14/10, gio 16/10.» oppure «🔒 Sondaggio chiuso.
  Nessuna data con il master e quattro giocatori.»
- **`/chiudi 14/10`** (una data del sondaggio, `g/m` o `g.m`, o il suo giorno,
  `mar`): ferma il sondaggio e scrive «🎲 Si gioca martedì 14/10.» (giorno per
  intero).
- **Rifiuti di `/chiudi`** (risposta al comando, il sondaggio resta aperto):
  - una data che non era nel sondaggio: «La data 15/10 non era nel
    sondaggio.»;
  - un giorno che nel sondaggio non c'è: «Nel sondaggio non c'è nessun
    venerdì.» («nessuna domenica»);
  - un giorno che nel sondaggio c'è più di una volta: «Nel sondaggio c'è più
    di un martedì: scrivi la data (14/10).» (il giorno per intero, con
    l'articolo giusto: «più di una domenica»; la data è la prima del sondaggio
    con quel giorno);
  - una parola non capita, o più di una parola: «Non capisco «boh»: scrivi una
    data del sondaggio (14/10), il suo giorno (mar) o rimanda.» (diverso dal
    rifiuto di `/sondaggio`).
- **`/chiudi rimanda`**: ferma il sondaggio, lancia un sondaggio nuovo sulla
  settimana dopo quella dell'ultima data, con gli stessi giorni della settimana
  del sondaggio chiuso e senza le date già passate, e scrive «🔁 Rimandiamo:
  nuovo sondaggio sulla settimana del 20/10.» (il lunedì della settimana del
  sondaggio nuovo, ricavato dalle sue date).
  - Il vecchio si chiude nel database insieme all'apertura del nuovo e al
    messaggio «🔁», in una transazione. Un'interruzione prima è recuperabile:
    il comando riletto trova il vecchio ancora aperto nel database, lo stop
    risponde che è già chiuso, e `rimanda` riprende (se il primo sondaggio
    nuovo era partito, nel gruppo ce ne sono due: caso raro, accettato).
  - Se Telegram non conferma il sondaggio nuovo, il vecchio si chiude e, nella
    stessa transazione, il bot scrive (le date del sondaggio nuovo, `g/m`, e
    il comando da solo sull'ultima riga, come in §3.1):

    ```
    🔒 Sondaggio chiuso. Telegram non ha confermato il sondaggio nuovo: se non lo vedete, lanciatelo con:
    /sondaggio@<bot> 21/10 23/10
    ```

    Nella stessa transazione ricorda il tentativo, se il sondaggio nuovo può
    essere partito (§3.1).
  - Se tutte le date della settimana dopo sono passate, il bot chiude il
    sondaggio e scrive «Le date del sondaggio sono passate: lo chiudo.», senza
    sondaggio nuovo.
- Se `stopPoll` fallisce perché il messaggio del sondaggio non c'è più
  (cancellato), il bot segna il sondaggio come chiuso e lo dice: «Il messaggio
  del sondaggio non c'è più: lo considero chiuso.»
- Se `stopPoll` risponde che il sondaggio è già chiuso (uno `stopPoll` di prima
  è passato, ma la risposta non è arrivata, o il processo è stato fermato prima
  di salvarlo), Telegram conferma che è fermo: il bot lo chiude, lo scrive nel
  log e procede come con un `/chiudi` normale («🔒…», «🎲…», o `rimanda`).
  Chiudere il sondaggio, per qualunque via, toglie la sua chiusura in sospeso.
- Se `stopPoll` non riesce per un altro motivo (rete, 5xx, un rifiuto, la pausa
  dopo un 429), il sondaggio resta aperto nel database e la chiusura resta **in
  sospeso**: il bot ricorda il sondaggio, il comando e il suo argomento, e
  nella stessa transazione accoda la risposta al comando, «Telegram non ha
  confermato la chiusura del sondaggio: riprovo da solo.». A ogni giro, finita
  l'eventuale pausa, il bot ritenta lo stop finché Telegram risponde che il
  sondaggio è fermo (o già chiuso, o che il messaggio non c'è più), e allora
  chiude come avrebbe fatto il comando («🔒…», con le date possibili di quel
  momento, «🎲…», o `rimanda`), con il messaggio nella stessa transazione della
  chiusura. Un rifiuto va nel log come errore una volta per processo, e lo
  stop si ritenta lo stesso. Se lo stop era passato, il nuovo tentativo trova
  il sondaggio già chiuso (il punto sopra).
- Mentre una chiusura è in sospeso:
  - `/sondaggio` risponde al comando «Il sondaggio di prima non è ancora
    chiuso: Telegram non ha confermato la chiusura. Riprovate fra poco.» (al
    posto di «C'è già un sondaggio aperto…», che sarebbe falso);
  - un altro `/chiudi` di chi può chiudere sostituisce l'argomento in sospeso
    con il suo (vale l'ultima decisione), non manda un altro stop e riceve la
    stessa risposta, «Telegram non ha confermato la chiusura del sondaggio:
    riprovo da solo.»; un `/chiudi` rifiutato non cambia niente;
  - l'avviso di un voto a un sondaggio sconosciuto è quello senza sondaggio
    aperto (§4).
- Il messaggio che dice la chiusura («🔒…», «🎲…», «Il messaggio del sondaggio
  non c'è più…») si salva insieme alla chiusura, nella stessa transazione: un
  processo fermato fra le due non lo perde. Con `rimanda`, «Il messaggio del
  sondaggio non c'è più…» parte prima del sondaggio nuovo, e quindi da solo.

### 3.8 La ripresa dopo il buio

Telegram conserva gli aggiornamenti di un bot per 24 ore; quelli più vecchi si
perdono, e nessuna API restituisce chi ha votato cosa. Il bot registra il
momento dell'ultima lettura riuscita. Quando una lettura riesce più di **23
ore** dopo la precedente (un'ora di margine sulle 24), dopo aver gestito gli
aggiornamenti ricevuti:

1. **Lo dice**: «🔌 Sono rimasto senza Telegram dal 12/10 alle 21:05 al 14/10
   alle 9:30. I comandi e i voti di quel periodo potrebbero non essermi
   arrivati.» (ore nel fuso `Europe/Zurich`).
2. **Se c'è un sondaggio aperto, lo ferma** (`stopPoll` restituisce i conteggi
   per opzione) e li confronta con i propri, calcolati su tutti i voti
   registrati (anche di chi non è nel roster):
   - uguali: «I conteggi del sondaggio sono gli stessi che avevo io.»;
   - diversi: «I conteggi del sondaggio sono diversi dai miei: mentre ero
     spento qualcuno ha votato o cambiato voto.».
3. **Lo riapre** con le date non ancora passate (stessa domanda, frase di
   «Nessuna» nuova) e **tiene buoni i voti registrati**: valgono per il
   sondaggio nuovo finché la persona non vota nel nuovo, e allora vale il voto
   nuovo. Messaggio: «Riapro il sondaggio. Ho già i voti di abe, emi e sem: se
   non avete cambiato idea, non serve rivotare. Non hanno ancora votato: sese,
   pippo.» (menzioni su chi non ha votato; parti omesse se vuote).
   Gli annunci già fatti restano validi (un «possibile» non si ripete).
4. Se nessuna data è ancora nel futuro: «Le date del sondaggio sono passate:
   lo chiudo.» e niente sondaggio nuovo.

Senza sondaggio aperto, il bot scrive solo il messaggio del punto 1.

## 4. Errori

- **Un messaggio che non parte** (rete, 5xx, 429 con `retry_after`): resta da
  mandare. A ogni giro del ciclo (long polling di 25 secondi) il bot ricalcola
  gli annunci dei sondaggi aperti e manda quelli mancanti. Un 429 si rispetta:
  nessun invio prima di `retry_after`, contato da quando arriva la risposta;
  nel frattempo il bot non prova nemmeno (un solo avviso nel log, quello del
  429), e un `/sondaggio` o un `/chiudi` ricevono la risposta «Telegram non ha
  confermato…» (§3.1, §3.7), che parte finita l'attesa.
- **Un annuncio rifiutato** da Telegram (4xx) va nel log come errore e non
  ferma gli annunci seguenti; non conta come fatto. Lo stesso testo avrebbe lo
  stesso rifiuto: il bot non lo riprova fino al prossimo avvio (un errore nel
  log, non uno a ogni giro).
- **Aggiornamenti doppi** dopo un riavvio (l'offset si salva dopo aver gestito
  l'aggiornamento): un voto sostituisce il precedente, un comando `/sondaggio` con
  un sondaggio già aperto risponde «già aperto», gli annunci sono calcolati
  dallo stato. Nessun doppione.
- **Un voto per un sondaggio sconosciuto**: Telegram manda a un bot solo i
  voti dei suoi sondaggi, quindi è un sondaggio del bot che il bot non ha
  registrato (una risposta persa, o il piano reale nella chat privata di
  Alberto). Va sempre nel log, con l'identificativo del sondaggio. Nel gruppo,
  una sola volta per sondaggio e solo se negli ultimi 7 giorni Telegram non ha
  confermato un sondaggio che può essere partito (di `/sondaggio`, o il
  sondaggio nuovo di `/chiudi rimanda`; §3.1). Senza un sondaggio aperto: «Ho
  ricevuto un voto per un sondaggio che non conosco: forse quello che Telegram
  non mi ha confermato. Rilanciate /sondaggio@<bot> e votate lì.» Con un
  sondaggio aperto, in risposta al suo messaggio: «Ho ricevuto un voto per un
  sondaggio che non conosco: forse quello che Telegram non mi ha confermato.
  Il sondaggio che conto è questo: votate qui.» Il tentativo resta anche dopo
  un `/sondaggio` riuscito. Senza un tentativo recente, solo il log: così i
  voti del piano reale non finiscono nel gruppo del party. Un voto per un
  sondaggio che il bot conosce ma che non è aperto si ignora. Per l'avviso, un
  sondaggio con la chiusura in sospeso (§3.7) non conta come aperto: chi può
  chiudere l'ha già chiuso.
- **Il ciclo non si ferma** per un errore: lo registra e continua (come
  `cicli.py` di `radiant-selfie-machine`).
- **Il token non finisce mai nei log** (stessa tecnica del client dei selfie:
  niente testo delle eccezioni di httpx, niente concatenazione, logger `httpx`
  a WARNING).
- **Un solo processo, un solo filo**: niente gare.

## 5. I pezzi

Repo `~/git/python/prossima-volta`, pacchetto `prossima`, Python 3.12 con uv,
httpx, `tzdata` (il fuso nel container). Nessuna parte web, nessuna porta.

| file | compito |
|---|---|
| `src/prossima/regole.py` | Puro: date (default, giorni, date, rifiuti), etichette, conteggi, classificazione (possibile, quasi, fuori), impossibile, e `annunci_da_fare(stato, fatti) -> list[Annuncio]`. |
| `src/prossima/testi.py` | I testi dei messaggi, con le menzioni come entità (scostamenti UTF-16), e le frasi di «Nessuna». |
| `src/prossima/store.py` | SQLite: sondaggi, voti (di tutti), annunci fatti, frasi usate, offset del bot, momento dell'ultima lettura. Una connessione per operazione, WAL. |
| `src/prossima/telegram.py` | Il client: `aggiornamenti`, `io` (getMe), `manda_sondaggio`, `scrivi` (con entità e risposta a un messaggio), `ferma_sondaggio`, `registra_comandi`. Errori `TelegramError` senza token; `TelegramTroppeRichieste` con `retry_after`. |
| `src/prossima/config.py` | Variabili d'ambiente e roster. |
| `src/prossima/bot.py` | Smista gli aggiornamenti (comandi, `poll_answer`), manda gli annunci, fa la ripresa. |
| `src/prossima/principale.py` | Avvio e ciclo; il battito per il controllo di salute. |

**Configurazione** (`config/prossima.env`, mai nel repo):
`PV_BOT_TOKEN`, `PV_GRUPPO` (l'identificativo del gruppo del party),
`PV_ROSTER=/config/roster.toml`, `PV_DB=/data/prossima.sqlite`,
`PV_BATTITO=/data/battito`, `PV_FUSO=Europe/Zurich`. Per il piano reale:
`PV_REALE_CHAT` (l'identificativo di Alberto).

**Roster** (`config/roster.toml`, mai nel repo; nel repo solo
`config.esempio/roster.toml` con identificativi finti):

```toml
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
```

(e così via per emi, sem, sese, pippo). Esattamente un master; soprannomi e
identificativi unici; un valore sbagliato ferma il servizio con un messaggio
chiaro.

**Container**: un servizio, `restart: unless-stopped`, volumi `./dati:/data` e
`./config:/config:ro`. Controllo di salute: il battito (un file che il ciclo
tocca a ogni giro) ha meno di 2 minuti.

**Il bot**: nuovo, da @BotFather, privacy attiva (il default), aggiunto al
gruppo del party. All'avvio registra i comandi (`setMyCommands`): `sondaggio`
(«Sondaggio per la prossima volta») e `chiudi` («Chiude il sondaggio»).

## 6. Prove

- **Veloci** (default di `pytest`), con un Telegram finto:
  - regole a tabella: date di default (anche a cavallo dell'anno e di
    domenica), giorni, date, mescolati, rifiuti; conteggi; possibile, quasi,
    fuori; impossibile (compreso il master che ha votato senza scegliere una
    data); `annunci_da_fare` (ogni annuncio una volta, «non più possibile» con
    chi ha tolto il voto, «possibile» di nuovo dopo).
  - testi: le menzioni cadono sui nomi giusti con emoji davanti (UTF-16); tutte
    le frasi di «Nessuna» stanno nei 100 caratteri e cominciano con «Nessuna»;
    rotazione senza ripetizioni.
  - store, config (roster sbagliati), client Telegram con un trasporto finto di
    httpx (nessun token nei messaggi d'errore).
  - il percorso completo nel bot: `/sondaggio`, voti, annunci, `/chiudi` nelle tre
    forme, rifiuti, invio fallito e ripreso, ripresa dopo il buio (conteggi
    uguali e diversi, date passate).
- **Piano reale** (`-m reale`), con il bot vero nella chat privata di Alberto
  (`PV_REALE_CHAT`), **a servizio fermo** (due lettori dello stesso bot si
  rubano gli aggiornamenti): sondaggio non anonimo a risposta multipla, il voto
  di Alberto che arriva come `poll_answer` con il suo identificativo e le
  opzioni, un messaggio con una menzione, `stopPoll` con i conteggi,
  `setMyCommands`.
- **A mano, nel gruppo**: `/sondaggio@<bot>` dal menu arriva al bot con la privacy
  attiva; le menzioni notificano.
- **`docs/differenze-fra-test-e-realta.md`**, scritto prima dei finti.

## 7. Fuori perimetro

- Frasi di «Nessuna» generate da Ollama.
- Ricordare la data scelta a ridosso della sessione, legarla a `ctc`.
- Più gruppi, più sondaggi aperti insieme.
