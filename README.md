# Ultimo Metro — demo hackathon

Web app locale per dimostrare il flusso **FMIS/xFarm → importazione ISOXML → pre-flight rispetto al profilo macchina e ai codici hardware ARAG → export annotato**.

> **Stato del prototipo.** Proof of concept da hackathon, non un sistema agronomico certificato né un exporter validato per terminali reali. Il programma legge gli elementi XML riconosciuti, calcola una stima idraulica e conserva il file originale: non riscrive le dosi `PDV` e non decodifica le celle binarie `GRD`. L'output è un pacchetto ISOXML annotato con commenti di pre-flight, non ancora una prescrizione garantita come eseguibile da una macchina ARAG.

## Avvio rapido su Windows

1. Installa **Python 3.10 o successivo** da <https://www.python.org/downloads/>. Se il programma di installazione propone **Add Python to PATH**, selezionalo.
2. Estrai l'archivio ZIP e conserva tutta la cartella `ultimo_metro_demo`.
3. Fai doppio clic su `run_windows.bat`. Si aprirà il browser all'indirizzo <http://127.0.0.1:5000>.
4. La dashboard parte vuota. Premi **Prova con il file demo** oppure carica un file `.zip` / `.isoxml` esportato da xFarm o il `TASKDATA.XML` singolo.
5. Per rimuovere l'analisi corrente, premi **Rimuovi e ricomincia**. Per sostituire il file senza perdere il profilo macchina, premi **Sostituisci file** oppure seleziona un nuovo file nell'area di upload. Il pulsante demo ricarica i dati sintetici.
6. Per fermare il server, torna alla finestra del terminale e premi **Ctrl+C**.

Il server usa solo la libreria standard di Python: non servono Flask, Node.js o un database.

## Avvio su Linux / Ubuntu

Da terminale nella cartella del progetto:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

Apri <http://127.0.0.1:5000>. Per fermare il server premi `Ctrl+C`.

## Come provare la demo

1. Premi **Prova con il file demo**: il pacchetto sintetico contiene un campo da 18,6 ha e due zone `TZN`, con target 250 e 180 L/ha letti da `PDV` e `VPN`.
2. Nel pannello **Setup macchina** seleziona i codici dei componenti effettivamente presenti. Il catalogo include esempi di terminali, ECU, controllo PWM, flussimetri, valvole, attuatori/portaugelli selettivi, pompe, ugelli e filtri.
3. La demo usa un profilo macchina di esempio (serbatoio, larghezza, portata utile calibrata e velocità min/max). Questi dati non si deducono in modo univoco dai soli codici dei componenti. Sono nascosti in **Parametri profilo** per rappresentare dati salvati una volta per macchina, non inseriti per ogni trattamento.
4. Con i default: 250 L/ha su 18 m a 10 km/h richiede 75 L/min. Il profilo usa 60 L/min, quindi il limite teorico è 8 km/h; la fascia da 250 L/ha diventa gialla. A 180 L/ha la velocità massima teorica è circa 11,1 km/h, per cui la fascia è verde. È una stima, non una misurazione della deposizione.
5. Modifica vento, temperatura o tempo alla pioggia: il semaforo meteo si aggiorna con soglie illustrative, non normative. Se Internet è disponibile e il file contiene coordinate, **Meteo live** richiama Open-Meteo.
6. Premi **Esporta ISOXML annotato**. Il pacchetto ZIP conserva `TASKDATA.XML` e i file accessori e aggiunge annotazioni `CAN` con sintesi hardware e meteo. I valori target originali sono preservati.

### Come leggere la mappa

- Il confine viene disegnato dai punti `PNT` nella prima geometria poligonale valida sotto `PFD → PLN → LSG`, quando presente.
- La tinta verde/gialla/rossa rappresenta la fattibilità idraulica teorica dei ratei che il parser riconosce, a fronte del profilo macchina configurato.
- Gli elementi `TZN` identificano zone/valori ma non forniscono sempre la loro geometria spaziale; la demo le visualizza come fasce schematiche. Se il pacchetto contiene `GRD`, la demo lo preserva ma non ne decodifica ancora le celle. Quindi **il colore non va interpretato come una ricostruzione geografica reale della prescrizione**.

## Modificare il codice con Visual Studio Code

1. Installa VS Code: <https://code.visualstudio.com/>.
2. In VS Code scegli **File → Open Folder…** e seleziona la cartella `ultimo_metro_demo` estratta dallo ZIP.
3. Modifica il file pertinente nella lista seguente.
4. Per modifiche a HTML, CSS, JavaScript o JSON: salva (`Ctrl+S`) e aggiorna il browser. Se non vedi le modifiche, usa `Ctrl+F5` per ricaricare senza cache.
5. Per modifiche a `app.py`: ferma il server con `Ctrl+C` e rilancia `run_windows.bat` o `./run_linux.sh`.
6. Per verificare la demo dal terminale, apri VS Code → **Terminal → New Terminal** e lancia:

```bash
python -m unittest discover -s tests -v
node --check static/app.js
python -m json.tool static/arag_catalog.json
```

### File da conoscere

| File | A cosa serve | Esempio di modifica |
|---|---|---|
| `static/index.html` | Struttura e testi della pagina | Rinominare una sezione o aggiungere un input |
| `static/styles.css` | Grafica, colori, responsive layout | Modificare verde/giallo/rosso, spazi e font |
| `static/app.js` | Logica nel browser: upload, debounce, mappa, stime, meteo e selettori | Cambiare una regola di classificazione o il comportamento dei pulsanti |
| `app.py` | Server locale, parser XML, stato della sessione, reset, export ZIP e commenti `CAN` | Aggiungere un campo al riepilogo estratto da ISOXML |
| `static/arag_catalog.json` | Catalogo dei codici hardware pubblici | Inserire un nuovo codice con categoria, descrizione, capacità note e URL ufficiale |
| `examples/TASKDATA_demo.xml` | Dati XML sintetici leggibili | Cambiare nome del campo o ratei demo |
| `examples/TASKDATA_demo.zip` | Pacchetto sintetico usato dal bottone demo | Va rigenerato se cambia l'XML d'esempio |
| `tests/test_core.py` | Test automatici del parser/export/reset | Aggiungere un test per una nuova regola |

Per aggiungere un prodotto al catalogo, apri `static/arag_catalog.json` e inserisci un oggetto in `products` con `category`, `code`, `name`, `short`, `specs`, `official_url` e `capabilities`. Il nome di `category` deve corrispondere a una categoria con selettore `data-catalog-category` in `static/index.html`. Non stimare dati tecnici che non compaiono nella scheda ufficiale: lascia `null` o indica “da verificare”.

## Ricerca di mercato

Consulta [RICERCA_MERCATO.md](RICERCA_MERCATO.md), con portfolio Nordson/ARAG, esempi di codici ufficiali, sovrapposizione funzionale con xFarm, differenziazione proposta e domande per i mentor.

## Limiti e sicurezza

- Il server ascolta solo su `127.0.0.1`: è una demo per uso locale, non esporlo direttamente a Internet.
- Il file è elaborato in memoria sul computer dell'utente; non viene inviato ad ARAG o a xFarm. Il pulsante **Meteo live** fa una richiesta separata a Open-Meteo con il centroide delle coordinate del campo.
- I codici nel catalogo sono esempi basati su schede pubbliche. La loro presenza nel menu non dimostra che una combinazione sia compatibile come sistema completo. Orion 3, ad esempio, viene descritto da ARAG per sistemi di distribuzione liquidi su seminatrici: l'idoneità per una specifica irroratrice va confermata.
- Range di un flussimetro e portata nominale di pompa/valvola non equivalgono alla portata effettiva agli ugelli: servono schema idraulico e calibrazione.
- La demo non decodifica griglie binarie `GRD`, non valida l'intero XSD ISOXML, non verifica le etichette fitosanitarie né le compatibilità di miscela e non ha accesso diretto a computer ARAG.
- Non usare il file sintetico su una macchina reale. Prima di inviare un export operativo occorre confermare il supporto al modello/firmware specifico con ARAG e provarlo in ambiente controllato.
