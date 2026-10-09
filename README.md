# Ultimo Metro — demo hackathon

Web app locale per dimostrare il flusso **FMIS/xFarm → lettura ISOXML → verifica hardware/meteo → pacchetto annotato**.

> **Stato del prototipo.** È un proof of concept da hackathon, non un sistema agronomico o un exporter certificato per terminali reali. L'esportazione aggiunge un commento ISOXML standard (`CAN`) alle operazioni: conserva i valori target `PDV`, le mappe `GRD` e gli altri file binari originali. Non modifica automaticamente la dose, la griglia di prescrizione o i comandi del controller.

## Avvio rapido su Windows

1. Installa **Python 3.10 o successivo** da <https://www.python.org/downloads/>. Se il programma di installazione propone l'opzione **Add Python to PATH**, selezionala.
2. Estrai tutta la cartella `ultimo_metro_demo` in una posizione facile da trovare.
3. Fai doppio clic su `run_windows.bat`.
4. Si aprirà il browser all'indirizzo <http://127.0.0.1:5000>. La dashboard carica inizialmente un file sintetico di esempio.
5. Per fermare il server, torna alla finestra nera aperta da `run_windows.bat` e premi **Ctrl+C**.

Il server usa solamente la libreria standard Python: non è necessario installare Flask, Node.js o altre dipendenze.

## Avvio su Linux / Ubuntu

Da un terminale nella cartella del progetto:

```bash
chmod +x run_linux.sh
./run_linux.sh
```

Poi apri <http://127.0.0.1:5000> nel browser e usa `Ctrl+C` per fermare il server.

## Come provare la demo

1. **Parti dal file demo** già caricato nella dashboard. Contiene una coltura dimostrativa, una superficie di 18,6 ha, due zone TZN e due prodotti con nomi esplicitamente dimostrativi.
2. Modifica capacità del serbatoio, larghezza, portata, velocità e dose target. Il pre-flight viene aggiornato dopo una breve pausa dai cambiamenti dell'interfaccia (debouncing di 300 ms).
3. Cambia vento, temperatura e ore alla pioggia per vedere il semaforo operativo. Le soglie sono illustrative, non normative e non associate a uno specifico prodotto.
4. Usa **Meteo live** per interrogare Open-Meteo alle coordinate del campo se la connessione Internet è disponibile. Il dato è una previsione indicativa: verificare sempre sul campo e con le istruzioni del prodotto. Se Internet non è disponibile, usare gli input manuali.
5. Premi **Esporta ISOXML annotato**. Verrà scaricato un file ZIP che mantiene i contenuti originali e aggiunge due commenti liberi `CAN` standard ai task: uno con serbatoio, intervallo velocità e famiglia di controller, uno con il semaforo e i parametri meteo impostati.
6. Per provare un file reale, usa l'area di upload e scegli il pacchetto ISOXML esportato dal FMIS (normalmente un archivio `.zip` con `TASKDATA.XML` e possibili file accessori) oppure direttamente `TASKDATA.XML`.

## Aprirlo e modificarlo con Visual Studio Code

1. Installa VS Code: <https://code.visualstudio.com/>.
2. In VS Code scegli **File → Open Folder…** e seleziona `ultimo_metro_demo`.
3. I file principali sono:
   - `app.py`: server HTTP, upload, parsing e creazione del pacchetto ZIP.
   - `static/index.html`: struttura dell'interfaccia.
   - `static/styles.css`: colori, spaziature e layout responsive.
   - `static/app.js`: interazioni, rendering dei dati, debouncing e calcoli pre-flight.
   - `examples/TASKDATA_demo.zip`: pacchetto sintetico caricato dalla demo.
4. Dopo aver modificato un file, aggiorna il browser con `Ctrl+R`. Se modifichi `app.py`, ferma il server con `Ctrl+C` e avvia di nuovo il `.bat` o lo script `.sh`.

## Cosa interpreta e cosa no

- Riconosce il contenitore `ISO11783_TaskData`, i metadati di versione/FMIS e i principali elementi `TSK`, `PFD`, `PDT`, `CTP`, `DVC`, `TZN`, `PDV`, `VPN`, `GRD`, `TLG` e `PNT`.
- Per i `PDV` che referenziano un `VPN`, mostra il valore visualizzato usando `valore × scale + offset` e l'unità dichiarata in `VPN.E`.
- Usa `PFD.D` come superficie in metri quadrati per ricavare gli ettari; legge le coordinate `PNT` per l'anteprima del confine.
- Calcola un limite teorico della velocità attraverso la relazione `L/ha = 600 × portata (L/min) / [velocità (km/h) × larghezza (m)]`.
- Non decodifica le celle binarie dei file GRD, non valida l'intero XSD ISOXML, non verifica etichette fitosanitarie o compatibilità delle miscele, e non prova il risultato su Bravo/ISOBUS.
- Le zone colorate della mappa sono una rappresentazione illustrativa; non sostituiscono una mappa di prescrizione ricostruita dai dati binari.
- La stima dei litri su una mappa variabile usa prudenzialmente la dose massima su tutta la superficie e **non** equivale al consumo reale della mappa.

## Limiti e sicurezza

- Il server ascolta solo su `127.0.0.1`: è pensato per una demo sul computer locale. Non metterlo direttamente su Internet.
- Il file caricato viene elaborato in memoria dal server locale; non viene inviato a xFarm o ad ARAG. Il pulsante **Meteo live** effettua una richiesta separata a Open-Meteo usando le coordinate lette dal file.
- Il pacchetto demo è sintetico e non deve essere caricato su una macchina operativa.
- Prima di usare file prodotti su un computer reale, convalidare la specifica versione ISOXML, i DDI, il valore fisico delle unità e il formato richiesto dal terminale/controller specifico. In caso di hackathon dichiarare chiaramente questa limitazione.

# Guida rapida per la demo live

## Prima di iniziare

- Avvia `run_windows.bat` e lascia aperta la finestra del server.
- Apri `http://127.0.0.1:5000` (la demo carica automaticamente il file sintetico).
- Se vuoi mostrare un file vero di xFarm, caricalo dalla prima scheda; conserva sempre una copia originale del file per confronto.

## Scaletta da 2–3 minuti

### 1. Import — “non partiamo da un foglio vuoto”

Mostra il file `TASKDATA_demo.zip`. La dashboard indica una operazione, un campo da 18,6 ha, due prodotti descrittivi e due zone. I valori 250 e 180 L/ha sono interpretati dal `PDV` e dal suo `VPN` nel file sintetico.

Frase suggerita: *“Ultimo Metro non sostituisce il FMIS: importa il piano ISOXML già generato e aggiunge una verifica sull'attrezzatura che eseguirà davvero il lavoro.”*

### 2. Hardware — fai emergere un problema concreto

Lascia i valori di esempio:

- volume target massimo: 250 L/ha
- larghezza barra: 18 m
- portata totale disponibile: 60 L/min
- velocità massima impostata: 10 km/h

A 10 km/h servirebbero teoricamente 75 L/min. Con 60 L/min, il limite teorico è 8 km/h. La demo mostra un avviso e non abbassa autonomamente la dose.

Frase suggerita: *“Non correggiamo una dose agronomica facendo sparire il problema: rendiamo visibile che l'hardware non è in grado di eseguire il piano alla velocità scelta e proponiamo una verifica di velocità o ugelli.”*

Puoi cambiare la portata totale a 90 L/min e mostrare come il controllo si aggiorna dopo una breve pausa: è il **debouncing** della UI, che evita di ricalcolare ad ogni singolo evento mentre si sta digitando.

### 3. Meteo — mostra il ruolo dell'operatore

Inserisci vento a 16 km/h, oppure pioggia tra un'ora: il semaforo diventa rosso secondo le **soglie illustrative configurate nella demo**. Poi ripristina valori più favorevoli. Se la connessione Internet è disponibile e il campo contiene coordinate, premi `Meteo live` per richiamare Open-Meteo.

Frase suggerita: *“Il dato meteo da solo non è una prescrizione: è un segnale da contestualizzare con prodotto, etichetta, ugello e condizioni locali.”*

### 4. Export — dimostra il collegamento di ritorno

Premi `Esporta ISOXML annotato`. Il file scaricato è un ZIP. Aprendolo con un archiviatore, dentro trovi `TASKDATA.XML`. In ogni task la demo aggiunge due commenti `CAN` con:

- serbatoio, intervallo di velocità e famiglia di controller selezionata;
- semaforo meteo e i valori inseriti per vento, temperatura e pioggia.

Confrontando il file esportato con quello originale, i `PDV` e i file accessori, se presenti, restano invariati.

Frase suggerita: *“Questo prototipo chiude il pre-flight con una nota interoperabile nel task; la prossima iterazione dovrà produrre e convalidare i cambiamenti realmente eseguibili dal controller ARAG specifico.”*

## Domande che la giuria potrebbe fare

**“L'export comanda davvero il Bravo 400S?”**

Risposta trasparente: *“Non ancora. La demo importa il pacchetto, fa i controlli e aggiunge commenti ISOXML; non afferma di impostare la macchina né di essere validata su un terminale reale. Per quel passaggio serve verificare il formato supportato dal singolo controller e provarlo con hardware.”*

**“Perché non abbassate la dose se la portata non basta?”**

*“Perché la dose è una decisione agronomica vincolata all'etichetta, non un parametro da ridurre per compensare un limite della macchina. Il sistema segnala il problema e propone di verificare velocità, ugelli, portata o fattibilità con il tecnico.”*

**“Dove sono satellite e AI?”**

*“Sono moduli successivi: questo primo prototipo è concentrato sul ponte ISOXML–macchina. La mappa del campo viene dal file quando sono presenti coordinate; la griglia binaria di prescrizione non viene ancora ricostruita. Per dichiarare una riduzione dei fitofarmaci servono dati satellitari/scouting reali, regole agronomiche approvate e test comparativi.”*

## Evoluzione consigliata dopo l'hackathon

1. Validare un vero export xFarm e versioni ISOXML v3/v4 con XSD e pacchetti che contengano GRD/TLG.
2. Verificare con ARAG il formato di prescrizione accettato dal modello di terminale/controller e fare un test in ambiente controllato.
3. Interpretare le mappe GRD binarie e gli eventuali log di esecuzione prima di introdurre modifiche alle rate.
4. Collegare un database nazionale aggiornato delle etichette, incluse dose min/max, coltura, avversità e compatibilità miscela, con conferma del tecnico.
5. Integrare scouting/satellite/meteo per raccomandazioni agronomiche solo con fonti tracciabili e validazione sul campo.
