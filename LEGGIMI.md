# Ultimo Metro

Carichi l'ISOXML del campo, scegli l'hardware Nordson/ARAG che hai sull'irroratrice, vedi **dove il trattamento riesce e dove no**, e scarichi un file **specializzato per il tuo impianto**.

## Avvio (non serve installare nulla oltre a Python 3.9+)

| Sistema | Cosa fare |
|---|---|
| Windows | doppio clic su `run_windows.bat` |
| macOS | doppio clic su `run_macos.command` (la prima volta: clic destro → Apri) |
| Linux | `./run_linux.sh` |

Si apre il browser su `http://localhost:8765/`. Nella finestra nera compaiono anche gli indirizzi per gli amici.

## Come si usa

1. **File**: trascina il `.zip` (o `TASKDATA.XML`) oppure prova uno degli 8 esempi.
2. **Hardware**: cambia ugelli, Flowtron, SELETRON, velocità… a ogni modifica la mappa, gli indicatori e il verdetto si aggiornano. «Rispetto a prima» ti dice quante zone vanno meglio o peggio; «Fissa come riferimento» congela il confronto.
3. **Scarica**: spunta la conferma sui ratei che cambiano e scarica `…_NORDSON.zip`. Il server rilegge il file prodotto e verifica che i ratei coincidano con quelli attesi.

Schede in basso: **Zone** (tabella con ugello, velocità, pressione, duty per ogni zona), **Ugelli e portate** (campo di rateo di ogni ugello + ugelli o coppie SELETRON che farebbero meglio), **Etichette**, **Meteo**, **Come si calcola**. Il bottone *Rapporto* apre una pagina stampabile.

## Perché gli amici non riuscivano ad aprirlo (e cosa è cambiato)

- Il server ora ascolta su tutte le interfacce (`0.0.0.0`), non solo su `localhost`.
- Gli indirizzi mostrati sono ordinati: prima quello della rete principale, in fondo gli adattatori virtuali (VirtualBox, Docker, WSL), che erano la causa tipica dell'IP sbagliato. Il bottone **Condividi con gli amici** mostra indirizzo e QR.
- La porta è **8765** (la 5000 su Mac è occupata da AirPlay). Se è occupata, prende la successiva e te lo dice.
- Ogni visitatore ha una **sessione separata** (cookie): prima il file caricato da uno finiva a tutti.
- Windows: alla prima esecuzione compare la finestra del firewall: scegli **Consenti**. Se l'hai chiusa o annullata, esegui `apri_firewall_windows.bat` come amministratore (`chiudi_firewall_windows.bat` toglie la regola). macOS: «Consenti connessioni in entrata».
- Gli amici devono essere sulla **stessa rete Wi-Fi** (non dati mobili, non rete «ospiti» isolata dal resto).
- Fuori casa serve un tunnel (ad esempio `cloudflared tunnel --url http://localhost:8765`): non è incluso e **non l'ho potuto provare**. Chi ha l'indirizzo può usare l'app e caricare file: usalo solo per il tempo necessario.

## Cosa fa il file specializzato (e cosa no)

- Riscrive nel TASKDATA **solo i ratei che il tuo impianto non può erogare**, portandoli al valore più vicino che riesce a distribuire (strategia *variabile*), oppure a un rateo unico con stesso volume totale se la catena non esegue ratei variabili (strategia *uniforme*). Le zone già raggiungibili restano identiche; la geometria non viene toccata. Aggiunge una nota breve («UM NORDSON …») nell'operazione.
- **Non** contiene comandi proprietari Nordson/ARAG: ugello, pressione, velocità e duty sono indicazioni per l'operatore (tabella Zone e Rapporto).
- Il rateo riscritto cambia la dose: per questo l'app mostra la variazione di volume e chiede conferma.

## Cosa è calcolato e cosa è un'ipotesi

- Portata per ugello `q = rateo × velocità × interasse / 600`; curva portata/pressione dal catalogo ARAG/ASJ (interpolata). Per gli ugelli con un solo punto di catalogo (famiglie WRC 80/110 e AFC 80) uso √pressione e lo segnalo come **stima**.
- Con Flowtron (PWM) pressione fissa e apertura variabile; il **duty minimo (20 %) è un'ipotesi** modificabile. Senza PWM regola solo la pressione.
- Compatibilità fra componenti (terminale con Task Controller, IBX con IBX, regolazione di portata, finestra di pressione) dal catalogo pubblico: **da confermare con ARAG** prima di lavorare.
- Orientamento delle griglie GRD (riga 0 a sud, colonne da ovest): lettura mia della norma, da **confermare con un tuo export reale**. Non provato su un terminale Delta vero.
- **Etichette**: non ho un archivio di etichette e non invento autorizzazioni. La scheda raccoglie i dati che copi dall'etichetta ufficiale (restano nel tuo browser) e li confronta con i ratei; link alla banca dati del Ministero della Salute.
- **Meteo**: previsioni Open-Meteo (serve internet sul dispositivo); soglie orientative, non un parere agronomico.
- Il catalogo ha 119 prodotti (ugelli ASJ AFC 80/110, WRC 80/110 e SF 110, SELETRON, FCV, flussimetri Orion, valvole 853, pompa MSP400, terminali Delta/Bravo, IBX50/IBX100) tratti da pagine pubbliche; `docs/RICERCA_MERCATO.md` elenca le fonti.

## Per sviluppatori

- Solo libreria standard Python, nessuna dipendenza. `python3 app.py [--port=9000] [--local] [--no-browser]`; variabili `PORT`, `ULTIMO_METRO_HOST`, `NO_BROWSER`.
- `python3 -m unittest discover -s tests -t .` (49 test: lettura ISOXML, idraulica, catene, specializzazione, server, sessioni, caricamenti ostili).
- `python3 tools/make_examples.py` rigenera gli 8 esempi in `examples/`.
- Limiti: file 25 MB, 4 milioni di celle, 80 sessioni in memoria per 6 ore. XML con DTD/entità e ZIP con percorsi non sicuri vengono rifiutati.
- Struttura: `um/isoxml.py` (lettura/scrittura), `um/hardware.py` (catalogo e catena), `um/engine.py` (idraulica, piano, specializzazione, suggerimenti), `um/service.py` (sessioni, API), `um/server.py` (HTTP), `static/` (interfaccia).
