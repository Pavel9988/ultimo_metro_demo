(() => {
  const $ = (id) => document.getElementById(id);
  let currentSummary = null;
  let busy = false;
  let weatherSource = 'manual';
  let toastTimer = null;
  let aragCatalog = { products: [], categories: {}, note: '' };

  function debounce(fn, delay = 280) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
  }

  function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3700);
  }

  function showGlobalError(message) {
    const box = $('globalMessage');
    box.textContent = message;
    box.classList.remove('hidden');
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function clearGlobalError() {
    $('globalMessage').classList.add('hidden');
    $('globalMessage').textContent = '';
  }

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Errore HTTP ${response.status}`);
    return data;
  }

  function setBusy(value) {
    busy = value;
    $('loadDemoBtn').disabled = value;
    $('exportBtn').disabled = value || !currentSummary;
    $('loadDemoBtn').style.opacity = value ? '.6' : '1';
  }

  function showLoadedState(summary) {
    currentSummary = summary;
    clearGlobalError();
    $('workspace').classList.remove('hidden');
    $('loadedFileBar').classList.remove('hidden');
    $('loadedFileName').textContent = summary.filename || 'TASKDATA.XML';
    $('loadedFileMeta').textContent = `ISOXML v${summary.version} · ${summary.counts.tasks} task · ${summary.package_files} file nel pacchetto`;
    $('metricTasks').textContent = summary.counts.tasks;
    $('metricArea').textContent = summary.total_area_ha == null ? '—' : formatNumber(summary.total_area_ha, 2);
    $('metricZones').textContent = summary.counts.zones + summary.counts.grids;
    $('metricProducts').textContent = summary.counts.products;
    $('metricTaskFoot').textContent = summary.counts.tasks === 1 ? '1 operazione individuata' : 'Operazioni individuate';
    $('metricZoneFoot').textContent = summary.has_grid ? `${summary.counts.grids} griglia/e GRD + ${summary.counts.zones} zone` : `${summary.counts.zones} zone TZN rilevate`;
    $('fieldName').textContent = summary.fields?.[0]?.name || 'Campo non identificato';
    $('fieldSub').textContent = summary.fields?.[0]?.id ? `ID campo: ${summary.fields[0].id}` : 'Nome campo non presente nel file';
    $('fieldArea').textContent = summary.fields?.[0]?.area_ha == null ? '—' : formatNumber(summary.fields[0].area_ha, 2);
    $('fieldCropChip').textContent = summary.fields?.[0]?.crop || 'Coltura non indicata';
    $('sourceSoftware').textContent = summary.manufacturer || 'FMIS non indicato';
    $('isoVersion').textContent = `ISOXML ${summary.version}`;
    $('packageFiles').textContent = `${summary.package_files} file${summary.was_zip ? '' : ' · XML singolo'}`;
    $('gridStatus').textContent = summary.has_grid ? 'Griglia GRD presente' : (summary.counts.zones ? 'Zone TZN presenti' : 'Prescrizione da verificare');
    $('targetRateSource').textContent = summary.target_rate_l_ha != null
      ? 'Valore letto da PDV + VPN · dose massima rilevata'
      : 'Nessun valore L/ha riconosciuto · inserimento manuale';
    if (summary.target_rate_l_ha != null && Number.isFinite(Number(summary.target_rate_l_ha))) {
      $('targetRate').value = Number(summary.target_rate_l_ha).toFixed(2).replace(/\.00$/, '');
    }
    renderZones(summary);
    renderFieldMap(summary, currentSummary ? getMachine() : null);
    renderValidationDetails(summary);
    $('exportReadyText').textContent = `Pacchetto pronto · ${summary.counts.tasks} task da annotare`;
    $('exportBtn').disabled = false;
    $('stepper')?.classList.remove('hidden');
    schedulePreflight();
  }

  function formatNumber(value, decimals = 1) {
    if (value == null || !Number.isFinite(Number(value))) return '—';
    return new Intl.NumberFormat('it-IT', { maximumFractionDigits: decimals, minimumFractionDigits: 0 }).format(Number(value));
  }

  function renderZones(summary) {
    const holder = $('zoneList');
    const zones = summary.zones || [];
    if (!zones.length) {
      holder.innerHTML = '<div class="empty-state">Nessuna TZN individuata. Il file potrebbe avere una griglia GRD o non contenere una prescrizione a rateo variabile.</div>';
      return;
    }
    holder.innerHTML = zones.map((zone, index) => {
      const rate = (zone.values || []).find(value => /l\/ha|lt\/ha/i.test(value.unit || ''));
      const mainValue = rate || (zone.values || [])[0];
      const rateLabel = mainValue ? `${escapeHTML(mainValue.display)} <small>${escapeHTML(mainValue.unit)}</small>` : '—';
      const detail = (zone.values || []).map(value => {
        const product = value.product ? ` · ${escapeHTML(value.product)}` : '';
        return `DDI ${escapeHTML(value.ddi || '—')}: ${escapeHTML(value.display)} ${escapeHTML(value.unit)}${product}`;
      }).join('<br>');
      return `<div class="zone-card"><span class="zone-color"></span><div class="zone-body"><div class="zone-title-row"><strong>${escapeHTML(zone.name || `Zona ${index + 1}`)}</strong><span class="zone-code">COD. ${escapeHTML(zone.code || '—')}</span></div><div class="zone-detail">${detail || 'Zona senza PDV leggibili nel file.'}</div></div><div class="zone-rate"><strong>${rateLabel}</strong><span>${mainValue ? 'valore interpretato' : 'nessun valore'}</span></div></div>`;
    }).join('');
  }

  function selectedCatalogProduct(selectId) {
    const code = $(selectId)?.value;
    return (aragCatalog.products || []).find(product => product.code === code) || null;
  }

  function zoneRate(zone) {
    for (const value of zone.values || []) {
      const unit = String(value.unit || '').toLowerCase().replace(/\s/g, '').replace('litri', 'l');
      if (unit.includes('l/ha') || unit.includes('lt/ha')) {
        const number = Number(value.value);
        if (Number.isFinite(number) && number > 0) return number;
      }
    }
    return null;
  }

  function classifyZone(zone, machine) {
    if (!machine?.valid) return { level: 'warn', label: 'DATI DA VERIFICARE', rate: zoneRate(zone) };
    const importedRate = zoneRate(zone);
    const rate = importedRate ?? machine.rate;
    if (!Number.isFinite(rate) || rate <= 0) return { level: 'warn', label: 'DOSE NON LETTA', rate: null };
    const maxSpeed = (600 * machine.flow) / (rate * machine.width);
    if (importedRate == null) {
      return { level: 'warn', label: 'DOSE FALLBACK', rate, maxSpeed, importedRate: false, meterOutOfRange: false };
    }
    const hydraulicLevel = maxSpeed < machine.speedMin ? 'bad' : maxSpeed < machine.speedMax ? 'warn' : 'good';
    // A selected meter can be out of its published measuring range at the requested speed/rate.
    // This makes the zone yellow pending verification; it must not be confused with pump flow.
    const requiredAtMin = (rate * machine.speedMin * machine.width) / 600;
    const requiredAtMax = (rate * machine.speedMax * machine.width) / 600;
    const meterCaps = machine.flowmeter?.capabilities;
    const meterOutOfRange = meterCaps && Number.isFinite(Number(meterCaps.range_min_l_min)) && Number.isFinite(Number(meterCaps.range_max_l_min))
      && (requiredAtMin < Number(meterCaps.range_min_l_min) || requiredAtMax > Number(meterCaps.range_max_l_min));
    if (hydraulicLevel === 'bad') return { level: 'bad', label: 'ROSSO', rate, maxSpeed, importedRate: importedRate != null, meterOutOfRange };
    if (hydraulicLevel === 'warn' || meterOutOfRange) return { level: 'warn', label: 'GIALLO', rate, maxSpeed, importedRate: importedRate != null, meterOutOfRange };
    return { level: 'good', label: 'VERDE', rate, maxSpeed, importedRate: importedRate != null, meterOutOfRange: false };
  }

  function renderFieldMap(summary, machine = null) {
    const svg = $('fieldMap');
    if (!svg) return;
    const points = (summary.field_points || []).filter(p => Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon)));
    const ns = 'http://www.w3.org/2000/svg';
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const make = (tag, attrs = {}, text = '') => {
      const el = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
      if (text !== '') el.textContent = text;
      return el;
    };
    svg.appendChild(make('defs'));
    const defs = svg.firstChild;
    const pattern = make('pattern', { id: 'gridPatternDynamic', width: '22', height: '22', patternUnits: 'userSpaceOnUse' });
    pattern.appendChild(make('path', { d: 'M 22 0 L 0 0 0 22', fill: 'none', stroke: '#d8e4db', 'stroke-width': '.7' }));
    defs.appendChild(pattern);
    svg.appendChild(make('rect', { width: '540', height: '245', fill: '#f3f7f2' }));
    svg.appendChild(make('rect', { width: '540', height: '245', fill: 'url(#gridPatternDynamic)' }));

    let projected = [];
    let actualBoundary = points.length >= 3;
    if (actualBoundary) {
      const lats = points.map(p => Number(p.lat)), lons = points.map(p => Number(p.lon));
      const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const latSpan = maxLat - minLat || 0.0001, lonSpan = maxLon - minLon || 0.0001;
      projected = points.map(p => ({ x: 48 + ((Number(p.lon) - minLon) / lonSpan) * 444, y: 30 + ((maxLat - Number(p.lat)) / latSpan) * 185 }));
    } else {
      projected = [{x:83,y:45},{x:419,y:31},{x:455,y:174},{x:331,y:211},{x:102,y:188}];
    }
    // ISOXML often repeats the first vertex as the final vertex; omit that duplicate when projecting zones.
    if (projected.length > 3 && Math.abs(projected[0].x - projected[projected.length - 1].x) < 0.1 && Math.abs(projected[0].y - projected[projected.length - 1].y) < 0.1) projected.pop();
    const fieldPath = projected.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ') + ' Z';
    const clip = make('clipPath', { id: 'fieldShapeClip', clipPathUnits: 'userSpaceOnUse' });
    clip.appendChild(make('path', { d: fieldPath }));
    defs.appendChild(clip);

    const zones = (summary.zones || []).filter(zone => zone && (zone.values || []).length);
    const displayZones = zones.length ? zones : [{ name: 'Area senza rateo letto', code: '—', values: [] }];
    const statuses = displayZones.map(zone => classifyZone(zone, machine));
    const xMin = Math.min(...projected.map(p => p.x)), xMax = Math.max(...projected.map(p => p.x));
    // TZN contains prescription values but no polygon coordinates. This clipped banding is intentionally schematic.
    const zoneLayer = make('g', { 'clip-path': 'url(#fieldShapeClip)' });
    const colors = { good: '#9fd29b', warn: '#f1cc69', bad: '#e98f83' };
    displayZones.forEach((zone, index) => {
      const left = xMin + (xMax - xMin) * index / displayZones.length;
      const right = xMin + (xMax - xMin) * (index + 1) / displayZones.length;
      const status = statuses[index];
      zoneLayer.appendChild(make('rect', { x: left, y: 18, width: Math.max(1, right - left), height: 220, fill: colors[status.level] || '#cdd9ce', opacity: '.9' }));
      // Distinguish the schematic subdivisions without pretending they are real GRD cell positions.
      if (index > 0) zoneLayer.appendChild(make('path', { d: `M ${left} 20 L ${left} 230`, stroke: '#ffffff', 'stroke-width': '2', 'stroke-dasharray': '4 4', opacity: '.9' }));
    });
    svg.appendChild(zoneLayer);
    svg.appendChild(make('path', { d: fieldPath, fill: 'none', stroke: '#315d3e', 'stroke-width': '2.8', 'stroke-linejoin': 'round' }));

    displayZones.forEach((zone, index) => {
      const left = xMin + (xMax - xMin) * index / displayZones.length;
      const right = xMin + (xMax - xMin) * (index + 1) / displayZones.length;
      const cx = (left + right) / 2;
      const status = statuses[index];
      const label = String(zone.name || `Zona ${index + 1}`).slice(0, 23);
      const rateText = status.rate != null ? `${formatNumber(status.rate, 1)} L/ha` : 'dose non letta';
      svg.appendChild(make('text', { x: cx, y: 112, 'text-anchor': 'middle', fill: '#24412e', 'font-size': displayZones.length > 3 ? '8' : '10', 'font-weight': '700', 'font-family': 'Manrope, sans-serif' }, label));
      svg.appendChild(make('text', { x: cx, y: 128, 'text-anchor': 'middle', fill: '#315d3e', 'font-size': '10', 'font-family': 'DM Mono, monospace' }, rateText));
      svg.appendChild(make('rect', { x: cx - 36, y: 138, width: 72, height: 19, rx: 6, fill: status.level === 'good' ? '#e3f5df' : status.level === 'warn' ? '#fff2c6' : '#ffe1dc', stroke: status.level === 'good' ? '#68ab67' : status.level === 'warn' ? '#d6a633' : '#d66e61', 'stroke-width': '.8' }));
      svg.appendChild(make('text', { x: cx, y: 151, 'text-anchor': 'middle', fill: status.level === 'good' ? '#28723a' : status.level === 'warn' ? '#89630e' : '#a43c32', 'font-size': '8', 'font-weight': '800', 'font-family': 'DM Mono, monospace' }, status.label));
      if (status.maxSpeed != null) {
        svg.appendChild(make('text', { x: cx, y: 170, 'text-anchor': 'middle', fill: '#315d3e', 'font-size': '8', 'font-family': 'DM Mono, monospace' }, `v max ${formatNumber(status.maxSpeed, 1)} km/h`));
      }
    });
    const tag = make('g', { transform: 'translate(16 13)' });
    tag.appendChild(make('rect', { width: '156', height: '24', rx: '6', fill: '#ffffff', stroke: '#dce6de', opacity: '.97' }));
    tag.appendChild(make('circle', { cx: '12', cy: '12', r: '3.3', fill: '#42784c' }));
    tag.appendChild(make('text', { x: '22', y: '15.5', fill: '#43634a', 'font-size': '8.5', 'font-family': 'DM Mono, monospace' }, actualBoundary ? 'CONFINE LETTO DA ISOXML' : 'GEOMETRIA SCHEMATICA'));
    svg.appendChild(tag);

    const hasGrid = Boolean(summary.has_grid || summary.counts?.grids);
    $('mapModeTag').textContent = machine?.valid ? 'PREFLIGHT PER ZONA' : 'CARICA / CONFIGURA';
    const source = actualBoundary ? 'il contorno deriva da PFD/PNT del file' : 'il contorno è sintetico perché mancano almeno 3 coordinate PNT';
    const gridText = hasGrid
      ? ' Il file contiene GRD, ma la demo non decodifica ancora le celle binarie: la posizione delle fasce non è la geografia reale della GRD.'
      : ' Le TZN non hanno una geometria spaziale: le fasce sono divise solo per visualizzare il confronto delle dosi.';
    const capabilityText = machine?.valid
      ? ` I colori confrontano ogni dose con il profilo demo (${formatNumber(machine.flow, 0)} L/min, barra ${formatNumber(machine.width, 1)} m, ${formatNumber(machine.speedMin, 1)}–${formatNumber(machine.speedMax, 1)} km/h).`
      : ' Configura un profilo macchina per calcolare i colori.';
    $('mapNote').innerHTML = `<span>ⓘ</span> ${source}.${gridText}${capabilityText} È una stima di capacità teorica, non una misura della deposizione reale degli ugelli.`;
  }

  function renderValidationDetails(summary) {
    const holder = $('validationDetails');
    const items = [];
    items.push({ level: 'good', icon: '✓', title: 'Struttura XML letta', detail: `Radice ${summary.root}; versione ${summary.version}; software: ${summary.manufacturer || 'non indicato'}.` });
    items.push({ level: summary.counts.tasks ? 'good' : 'bad', icon: summary.counts.tasks ? '✓' : '!', title: 'Task e collegamenti', detail: `${summary.counts.tasks} task e ${summary.counts.fields} campi; verifica riferimenti e contenuti mancanti prima di inviare a un terminale.` });
    items.push({ level: summary.has_recipe ? 'good' : 'warn', icon: summary.has_recipe ? '✓' : '!', title: 'Prescrizione', detail: summary.has_grid ? `${summary.counts.grids} elemento/i GRD presenti. I binari sono preservati, ma non visualizzati cella per cella.` : `${summary.counts.zones} zona/e TZN. L'eventuale geometria spaziale della dose non viene convalidata da questa demo.` });
    items.push({ level: summary.counts.products ? 'good' : 'warn', icon: summary.counts.products ? '✓' : '!', title: 'Catalogo prodotti', detail: summary.counts.products ? `${summary.counts.products} record PDT individuati. Non viene verificata l'autorizzazione fitosanitaria nazionale né la compatibilità di miscela.` : 'Nessun record PDT individuato.' });
    items.push({ level: 'warn', icon: 'i', title: 'Controllo standard / macchina', detail: 'Non viene eseguita una validazione XSD completa, né una prova su Bravo/terminali ARAG. Il formato non basta da solo a garantire la compatibilità.' });
    holder.innerHTML = items.map(item => `<div class="diagnostic-card ${item.level === 'good' ? '' : item.level}"><span class="diagnostic-icon">${item.icon}</span><div><strong>${escapeHTML(item.title)}</strong><p>${escapeHTML(item.detail)}</p></div></div>`).join('');
  }

  function getWeatherStatus() {
    const wind = Number($('wind').value);
    const temperature = Number($('temperature').value);
    const rain = Number($('rainHours').value);
    if (![wind, temperature, rain].every(Number.isFinite)) return { status: 'GIALLA', level: 'warn', title: 'Dati meteo incompleti', detail: 'Inserisci vento, temperatura e pioggia prevista.' };
    if (wind > 15 || rain < 2 || temperature >= 32) {
      let reason = wind > 15 ? 'vento elevato' : (rain < 2 ? 'pioggia imminente' : 'temperatura elevata');
      return { status: 'ROSSA', level: 'bad', title: 'Trattamento da rivalutare', detail: `Attenzione: ${reason}. Verifica etichetta, condizioni locali e indicazioni del tecnico.` };
    }
    if (wind > 10 || rain < 4 || temperature >= 28) {
      return { status: 'GIALLA', level: 'warn', title: 'Condizioni da verificare', detail: 'Valuta ugello, deriva, prodotto e finestra utile prima di partire.' };
    }
    return { status: 'VERDE', level: 'good', title: 'Condizioni favorevoli (demo)', detail: 'I parametri inseriti non superano le soglie dimostrative.' };
  }

  function getMachine() {
    const tank = Number($('tank').value);
    const width = Number($('width').value);
    const flow = Number($('flow').value);
    const speedMin = Number($('speedMin').value);
    const speedMax = Number($('speedMax').value);
    const rate = Number($('targetRate').value);
    const fieldArea = currentSummary?.fields?.[0]?.area_ha;
    const controller = selectedCatalogProduct('controllerCode');
    const rateControl = selectedCatalogProduct('rateControlCode');
    const flowmeter = selectedCatalogProduct('flowmeterCode');
    const actuator = selectedCatalogProduct('actuatorCode');
    const ecu = selectedCatalogProduct('ecuCode');
    const values = [tank, width, flow, speedMin, speedMax, rate];
    if (!values.every(Number.isFinite) || values.some(value => value <= 0) || speedMin > speedMax) return { valid: false };
    const maxAchievableSpeed = (600 * flow) / (rate * width);
    const requiredFlowAtMaxSpeed = (rate * speedMax * width) / 600;
    const requiredFlowAtMinSpeed = (rate * speedMin * width) / 600;
    const litersEstimate = Number.isFinite(fieldArea) ? fieldArea * rate : null;
    const tanksEstimate = litersEstimate != null ? Math.ceil(litersEstimate / tank) : null;
    let level = 'good';
    let title = 'Fattibilità idraulica compatibile';
    let detail = `A ${formatNumber(rate, 1)} L/ha e ${formatNumber(speedMax, 1)} km/h servono circa ${formatNumber(requiredFlowAtMaxSpeed, 1)} L/min. Portata configurata: ${formatNumber(flow, 1)} L/min.`;
    if (maxAchievableSpeed < speedMin) {
      level = 'bad';
      title = 'Piano non fattibile con questi parametri';
      detail = `Per mantenere ${formatNumber(rate, 1)} L/ha la velocità teorica massima è ${formatNumber(maxAchievableSpeed, 1)} km/h, inferiore al minimo impostato (${formatNumber(speedMin, 1)} km/h). Verifica ugelli, portata e larghezza.`;
    } else if (maxAchievableSpeed < speedMax) {
      level = 'warn';
      title = `Velocità massima consigliata: ${formatNumber(maxAchievableSpeed, 1)} km/h`;
      detail = `A ${formatNumber(speedMax, 1)} km/h servirebbero ${formatNumber(requiredFlowAtMaxSpeed, 1)} L/min. La portata inserita consente teoricamente fino a ${formatNumber(maxAchievableSpeed, 1)} km/h; non abbassare la dose per compensare.`;
    }
    const chainCompatible = Boolean(controller) && !(rateControl?.capabilities?.pwm && controller?.capabilities?.ibx_only !== true);
    const meterRangeWarning = Boolean(flowmeter?.capabilities && Number.isFinite(Number(flowmeter.capabilities.range_max_l_min)) &&
      (requiredFlowAtMaxSpeed > Number(flowmeter.capabilities.range_max_l_min) ||
       requiredFlowAtMinSpeed < Number(flowmeter.capabilities.range_min_l_min)));
    return { valid: true, level, title, detail, tank, width, flow, speedMin, speedMax, rate, maxAchievableSpeed, requiredFlowAtMaxSpeed, requiredFlowAtMinSpeed, litersEstimate, tanksEstimate, fieldArea, controller, rateControl, flowmeter, actuator, ecu, meterRangeWarning, chainCompatible };
  }

  function setCheckRow(level, title, detail, tag) {
    const marker = level === 'good' ? '✓' : level === 'bad' ? '!' : '•';
    return `<div class="check-row ${level === 'good' ? '' : level}"><span class="check-symbol">${marker}</span><div><strong>${escapeHTML(title)}</strong><small>${escapeHTML(detail)}</small></div><span class="check-state">${escapeHTML(tag)}</span></div>`;
  }

  function updatePreflight() {
    if (!currentSummary) return;
    const weather = getWeatherStatus();
    const machine = getMachine();
    const summary = currentSummary;
    renderFieldMap(summary, machine);
    renderHardwareCatalogResult(machine);
    $('weatherStatusText').textContent = weather.title;
    $('weatherStatusDetail').textContent = weather.detail;
    $('weatherTag').textContent = weather.status;
    $('weatherTag').className = `weather-tag ${weather.level === 'good' ? 'green-tag' : weather.level === 'warn' ? 'yellow-tag' : 'red-tag'}`;
    $('weatherOrb').className = `weather-orb ${weather.level === 'good' ? 'green-orb' : weather.level === 'warn' ? 'yellow-orb' : 'red-orb'}`;

    let rows = [];
    rows.push(setCheckRow(summary.counts.tasks > 0 ? 'good' : 'bad', 'Struttura e task', `${summary.counts.tasks} task · ISOXML ${summary.version} · origine ${summary.manufacturer || 'non indicata'}`, summary.counts.tasks ? 'LETTO' : 'ERRORE'));
    rows.push(setCheckRow(summary.fields.length > 0 ? 'good' : 'warn', 'Campo e superficie', summary.fields.length ? `${summary.fields.length} campo/i; geometria ${summary.field_points?.length >= 3 ? 'presente' : 'non individuata'}.` : 'Il file non contiene PFD riconoscibili.', summary.fields.length ? 'OK' : 'ATTENZIONE'));
    rows.push(setCheckRow(summary.has_recipe ? 'good' : 'warn', 'Prescrizione', summary.has_grid ? `${summary.counts.grids} griglia/e trovate; binari non interpretati nella mappa.` : `${summary.counts.zones} zone TZN; unità/valori dipendono dai riferimenti VPN.`, summary.has_recipe ? 'RILEVATA' : 'VERIFICARE'));
    rows.push(setCheckRow(machine.valid ? machine.level : 'bad', 'Compatibilità idraulica', machine.valid ? machine.detail : 'Controlla il profilo macchina nei parametri avanzati.', machine.valid ? ({ good: 'OK', warn: 'LIMITE', bad: 'NON FATTIBILE' }[machine.level]) : 'DATI'));
    const meterCheckLevel = !machine.valid || !machine.flowmeter || machine.meterRangeWarning ? 'warn' : 'good';
    const meterCheckDetail = !machine.flowmeter
      ? 'Nessun flussimetro selezionato: la capacità è stimata dal profilo macchina e va confermata.'
      : machine.meterRangeWarning
        ? 'La richiesta teorica alle velocità impostate esce dal range del sensore scelto; verifica il dato e l’applicazione del modello.'
        : 'Nessun superamento teorico del range pubblicato rilevato. Tipo di applicazione e calibrazione restano da confermare.';
    rows.push(setCheckRow(meterCheckLevel, 'Range flussimetro selezionato', meterCheckDetail, machine.meterRangeWarning ? 'VERIFICARE' : (machine.flowmeter ? 'RANGE' : 'N/D')));
    const controllerName = machine.controller ? `${machine.controller.code} · ${machine.controller.name}` : 'Controller non selezionato';
    const rateName = machine.rateControl ? `${machine.rateControl.code} · ${machine.rateControl.name}` : 'Nessun modulo PWM / rateo selezionato';
    const precisionDetail = machine.chainCompatible ? `${controllerName}; ${rateName}. Verifica finale del cablaggio e del modello specifico necessaria.` : `${controllerName} e ${rateName}: combinazione da verificare; Flowtron IBX richiede un'architettura IBX compatibile.`;
    rows.push(setCheckRow(machine.chainCompatible ? (machine.rateControl?.capabilities?.variable_rate ? 'good' : 'warn') : 'bad', 'Catena di controllo ARAG', precisionDetail, machine.chainCompatible ? (machine.rateControl?.capabilities?.variable_rate ? 'VRA / DA VERIFICARE' : 'DA VERIFICARE') : 'VERIFICA'));
    rows.push(setCheckRow(weather.level, 'Finestra meteo', weather.detail, weather.status));
    $('checkList').innerHTML = rows.join('');

    let overallLevel = 'good';
    let overallTitle = 'Pre-flight senza blocchi dimostrativi';
    let overallDetail = 'Il file è stato letto e i parametri inseriti risultano compatibili con le soglie della demo.';
    if (!machine.valid || machine.level === 'bad' || weather.level === 'bad' || summary.counts.tasks === 0) {
      overallLevel = 'bad'; overallTitle = 'Revisione necessaria prima del trattamento'; overallDetail = 'C’è almeno una condizione critica. Correggi i parametri o rivaluta la finestra operativa con il tecnico.';
    } else if (machine.level === 'warn' || weather.level === 'warn' || !summary.has_recipe || !summary.fields.length || !machine.chainCompatible || !machine.rateControl?.capabilities?.variable_rate || machine.meterRangeWarning || !machine.flowmeter || (machine.ecu?.code === '4679900' && machine.rateControl?.capabilities?.pwm)) {
      overallLevel = 'warn'; overallTitle = 'Controlli da completare'; overallDetail = 'La lettura è riuscita, ma almeno un vincolo richiede una verifica manuale.';
    }
    const overall = $('overallStatus');
    overall.className = `overall-status ${overallLevel}`;
    overall.querySelector('.overall-icon').textContent = overallLevel === 'good' ? '✓' : overallLevel === 'warn' ? '!' : '×';
    overall.querySelector('strong').textContent = overallTitle;
    overall.querySelector('small').textContent = overallDetail;

    const result = $('hardwareResult');
    result.className = `hardware-result ${machine.valid ? machine.level : 'bad'}`;
    result.querySelector('.result-icon').textContent = machine.valid && machine.level === 'good' ? '✓' : machine.valid && machine.level === 'warn' ? '↘' : '!';
    if (machine.valid) {
      let note = machine.detail;
      if (machine.litersEstimate != null) {
        const caveat = summary.zones?.length > 1 ? 'dose massima applicata a tutta l’area; stima cautelativa, non consumo reale della mappa' : 'stima teorica basata sulla superficie e sulla dose inserita';
        note += ` Stima ${formatNumber(machine.litersEstimate, 0)} L (${machine.tanksEstimate} serbatoi da ${formatNumber(machine.tank, 0)} L): ${caveat}.`;
      }
      result.querySelector('strong').textContent = machine.title;
      result.querySelector('small').textContent = note;
    } else {
      result.querySelector('strong').textContent = 'Parametri da correggere';
      result.querySelector('small').textContent = 'Inserisci valori positivi e una velocità minima non superiore alla massima.';
    }
    $('exportReadyText').textContent = overallLevel === 'good' ? 'Controlli demo completati' : overallLevel === 'warn' ? 'Esportazione possibile con avvertenze' : 'Esportazione annotata con blocchi/criticità';
    $('exportBtn').disabled = busy;
  }

  const schedulePreflight = debounce(updatePreflight, 300);

  async function importFile(file) {
    if (!file) return;
    setBusy(true);
    $('exportBtn').disabled = true;
    showToast('Lettura del pacchetto ISOXML…');
    try {
      const formData = new FormData();
      formData.append('file', file, file.name);
      const data = await jsonRequest('/api/import', { method: 'POST', body: formData });
      weatherSource = 'manual';
      $('weatherSourceNote').textContent = 'Modalità manuale/demo · inserisci i dati conosciuti sul campo.';
      showLoadedState(data.summary);
      showToast('File importato e analizzato.');
      $('workspace').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      showGlobalError(error.message || 'Impossibile leggere il file.');
      showToast('Importazione non riuscita.');
    } finally {
      setBusy(false);
      $('fileInput').value = '';
      updatePreflight();
    }
  }

  async function loadDemo() {
    if (busy) return;
    setBusy(true);
    try {
      const data = await jsonRequest('/api/demo', { method: 'POST' });
      weatherSource = 'manual';
      $('weatherSourceNote').textContent = 'File sintetico dimostrativo · coordinate rappresentative, non riferite a un cliente.';
      showLoadedState(data.summary);
      showToast('File demo caricato. Il contorno e le fasce sono distinti dalla prescrizione reale.');
    } catch (error) {
      showGlobalError(error.message || 'Non riesco a caricare il file demo.');
    } finally {
      setBusy(false);
      updatePreflight();
    }
  }

  async function exportPackage() {
    if (!currentSummary || busy) return;
    setBusy(true);
    $('exportBtn').textContent = 'Preparazione…';
    const machine = getMachine();
    const weather = getWeatherStatus();
    const payload = {
      tank_l: Number($('tank').value),
      width_m: Number($('width').value),
      flow_l_min: Number($('flow').value),
      speed_min: Number($('speedMin').value),
      speed_max: Number($('speedMax').value),
      target_rate_l_ha: Number($('targetRate').value),
      controller: $('controllerCode').value,
      rate_control_code: $('rateControlCode').value,
      ecu_code: $('ecuCode').value,
      flowmeter_code: $('flowmeterCode').value,
      actuator_code: $('actuatorCode').value,
      nozzle_holder_code: $('nozzleHolderCode').value,
      valve_code: $('valveCode').value,
      pump_code: $('pumpCode').value,
      nozzle_code: $('nozzleCode').value,
      wind_kmh: Number($('wind').value),
      temperature_c: Number($('temperature').value),
      rain_hours: Number($('rainHours').value),
      weather_status: weather.status,
      hydraulic_status: machine.valid ? machine.level : 'DATI DA VERIFICARE'
    };
    try {
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Errore esportazione (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(currentSummary.filename || 'TASKDATA').replace(/\.(zip|isoxml|xml)$/i, '').replace(/[^a-zA-Z0-9_-]+/g, '_')}_ultimometro.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      showToast('Pacchetto annotato scaricato. La dose/mappa originale è rimasta invariata.');
    } catch (error) {
      showGlobalError(error.message || 'Esportazione non riuscita.');
      showToast('Esportazione non riuscita.');
    } finally {
      setBusy(false);
      $('exportBtn').innerHTML = '<span>Esporta ISOXML annotato</span><b>→</b>';
      updatePreflight();
    }
  }

  async function loadLiveWeather() {
    if (!currentSummary) return;
    const points = currentSummary.field_points || [];
    if (!points.length) {
      showToast('Nel file non ci sono coordinate di campo: usa i parametri meteo manuali.');
      return;
    }
    const lat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
    const lon = points.reduce((sum, p) => sum + p.lon, 0) / points.length;
    const button = $('loadWeatherBtn');
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = '↻ Carico…';
    try {
      const url = new URL('https://api.open-meteo.com/v1/forecast');
      url.searchParams.set('latitude', lat.toFixed(5));
      url.searchParams.set('longitude', lon.toFixed(5));
      url.searchParams.set('current', 'temperature_2m,wind_speed_10m');
      url.searchParams.set('hourly', 'precipitation_probability');
      url.searchParams.set('forecast_days', '2');
      url.searchParams.set('timezone', 'Europe/Rome');
      url.searchParams.set('wind_speed_unit', 'kmh');
      const response = await fetch(url.toString());
      if (!response.ok) throw new Error('Servizio meteo non disponibile');
      const data = await response.json();
      const temp = data.current?.temperature_2m;
      const wind = data.current?.wind_speed_10m;
      if (!Number.isFinite(temp) || !Number.isFinite(wind)) throw new Error('Risposta meteo incompleta');
      const times = data.hourly?.time || [];
      const probs = data.hourly?.precipitation_probability || [];
      const now = new Date();
      let rainInHours = 24;
      let rainFound = false;
      for (let i = 0; i < times.length; i++) {
        const forecastTime = new Date(times[i]);
        const hours = (forecastTime.getTime() - now.getTime()) / 3600000;
        if (hours >= -0.1 && Number(probs[i]) >= 60) {
          rainInHours = Math.max(0, Math.round(hours * 10) / 10);
          rainFound = true;
          break;
        }
      }
      $('wind').value = Math.round(wind);
      $('temperature').value = Math.round(temp * 10) / 10;
      $('rainHours').value = rainFound ? rainInHours : 24;
      weatherSource = 'live';
      $('weatherSourceNote').textContent = `Open-Meteo · stima sul centroide delle coordinate ISOXML (${lat.toFixed(3)}, ${lon.toFixed(3)}). Pioggia: prima ora con probabilità ≥60%; se non presente nelle prossime 48 h, impostata a 24 h.`;
      schedulePreflight();
      showToast('Meteo aggiornato. Conferma comunque le condizioni locali prima di trattare.');
    } catch (error) {
      showToast(`${error.message || 'Errore meteo'}. Inserisci i valori manualmente.`);
    } finally {
      button.disabled = false;
      button.textContent = oldText;
    }
  }

  function attachEvents() {
    const dropzone = $('dropzone');
    dropzone.addEventListener('click', () => $('fileInput').click());
    dropzone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('fileInput').click(); }
    });
    $('fileInput').addEventListener('change', (event) => importFile(event.target.files?.[0]));
    dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (event) => {
      event.preventDefault(); dropzone.classList.remove('dragover');
      const file = event.dataTransfer?.files?.[0];
      if (file) importFile(file);
    });
    $('loadDemoBtn').addEventListener('click', loadDemo);
    $('resetBtn').addEventListener('click', () => { $('fileInput').value = ''; $('fileInput').click(); });
    $('clearBtn').addEventListener('click', clearAnalysis);
    $('toggleAdvancedBtn').addEventListener('click', toggleAdvancedSettings);
    ['controllerCode','rateControlCode','ecuCode','flowmeterCode','valveCode','actuatorCode','pumpCode','nozzleCode','nozzleHolderCode','filterCode'].forEach(id => {
      $(id).addEventListener('change', () => { updatePreflight(); showToast('Configurazione hardware aggiornata dal catalogo.'); });
    });
    $('exportBtn').addEventListener('click', exportPackage);
    $('loadWeatherBtn').addEventListener('click', loadLiveWeather);
    ['wind', 'temperature', 'rainHours', 'tank', 'width', 'flow', 'speedMin', 'speedMax', 'targetRate'].forEach(id => {
      $(id).addEventListener('input', schedulePreflight);
      $(id).addEventListener('change', schedulePreflight);
    });
  }

  function renderHardwareCatalogResult(machine) {
    const box = $('hardwareCatalogResult');
    if (!box || !aragCatalog.products.length) return;
    const selectedIds = ['controllerCode','rateControlCode','ecuCode','flowmeterCode','valveCode','actuatorCode','pumpCode','nozzleCode','nozzleHolderCode','filterCode'];
    const items = selectedIds.map(id => selectedCatalogProduct(id)).filter(Boolean);
    const codeLine = items.map(item => `<span class="hardware-code-pill"><b>${escapeHTML(item.code)}</b> ${escapeHTML(item.name)}</span>`).join('');
    const controller = machine?.controller;
    const flowtron = machine?.rateControl;
    let compat = '';
    if (flowtron?.capabilities?.pwm) {
      compat = controller?.capabilities?.ibx_only
        ? '<div class="catalog-callout good"><b>Catena coerente a livello di famiglia.</b> Delta IBX + IBX100 Flowtron è coerente a livello di famiglia; resta da verificare la variante, software, cablaggio e attrezzatura reali.</div>'
        : '<div class="catalog-callout warn"><b>Compatibilità da verificare.</b> Il modulo Flowtron selezionato è IBX; scegli un terminale della famiglia IBX oppure conferma una diversa architettura con ARAG.</div>';
      if (machine?.ecu?.code === '4679900') compat += '<div class="catalog-callout warn"><b>Centralina aggiuntiva selezionata: verifica necessaria.</b> Il catalogo non attesta che IBX50 e IBX100 Flowtron debbano essere installati insieme; conferma l’architettura con ARAG.</div>';
    } else {
      compat = '<div class="catalog-callout warn"><b>Rateo variabile per ugello non dimostrato.</b> Il catalogo selezionato non mostra una catena Flowtron PWM completa. Il verde/giallo/rosso sulla mappa riguarda solo il profilo idraulico della demo.</div>';
    }
    const meterCallout = machine?.meterRangeWarning ? '<div class="catalog-callout warn"><b>Range del flussimetro da verificare.</b> La portata richiesta nel profilo esce almeno in parte dal range pubblicato del sensore selezionato. La portata utile deve essere confermata con calibrazione e scheda applicativa.</div>' : '';
    box.innerHTML = `<div class="catalog-selected-label">CODICI SELEZIONATI (${items.length})</div><div class="hardware-code-list">${codeLine}</div>${compat}${meterCallout}<p class="catalog-footnote">Il catalogo pubblico descrive i singoli componenti, non certifica la combinazione. Per esempio, il range di un flussimetro e la portata nominale di una pompa non equivalgono alla portata utile agli ugelli.</p>`;
  }

  function populateHardwareCatalog() {
    const products = aragCatalog.products || [];
    const defaults = {
      controller: '4675204', rate_control: '4679013', flowmeter: '46211P40000', valve: '853T04A55',
      actuator: '4063T95A0', pump: '97055201', nozzle: 'AFC11002', filter: '42433135',
      nozzle_holder: '', ecu: ''
    };
    document.querySelectorAll('[data-catalog-category]').forEach(select => {
      const category = select.dataset.catalogCategory;
      const keep = select.value || select.dataset.defaultCode || '';
      const blankLabel = category === 'rate_control' ? 'Nessun modulo PWM / rateo' : category === 'flowmeter' ? 'Nessun flussimetro selezionato' : category === 'ecu' ? 'Non dichiarata / integrata' : 'Non dichiarato / altro';
      const options = [`<option value="">${blankLabel}</option>`];
      products.filter(item => item.category === category).forEach(item => {
        const short = item.short ? ` · ${item.short}` : '';
        options.push(`<option value="${escapeHTML(item.code)}">${escapeHTML(item.code)} · ${escapeHTML(item.name)}${escapeHTML(short)}</option>`);
      });
      select.innerHTML = options.join('');
      const desired = keep && products.some(item => item.category === category && item.code === keep) ? keep : (defaults[category] || '');
      select.value = desired;
    });
  }

  async function initCatalog() {
    try {
      const response = await fetch('/static/arag_catalog.json', { cache: 'no-store' });
      if (!response.ok) throw new Error('Catalogo locale non disponibile');
      aragCatalog = await response.json();
      populateHardwareCatalog();
      const note = document.querySelector('.catalog-status span:nth-child(2)');
      if (note && aragCatalog.catalogue_version) note.textContent = `${aragCatalog.catalogue_version} · dati pubblici iniziali, compatibilità da confermare.`;
      updatePreflight();
    } catch (error) {
      showToast('Catalogo ARAG locale non caricato: controlla che il file static/arag_catalog.json sia presente.');
    }
  }

  async function clearAnalysis() {
    if (busy) return;
    try {
      await jsonRequest('/api/reset', { method: 'POST' });
      currentSummary = null;
      $('workspace').classList.add('hidden');
      $('loadedFileBar').classList.add('hidden');
      $('fileInput').value = '';
      clearGlobalError();
      $('exportReadyText').textContent = 'Carica un piano per iniziare';
      $('exportBtn').disabled = true;
      $('fieldName').textContent = 'Campo importato';
      $('fieldSub').textContent = 'In attesa di un file';
      $('fieldArea').textContent = '—';
      $('fieldCropChip').textContent = 'Coltura non indicata';
      $('zoneList').innerHTML = '<div class="empty-state">Analisi rimossa. Carica un altro ISOXML o seleziona “Prova con il file demo”.</div>';
      $('validationDetails').innerHTML = '';
      $('hardwareCatalogResult').innerHTML = '<strong>Configurazione hardware mantenuta</strong><p>Il profilo macchina resta disponibile per il prossimo file. L’analisi ISOXML precedente è stata cancellata dalla sessione.</p>';
      $('overallStatus').className = 'overall-status neutral';
      $('overallStatus').querySelector('strong').textContent = 'In attesa di un nuovo piano';
      $('overallStatus').querySelector('small').textContent = 'Carica un file ISOXML o usa il pacchetto demo.';
      $('checkList').innerHTML = '<div class="check-row"><span class="check-symbol">•</span><div><strong>Struttura ISOXML</strong><small>Carica un file per iniziare.</small></div><span class="check-state">—</span></div>';
      showToast('Analisi cancellata. Configurazione hardware mantenuta.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      showGlobalError(error.message || 'Non riesco a cancellare l’analisi.');
    }
  }

  function toggleAdvancedSettings() {
    const panel = $('advancedSettings');
    const opening = panel.classList.contains('hidden');
    panel.classList.toggle('hidden', !opening);
    $('toggleAdvancedBtn').textContent = opening ? 'Nascondi parametri' : 'Parametri profilo';
  }

  attachEvents();
  initCatalog();
})();
