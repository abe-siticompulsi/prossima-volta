# Annunci brevi, il sabato e /aiuto — piano

> **Per chi esegue:** sub-skill: superpowers:executing-plans (eseguito nella sessione che l'ha scritto, con
> TDD e una revisione indipendente alla fine). I passi usano le caselle (`- [ ]`).

**Obiettivo:** annunci più brevi e naturali, mandati dopo 2 minuti senza voti nuovi e accorpati per tipo;
il sabato fuori dai giorni di sempre (`PV_GIORNI`, `con sabato`, giorni per intero); il comando `/aiuto`.

**Architettura:** `regole` decide quali annunci servono (regole nuove per «quasi», ordine per tipo) e legge
i giorni; `testi` scrive un messaggio per gruppo di annunci dello stesso tipo, con i nomi con la maiuscola e
le date dette per giorno; il bot aspetta 2 minuti dall'ultimo voto prima di annunciare, raggruppa e risponde a
`/aiuto`; `config` legge `PV_GIORNI`.

**Tecnologie:** Python 3.12, uv, pytest, ruff. Nessuna dipendenza nuova.

## Vincoli di tutto il piano

- Spec: `docs/superpowers/specs/2026-10-07-prossima-volta-design.md`, §2, §3.1, §3.5, §3.7, §3.9, §5, §6
  (commit 4b59806 e 46d8157). I testi si copiano alla lettera da lì.
- Emoji solo ✅ (possibile) e 😬 (impossibile); «quasi» e «non più» senza emoji.
- In «impossibile» si menziona solo il master (se non ha `chiude = true`, chi ce l'ha).
- `ATTESA_ANNUNCI = 2 minuti`, in memoria; i comandi rispondono subito.
- Un messaggio di errore di configurazione non ripete il valore della variabile.
- Commit in inglese, brevi, con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Alla fine di ogni task: `uv run pytest -q` e `uv run ruff check src tests` puliti.

## I file

| File | Cosa cambia |
|---|---|
| `src/prossima/regole.py` | `GIORNI_DI_SEMPRE`, `giorno_della_parola`, `ConSbagliato`, `date_del_comando` con «con» e i giorni di sempre, giorni per intero anche in `data_da_chiudere`; `annunci_da_fare` con le regole nuove di «quasi» e l'ordine per tipo |
| `src/prossima/testi.py` | `nome` (maiuscola), menzioni con «e»; `una_settimana`, `giorno_detto`, `date_dette`; `chi_chiude`, `solo_chi_chiude(roster)`; `annunci(gruppo, …)` al posto di `annuncio`; `rifiuto(r, nome_bot)` con `ConSbagliato`; `aiuto` |
| `src/prossima/config.py` | `Impostazioni.giorni` da `PV_GIORNI` |
| `src/prossima/bot.py` | `giorni`, `attesa_annunci`, `_ultimo_voto`; annunci raggruppati e in attesa; `/aiuto`; `COMANDI` |
| `src/prossima/chiusura.py` | `solo_chi_chiude(self._roster)` |
| `src/prossima/principale.py` | passa `giorni`; la riga dell'avvio li dice |
| `tests/…` | le prove nuove e quelle dei testi vecchi aggiornate |
| `docs/…`, `config.esempio/prossima.env` | guida, piano principale («Deviazioni»), esempio di configurazione |

---

### Task 1: I giorni di sempre, «con» e i giorni per intero

**File:** `src/prossima/regole.py`, `src/prossima/config.py`, `src/prossima/bot.py`, `src/prossima/testi.py`,
`src/prossima/principale.py`; prove in `tests/test_date.py`, `tests/test_config.py`, `tests/test_bot.py`,
`tests/test_testi.py`.

**Interfacce prodotte:**
- `regole.GIORNI_DI_SEMPRE: tuple[int, ...] = (0, 1, 2, 3, 4, 6)`
- `regole.giorno_della_parola(parola: str) -> int | None`
- `regole.ConSbagliato(Rifiuto)`
- `regole.date_del_comando(parole, oggi, giorni_di_sempre=GIORNI_DI_SEMPRE) -> list[date]`
- `config.Impostazioni.giorni: tuple[int, ...]`
- `Bot(..., giorni: Sequence[int] = regole.GIORNI_DI_SEMPRE)`
- `testi.rifiuto(r, nome_bot: str) -> Testo`

- [ ] **Passo 1: le prove che falliscono**

`tests/test_date.py` (la prova dei sette giorni diventa quella dei giorni di sempre):

```python
def test_senza_parole_i_giorni_di_sempre_senza_il_sabato():
    assert regole.date_del_comando([], OGGI) == [d(g) for g in ("13/10", "14/10", "15/10", "16/10", "17/10", "19/10")]


def test_i_giorni_di_sempre_si_scelgono():
    assert regole.date_del_comando([], OGGI, (0, 1)) == [d("13/10"), d("14/10")]


@pytest.mark.parametrize("parole", [["con", "sabato"], ["con", "sab"], ["CON", "Sabato"]])
def test_con_aggiunge_un_giorno_a_quelli_di_sempre(parole):
    assert regole.date_del_comando(parole, OGGI) == [d("13/10") + timedelta(days=i) for i in range(7)]


def test_con_un_giorno_che_c_e_gia_non_cambia_niente():
    assert regole.date_del_comando(["con", "dom"], OGGI) == regole.date_del_comando([], OGGI)


@pytest.mark.parametrize("parole", [["con"], ["con", "14/10"], ["con", "xyz"], ["mar", "con", "sab"]])
def test_con_usato_male(parole):
    with pytest.raises(regole.ConSbagliato):
        regole.date_del_comando(parole, OGGI)


@pytest.mark.parametrize("scritta", ["martedì", "martedi", "Martedì", "mar"])
def test_i_giorni_per_intero(scritta):
    assert regole.date_del_comando([scritta], OGGI) == [d("14/10")]


def test_chiudi_con_il_giorno_per_intero():
    assert regole.data_da_chiudere("martedì", [d("14/10"), d("16/10")], OGGI) == d("14/10")
```

`tests/test_config.py`:

```python
def test_senza_pv_giorni_i_giorni_di_sempre(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path)).giorni == (0, 1, 2, 3, 4, 6)


def test_i_giorni_da_pv_giorni(tmp_path):
    assert config.da_ambiente(ambiente(tmp_path, PV_GIORNI="ven lun  mercoledì lun")).giorni == (0, 2, 4)


def test_un_giorno_sconosciuto_in_pv_giorni(tmp_path):
    with pytest.raises(ConfigurazioneErrata, match="PV_GIORNI: i giorni si scrivono") as errore:
        config.da_ambiente(ambiente(tmp_path, PV_GIORNI="lun SEGRETO"))
    assert "SEGRETO" not in str(errore.value)
```

e `giorni=regole.GIORNI_DI_SEMPRE` in `test_le_impostazioni_dall_ambiente`.

`tests/test_bot.py`: `SETTIMANA` senza «sab 18/10»; una prova nuova:

```python
def test_con_sabato(bot, telegram):
    bot.ricevi([comando("/sondaggio con sabato")])
    assert telegram.ultimo_sondaggio["opzioni"][:-1] == [
        "lun 13/10", "mar 14/10", "mer 15/10", "gio 16/10", "ven 17/10", "sab 18/10", "dom 19/10"
    ]


def test_con_usato_male_risponde_come_si_scrive(bot, telegram):
    bot.ricevi([comando("/sondaggio mar con sab")])
    assert telegram.scritti() == ["Per aggiungere un giorno a quelli di sempre: /sondaggio@ProssimaVoltaBot con sabato."]
    assert telegram.di_tipo("manda_sondaggio") == []


def test_i_giorni_di_sempre_dalla_configurazione(riavvia, telegram):
    riavvia(giorni=(1, 3)).ricevi([comando("/sondaggio")])
    assert telegram.ultimo_sondaggio["opzioni"][:-1] == ["mar 14/10", "gio 16/10"]
```

- [ ] **Passo 2: farle fallire** — `uv run pytest -q tests/test_date.py tests/test_config.py tests/test_bot.py`:
  falliscono per `ConSbagliato`, `giorni` e i sei giorni.

- [ ] **Passo 3: il codice**

`regole.py`, dopo `GIORNI_INTERI`:

```python
# I giorni di sempre di `/sondaggio`: tutti tranne il sabato, che per la maggior
# parte delle settimane non va bene a nessuno (`PV_GIORNI` li cambia).
GIORNI_DI_SEMPRE = (0, 1, 2, 3, 4, 6)
CON = "con"
# «mar», «martedì» e «martedi»: come lo scrive chi usa il telefono.
_NOMI_DEI_GIORNI = {
    **{g: i for i, g in enumerate(GIORNI)},
    **{g: i for i, g in enumerate(GIORNI_INTERI)},
    **{g.replace("ì", "i"): i for i, g in enumerate(GIORNI_INTERI)},
}


def giorno_della_parola(parola: str) -> int | None:
    """Il giorno della settimana di una parola («mar», «Martedì», «martedi» →
    1), o None se la parola non è un giorno."""
    return _NOMI_DEI_GIORNI.get(parola.lower())
```

(`giorno_della_parola` va definita prima di `_data_della_parola`), il rifiuto:

```python
class ConSbagliato(Rifiuto):
    """«con» non per primo, da solo, o seguito da qualcosa che non è un giorno."""
```

in `_data_della_parola` il giorno della settimana:

```python
    settimanale = giorno_della_parola(parola)
    if settimanale is not None:
        return lunedi_seguente(oggi) + timedelta(days=settimanale)
```

`date_del_comando`:

```python
def date_del_comando(
    parole: Sequence[str], oggi: date, giorni_di_sempre: Sequence[int] = GIORNI_DI_SEMPRE
) -> list[date]:
    """Le date di `/sondaggio`. Senza parole, i giorni di sempre della settimana
    seguente; con «con» e dei giorni, quei giorni più quelli di sempre; con
    giorni (abbreviati o per intero) quei giorni della settimana seguente; con
    date, quelle date. Giorni e date si mescolano; il risultato è ordinato,
    senza doppioni. La prima parola che non va ferma tutto."""
    lunedi = lunedi_seguente(oggi)
    if not parole:
        return [lunedi + timedelta(days=g) for g in sorted(set(giorni_di_sempre))]
    if parole[0].lower() == CON:
        aggiunti = [giorno_della_parola(p) for p in parole[1:]]
        if not aggiunti or None in aggiunti:
            raise ConSbagliato()
        giorni = set(giorni_di_sempre) | {g for g in aggiunti if g is not None}
        return [lunedi + timedelta(days=g) for g in sorted(giorni)]
    if any(p.lower() == CON for p in parole):
        raise ConSbagliato()
    scelte = {_data_della_parola(parola, oggi) for parola in parole}
    if len(scelte) > MASSIMO_DATE:
        raise TroppeDate()
    return sorted(scelte)
```

e in `data_da_chiudere` il giorno con `giorno_della_parola(parola)` al posto di `minuscola in GIORNI` /
`GIORNI.index(minuscola)`.

`config.py`: `giorni: tuple[int, ...]` in `Impostazioni`, `giorni=_giorni(env)` in `da_ambiente`, e

```python
def _giorni(env: Mapping[str, str]) -> tuple[int, ...]:
    """I giorni di sempre di `/sondaggio`, o quelli predefiniti. Il messaggio
    d'errore non ripete il valore, come per le altre variabili."""
    parole = (env.get("PV_GIORNI") or "").split()
    if not parole:
        return GIORNI_DI_SEMPRE
    giorni = [giorno_della_parola(p) for p in parole]
    if None in giorni:
        raise ConfigurazioneErrata(
            "PV_GIORNI: i giorni si scrivono lun mar mer gio ven sab dom (o per intero), "
            "separati da spazi"
        )
    return tuple(sorted({g for g in giorni if g is not None}))
```

`bot.py`: parametro `giorni`, `self._giorni = tuple(giorni)`, `regole.date_del_comando(parole, self._oggi(),
self._giorni)` e `testi.rifiuto(r, self._nome)`. `testi.rifiuto(r, nome_bot)` con:

```python
        case regole.ConSbagliato():
            return Testo(
                f"Per aggiungere un giorno a quelli di sempre: /sondaggio@{nome_bot} con sabato."
            )
```

`principale.py`: `giorni=imp.giorni`, e nella riga dell'avvio `giorni di sempre: lun mar mer gio ven dom`
(`" ".join(regole.GIORNI[g] for g in imp.giorni)`).

- [ ] **Passo 4: la suite** — le prove che votavano il sabato in un `/sondaggio` senza parole si aggiornano
  (con `con sabato` o con un altro giorno): si cerca con `uv run pytest -q`. Poi tutto verde e ruff pulito.

- [ ] **Passo 5: commit** — `days: Saturday out by default (PV_GIORNI), "con sabato", day names in full`.

---

### Task 2: Nomi con la maiuscola, date dette, chi chiude

**File:** `src/prossima/testi.py`, `src/prossima/chiusura.py`; prove in `tests/test_testi.py`,
`tests/test_chiudi.py`.

**Interfacce prodotte:** `testi.nome(persona) -> str`; `_Scrittura.menzioni(persone, ultima=", ")`;
`testi.una_settimana(date_) -> bool`; `testi.giorno_detto(giorno, solo_il_giorno) -> str`;
`testi.date_dette(giorni, solo_il_giorno) -> str`; `testi.chi_chiude(roster) -> str`;
`testi.solo_chi_chiude(roster) -> Testo`.

- [ ] **Passo 1: le prove che falliscono** (`tests/test_testi.py`):

```python
def test_i_nomi_con_la_maiuscola():
    assert testi.nome(GIO) == "Gio"
    t = testi.riapro((ABE,), (SESE, PIPPO))
    assert t.testo.endswith("Non hanno ancora votato: Sese, Pippo.")
    assert menzionati(t) == [("Sese", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]


def test_la_maiuscola_non_sposta_le_menzioni():
    strano = Persona("èsè🎲", 7, "giocatore")
    t = testi.riapro((), (strano,))
    assert menzionati(t) == [("Èsè🎲", 7)]


def test_le_date_dette():
    settimana = [d("13/10"), d("14/10"), d("16/10")]
    assert testi.una_settimana(settimana)
    assert not testi.una_settimana([d("19/10"), d("20/10")])
    assert testi.date_dette([d("16/10"), d("13/10")], True) == "lunedì e giovedì"
    assert testi.date_dette([d("13/10"), d("14/10"), d("16/10")], False) == "lunedì 13, martedì 14 e giovedì 16"


def test_chi_chiude():
    assert testi.solo_chi_chiude(ROSTER).testo == "Il sondaggio lo chiude Gio (o Abe, in emergenza)."
    solo_gio = Roster((GIO, replace(ABE, chiude=False), EMI))
    assert testi.chi_chiude(solo_gio) == "chiude Gio"
    senza_master = Roster((replace(GIO, chiude=False), ABE, replace(EMI, chiude=True)))
    assert testi.chi_chiude(senza_master) == "chiudono Abe e Emi"
```

(`menzionati` esiste già in `test_testi.py`; `replace` da `dataclasses`, `Roster` e `Persona` da
`prossima.regole`.) In `test_chiudi.py` la risposta a chi non può chiudere diventa «Il sondaggio lo chiude Gio
(o Abe, in emergenza).».

- [ ] **Passo 2: farle fallire.**

- [ ] **Passo 3: il codice** (`testi.py`):

```python
def nome(persona: Persona) -> str:
    """Il soprannome con l'iniziale maiuscola: «gio» → «Gio»."""
    return persona.soprannome[:1].upper() + persona.soprannome[1:]


def _nomi(persone: Sequence[Persona]) -> list[str]:
    return [nome(p) for p in persone]


def _maiuscola(testo: str) -> str:
    return testo[:1].upper() + testo[1:]


def una_settimana(date_sondaggio: Sequence[date]) -> bool:
    """Tutte le date nella stessa settimana di calendario, da lunedì a domenica."""
    return len({regole.lunedi(g) for g in date_sondaggio}) <= 1


def giorno_detto(giorno: date, solo_il_giorno: bool) -> str:
    """«martedì», o «martedì 13» se il sondaggio non sta in una settimana."""
    intero = regole.GIORNI_INTERI[giorno.weekday()]
    return intero if solo_il_giorno else f"{intero} {giorno.day}"


def date_dette(giorni: Sequence[date], solo_il_giorno: bool) -> str:
    """«lunedì e giovedì», nell'ordine del calendario."""
    return elenco([giorno_detto(g, solo_il_giorno) for g in sorted(giorni)])


def chi_chiude(roster: regole.Roster) -> str:
    """«chiude Gio (o Abe, in emergenza)»: il master, e chi può chiudere quando
    il master non c'è. Se il master non può chiudere, chi può."""
    master = roster.master
    if not master.chiude:
        chiudono = roster.chi_chiude
        verbo = "chiude" if len(chiudono) == 1 else "chiudono"
        return f"{verbo} {elenco(_nomi(chiudono))}"
    altri = [p for p in roster.chi_chiude if p != master]
    if not altri:
        return f"chiude {nome(master)}"
    return f"chiude {nome(master)} (o {elenco(_nomi(altri), 'o')}, in emergenza)"


def solo_chi_chiude(roster: regole.Roster) -> Testo:
    return Testo(f"Il sondaggio lo {chi_chiude(roster)}.")
```

`_Scrittura.menzione` scrive e misura `nome(persona)`; `menzioni(persone, ultima=", ")` mette `ultima` prima
dell'ultimo nome («Sese e Pippo» con `ultima=" e "`). `chiusura.py`: `testi.solo_chi_chiude(self._roster)`.

- [ ] **Passo 4: la suite** — le prove con i nomi minuscoli nei testi (riapro, chi chiude) si aggiornano.
- [ ] **Passo 5: commit** — `texts: nicknames capitalised, dates said as days, "lo chiude Gio (o Abe, in emergenza)"`.

---

### Task 3: Le regole degli annunci

**File:** `src/prossima/regole.py`; prove in `tests/test_regole.py`.

- [ ] **Passo 1: le prove che falliscono**

```python
def test_quasi_solo_se_qualcuno_non_ha_votato():
    """Hanno votato tutti: il 14/10 è quasi, ma non c'è nessuno da chiamare (e
    con tutti i voti nessuna data può più arrivare a quattro: «impossibile»)."""
    s = stato(gio="14/10", abe="14/10", emi="14/10", sem="14/10", sese="16/10", pippo="16/10")
    assert [type(a) for a in regole.annunci_da_fare(s, Fatti())] == [regole.Impossibile]


def test_quasi_non_con_una_data_possibile():
    s = stato(gio="14/10 16/10", abe="14/10 16/10", emi="14/10 16/10", sem="14/10 16/10", sese="14/10")
    assert [type(a) for a in regole.annunci_da_fare(s, Fatti())] == [regole.Possibile]


def test_gli_annunci_per_tipo():
    """Prima i «non più», poi i «possibile», poi i «quasi», e «impossibile» in fondo."""
    fatti = Fatti(possibili={d("14/10"): frozenset({GIO.telegram_id, ABE.telegram_id, EMI.telegram_id, SEM.telegram_id, SESE.telegram_id})})
    s = stato("14/10 16/10 17/10", gio="14/10 16/10", abe="14/10 16/10", emi="14/10 16/10", sem="16/10")
    assert [type(a) for a in regole.annunci_da_fare(s, fatti)] == [regole.NonPiu, regole.Quasi]
```

(con il roster delle prove: nella terza, il 16/10 ha Gio e tre giocatori, Sese e Pippo non hanno votato.) Le
prove esistenti che si aspettavano un «quasi» con tutti che hanno votato, o insieme a una data possibile, si
aggiornano alla regola nuova.

- [ ] **Passo 2: farle fallire.**
- [ ] **Passo 3: il codice**

```python
def annunci_da_fare(stato: Stato, fatti: Fatti) -> list[Annuncio]:
    """Gli annunci che lo stato chiede e che non sono ancora stati fatti: prima
    i «non più», poi i «possibile», poi i «quasi», ognuno nell'ordine delle date,
    e «impossibile» in fondo. Pura: rifarla non ripete niente.

    Un «quasi» si annuncia solo se qualcuno del roster non ha ancora votato (il
    messaggio serve a chiamarlo) e se nessuna data è possibile adesso; se no
    resta da annunciare, e lo sarà se le condizioni cambiano. (resto della
    docstring di oggi)"""
    conteggi = [conta(stato, g) for g in stato.date]
    possibile_adesso = any(c.possibile for c in conteggi)
    non_piu: list[Annuncio] = []
    nuove: list[Annuncio] = []
    quasi: list[Annuncio] = []
    for c in conteggi:
        if c.giorno in fatti.possibili and not c.possibile:
            non_piu.append(NonPiu(c.giorno, _andati_via(stato, fatti.possibili[c.giorno], c)))
        if c.possibile and c.giorno not in fatti.possibili:
            nuove.append(Possibile(c.giorno, c.presenti))
        if c.quasi and c.giorno not in fatti.quasi and stato.senza_voto and not possibile_adesso:
            quasi.append(Quasi(c.giorno, c.presenti, stato.senza_voto))
    annunci = [*non_piu, *nuove, *quasi]
    if impossibile(stato) and not fatti.impossibile and not _possibile_passata(stato, fatti):
        annunci.append(Impossibile(tuple((c.giorno, c.presenti) for c in conteggi if c.con_tre)))
    return annunci
```

- [ ] **Passo 4: la suite.**
- [ ] **Passo 5: commit** — `announcements: "almost" only with someone to call and no possible date; ordered by kind`.

---

### Task 4: I testi degli annunci, accorpati

**File:** `src/prossima/testi.py`; prove in `tests/test_testi.py`.

**Interfaccia prodotta:** `testi.annunci(gruppo: Sequence[regole.Annuncio], roster, nome_bot, date_sondaggio)
-> Testo` (un gruppo è fatto di annunci dello stesso tipo); via `quasi`, `possibile`, `non_piu`, `impossibile`,
`annuncio`.

- [ ] **Passo 1: le prove che falliscono** (`SETTIMANA_PROVE = [d("13/10") + timedelta(days=i) for i in
  range(7)]`, `DUE_SETTIMANE = SETTIMANA_PROVE + [d("20/10")]`):

```python
def test_quasi():
    t = testi.annunci([Quasi(d("14/10"), (GIO, ABE, EMI, SEM), (PIPPO,))], ROSTER, NOME, SETTIMANA_PROVE)
    assert t.testo == "Martedì ci siamo quasi. Pippo, ci sei?"
    assert menzionati(t) == [("Pippo", PIPPO.telegram_id)]


def test_quasi_accorpato_con_piu_persone():
    gruppo = [Quasi(d(g), (GIO, ABE, EMI, SEM), (SESE, PIPPO)) for g in ("13/10", "16/10")]
    t = testi.annunci(gruppo, ROSTER, NOME, DUE_SETTIMANE)
    assert t.testo == "Lunedì 13 e giovedì 16 ci siamo quasi. Sese e Pippo, ci siete?"
    assert menzionati(t) == [("Sese", SESE.telegram_id), ("Pippo", PIPPO.telegram_id)]


def test_possibile():
    gruppo = [Possibile(d(g), (GIO, ABE, EMI, SEM, SESE)) for g in ("13/10", "14/10")]
    assert testi.annunci(gruppo[:1], ROSTER, NOME, SETTIMANA_PROVE).testo == "✅ Lunedì si può fare!"
    assert testi.annunci(gruppo, ROSTER, NOME, SETTIMANA_PROVE).testo == "✅ Lunedì e martedì si può fare!"


def test_non_piu():
    sem, sese = NonPiu(d("14/10"), (SEM,)), NonPiu(d("16/10"), (SESE, SEM))
    assert testi.annunci([sem], ROSTER, NOME, SETTIMANA_PROVE).testo == "Martedì è saltato, Sem non può più."
    assert testi.annunci([sem, sese], ROSTER, NOME, SETTIMANA_PROVE).testo == (
        "Martedì e giovedì sono saltati, Sem e Sese non possono più."
    )


def test_non_piu_domenica_e_senza_nomi():
    assert testi.annunci([NonPiu(d("19/10"), (SEM,))], ROSTER, NOME, SETTIMANA_PROVE).testo == (
        "Domenica è saltata, Sem non può più."
    )
    domeniche = [NonPiu(d("19/10"), (SEM,)), NonPiu(d("26/10"), ())]
    assert testi.annunci(domeniche, ROSTER, NOME, [d("19/10"), d("26/10")]).testo == (
        "Domenica 19 e domenica 26 sono saltate."
    )


def test_impossibile():
    con_tre = Impossibile(((d("13/10"), (GIO, ABE, EMI, SEM)), (d("16/10"), (GIO, ABE, EMI, SESE))))
    t = testi.annunci([con_tre], ROSTER, NOME, SETTIMANA_PROVE)
    assert t.testo == (
        "😬 Con i voti attuali non ci sono date con quattro giocatori. Con tre: lunedì e giovedì. "
        f"Gio: /chiudi@{NOME} 13/10 per tenerne una, /chiudi@{NOME} rimanda per rimandare alla prossima settimana."
    )
    assert menzionati(t) == [("Gio", GIO.telegram_id)]
    una = Impossibile(((d("13/10"), (GIO, ABE, EMI, SEM)),))
    assert "13/10 per tenerla," in testi.annunci([una], ROSTER, NOME, SETTIMANA_PROVE).testo
    senza = testi.annunci([Impossibile(())], ROSTER, NOME, SETTIMANA_PROVE)
    assert senza.testo == (
        "😬 Con i voti attuali non ci sono date con quattro giocatori, e nemmeno con tre. "
        f"Gio: /chiudi@{NOME} rimanda per rimandare alla prossima settimana."
    )
```

Le prove di oggi su `quasi`, `possibile`, `non_piu`, `impossibile` e `annuncio` lasciano il posto a queste.

- [ ] **Passo 2: farle fallire.**
- [ ] **Passo 3: il codice**

```python
def annunci(
    gruppo: Sequence[regole.Annuncio],
    roster: regole.Roster,
    nome_bot: str,
    date_sondaggio: Sequence[date],
) -> Testo:
    """Un messaggio per un gruppo di annunci dello stesso tipo, nell'ordine
    delle date. Le date si dicono per giorno se il sondaggio sta in una
    settimana (`date_sondaggio`: tutte le sue date)."""
    solo_il_giorno = una_settimana(date_sondaggio)
    giorni = [a.giorno for a in gruppo if not isinstance(a, regole.Impossibile)]
    match gruppo[0]:
        case regole.Quasi(senza_voto=senza_voto):
            domanda = "ci sei?" if len(senza_voto) == 1 else "ci siete?"
            return (
                _Scrittura()
                .testo(f"{_maiuscola(date_dette(giorni, solo_il_giorno))} ci siamo quasi. ")
                .menzioni(senza_voto, " e ")
                .testo(f", {domanda}")
                .fatto()
            )
        case regole.Possibile():
            return Testo(f"✅ {_maiuscola(date_dette(giorni, solo_il_giorno))} si può fare!")
        case regole.NonPiu():
            return _non_piu(gruppo, roster, giorni, solo_il_giorno)
        case regole.Impossibile() as a:
            return _impossibile(a, roster, nome_bot, solo_il_giorno)
    raise TypeError(f"annuncio sconosciuto: {gruppo[0]!r}")


def _non_piu(gruppo, roster, giorni, solo_il_giorno) -> Testo:
    """I nomi solo se il bot sa chi se n'è andato per tutte le date (dopo una
    ripresa non lo sa). Domenica è femminile."""
    femminile = all(g.weekday() == 6 for g in giorni)
    if len(giorni) == 1:
        saltato = "è saltata" if femminile else "è saltato"
    else:
        saltato = "sono saltate" if femminile else "sono saltati"
    inizio = f"{_maiuscola(date_dette(giorni, solo_il_giorno))} {saltato}"
    if not all(a.andati_via for a in gruppo):
        return Testo(f"{inizio}.")
    andati = {p.telegram_id for a in gruppo for p in a.andati_via}
    persone = [p for p in roster.persone if p.telegram_id in andati]
    verbo = "non può più" if len(persone) == 1 else "non possono più"
    return Testo(f"{inizio}, {elenco(_nomi(persone))} {verbo}.")


def _impossibile(a, roster, nome_bot, solo_il_giorno) -> Testo:
    """Menziona il master; se il master non può chiudere, chi può."""
    chi = (roster.master,) if roster.master.chiude else roster.chi_chiude
    rimanda = f"/chiudi@{nome_bot} rimanda per rimandare alla prossima settimana."
    s = _Scrittura()
    if a.con_tre:
        giorni = [g for g, _ in a.con_tre]
        tenere = "per tenerla" if len(giorni) == 1 else "per tenerne una"
        s.testo(
            "😬 Con i voti attuali non ci sono date con quattro giocatori. "
            f"Con tre: {date_dette(giorni, solo_il_giorno)}. "
        )
        s.menzioni(chi, " e ").testo(f": /chiudi@{nome_bot} {regole.breve(giorni[0])} {tenere}, {rimanda}")
    else:
        s.testo("😬 Con i voti attuali non ci sono date con quattro giocatori, e nemmeno con tre. ")
        s.menzioni(chi, " e ").testo(f": {rimanda}")
    return s.fatto()
```

(«per tenerla» con una sola data è una piccola aggiunta alla spec: si scrive in §3.5 nel Task 7.)

- [ ] **Passo 4: la suite** — il bot usa ancora `testi.annuncio`: nel Task 5 passa a `testi.annunci`; fino a
  lì `annuncio(a, roster, nome_bot)` resta come `annunci([a], roster, nome_bot, [a.giorno])`, solo per non
  rompere il bot fra un commit e l'altro.
- [ ] **Passo 5: commit** — `texts: short announcements, one message for a group of the same kind`.

---

### Task 5: Il bot aspetta 2 minuti e accorpa

**File:** `src/prossima/bot.py`, `tests/conftest.py`; prove in `tests/test_bot.py`.

**Interfacce:** `bot.ATTESA_ANNUNCI = timedelta(minutes=2)`; `Bot(..., attesa_annunci: timedelta =
ATTESA_ANNUNCI)`; in `conftest.riavvia` l'argomento predefinito diventa `attesa_annunci=timedelta(0)`, così
le prove di oggi sugli annunci restano immediate, e quelle dell'attesa la chiedono.

- [ ] **Passo 1: le prove che falliscono**

```python
ATTESA = bot_mod.ATTESA_ANNUNCI


def quattro_su_martedi(bot, telegram):
    """Gio e tre giocatori su martedì; Sese e Pippo non hanno votato: «quasi»."""
    bot.ricevi([comando("/sondaggio")])
    for p in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, p, "14/10")


def test_gli_annunci_aspettano_due_minuti_senza_voti(riavvia, telegram, orologio):
    bot = riavvia(attesa_annunci=ATTESA)
    quattro_su_martedi(bot, telegram)
    assert telegram.scritti() == []
    orologio.avanza(minutes=1, seconds=59)
    bot.ricevi([])
    assert telegram.scritti() == []
    orologio.avanza(seconds=2)
    bot.ricevi([])
    assert telegram.scritti() == ["Martedì ci siamo quasi. Sese e Pippo, ci siete?"]


def test_uno_stato_di_passaggio_non_si_annuncia(riavvia, telegram, orologio):
    bot = riavvia(attesa_annunci=ATTESA)
    quattro_su_martedi(bot, telegram)
    vota(bot, telegram, SESE, "14/10")  # martedì va bene…
    vota(bot, telegram, SESE, "")  # …per un attimo
    orologio.avanza(minutes=3)
    bot.ricevi([])
    assert telegram.scritti() == ["Martedì ci siamo quasi. Sese e Pippo, ci siete?"]


def test_un_voto_che_cambia_due_date_fa_un_messaggio(bot, telegram):
    bot.ricevi([comando("/sondaggio")])
    for p in (GIO, ABE, EMI, SEM):
        vota(bot, telegram, p, "13/10 14/10")
    assert telegram.scritti() == ["Lunedì e martedì ci siamo quasi. Sese e Pippo, ci siete?"]
    vota(bot, telegram, SESE, "13/10 14/10")
    assert telegram.scritti()[-1] == "✅ Lunedì e martedì si può fare!"
    vota(bot, telegram, SEM, "nessuna")
    assert telegram.scritti()[-1] == "Lunedì e martedì sono saltati, Sem non può più."


def test_i_comandi_non_aspettano(riavvia, telegram):
    bot = riavvia(attesa_annunci=ATTESA)
    quattro_su_martedi(bot, telegram)
    bot.ricevi([comando("/sondaggio")])
    assert telegram.scritti() == ["C'è già un sondaggio aperto: chiudilo prima con /chiudi@ProssimaVoltaBot."]


def test_dopo_un_riavvio_gli_annunci_dovuti_partono_subito(riavvia, telegram):
    quattro_su_martedi(riavvia(attesa_annunci=ATTESA), telegram)
    riavvia(attesa_annunci=ATTESA).ricevi([])
    assert telegram.scritti() == ["Martedì ci siamo quasi. Sese e Pippo, ci siete?"]
```

(`import prossima.bot as bot_mod`.) Le prove di oggi con i testi vecchi degli annunci si aggiornano ai testi
nuovi (§3.5) e alle regole del Task 3.

- [ ] **Passo 2: farle fallire.**
- [ ] **Passo 3: il codice** (`bot.py`):

```python
# Gli annunci aspettano che i voti si assestino (spec §3.5).
ATTESA_ANNUNCI = timedelta(minutes=2)
```

nel costruttore `attesa_annunci: timedelta = ATTESA_ANNUNCI`, `self._attesa_annunci = attesa_annunci`,
`self._ultimo_voto: datetime | None = None` (in memoria: dopo un riavvio gli annunci dovuti partono subito);
in `_voto`, dopo ogni `registra_voto` e `registra_voto_tardivo`, `self._ultimo_voto = self._adesso()`;
`_manda_annunci`:

```python
    def _manda_annunci(self) -> None:
        sondaggio = self._store.sondaggio_aperto()
        if sondaggio is None or self._in_chiusura(sondaggio):
            # (commento di oggi)
            return
        if self._ultimo_voto is not None and self._adesso() - self._ultimo_voto < self._attesa_annunci:
            return  # i voti non si sono ancora assestati: si dice com'è dopo
        stato = self._stato(sondaggio)
        fatti = self._store.fatti(sondaggio.id)
        if regole.rientrato(stato, fatti):
            fatti = regole.dopo(fatti, regole.Rientro())
            self._store.salva_fatti(sondaggio.id, fatti)
        for gruppo in _per_tipo(regole.annunci_da_fare(stato, fatti)):
            if (sondaggio.id, gruppo) in self._annunci_rifiutati:
                continue
            testo = testi.annunci(gruppo, self._roster, self._nome, sondaggio.date)
            try:
                self._invio.scrivi(testo)
            except TelegramRifiuto as e:
                # (commento di oggi)
                log.error("annuncio rifiutato da Telegram: %s (%r)", e, testo.testo)
                self._annunci_rifiutati.add((sondaggio.id, gruppo))
                continue
            for annuncio in gruppo:
                fatti = regole.dopo(fatti, annuncio)
            self._store.salva_fatti(sondaggio.id, fatti)
```

e, in fondo al modulo:

```python
def _per_tipo(annunci: Sequence[regole.Annuncio]) -> list[tuple[regole.Annuncio, ...]]:
    """Gli annunci dello stesso tipo, insieme: `annunci_da_fare` li dà già in
    ordine di tipo, quindi bastano quelli consecutivi."""
    gruppi: list[list[regole.Annuncio]] = []
    for annuncio in annunci:
        if gruppi and type(gruppi[-1][0]) is type(annuncio):
            gruppi[-1].append(annuncio)
        else:
            gruppi.append([annuncio])
    return [tuple(g) for g in gruppi]
```

Si toglie `testi.annuncio`.

- [ ] **Passo 4: la suite.**
- [ ] **Passo 5: commit** — `bot: announcements wait 2 quiet minutes and go out grouped by kind`.

---

### Task 6: `/aiuto`

**File:** `src/prossima/bot.py`, `src/prossima/testi.py`; prove in `tests/test_bot.py`, `tests/test_testi.py`,
`tests/test_principale.py`.

- [ ] **Passo 1: le prove che falliscono**

```python
def test_aiuto(bot, telegram):
    bot.ricevi([comando("/aiuto@ProssimaVoltaBot")])
    assert telegram.scritti() == [
        "Come si usa:\n"
        "/sondaggio@ProssimaVoltaBot — sondaggio sulla settimana prossima, sabato escluso\n"
        "/sondaggio@ProssimaVoltaBot con sabato — anche il sabato\n"
        "/sondaggio@ProssimaVoltaBot mar gio — solo quei giorni\n"
        "/sondaggio@ProssimaVoltaBot 14/10 16/10 — quelle date\n"
        "Chiude Gio (o Abe, in emergenza):\n"
        "/chiudi@ProssimaVoltaBot — chiude e dice le date possibili\n"
        "/chiudi@ProssimaVoltaBot 14/10 (o mar) — chiude e tiene quella data\n"
        "/chiudi@ProssimaVoltaBot rimanda — chiude e rifà il sondaggio sulla settimana dopo"
    ]
```

e in `test_testi.py`:

```python
def test_aiuto_dai_giorni_di_sempre():
    tutti = testi.aiuto(NOME, ROSTER, range(7)).testo.split("\n")
    assert tutti[1] == f"/sondaggio@{NOME} — sondaggio sulla settimana prossima"
    assert not any(" con " in riga for riga in tutti)
    senza_domenica = testi.aiuto(NOME, ROSTER, (0, 1, 2, 3, 4, 5)).testo.split("\n")
    assert senza_domenica[1].endswith("domenica esclusa")
    assert senza_domenica[2] == f"/sondaggio@{NOME} con domenica — anche la domenica"
    senza_due = testi.aiuto(NOME, ROSTER, (0, 1, 2, 3, 4)).testo.split("\n")
    assert senza_due[1].endswith("sabato e domenica esclusi")
    assert senza_due[2] == f"/sondaggio@{NOME} con sabato — anche il sabato"
```

`test_principale.py`: `registra_comandi` riceve anche `("aiuto", "Come si usano i comandi")`.

- [ ] **Passo 2: farle fallire.**
- [ ] **Passo 3: il codice** — in `bot.py` `COMANDI` con `("aiuto", "Come si usano i comandi")` e in
  `_messaggio`:

```python
        elif comando == "aiuto":
            self._invio.accoda(
                testi.aiuto(self._nome, self._roster, self._giorni),
                risposta_a=messaggio["message_id"],
            )
```

in `testi.py`:

```python
def aiuto(nome_bot: str, roster: regole.Roster, giorni_di_sempre: Collection[int]) -> Testo:
    """Le istruzioni di `/aiuto` (spec §3.9): i giorni fuori e chi chiude
    vengono dalla configurazione."""
    sondaggio, chiudi = f"/sondaggio@{nome_bot}", f"/chiudi@{nome_bot}"
    fuori = [g for g in range(7) if g not in giorni_di_sempre]
    righe = ["Come si usa:"]
    if fuori:
        nomi = [regole.GIORNI_INTERI[g] for g in fuori]
        if len(fuori) > 1:
            esclusi = "esclusi"
        else:
            esclusi = "esclusa" if fuori[0] == 6 else "escluso"
        articolo = "la" if fuori[0] == 6 else "il"
        righe += [
            f"{sondaggio} — sondaggio sulla settimana prossima, {elenco(nomi)} {esclusi}",
            f"{sondaggio} con {nomi[0]} — anche {articolo} {nomi[0]}",
        ]
    else:
        righe.append(f"{sondaggio} — sondaggio sulla settimana prossima")
    righe += [
        f"{sondaggio} mar gio — solo quei giorni",
        f"{sondaggio} 14/10 16/10 — quelle date",
        f"{_maiuscola(chi_chiude(roster))}:",
        f"{chiudi} — chiude e dice le date possibili",
        f"{chiudi} 14/10 (o mar) — chiude e tiene quella data",
        f"{chiudi} rimanda — chiude e rifà il sondaggio sulla settimana dopo",
    ]
    return Testo("\n".join(righe))
```

- [ ] **Passo 4: la suite.**
- [ ] **Passo 5: commit** — `bot: /aiuto, built from the usual days and the roster`.

---

### Task 7: Documenti e configurazione d'esempio

- [ ] `config.esempio/prossima.env`: dopo `PV_DOMANDA`,

```
# I giorni di sempre di /sondaggio, separati da spazi. Senza questa riga, tutti
# tranne il sabato; chi lancia il sondaggio aggiunge un giorno con «con sabato».
# PV_GIORNI=lun mar mer gio ven dom
```

- [ ] `docs/messa-in-produzione.md`: la riga dell'avvio con i giorni; una sezione «Cambiare i giorni di
  sempre» (`PV_GIORNI`, poi `docker compose up -d`); in §5 (a mano nel gruppo) `/aiuto` dal menu.
- [ ] Spec §3.5: «per tenerla» con una sola data in «impossibile».
- [ ] Piano principale, «Deviazioni durante l'esecuzione»: una sezione per questo lavoro, con le scelte fatte
  durante l'esecuzione.
- [ ] `uv run pytest -q`, `uv run ruff check src tests`, `uv run pytest -m reale -q -rs` (salta tutto).
- [ ] Commit — `docs: usual days, /aiuto, shorter announcements`.

### Alla fine

Revisione indipendente del ramo (un agente, solo lettura), correzioni, e poi l'assenso di Alberto per
fondere e pubblicare. Sul server: `git pull`, `sudo docker compose build --pull`, `sudo docker compose up -d`.
