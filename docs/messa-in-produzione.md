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
5. Chiedi alle altre cinque persone del roster di scrivere anche loro `/start`
   al bot in privato, una volta. Il bot le menziona per identificativo («Non
   hanno ancora votato: …», «gio, abe: /chiudi…»), e che cosa succede a una
   menzione verso chi non gli ha mai scritto non è verificato: potrebbe non
   notificare, o Telegram potrebbe rifiutare il messaggio (v.
   `docs/differenze-fra-test-e-realta.md`). Nemmeno con `/start` la notifica è
   verificata nel gruppo: il controllo a mano (punto 5) prova i due casi.

## 2. Il codice

Porta il repository sul server (un `git clone`, o una copia della cartella senza
`.venv`, `dati` e `config`), entra nella cartella e:

```bash
mkdir -p config dati
sudo chown 10001:10001 dati
```

Nel container il bot gira come utente 10001, senza privilegi (`Dockerfile`):
`dati`, dove scrive il database e il battito, deve essere suo.

## 3. La configurazione

```bash
cp config.esempio/prossima.env config/prossima.env
cp config.esempio/roster.toml config/roster.toml
cp config.esempio/frasi.txt config/frasi.txt
chmod 600 config/prossima.env
chmod 640 config/roster.toml config/frasi.txt
sudo chgrp 10001 config/roster.toml config/frasi.txt
```

`prossima.env` lo legge Docker, non il bot: resta solo tuo. Il roster e le frasi
li legge il bot, attraverso il gruppo 10001; tu ne resti il proprietario e li
modifichi come sempre.

In `config/prossima.env` metti il token. In `config/roster.toml` metti gli
identificativi Telegram veri delle sei persone (i numeri: li ha già il roster di
`ctc`, sul Mac in `~/.config/close-the-circle/roster.toml`, chiave
`telegram_id`).

In `config/frasi.txt` ci sono le frasi di «Nessuna di queste»: quelle d'esempio,
a cui aggiungere quelle che nel repository non stanno, come le battute sulle
persone del gruppo. Le regole sono in testa al file.

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
<PV_GRUPPO>, 6 persone nel roster, frasi di «Nessuna»: <quante>, domanda «Prossima volta?», giorni di sempre: lun mar mer gio ven dom». Un roster, un
file delle frasi o un valore di `prossima.env` sbagliato ferma l'avvio con una riga «configurazione: …» che dice cosa
correggere. Dopo aver corretto: `docker compose up -d`. Il riavvio automatico del
container (`restart: unless-stopped`) non rilegge `prossima.env`: Docker lo legge
quando crea il container, e solo `up -d` ne crea uno nuovo.

Dopo un paio di minuti `docker compose ps` mostra il servizio `healthy`: il
controllo di salute guarda il battito, un file che il ciclo del bot tocca a ogni
giro (`/data/battito`, deve avere meno di 2 minuti).

Prova anche `docker compose stop prossima`: deve tornare subito, non dopo 10
secondi (`init: true` in `compose.yaml` fa arrivare il segnale a Python). Poi
`docker compose start prossima`.

## 5. A mano, nel gruppo

- Dal menu dei comandi (il tasto `/` accanto al campo di testo) scegli
  `/sondaggio`: il menu scrive `/sondaggio@<nome_del_bot>`, e il sondaggio della
  settimana seguente compare nel gruppo, senza il sabato (con `/sondaggio con
  sabato` c'è anche quello).
- Gli annunci arrivano due minuti dopo l'ultimo voto, non subito: è voluto.
- La prima volta che arriva «impossibile» con i bottoni: chi non può chiudere
  e ne tocca uno vede l'avviso «Il sondaggio lo chiude Gio (o Abe, in
  emergenza).»; il tocco di Gio fa quello che dice il bottone, e i bottoni
  spariscono.
- `/aiuto` non serve provarlo nel gruppo: il piano reale (punto 6) manda le
  stesse istruzioni nella chat privata.
- Quando arriva il primo annuncio con dei nomi («Martedì ci siamo quasi. Pippo,
  ci sei?»), chiedi alle persone nominate se hanno ricevuto la notifica. Il controllo
  copre due casi: una persona che ha già scritto `/start` al bot (punto 1) e
  una che non l'ha ancora fatto (finché qualcuno non l'ha fatto, è il momento).
  Se l'annuncio non compare nel gruppo, cerca nel log «annuncio rifiutato da
  Telegram». Il piano reale non prova né l'uno né l'altro nel gruppo: lì il bot
  menziona solo te, in privato.
- Chiudi il sondaggio di prova con `/chiudi`.

## 6. Il piano reale

Si lancia **a servizio fermo**: due lettori dello stesso bot si rubano gli
aggiornamenti. Il piano reale legge `getUpdates` senza offset e non conferma
niente, quindi alla ripartenza il servizio ritrova tutto quello che è arrivato
nel frattempo.

In `config/prossima.env` (punto 3) togli il `#` dalla riga `PV_REALE_CHAT=` e
scrivi il tuo identificativo subito dopo il segno `=`, senza altro sulla riga
(Docker terrebbe tutto quello che c'è dopo come valore). Poi:

```bash
docker compose stop prossima
docker compose --profile prova run --rm --build prova
docker compose start prossima
```

Un test manda nella chat privata un messaggio con un bottone e aspetta fino a
tre minuti che tu lo tocchi: compare l'avviso «🧪 Tocco ricevuto», e il bottone
sparisce. Un altro manda le istruzioni di `/aiuto` e aspetta fino a tre minuti
che tu tocchi l'ultimo comando (quello di «rimanda»), lo incolli nella chat e lo
mandi: il tocco deve copiarlo intero, non farlo partire. Un altro manda un sondaggio di prova e aspetta fino a tre minuti: fai
quello che dice la domanda (spunta la prima e la terza data e vota, togli solo
la terza, ritira il voto, spunta la seconda e vota). Il piano reale è verde solo se **non
salta niente**: un test saltato non è un test superato, e `-rs` dice quale
variabile mancava.

## Cambiare le frasi

Modifica `config/frasi.txt` e riavvia il servizio:

```bash
docker compose restart prossima
docker compose logs --tail 5 prossima
```

Basta `restart`: il file lo legge il bot quando parte. La riga dell'avvio nel
log dice quante frasi ha letto; una frase troppo lunga o ripetuta ferma l'avvio
con una riga «configurazione: …» che dice quale riga correggere (dopo, di nuovo
`docker compose restart prossima`). Se la riga dice «Permission denied», il file
ha perso il gruppo (succede con un editor che lo riscrive da capo): `sudo chgrp
10001 config/frasi.txt`, poi di nuovo `restart`. Il bot propone prima le frasi che non ha
ancora usato in questo giro, quindi anche quelle nuove.

## Cambiare la domanda

La domanda del sondaggio sta in `config/prossima.env`, nella riga `PV_DOMANDA=`
(senza, «Prossima volta?»). Dopo averla cambiata:

```bash
docker compose up -d
docker compose logs --tail 5 prossima
```

Qui non basta `restart`: `prossima.env` Docker lo legge solo quando crea il
container. La riga dell'avvio nel log riporta la domanda. Al massimo 300
caratteri, un'emoji ne vale due; con un `#` nella domanda, mettila fra
virgolette, altrimenti Docker legge il resto come un commento. Vale dal
sondaggio seguente: quello aperto resta com'è.

## Cambiare i giorni di sempre

I giorni del sondaggio senza parametri stanno in `config/prossima.env`, nella
riga `PV_GIORNI=` (per esempio `PV_GIORNI=lun mar mer gio ven dom`; senza, tutti
tranne il sabato). Come per la domanda, dopo averli cambiati:

```bash
docker compose up -d
docker compose logs --tail 5 prossima
```

La riga dell'avvio nel log riporta i giorni, e `/aiuto` li dice nel gruppo
(«sabato escluso»). Chi lancia il sondaggio aggiunge un giorno escluso con
`/sondaggio con sabato`.

## Se il bot resta bloccato

Il bot ritenta da solo quello che Telegram non conferma, e a ogni avvio riprova
una volta quello che si è fermato per un altro errore. Se anche dopo un riavvio
(`docker compose restart prossima`) resta fermo su una chiusura o su una
ripresa (nel gruppo `/sondaggio` risponde sempre «Telegram non ha ancora
confermato la chiusura del sondaggio di prima…» o «Non sono riuscito a
completare la chiusura del sondaggio di prima…», e un `/chiudi` non lo
sblocca; nel log tornano «chiusura del sondaggio N non completata» o «ripresa
del sondaggio N non riuscita»), prima guarda nel log il perché: «chiusura del
sondaggio N rifiutata da Telegram» (il bot tolto dal gruppo, per esempio) si
sistema su Telegram. Poi, a servizio fermo:

```bash
docker compose stop prossima
docker compose run --rm prossima prossima sblocca
docker compose start prossima
```

`prossima sblocca` toglie la chiusura in sospeso e la ripresa e, se una delle
due era del sondaggio aperto, chiude nel database quel sondaggio. Un sondaggio
aperto senza niente in sospeso non lo tocca: il comando si può provare senza
rischi. Nel log scrive una riga per ogni cosa che ha tolto («niente da
sbloccare», se non c'era niente). Nel gruppo non scrive niente. Su Telegram il
sondaggio chiuso così resta com'è e il bot ne ignora i voti: se serve, lanciane
uno nuovo con `/sondaggio`.

## Aggiornare

```bash
git pull && docker compose up -d --build
```
