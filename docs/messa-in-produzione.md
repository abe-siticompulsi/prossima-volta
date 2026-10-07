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
<PV_GRUPPO>, 6 persone nel roster». Un roster o un valore di `prossima.env`
sbagliato ferma l'avvio con una riga «configurazione: …» che dice cosa
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
  settimana seguente compare nel gruppo.
- Quando arriva il primo annuncio con dei nomi («Non hanno ancora votato: …»),
  chiedi alle persone nominate se hanno ricevuto la notifica.
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
