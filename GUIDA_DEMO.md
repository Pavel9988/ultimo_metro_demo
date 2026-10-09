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
