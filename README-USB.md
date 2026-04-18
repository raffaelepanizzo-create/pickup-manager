# PickUp Manager - Deploy locale su chiavetta USB (Windows + LAN)

Questa guida spiega come trasformare la web app in un eseguibile Windows
standalone (`PickupManager.exe`) da mettere su una chiavetta USB.
L'app gira sul PC dove la lanci ed e' raggiungibile dagli altri PC della
LAN tramite l'IP del PC ospitante.

Vantaggio principale: il database SQLite (`pickup.db`) vive accanto
all'eseguibile sulla chiavetta, quindi i dati sono **persistenti** e
si spostano insieme alla chiavetta.

---

## 1. Prerequisiti (UNA TANTUM, sul PC dove costruirai il .exe)

1. Installa **Python 3.10 o superiore** da <https://www.python.org/downloads/>
   - **IMPORTANTE**: durante l'installazione spunta *"Add Python to PATH"*.
2. Installa **Git** da <https://git-scm.com/download/win> (opzionale,
   serve solo per scaricare il repo via comando).

## 2. Scarica il repository sul PC

Apri *Prompt dei comandi* in una cartella di tua scelta e lancia:

```
git clone https://github.com/raffaelepanizzo-create/pickup-manager.git
cd pickup-manager
```

In alternativa puoi scaricare lo ZIP da GitHub (bottone verde "Code" >
"Download ZIP") ed estrarlo.

## 3. Build dell'eseguibile

Sempre dal Prompt dei comandi, dentro la cartella `pickup-manager`:

```
build_windows.bat
```

Lo script:
- crea un virtual environment in `.venv\`
- installa Flask, pandas, openpyxl, waitress, pyinstaller
- esegue PyInstaller con `pickup_manager.spec`
- produce `dist\PickupManager.exe` (~40-60 MB, single-file)

Tempo richiesto: 3-8 minuti la prima volta, 1-2 minuti dalle volte
successive.

## 4. Prepara la chiavetta USB

Sulla chiavetta crea una cartella (es. `PickupManager\`) e copia DENTRO:

```
CHIAVETTA:\PickupManager\
+-- PickupManager.exe   (da dist\)
+-- avvia.bat            (dalla root del repo)
```

Non serve copiare nient'altro: templates, librerie e Python sono tutti
dentro l'`.exe`.

## 5. Uso quotidiano

1. Inserisci la chiavetta in un PC Windows.
2. Apri la cartella `PickupManager\` e fai doppio click su
   **avvia.bat**.
3. Si apre una finestra nera (terminale) che mostra qualcosa come:

   ```
   ============================================================
     PickUp Manager - Server Locale
   ============================================================
     Database:     E:\PickupManager\pickup.db
     Uploads:      E:\PickupManager\uploads
   
     Accesso dal PC locale:
       http://127.0.0.1:5000
     Accesso dagli altri PC in LAN:
       http://192.168.1.42:5000
   ============================================================
   ```

4. Il browser si apre automaticamente sull'app.
5. Al primo avvio: vai su **/caricamento** per importare l'Excel e
   su **/impostazioni** per inserire i target mensili.
6. Per fermare il server: chiudi la finestra nera.

## 6. Accesso da altri PC della LAN

Comunica agli altri utenti l'URL mostrato nel terminale, ad esempio
**http://192.168.1.42:5000**, dove `192.168.1.42` e' l'IP del PC
ospitante. Devono essere sulla stessa rete Wi-Fi/LAN.

### Firewall di Windows
Al primo avvio Windows potrebbe chiedere di consentire `PickupManager`
sulla rete: spunta **Reti private** e clicca *Consenti accesso*. Senza
questa autorizzazione gli altri PC non riusciranno a collegarsi.

### IP fisso (consigliato)
Se vuoi un URL stabile, chiedi al tuo amministratore di rete di
assegnare al PC ospitante un **IP fisso** o una **prenotazione DHCP**.
Altrimenti l'IP del PC potrebbe cambiare al riavvio.

## 7. Persistenza dei dati

Il file `pickup.db` viene creato automaticamente accanto a
`PickupManager.exe` e contiene:
- Excel caricati (rate, occupazione, revenue, RSN)
- Target mensili impostati
- Storico upload

Spostando la chiavetta su un altro PC, **i dati seguono la chiavetta**.

Per fare un backup: copia il file `pickup.db` dalla chiavetta
in un'altra cartella o servizio cloud.

## 8. Aggiornamento dell'app

Quando esce una nuova versione del codice:
1. Aggiorna il repo (`git pull` oppure scarica ZIP nuovo).
2. Rilancia `build_windows.bat`.
3. Sostituisci `PickupManager.exe` sulla chiavetta con quello nuovo
   in `dist\`.
4. **NON toccare** `pickup.db` sulla chiavetta: i tuoi dati restano
   intatti.

## 9. Cambiare username/password (opzionale)

Le credenziali default sono `admin` / `changeme`. Per cambiarle, crea
sulla chiavetta un file `.env` accanto al `.exe` con:

```
APP_USERNAME=tuo_user
APP_PASSWORD=tua_password
SECRET_KEY=stringa_random_lunga
```

Riavvia `avvia.bat`.

## 10. Risoluzione problemi

**"Python non trovato"** quando lancio `build_windows.bat`
> Reinstalla Python da python.org spuntando "Add Python to PATH".

**Build fallisce con errore su pandas/openpyxl**
> Controlla di avere Python 64-bit (non 32-bit). Lancia `python -c "import platform; print(platform.architecture())"`.

**Gli altri PC non vedono il server**
> 1. Verifica che siano sulla stessa rete LAN. 2. Verifica il firewall di Windows (vedi sezione 6). 3. Prova a raggiungerlo via IP esatto, non via nome PC.

**Antivirus blocca `PickupManager.exe`**
> Eseguibili PyInstaller possono dare falsi positivi. Aggiungi
> un'eccezione nel tuo antivirus per il file.

---

Per qualsiasi problema durante il build apri una *Issue* sul repo
GitHub.

