(() => {
  const $ = (id) => document.getElementById(id);
  let currentSummary = null;
  let busy = false;
  let weatherSource = 'manual';
  let toastTimer = null;

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
    renderFieldMap(summary);
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

  function renderFieldMap(summary) {
    const svg = $('fieldMap');
    const points = summary.field_points || [];
    const ns = 'http://www.w3.org/2000/svg';
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const make = (tag, attrs = {}, text = '') => {
      const el = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
      if (text) el.textContent = text;
      return el;
    };
    svg.appendChild(make('defs'));
    const defs = svg.firstChild;
    const pattern = make('pattern', { id: 'gridPatternDynamic', width: '22', height: '22', patternUnits: 'userSpaceOnUse' });
    pattern.appendChild(make('path', { d: 'M 22 0 L 0 0 0 22', fill: 'none', stroke: '#d8e4db', 'stroke-width': '.7' }));
    defs.appendChild(pattern);
    svg.appendChild(make('rect', { width: '540', height: '245', fill: '#f3f7f2' }));
    svg.appendChild(make('rect', { width: '540', height: '245', fill: 'url(#gridPatternDynamic)' }));

    if (points.length >= 3) {
      const lats = points.map(p => p.lat), lons = points.map(p => p.lon);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats), minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const latSpan = maxLat - minLat || 0.0001, lonSpan = maxLon - minLon || 0.0001;
      const projected = points.map(p => ({ x: 58 + ((p.lon - minLon) / lonSpan) * 420, y: 30 + ((maxLat - p.lat) / latSpan) * 180 }));
      const path = projected.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ') + ' Z';
      svg.appendChild(make('path', { d: path, fill: '#c8dfc2', stroke: '#477750', 'stroke-width': '2.3', 'stroke-linejoin': 'round' }));
      // A subtle diagonal treatment is decorative only; never claim it is the extracted prescription grid.
      for (let i = 0; i < 7; i++) {
        const x = 85 + i * 56;
        svg.appendChild(make('path', { d: `M ${x} 34 L ${x + 75} 210`, stroke: '#86b57e', 'stroke-width': '1', opacity: '.45', 'stroke-dasharray': '4 4' }));
      }
      const centroidX = projected.reduce((sum, p) => sum + p.x, 0) / projected.length;
      const centroidY = projected.reduce((sum, p) => sum + p.y, 0) / projected.length;
      svg.appendChild(make('rect', { x: Math.max(75, centroidX - 69), y: Math.max(55, centroidY - 15), width: '138', height: '30', rx: '6', fill: '#ffffff', stroke: '#d7e4d6', opacity: '.96' }));
      svg.appendChild(make('text', { x: Math.max(75, centroidX - 69) + 69, y: Math.max(55, centroidY - 15) + 19, 'text-anchor': 'middle', fill: '#426747', 'font-size': '10', 'font-family': 'DM Mono, monospace' }, 'CONFINE ISOXML'));
      svg.appendChild(make('g')).setAttribute('transform', 'translate(20 18)');
    } else {
      svg.appendChild(make('path', { d: 'M83 45 L419 31 L455 174 L331 211 L102 188 Z', fill: '#c9dfc4', stroke: '#426d48', 'stroke-width': '2' }));
      svg.appendChild(make('path', { d: 'M83 45 L251 38 L262 199 L102 188 Z', fill: '#a8cfa2', opacity: '.92' }));
      svg.appendChild(make('path', { d: 'M251 38 L419 31 L455 174 L262 199 Z', fill: '#dbe8b7', opacity: '.94' }));
      svg.appendChild(make('text', { x: '161', y: '112', class: 'map-zone-label' }, 'ZONA A'));
      svg.appendChild(make('text', { x: '331', y: '112', class: 'map-zone-label' }, 'ZONA B'));
    }
    const tag = make('g', { transform: 'translate(20 18)' });
    tag.appendChild(make('rect', { width: '116', height: '25', rx: '6', fill: '#fff', stroke: '#dce6de' }));
    tag.appendChild(make('circle', { cx: '12', cy: '12.5', r: '3.3', fill: '#42784c' }));
    tag.appendChild(make('text', { x: '22', y: '16', fill: '#58735d', 'font-size': '9', 'font-family': 'DM Mono, monospace' }, points.length >= 3 ? 'BOUNDARY DATA' : 'FIELD PREVIEW'));
    svg.appendChild(tag);
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
    return { valid: true, level, title, detail, tank, width, flow, speedMin, speedMax, rate, maxAchievableSpeed, requiredFlowAtMaxSpeed, requiredFlowAtMinSpeed, litersEstimate, tanksEstimate, fieldArea };
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
    $('weatherStatusText').textContent = weather.title;
    $('weatherStatusDetail').textContent = weather.detail;
    $('weatherTag').textContent = weather.status;
    $('weatherTag').className = `weather-tag ${weather.level === 'good' ? 'green-tag' : weather.level === 'warn' ? 'yellow-tag' : 'red-tag'}`;
    $('weatherOrb').className = `weather-orb ${weather.level === 'good' ? 'green-orb' : weather.level === 'warn' ? 'yellow-orb' : 'red-orb'}`;

    let rows = [];
    rows.push(setCheckRow(summary.counts.tasks > 0 ? 'good' : 'bad', 'Struttura e task', `${summary.counts.tasks} task · ISOXML ${summary.version} · origine ${summary.manufacturer || 'non indicata'}`, summary.counts.tasks ? 'LETTO' : 'ERRORE'));
    rows.push(setCheckRow(summary.fields.length > 0 ? 'good' : 'warn', 'Campo e superficie', summary.fields.length ? `${summary.fields.length} campo/i; geometria ${summary.field_points?.length >= 3 ? 'presente' : 'non individuata'}.` : 'Il file non contiene PFD riconoscibili.', summary.fields.length ? 'OK' : 'ATTENZIONE'));
    rows.push(setCheckRow(summary.has_recipe ? 'good' : 'warn', 'Prescrizione', summary.has_grid ? `${summary.counts.grids} griglia/e trovate; binari non interpretati nella mappa.` : `${summary.counts.zones} zone TZN; unità/valori dipendono dai riferimenti VPN.`, summary.has_recipe ? 'RILEVATA' : 'VERIFICARE'));
    rows.push(setCheckRow(machine.valid ? machine.level : 'bad', 'Compatibilità idraulica', machine.valid ? machine.detail : 'Controlla che i parametri della macchina siano numeri positivi e che velocità minima ≤ massima.', machine.valid ? ({ good: 'OK', warn: 'LIMITE', bad: 'NON FATTIBILE' }[machine.level]) : 'DATI'));
    rows.push(setCheckRow(weather.level, 'Finestra meteo', weather.detail, weather.status));
    $('checkList').innerHTML = rows.join('');

    let overallLevel = 'good';
    let overallTitle = 'Pre-flight senza blocchi dimostrativi';
    let overallDetail = 'Il file è stato letto e i parametri inseriti risultano compatibili con le soglie della demo.';
    if (!machine.valid || machine.level === 'bad' || weather.level === 'bad' || summary.counts.tasks === 0) {
      overallLevel = 'bad'; overallTitle = 'Revisione necessaria prima del trattamento'; overallDetail = 'C’è almeno una condizione critica. Correggi i parametri o rivaluta la finestra operativa con il tecnico.';
    } else if (machine.level === 'warn' || weather.level === 'warn' || !summary.has_recipe || !summary.fields.length) {
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
      showToast('File demo caricato. Puoi provare i controlli.');
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
      controller: $('controller').value,
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
    $('resetBtn').addEventListener('click', () => $('fileInput').click());
    $('exportBtn').addEventListener('click', exportPackage);
    $('loadWeatherBtn').addEventListener('click', loadLiveWeather);
    ['wind', 'temperature', 'rainHours', 'tank', 'width', 'flow', 'speedMin', 'speedMax', 'targetRate', 'controller'].forEach(id => {
      $(id).addEventListener('input', schedulePreflight);
      $(id).addEventListener('change', schedulePreflight);
    });
  }

  attachEvents();
  // Open with a synthetic plan so the team sees a working dashboard immediately.
  loadDemo();
})();
