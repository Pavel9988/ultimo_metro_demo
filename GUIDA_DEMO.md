# Guida rapida per la demo live

## Prima di iniziare

- Avvia `run_windows.bat` e lascia aperta la finestra del server.
- Apri `http://127.0.0.1:5000`.
- La dashboard parte vuota: premi **Prova con il file demo**. In alternativa, carica un export ISOXML di xFarm (ZIP/ISOXML o `TASKDATA.XML`).
- Per ripetere l'esercizio usa **Rimuovi e ricomincia**; per passare a un altro file usa **Sostituisci file**. Il profilo hardware rimane selezionato.

## Scaletta da 2–3 minuti

### 1. Import — “non partiamo da un foglio vuoto”

Mostra il file sintetico: un campo rappresentativo da 18,6 ha e due zone, con target 250 e 180 L/ha letti dal `PDV` e dal riferimento di presentazione `VPN`.

Frase suggerita: *“Ultimo Metro non sostituisce il FMIS: importa il piano già creato e controlla prima di partire se il profilo dell'attrezzatura può eseguirlo.”*

### 2. Hardware — scegli i codici, non compilare schede tecniche

Nel pannello **Setup macchina**, seleziona i codici realmente montati. Per la demo usa una catena rappresentativa della famiglia IBX:

- terminale `4675204` — Delta 70T IBX;
- controllo rateo `4679013` — IBX100 ISOBUS Flowtron;
- flussimetro `46211P40000` — ORION 2+ (2–200 L/min nella scheda pubblica; la portata effettiva agli ugelli va comunque calibrata);
- valvola `853T04A55`;
- attuatore / portaugello selettivo `4063T95A0`;
- pompa `97055201`;
- ugello `AFC11002`;
- filtro `42433135`.

La lista dimostra un **profilo software**, non certifica da sola una combinazione di componenti. Nel prototipo il dato di portata utile calibrata, larghezza, velocità e serbatoio si trova sotto **Parametri profilo**: nella versione di prodotto andrebbe acquisito una volta per macchina, dal setup/installatore, calibrazione e dati ECU, non chiesto a ogni operatore.

### 3. Mappa — fai vedere la fascia limitata

Con i valori iniziali:

- rateo alto: 250 L/ha;
- rateo basso: 180 L/ha;
- larghezza: 18 m;
- portata utile profilo: 60 L/min;
- velocità configurata: 5–10 km/h.

A 10 km/h la zona da 250 L/ha richiede teoricamente 75 L/min, oltre ai 60 L/min del profilo: la fascia si colora di giallo e il limite velocità teorico è 8 km/h. Il rateo da 180 L/ha richiede 54 L/min a 10 km/h e risulta raggiungibile nel modello.

**Trasparenza sulla mappa:** il contorno può essere letto dalle coordinate `PNT`, ma le fasce colorate sono schematiche se il task ha soltanto `TZN`. Le griglie binarie `GRD` sono preservate ma non decodificate: non presentare queste fasce come le celle spaziali reali della prescrizione.

### 4. Meteo — mostra il ruolo del contesto

Inserisci vento a 16 km/h o pioggia tra un'ora: il semaforo diventa rosso secondo soglie illustrative. Se sono disponibili rete e coordinate, premi **Meteo live** per interrogare Open-Meteo.

Frase suggerita: *“Il meteo è un controllo contestuale e non una prescrizione: la regola finale dipende da etichetta, prodotto, ugello e valutazione locale.”*

### 5. Export — chiudi il ciclo

Premi **Esporta ISOXML annotato**. Il pacchetto mantiene XML e file accessori originali e aggiunge commenti `CAN` con profilo, codici ARAG selezionati e meteo. I `PDV` originali non vengono modificati.

Frase suggerita: *“Questo proof of concept dimostra il pre-flight e registra quali componenti abbiamo valutato. Il passo successivo è scrivere e convalidare una prescrizione effettivamente eseguibile sul terminale specifico.”*

## Domande che la giuria potrebbe fare

**“L'export comanda davvero il Bravo o il Delta?”**

*“Non ancora. La demo importa il pacchetto, calcola un controllo teorico e aggiunge commenti; non modifica la mappa target e non dichiara una validazione su terminale reale. Per quel passaggio servono documentazione del controller, test con ARAG e verifica su un pacchetto accettato dalla macchina.”*

**“Perché non abbassate la dose se la portata non basta?”**

*“La dose non va ridotta automaticamente per compensare un limite hardware: deve restare dentro all'etichetta e alla decisione del tecnico. Il sistema evidenzia la non fattibilità e fa valutare velocità, componenti, calibrazione o un'altra strategia.”*

**“Non lo fa già xFarm?”**

*“xFarm pubblicizza già mappe di prescrizione esportabili in ISOXML e scambio di task/mappe con monitor in cabina. La nostra ipotesi di differenziazione è il livello di dettaglio del singolo impianto ARAG — codici componenti, range misurabili, limiti di velocità/portata e pre-flight prima di uscire. Non diamo per scontato che xFarm non possa fare queste verifiche: la domanda è da validare con xFarm, ARAG e contoterzisti.”*

## Evoluzione consigliata dopo l'hackathon

1. Ottenere due o tre export reali xFarm e verificare gli elementi e le versioni ISOXML; implementare il parser `GRD` in una fase separata.
2. Chiedere ad ARAG una matrice ufficiale di compatibilità tra terminali, ECU, Flowtron/PWM, ugelli, sensori, cablaggi, firmware e versioni Task Controller.
3. Associare i codici alla scheda tecnica e alle curve di portata ugello/pressione, più i dati di calibrazione della macchina.
4. Integrare etichette fitosanitarie nazionali e compatibilità delle miscele solo con fonti aggiornate e approvazione del tecnico.
5. Con un contoterzista pilota registrare richieste di portata, limiti segnalati, modifiche effettuate, residuo in serbatoio e rapporto pianificato/eseguito.
