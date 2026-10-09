# Ultimo Metro — ricerca di mercato preliminare

**Data della ricognizione: 9 ottobre 2026.** Ricerca desk limitata a pagine pubbliche ufficiali Nordson/ARAG e xFarm. I codici sotto sono esempi per un prototipo: verificare sempre revisione, mercato, scheda tecnica, configurazione e disponibilità con il produttore. Questa nota non è una matrice certificata di compatibilità.

## 1. Cosa vende Nordson Precision Agriculture / ARAG

Nordson presenta Precision Agriculture come portfolio di sistemi e componenti per irrorazione di precisione, controllo infestanti, protezione colture e altre applicazioni agricole. Le famiglie pubblicate includono sistemi di controllo/monitor, centraline elettroniche, flussimetri e sensori, control box, valvole e collettori, valvole a sfera, raccordi, filtri, coperchi serbatoio, pompe, portaugelli/cappucci, ugelli, lance e accessori di irrorazione, irrigazione e componentistica industriale.

Fonte principale: [Nordson Precision Agriculture](https://www.nordson.com/en/divisions/precision-agriculture). La pagina evidenzia come prodotti principali Delta 70T, Flowtron, Orion 3 e valvole 853.

### Esempi di hardware per il prototipo

| Categoria | Codice e prodotto pubblico | Cosa può contribuire al controllo | Limite da non ignorare | Fonte ufficiale |
|---|---|---|---|---|
| Terminale / ISOBUS | `4675204` — Delta 70T IBX | Monitor, GPS/NAV, UT e funzioni Task Controller; terminale della famiglia IBX | Specificamente indicato per unità di controllo ARAG IBX; non equivale a compatibilità universale con qualsiasi ECU | [Scheda Delta 70T](https://www.aragnet.com/EN/INT/246/products/?PRD=110536) |
| Terminale / ISOBUS | `4675304` — Delta 80T IBX | Terminale IBX con funzioni GPS/NAV, UT e Task Controller | Verificare generazione, firmware e architettura installata | [Portfolio Delta](https://www.aragnet.com/EN/INT/246/products/?SEC=296&controlKey=&goTo=1) |
| Centralina irroratrice | `4679900` — IBX50 Sprayer | Controllo delle funzioni dell'irroratrice, integrato con monitor Delta IBX | Non assumere che sia intercambiabile o cumulabile con IBX100 Flowtron senza conferma del costruttore | [Scheda IBX50](https://www.aragnet.com/EN/INT/246/products/?PRD=142857) |
| PWM / rateo variabile | `4679013` — IBX100 ISOBUS Flowtron | La scheda cita shut-off ugello per ugello, applicazione a rateo variabile, raccolta dei dati di lavoro e integrazione con sistemi di visione AI/spot spraying | È il controllo di un sistema Flowtron; terminale, ECU, valvole, alimentazione, ugelli e configurazione devono essere verificati insieme | [Scheda IBX100 Flowtron](https://www.aragnet.com/EN/INT/246/products/?PRD=141923) |
| Computer irroratrice | `4674L0701` / `4674L0713` — Bravo 400S LT | Rate controller e monitor integrato; le varianti pubblicate hanno 7 sezioni/7 vie, quella 0713 comprende funzioni idrauliche | Non assumere che ogni configurazione Bravo esponga lo stesso controllo a singolo ugello/PWM di Flowtron | [Scheda Bravo 400S LT](https://www.aragnet.com/EN/INT/246/products/?PRD=115654) |
| Flussimetro | `46211P40000` — ORION 2+, range pubblicato 2–200 L/min | Confronto del range di misura con la richiesta teorica; famiglia citata da ARAG anche nei gruppi per atomizzatori | Il range di misura non è la portata realmente disponibile agli ugelli; servono taratura e verifica della configurazione | [Scheda ORION 2+](https://www.aragnet.com/EN/INT/246/products/?PRD=142638) |
| Flussimetro per altro contesto | `462032` — Orion 3, range pubblicato 2–80 L/min | Esempio di codice/sensore che può essere confrontato con un profilo | ARAG descrive Orion 3 per distribuzione di liquidi su seminatrici; non impostarlo come default per un'irroratrice senza conferma applicativa | [Scheda Orion 3](https://www.aragnet.com/EN/INT/246/products/?PRD=141196) |
| Valvola a sfera | `853T04A55` — valvola 853 | Verifica preliminare di pressione/portata nominale della valvola | La portata nominale a una specifica Δp non è la portata di lavoro dell'intero impianto né una certificazione del circuito | [Famiglia valvole 853](https://www.aragnet.com/EN/INT/246/products/?PRD=126532) |
| Attuatore / portaugello selettivo | `4063T95A0` — SELETRON quadruplo | Controllo elettronico selettivo dei set di ugelli; la scheda descrive comunicazione CAN-Bus e pressione massima di 8 bar per la famiglia esposta | Verificare versione, tenuta, montaggio, alimentazione e curva di lavoro effettivi | [Scheda SELETRON](https://www.aragnet.com/EN/INT/246/products/?PRD=97808) |
| Pompa | `97055201` — MSP400 | Riferimento nominale per controllo di plausibilità dell'impianto | La portata nominale di una pompa non coincide con la portata disponibile a pressione, perdite e utenze reali | [Catalogo pompe ARAG](https://www.aragnet.com/EN/INT/246/products/?SEC=296&controlKey=&goTo=1) |
| Ugello | `AFC11002` — ASJ/ARAG AFC 110 antideriva | Categoria di ugello; in una futura versione il codice dovrebbe puntare alla curva portata/pressione e alla compatibilità PWM dichiarata dal costruttore | Non è sufficiente conoscere il solo codice per stimare la portata senza pressione effettiva e dati tecnici completi | [ASJ AFC](https://asjnozzle.it/en/product/fan-low-drift-nozzles-afc-80-110/) |
| Ugello | `WRC11002` — ASJ/ARAG WRC 110 | Confronto tra famiglie di ugelli e caratteristiche pubblicate | Verificare portata a pressione, formulato, deriva e compatibilità applicativa | [ASJ WRC](https://asjnozzle.it/en/product/fan-nozzles-traditional-wrc/) |

Questa selezione iniziale è sufficiente a dimostrare un **catalogo per codici prodotto**, ma non sostituisce le specifiche complete. Nel codice i dati nulli o non confermati devono restare “da verificare”: non vanno colmati con valori ipotizzati.

## 2. Dove si sovrappone xFarm

La documentazione pubblica di xFarm afferma già che la piattaforma crea mappe di prescrizione a partire da immagini satellitari, consente l'analisi di mappe e offre l'esportazione in ISOXML, Shapefile, Trimble e John Deere. L'offerta pubblica descrive anche lo scambio di task, prescrizioni e mappe di applicazione con monitor in cabina tramite moduli di telemetry/task management e funzioni per attività agronomiche.

Fonti:

- [xFarm — Precision Agriculture](https://www.xfarm.ag/en/precision-agriculture)
- [xFarm — release notes](https://www.xfarm.ag/en/release-notes)
- [xFarm Demo — funzioni della piattaforma](https://www.xfarm.ag/en/xfarm-demo)

**Conseguenza per il pitch:** non è credibile differenziarsi soltanto con “carichiamo ISOXML, vediamo la mappa, controlliamo il meteo e registriamo il trattamento”. Una parte importante di questo workflow è già descritta pubblicamente da xFarm. Non abbiamo prove per affermare che xFarm sia incapace di usare la configurazione specifica di una macchina: va chiesto e provato, non presunto.

## 3. Ipotesi di differenziazione di Ultimo Metro

La proposta più forte è diventare un **pre-flight checker, o gemello digitale tecnico della macchina**, che riceve una prescrizione già approvata e la confronta con la precisa configurazione installata sull'irroratrice.

1. **Inventario tramite codice prodotto.** Il contoterzista o l'installatore registra terminale, ECU, sistema PWM, flussimetro, valvole, attuatori SELETRON, pompa, filtri e ugelli. Il dato viene salvato nel profilo della macchina e non reinserito a ogni lavoro.
2. **Modello d'impianto.** Il codice rimanda alla scheda ufficiale, ma il modello utilizza anche la variante precisa, la curva di portata/pressione dell'ugello, il numero di ugelli, la larghezza, l'intervallo operativo, l'eventuale duty-cycle PWM e la calibrazione. I dati sconosciuti generano una richiesta di verifica.
3. **Fattibilità della prescrizione.** Per ogni rateo riconosciuto confronta la portata teorica richiesta \(Q = R \times v \times W / 600\) con la portata utile misurata/calibrata e i limiti dei componenti, mantenendo unità e riferimenti ISOXML coerenti. Evidenzia dove la macchina non può rispettare la prescrizione al regime scelto, senza cambiare in automatico la dose agronomica.
4. **Piano di correzione operativo.** Suggerisce azioni approvate/possibili — per esempio verificare velocità, pressione, ugello, configurazione o pianificare un passaggio distinto — solo quando la matrice tecnica documenta la conseguenza.
5. **Dopo il lavoro.** Se il controller espone dati di esecuzione, confronta target ed eseguito e crea un rapporto tracciabile. In fase di demo il log simulato deve essere dichiarato come simulato.

In breve: **xFarm pianifica la prescrizione; Ultimo Metro verifica se la macchina ARAG effettivamente configurata può eseguirla e documenta le eccezioni prima di entrare in campo.** Questa è l'ipotesi di differenziazione da verificare con i partner.

## 4. Quali input manuali servono davvero

Non chiedere all'operatore una lunga scheda tecnica a ogni trattamento. Il dato deve essere raccolto una volta per macchina, idealmente da installatore, QR/seriale, anagrafica o ECU:

- codici precisi delle unità e dei componenti installati; versione hardware/firmware e tipo di terminale/Task Controller;
- modello e geometria dell'attrezzatura, serbatoio, larghezza, numero di ugelli e sezioni, pressione operativa, velocità realistiche;
- curve ufficiali di portata degli ugelli e relativi limiti PWM, portata utile della pompa/circuito, calibrazione del flussimetro, stato di manutenzione/usura;
- configurazione idraulica (selezione valvole, filtri, ritorni) e connessioni che incidono sul comportamento del circuito.

Per il singolo lavoro l'operatore dovrebbe confermare soltanto le variabili che cambiano: campo/task, attrezzatura effettivamente agganciata, stato della miscela/serbatoio, eventuali anomalie, meteo locale e condizioni che il sistema non legge automaticamente. La scelta del prodotto e l'autorizzazione agronomica restano al tecnico.

## 5. I tre dati di mercato da chiedere ai mentor

1. **A xFarm:** quale parte di machine profile, configurazione ugelli/PWM, calibrazione e dati di esecuzione è già disponibile nell'offerta italiana e nelle integrazioni API? Si può importare un task reale e ottenere la curva/set-up della macchina?
2. **Ad ARAG:** esiste una matrice ufficiale macchina/controller/ECU/Flowtron/SELETRON/nozzle e una API o telemetria per leggere target ed eseguito? Quali modelli e versioni possono ricevere una prescrizione modificata?
3. **A un contoterzista:** gli è mai capitato di ricevere una mappa teoricamente corretta ma non eseguibile alla velocità/pressione prevista? Quante volte, quale conseguenza (area non trattata, calo velocità, residuo, ritorno in campo) e come la scopre oggi?

Un solo caso vero e quantificato — “la mappa chiedeva X, la macchina riusciva a Y, il problema è stato trovato prima/dopo?” — è più persuasivo di un ROI inventato.

## 6. KPI del pilot

- percentuale dell'area mappata con fattibilità stimata e percentuale con dati hardware mancanti;
- numero di prescrizioni con almeno una zona oltre la portata/pressione/velocità documentata;
- differenza tra rateo target e rateo effettivo (se il controller offre telemetria utilizzabile);
- residuo di miscela a fine giornata e tempo di compilazione/report risparmiato;
- tasso di falsi positivi delle segnalazioni e tempo necessario per risolvere un warning.

## 7. Rischi tecnici da dichiarare

- **ISOXML:** un pacchetto può includere `TASKDATA.XML` e file binari collegati come `GRD`/`TLG`. Leggere l'XML non equivale a ricostruire la griglia reale o a modificare una prescrizione completa.
- **Codici hardware:** un catalogo pubblico descrive singoli prodotti, ma non certifica in automatico la catena completa, la variante, il cablaggio, la pressione o il firmware.
- **Agronomia e normativa:** non dedurre l'etichetta, la dose ammessa o la compatibilità di miscela dal nome del prodotto. Questi dati richiedono database aggiornato, tracciabilità e validazione del tecnico.
- **Dati post-trattamento:** non dire “leggiamo dalla macchina” finché non avete confermato interfaccia, telemetria e API con ARAG.

## Fonti consultate

- Nordson Precision Agriculture: <https://www.nordson.com/en/divisions/precision-agriculture>
- ARAG Delta 70T: <https://www.aragnet.com/EN/INT/246/products/?PRD=110536>
- ARAG Delta 80T / catalogo terminali: <https://www.aragnet.com/EN/INT/246/products/?SEC=296&controlKey=&goTo=1>
- ARAG IBX50: <https://www.aragnet.com/EN/INT/246/products/?PRD=142857>
- ARAG IBX100 Flowtron: <https://www.aragnet.com/EN/INT/246/products/?PRD=141923>
- ARAG Bravo 400S LT: <https://www.aragnet.com/EN/INT/246/products/?PRD=115654>
- ARAG ORION 2+: <https://www.aragnet.com/EN/INT/246/products/?PRD=142638>
- ARAG Orion 3: <https://www.aragnet.com/EN/INT/246/products/?PRD=141196>
- ARAG SELETRON: <https://www.aragnet.com/EN/INT/246/products/?PRD=97808>
- ARAG valves 853: <https://www.aragnet.com/EN/INT/246/products/?PRD=126532>
- ASJ/ARAG AFC: <https://asjnozzle.it/en/product/fan-low-drift-nozzles-afc-80-110/>
- ASJ/ARAG WRC: <https://asjnozzle.it/en/product/fan-nozzles-traditional-wrc/>
- xFarm Precision Agriculture: <https://www.xfarm.ag/en/precision-agriculture>
- xFarm release notes: <https://www.xfarm.ag/en/release-notes>
- xFarm platform tour: <https://www.xfarm.ag/en/xfarm-demo>
