export const HORIZONS = ['1', '3', '5', '7', '14', '30'];
export const PAGE_SIZE = 15;

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function sortRows(rows, horizon, metric) {
  const key = String(horizon);
  return [...rows].sort((left, right) => {
    const leftValue = finiteNumber(left?.horizons?.[key]?.[metric]);
    const rightValue = finiteNumber(right?.horizons?.[key]?.[metric]);
    if (leftValue === null && rightValue === null) return 0;
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    return rightValue - leftValue;
  });
}

export function filterRows(rows, options = {}) {
  const horizon = String(options.horizon ?? '7');
  const kind = options.kind ?? 'all';
  const eligibility = options.eligibility ?? 'all';
  const query = String(options.query || '').trim().toLowerCase();
  return rows.filter((row) => {
    if (query && !`${row.symbol} ${row.name || ''}`.toLowerCase().includes(query)) return false;
    if (kind !== 'all' && row?.kind !== kind) return false;
    const selected = row?.horizons?.[horizon];
    if (eligibility === 'eligible' && selected?.eligible !== true) return false;
    if (eligibility === 'excluded' && selected?.eligible === true) return false;
    if (options.positiveAll && !HORIZONS.every((key) => finiteNumber(row?.horizons?.[key]?.expected_return) > 0)) return false;
    return true;
  });
}

export function paginateRows(rows, requested = 1) {
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const page = Math.max(1, Math.min(pages, Math.trunc(requested) || 1));
  const start = (page - 1) * PAGE_SIZE;
  return { rows: rows.slice(start, start + PAGE_SIZE), page, pages, start };
}

export function updateRanking(state, changes) {
  Object.assign(state, changes, { page: 1 });
}

export function dataURL(staticMode, route, params = {}) {
  if (!staticMode) return `/api/${route}${Object.keys(params).length ? `?${new URLSearchParams(params)}` : ''}`;
  const id = encodeURIComponent(params.id || '');
  if (route === 'state') return './data/state.json';
  if (route === 'snapshot') return `./data/snapshots/${id}.json`;
  if (route === 'export') return `./data/csv/${id}-${params.horizon}-${params.sort}.csv`;
  throw new Error('雲端網頁只提供已發布的研究資料');
}

export function dataAgeWarning(asOf, nextSession, current = new Date()) {
  const taipei = new Date(current.getTime() + 8 * 3600000);
  const today = taipei.toISOString().slice(0, 10);
  if (!asOf || asOf >= today) return '';
  if (nextSession) {
    return today > nextSession || (today === nextSession && taipei.getUTCHours() >= 20)
      ? '尚未發布下一交易日資料，可能更新延遲或失敗；請確認資料日期。' : '';
  }
  return taipei.getUTCDay() > 0 && taipei.getUTCDay() < 6 && taipei.getUTCHours() >= 20
    ? '平日盤後尚無新資料；未取得完整開休市日，請另確認是否休市或更新失敗。' : '';
}

export function createDetailLoader(fetcher) {
  let request = 0;
  return {
    invalidate() { request++; },
    async load(row) {
      const current = ++request;
      try {
        const result = row.detail_url ? await fetcher(row.detail_url) : row;
        return current === request ? result : null;
      } catch (error) { if (current === request) throw error; return null; }
    },
  };
}

const STATIC_MODE = typeof document !== 'undefined' && document.querySelector('meta[name="deployment-mode"]')?.content === 'static';
const detailLoader = createDetailLoader((url) => fetchJSON(url));

export function signalDatesWithLabels(signals) {
  return new Set((Array.isArray(signals) ? signals : [])
    .filter(({ labels }) => Array.isArray(labels) && labels.length > 0)
    .map(({ date }) => date));
}

export function verificationLabel(snapshot) {
  const status = snapshot?.data_quality?.verification_status;
  if (status === 'single_source') return '單一官方來源／未完成跨來源複查';
  if (status === 'missing_evidence') return '來源證據不足／待複查';
  return '未記錄複查狀態';
}

const METRICS = {
  expected_return: '預期淨報酬',
  p_positive: '到期獲利比例',
  p_recovery: '收盤曾回正比例',
  score: '綜合排序分',
};

const appState = {
  snapshot: null,
  settings: null,
  history: [],
  universe: [],
  job: null,
  horizon: '7',
  sort: 'expected_return',
  kind: 'all',
  eligibility: 'eligible',
  positiveAll: false,
  pollTimer: null,
  query: '',
  page: 1,
  checkedAt: null,
  nextSession: null,
  schedule: '',
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function formatDate(value, includeTime = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat('zh-TW', includeTime
    ? { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
    : { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

function formatPercent(value, probability = false, digits = 1) {
  const number = finiteNumber(value);
  if (number === null) return '—';
  const shown = probability ? number * 100 : number;
  return `${shown > 0 && !probability ? '+' : ''}${shown.toFixed(digits)}%`;
}

function formatDecimal(value, digits = 3) {
  const number = finiteNumber(value);
  return number === null ? '—' : number.toFixed(digits);
}

function formatInteger(value) {
  const number = finiteNumber(value);
  return number === null ? '—' : new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 0 }).format(number);
}

function toneClass(value) {
  const number = finiteNumber(value);
  if (number === null || number === 0) return '';
  return number > 0 ? 'positive' : 'negative';
}

function kindLabel(kind) {
  return kind === 'etf' ? 'ETF' : kind === 'stock' ? '股票' : String(kind || '標的').toUpperCase();
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    cache: 'no-store',
    headers: { Accept: 'application/json', ...(options.headers || {}) },
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch { /* handled below */ }
  if (!response.ok) {
    const message = payload?.error || payload?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  if (payload === null) throw new Error('伺服器未回傳可讀取的 JSON');
  return payload;
}

function showError(message) {
  $('#errorMessage').textContent = message || '無法連線，請確認本機服務是否已啟動。';
  $('#errorBanner').hidden = false;
  $('.live-dot').classList.add('error');
}

function clearError() {
  $('#errorBanner').hidden = true;
  $('.live-dot').classList.remove('error');
}

let toastTimer;
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2800);
}

function normalizeHistory(history) {
  if (!Array.isArray(history)) return [];
  return history.map((entry) => typeof entry === 'string' ? { id: entry } : entry).filter((entry) => entry?.id);
}

function renderHistory() {
  const select = $('#snapshotSelect');
  const history = normalizeHistory(appState.history);
  const latest = appState.snapshot;
  if (latest?.id && !history.some(({ id }) => id === latest.id)) {
    history.unshift({ id: latest.id, as_of: latest.as_of, created_at: latest.created_at });
  }
  if (!history.length) {
    select.innerHTML = '<option value="">尚無快照</option>';
    select.disabled = true;
    return;
  }
  const dates = history.map(({ as_of }) => as_of);
  select.innerHTML = history.map((entry, index) => {
    const repeated = entry.as_of && dates.indexOf(entry.as_of) !== dates.lastIndexOf(entry.as_of);
    const created = entry.created_at ? new Date(entry.created_at) : null;
    const time = repeated && created && !Number.isNaN(created.getTime())
      ? ` · 建於 ${new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(created)}`
      : '';
    const label = entry.as_of ? `${formatDate(entry.as_of)}${time}${index === 0 ? ' · 最新' : ''}` : entry.id;
    return `<option value="${escapeHtml(entry.id)}">${escapeHtml(label)}</option>`;
  }).join('');
  select.disabled = false;
  if (latest?.id) select.value = latest.id;
}

function renderSnapshotHeader() {
  const snapshot = appState.snapshot;
  if (!snapshot) {
    $('#snapshotStatus').textContent = '尚無完成的研究快照';
    $('#asOf').textContent = '—';
    $('#modelVersion').textContent = '—';
    const researchSize = Array.isArray(appState.settings?.symbols) ? appState.settings.symbols.length : 0;
    $('#universeCount').textContent = researchSize ? `${researchSize} 檔研究清單` : '等待更新';
    return;
  }
  const latest = appState.history[0];
  $('#snapshotStatus').textContent = `${latest?.id && latest.id !== snapshot.id ? '歷史快照' : '快照'}建立於 ${formatDate(snapshot.created_at, true)}`;
  $('#asOf').textContent = formatDate(snapshot.as_of);
  $('#modelVersion').textContent = snapshot.model_version || '未標示';
  $('#universeCount').textContent = snapshot.coverage ? `${snapshot.coverage.universe_count} 檔標的` : `${snapshot.rows?.length || 0} 檔清單`;
  const coverage = snapshot.coverage;
  $('#cloudStatus').hidden = !STATIC_MODE;
  if (STATIC_MODE) {
    $('#cloudTiming').textContent = `最近檢查：${formatDate(appState.checkedAt, true)}`;
    $('#cloudSchedule').textContent = appState.schedule;
    $('#coverageText').textContent = coverage ? `母集合 ${coverage.stocks} 檔股票、${coverage.etfs} 檔股票 ETF；可建立當日特徵 ${coverage.analyzed_count} 檔，資料不足或不適用 ${coverage.unavailable_count} 檔（可在「僅看排除」查看）。` : '';
    const ageWarning = dataAgeWarning(latest?.as_of || snapshot.as_of, appState.nextSession);
    $('#ageWarningDetail').textContent = ageWarning;
    $('#ageWarning').hidden = !ageWarning;
  }
}

function renderNotes() {
  const snapshot = appState.snapshot;
  const section = $('#snapshotNotes');
  if (!snapshot) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  $('#methodologyText').textContent = snapshot.methodology || '此快照未附方法摘要。';
  $('#qualityStatus').textContent = verificationLabel(snapshot);
  const manifest = snapshot.data_quality?.source_manifest || [];
  const fetched = manifest.map((item) => item.fetched_at).filter(Boolean).sort();
  $('#qualityTiming').textContent = fetched.length
    ? `資料基準日 ${snapshot.as_of}；最後抓取 ${formatDate(fetched.at(-1), true)}。抓取時間不等於公告時間。`
    : '此快照未附完整來源時間紀錄。';
  $('#sourceManifest').innerHTML = manifest.length
    ? manifest.map((item) => `<li><b>${escapeHtml(item.dataset)}</b> · ${escapeHtml(item.source_family)} · ${escapeHtml(item.symbol || '市場')}<br><small>${escapeHtml(item.url)}<br>SHA256 ${escapeHtml(item.sha256 || '未記錄')}</small></li>`).join('')
    : '<li>舊快照未補造來源或複查紀錄。</li>';
  const warnings = Array.isArray(snapshot.warnings) ? snapshot.warnings.filter(Boolean) : [];
  $('#warningsList').innerHTML = warnings.length
    ? warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')
    : '<li>此快照未附額外警示；仍請依頁面方法限制解讀。</li>';
}

function renderRows() {
  detailLoader.invalidate();
  const rows = Array.isArray(appState.snapshot?.rows) ? appState.snapshot.rows : [];
  const filtered = filterRows(rows, {
    horizon: appState.horizon,
    kind: appState.kind,
    eligibility: appState.eligibility,
    positiveAll: appState.positiveAll,
    query: appState.query,
  });
  const ranked = sortRows(filtered, appState.horizon, appState.sort);
  const paged = paginateRows(ranked, appState.page);
  appState.page = paged.page;
  for (const suffix of ['', 'Bottom']) {
    $(`#pageText${suffix}`).textContent = `第 ${paged.page} / ${paged.pages} 頁 · 每頁最多${PAGE_SIZE}檔`;
    $(`#previousPage${suffix}`).disabled = paged.page <= 1;
    $(`#nextPage${suffix}`).disabled = paged.page >= paged.pages;
    $(`#pagination${suffix}`).hidden = ranked.length <= PAGE_SIZE;
  }
  const body = $('#resultsBody');
  const shell = $('#tableShell');
  const empty = $('#emptyState');
  const summary = $('#resultSummary');
  const exportParams = new URLSearchParams({ horizon: appState.horizon, sort: appState.sort });
  if (appState.snapshot?.id) exportParams.set('id', appState.snapshot.id);
  $('#exportLink').href = dataURL(STATIC_MODE, 'export', Object.fromEntries(exportParams));
  $('#exportLink').hidden = !appState.snapshot;

  if (!appState.snapshot) {
    shell.hidden = true;
    empty.hidden = false;
    $('#emptyTitle').textContent = '從第一份盤後資料開始';
    $('#emptyMessage').textContent = STATIC_MODE ? '目前無法顯示已發布資料。請重試讀取，或從上方「手動更新／查看進度」確認雲端狀態。' : '更新會從臺灣證券交易所取得研究清單的實際行情；過程與任何失敗都會顯示在這裡。';
    $('#emptyUpdateButton').hidden = Boolean(appState.job?.running);
    summary.textContent = '尚無可排行的研究資料';
    return;
  }

  if (!ranked.length) {
    shell.hidden = true;
    empty.hidden = false;
    $('#emptyTitle').textContent = '目前條件沒有標的';
    $('#emptyMessage').textContent = rows.length
      ? '零入選是有效結果。可切換「全部標的」或其他期限查看排除原因。'
      : '這份快照沒有可顯示的列，請查看資料警示或重新更新。';
    $('#emptyUpdateButton').hidden = true;
    summary.innerHTML = `共 <strong>${rows.length}</strong> 檔，篩選後為 <strong>0</strong> 檔`;
    return;
  }

  empty.hidden = true;
  shell.hidden = false;
  summary.innerHTML = `${appState.horizon} 曆日 · 依${METRICS[appState.sort]}排列 · 顯示 <strong>${ranked.length}</strong>／${rows.length} 檔`;
  body.innerHTML = paged.rows.map((row, index) => {
    const horizon = row?.horizons?.[appState.horizon];
    const eligible = horizon?.eligible === true;
    const expected = horizon?.expected_return;
    return `<tr>
      <td class="rank" data-label="順位">${String(index + paged.start + 1).padStart(2, '0')}</td>
      <td class="security-cell" data-label="標的"><div class="security"><span class="ticker-mark">${escapeHtml(kindLabel(row.kind))}</span><div><b>${escapeHtml(row.symbol)}</b><small>${escapeHtml(row.name || '未提供名稱')}</small></div></div></td>
      <td data-label="預期淨報酬"><span class="numeric ${toneClass(expected)}">${formatPercent(expected)}</span><small class="sub-value">中位 ${formatPercent(horizon?.median_return)}</small></td>
      <td data-label="到期獲利"><span class="numeric">${formatPercent(horizon?.p_positive, true)}</span></td>
      <td data-label="曾回正"><span class="numeric">${formatPercent(horizon?.p_recovery, true)}</span><small class="sub-value">中位 ${finiteNumber(horizon?.median_recovery_days) === null ? '—' : `${formatDecimal(horizon.median_recovery_days, 1)} 日`}</small></td>
      <td data-label="下檔 q10"><span class="numeric ${toneClass(horizon?.q10)}">${formatPercent(horizon?.q10)}</span><small class="sub-value">期間 ${formatPercent(horizon?.worst_close_q10)}</small></td>
      <td data-label="樣本"><span class="numeric">${formatInteger(horizon?.n)}</span></td>
      <td class="status-cell" data-label="資格"><span class="status-pill ${eligible ? '' : 'excluded'}">${eligible ? '符合門檻' : '排除'}</span></td>
      <td class="row-action"><button class="row-button" type="button" data-detail-symbol="${escapeHtml(row.symbol)}" aria-label="查看 ${escapeHtml(row.symbol)} 詳情">›</button></td>
    </tr>`;
  }).join('');
}

function renderJob() {
  const job = appState.job;
  const panel = $('#jobPanel');
  if (STATIC_MODE) {
    panel.hidden = true;
    setUpdateButtons(false);
    return;
  }
  if (!job || (!job.running && !job.error && !job.finished_at)) {
    panel.hidden = true;
    setUpdateButtons(false);
    return;
  }
  panel.hidden = false;
  const total = finiteNumber(job.total) ?? 0;
  const progress = finiteNumber(job.progress) ?? 0;
  const ratio = total > 0 ? Math.max(0, Math.min(100, progress / total * 100)) : (job.running ? 8 : 100);
  $('#jobPhase').textContent = job.error ? '更新未完成' : job.running ? (job.phase || '更新中') : '更新完成';
  $('#jobMessage').textContent = job.error || job.message || (job.running ? '正在處理資料…' : `完成於 ${formatDate(job.finished_at, true)}`);
  $('#jobFraction').textContent = total ? `${progress} / ${total}` : job.running ? '處理中' : '完成';
  $('#jobProgress').style.width = `${ratio}%`;
  $('.spinner').hidden = !job.running;
  setUpdateButtons(Boolean(job.running));
}

function setUpdateButtons(running) {
  for (const button of [$('#updateButton'), $('#emptyUpdateButton')]) {
    if (!button) continue;
    button.disabled = running;
    if (button.id === 'updateButton') button.lastChild.textContent = STATIC_MODE ? '讀取最新結果' : running ? ' 更新中' : ' 更新資料';
  }
}

function renderAll() {
  renderSnapshotHeader();
  renderHistory();
  renderJob();
  renderRows();
  renderNotes();
}

function schedulePoll() {
  clearTimeout(appState.pollTimer);
  if (!appState.job?.running) return;
  appState.pollTimer = setTimeout(async () => {
    await loadState({ quiet: true });
  }, 1400);
}

async function loadState({ quiet = false } = {}) {
  if (!quiet) $('#snapshotStatus').textContent = STATIC_MODE ? '正在讀取雲端研究資料' : '正在連線本機資料服務';
  try {
    const payload = await fetchJSON(dataURL(STATIC_MODE, 'state'));
    appState.checkedAt = payload.checked_at;
    appState.nextSession = payload.next_session;
    appState.schedule = payload.schedule || '';
    appState.settings = payload.settings ?? appState.settings;
    appState.snapshot = payload.latest ?? null;
    appState.history = payload.history ?? [];
    appState.job = payload.job ?? null;
    appState.universe = payload.universe ?? [];
    clearError();
    renderAll();
    schedulePoll();
    return true;
  } catch (error) {
    showError(error.message);
    if (!appState.snapshot) renderAll();
    return false;
  }
}

async function startUpdate() {
  if (STATIC_MODE) {
    setUpdateButtons(true);
    try {
      if (await loadState()) showToast('已讀取最新發布結果；資料日期請看「共同資料日」');
    } finally { setUpdateButtons(false); }
    return;
  }
  clearError();
  setUpdateButtons(true);
  try {
    const payload = await fetchJSON('/api/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    appState.job = payload.job;
    renderJob();
    schedulePoll();
  } catch (error) {
    showError(error.message);
    setUpdateButtons(false);
  }
}

async function selectSnapshot(id) {
  if (!id || id === appState.snapshot?.id) return;
  const select = $('#snapshotSelect');
  select.disabled = true;
  try {
    detailLoader.invalidate();
    const payload = await fetchJSON(dataURL(STATIC_MODE, 'snapshot', { id }));
    appState.snapshot = payload.snapshot ?? payload;
    clearError();
    renderAll();
  } catch (error) {
    showError(error.message);
  } finally {
    select.disabled = false;
  }
}

function settingsValues() {
  const form = $('#settingsForm');
  const data = new FormData(form);
  const symbols = String(data.get('symbols') || '').split(/[\s,，]+/).map((symbol) => symbol.trim()).filter(Boolean);
  const integers = ['months', 'min_samples', 'neighbors', 'min_turnover'];
  const decimals = ['min_probability', 'max_downside', 'fee_rate', 'slippage_rate'];
  const settings = { symbols };
  for (const key of integers) settings[key] = Number.parseInt(data.get(key), 10);
  for (const key of decimals) settings[key] = Number.parseFloat(data.get(key));
  if (!symbols.length) throw new Error('研究清單至少需要一個代號。');
  for (const key of [...integers, ...decimals]) {
    if (!Number.isFinite(settings[key])) throw new Error(`${key} 必須是有效數字。`);
  }
  return settings;
}

function openSettings() {
  const form = $('#settingsForm');
  const settings = appState.settings || {};
  form.elements.symbols.value = Array.isArray(settings.symbols) ? settings.symbols.join(', ') : '';
  for (const key of ['months', 'min_samples', 'neighbors', 'min_turnover', 'min_probability', 'max_downside', 'fee_rate', 'slippage_rate']) {
    form.elements[key].value = settings[key] ?? '';
  }
  $('#settingsError').hidden = true;
  $('#settingsDialog').showModal();
}

async function saveSettings(event) {
  event.preventDefault();
  const errorBox = $('#settingsError');
  const saveButton = $('#saveSettingsButton');
  try {
    const settings = settingsValues();
    saveButton.disabled = true;
    errorBox.hidden = true;
    const payload = await fetchJSON('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    appState.settings = payload.settings;
    $('#settingsDialog').close();
    showToast('設定已儲存，將套用於下一次更新');
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
}

function chartSvg(bars = [], signals = []) {
  const clean = bars.slice(-60).map((bar) => ({
    ...bar,
    open: finiteNumber(bar.open), high: finiteNumber(bar.high), low: finiteNumber(bar.low),
    close: finiteNumber(bar.close), volume: finiteNumber(bar.volume),
  })).filter((bar) => [bar.open, bar.high, bar.low, bar.close].every((value) => value !== null));
  if (!clean.length) return '<div class="notice"><p>此列沒有可繪製的有效 OHLC 資料。</p></div>';
  const width = 700, height = 310, left = 44, right = 12, priceTop = 16, priceBottom = 216, volumeTop = 239, volumeBottom = 286;
  const lows = clean.map(({ low }) => low), highs = clean.map(({ high }) => high);
  let minPrice = Math.min(...lows), maxPrice = Math.max(...highs);
  if (minPrice === maxPrice) { minPrice -= 1; maxPrice += 1; }
  const maxVolume = Math.max(...clean.map(({ volume }) => volume || 0), 1);
  const plotWidth = width - left - right;
  const step = plotWidth / clean.length;
  const candleWidth = Math.max(2, Math.min(8, step * .56));
  const yPrice = (value) => priceBottom - (value - minPrice) / (maxPrice - minPrice) * (priceBottom - priceTop);
  const signalDates = signalDatesWithLabels(signals);
  const grid = [0, .25, .5, .75, 1].map((fraction) => {
    const y = priceTop + (priceBottom - priceTop) * fraction;
    const price = maxPrice - (maxPrice - minPrice) * fraction;
    return `<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" stroke="#ccd1ca" stroke-width="1"/><text x="${left-6}" y="${y+3}" text-anchor="end" fill="#718083" font-size="9" font-family="monospace">${price.toFixed(1)}</text>`;
  }).join('');
  const candles = clean.map((bar, index) => {
    const x = left + step * index + step / 2;
    const rising = bar.close >= bar.open;
    const color = rising ? '#b94d44' : '#0d746f';
    const bodyTop = Math.min(yPrice(bar.open), yPrice(bar.close));
    const bodyHeight = Math.max(1.5, Math.abs(yPrice(bar.close) - yPrice(bar.open)));
    const volumeHeight = (bar.volume || 0) / maxVolume * (volumeBottom - volumeTop);
    const marker = signalDates.has(bar.date) ? `<circle cx="${x}" cy="${Math.max(8, yPrice(bar.high)-8)}" r="2.8" fill="#c79b4a"/>` : '';
    return `<line x1="${x}" y1="${yPrice(bar.high)}" x2="${x}" y2="${yPrice(bar.low)}" stroke="${color}" stroke-width="1"/><rect x="${x-candleWidth/2}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}" rx="1" fill="${color}"/><rect x="${x-candleWidth/2}" y="${volumeBottom-volumeHeight}" width="${candleWidth}" height="${volumeHeight}" fill="${color}" opacity=".45"/>${marker}`;
  }).join('');
  const firstDate = escapeHtml(clean[0].date || '');
  const lastDate = escapeHtml(clean.at(-1).date || '');
  return `<div class="chart-wrap"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="最近 ${clean.length} 筆 K 線與成交量">
    ${grid}<line x1="${left}" y1="${priceBottom}" x2="${width-right}" y2="${priceBottom}" stroke="#9ca9a6"/><line x1="${left}" y1="${volumeBottom}" x2="${width-right}" y2="${volumeBottom}" stroke="#9ca9a6"/>
    ${candles}<text x="${left}" y="${height-6}" fill="#718083" font-size="9" font-family="monospace">${firstDate}</text><text x="${width-right}" y="${height-6}" text-anchor="end" fill="#718083" font-size="9" font-family="monospace">${lastDate}</text>
    <circle cx="${width-100}" cy="10" r="3" fill="#c79b4a"/><text x="${width-92}" y="13" fill="#718083" font-size="9">訊號日</text>
  </svg></div>`;
}

function calibrationText(calibration) {
  if (!Array.isArray(calibration) || !calibration.length) return '未提供校準分箱；歷史比例不應視為已校準機率。';
  return calibration.map((bucket) => `n=${formatInteger(bucket.n)}：估計 ${formatPercent(bucket.predicted, true)}／實際 ${formatPercent(bucket.actual, true)}`).join('；');
}

async function openDetail(symbol) {
  let row = appState.snapshot?.rows?.find((item) => String(item.symbol) === String(symbol));
  if (!row) return;
  try {
    row = await detailLoader.load(row);
    if (!row) return;
    if (String(row.symbol) !== String(symbol)) throw new Error('詳情代號與選取標的不符');
  } catch (error) { showError(error.message); return; }
  const horizon = row.horizons?.[appState.horizon];
  const validation = row.validation?.[appState.horizon];
  const reasons = [...new Set([...(Array.isArray(row.reasons) ? row.reasons : []), ...(Array.isArray(horizon?.reasons) ? horizon.reasons : [])])];
  const signals = Array.isArray(row.signals) ? row.signals : [];
  const samples = Array.isArray(horizon?.samples) ? horizon.samples : [];
  $('#detailKind').textContent = `${kindLabel(row.kind)} · ${appState.horizon} 曆日研究`;
  $('#detailTitle').textContent = `${row.symbol} ${row.name || ''}`.trim();
  $('#detailSubtitle').textContent = `研究日 ${formatDate(row.as_of || appState.snapshot?.as_of)} · 行情日 ${formatDate(row.data_as_of || row.bars?.at(-1)?.date)} · ${row.currency || 'TWD'} · ${horizon?.target_date ? `目標交易日 ${formatDate(horizon.target_date)}` : '目標日尚未確定'}`;
  const samplesHtml = samples.length ? `<div class="table-shell"><table class="sample-table"><thead><tr><th>訊號日</th><th>模擬進場</th><th>模擬出場</th><th>成本後報酬</th><th>曾回正</th></tr></thead><tbody>${samples.map((sample) => `<tr><td>${escapeHtml(sample.signal_date || '—')}</td><td>${escapeHtml(sample.entry_date || '—')}</td><td>${escapeHtml(sample.exit_date || '—')}</td><td class="numeric ${toneClass(sample.return_pct)}">${formatPercent(sample.return_pct)}</td><td>${sample.recovered === true ? '是' : sample.recovered === false ? '否' : '—'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="notice"><p>此期限沒有可顯示的歷史樣本日期。</p></div>';
  const signalsHtml = signals.length
    ? signals.slice().reverse().slice(0, 12).map((signal) => `<span class="reason-chip neutral">${escapeHtml(signal.date)} · ${escapeHtml((signal.labels || []).join('、') || '訊號')}</span>`).join('')
    : '<span class="reason-chip neutral">沒有訊號標記</span>';
  const validationHtml = validation ? `<div class="validation-card">
    <div class="validation-head"><strong>時間前推抽樣檢查</strong><span class="validation-status">${escapeHtml(validation.status || '未標示狀態')}</span></div>
    <div class="validation-grid"><div><small>驗證筆數</small><b>${formatInteger(validation.n)}</b></div><div><small>MAE</small><b>${formatDecimal(validation.mae)}</b></div><div><small>Brier</small><b>${formatDecimal(validation.brier)}</b></div><div><small>基準 Brier</small><b>${formatDecimal(validation.baseline_brier)}</b></div><div><small>平均報酬</small><b>${formatPercent(validation.mean_return)}</b></div><div><small>命中率</small><b>${formatPercent(validation.hit_rate, true)}</b></div><div><small>保留預測</small><b>${formatInteger(Array.isArray(validation.predictions) ? validation.predictions.length : null)}</b></div></div>
    <p class="calibration">${escapeHtml(calibrationText(validation.calibration))}</p>
  </div>` : '<div class="notice"><p>尚無此期限的時間前推檢查結果，不以 0 補值。</p></div>';
  $('#detailContent').innerHTML = `
    <div class="detail-stat-grid">
      <div class="detail-stat"><small>預期淨報酬</small><b class="${toneClass(horizon?.expected_return)}">${formatPercent(horizon?.expected_return)}</b></div>
      <div class="detail-stat"><small>到期獲利比例</small><b>${formatPercent(horizon?.p_positive, true)}</b></div>
      <div class="detail-stat"><small>收盤曾回正比例</small><b>${formatPercent(horizon?.p_recovery, true)}</b></div>
      <div class="detail-stat"><small>綜合排序分</small><b>${formatDecimal(horizon?.score, 2)}</b></div>
    </div>
    <section class="detail-section"><div class="detail-section-header"><h3>價格與成交量</h3><span>最近 ${Math.min(60, row.bars?.length || 0)} 筆 · 紅漲綠跌</span></div>${chartSvg(row.bars, signals)}</section>
    <section class="detail-section"><div class="detail-section-header"><h3>門檻與排除依據</h3><span>期間下檔 q10 ${formatPercent(horizon?.worst_close_q10)}</span></div><div class="reason-list">${reasons.length ? reasons.map((reason) => `<span class="reason-chip">${escapeHtml(reason)}</span>`).join('') : '<span class="reason-chip neutral">此期限未列排除原因</span>'}</div></section>
    <section class="detail-section"><div class="detail-section-header"><h3>近期訊號</h3><span>黃點標在 K 線圖</span></div><div class="reason-list">${signalsHtml}</div></section>
    <section class="detail-section"><div class="detail-section-header"><h3>相似歷史樣本</h3><span>共 ${formatInteger(horizon?.n)} 筆</span></div>${samplesHtml}</section>
    <section class="detail-section"><div class="detail-section-header"><h3>驗證紀錄</h3><span>比例仍屬歷史估計</span></div>${validationHtml}</section>`;
  $('#detailDialog').showModal();
}

function bindEvents() {
  const popovers = $$('.info-popover');
  popovers.forEach((popover) => popover.addEventListener('toggle', () => {
    popover.classList.toggle('is-dismissed', !popover.open);
    if (popover.open) popovers.forEach((other) => { if (other !== popover) other.open = false; });
  }));
  popovers.forEach((popover) => {
    popover.addEventListener('pointerleave', () => popover.classList.remove('is-dismissed'));
    popover.addEventListener('focusout', (event) => {
      if (!popover.contains(event.relatedTarget)) popover.classList.remove('is-dismissed');
    });
  });
  document.addEventListener('pointerdown', (event) => {
    popovers.forEach((popover) => { if (!popover.contains(event.target)) popover.open = false; });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') popovers.forEach((popover) => {
      popover.open = false;
      popover.classList.add('is-dismissed');
    });
  });
  const changeRanking = changes => { updateRanking(appState, changes); renderRows(); };
  $('#searchInput').addEventListener('input', event => changeRanking({ query: event.target.value }));
  for (const suffix of ['', 'Bottom']) {
    const changePage = delta => {
      appState.page += delta;
      renderRows();
      if (suffix) $('#pagination').scrollIntoView({ block: 'start' });
    };
    $(`#previousPage${suffix}`).addEventListener('click', () => changePage(-1));
    $(`#nextPage${suffix}`).addEventListener('click', () => changePage(1));
  }
  $('#retryButton').addEventListener('click', () => loadState());
  $('#updateButton').addEventListener('click', startUpdate);
  $('#emptyUpdateButton').addEventListener('click', startUpdate);
  $('#settingsButton').addEventListener('click', openSettings);
  $('#settingsForm').addEventListener('submit', saveSettings);
  $('#snapshotSelect').addEventListener('change', (event) => selectSnapshot(event.target.value));
  $('#horizonButtons').addEventListener('click', (event) => {
    const button = event.target.closest('[data-horizon]');
    if (!button) return;
    appState.horizon = button.dataset.horizon;
    appState.page = 1;
    $$('[data-horizon]').forEach((item) => {
      const active = item === button;
      item.classList.toggle('active', active);
      item.setAttribute('aria-pressed', String(active));
    });
    renderRows();
  });
  $('#sortSelect').addEventListener('change', event => changeRanking({ sort: event.target.value }));
  $('#kindSelect').addEventListener('change', event => changeRanking({ kind: event.target.value }));
  $('#eligibilitySelect').addEventListener('change', event => changeRanking({ eligibility: event.target.value }));
  $('#positiveAllCheck').addEventListener('change', event => changeRanking({ positiveAll: event.target.checked }));
  $('#resultsBody').addEventListener('click', (event) => {
    const button = event.target.closest('[data-detail-symbol]');
    if (button) openDetail(button.dataset.detailSymbol);
  });
  $$('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => $(`#${button.dataset.closeDialog}`).close()));
  for (const dialog of [$('#detailDialog'), $('#settingsDialog')]) {
    dialog.addEventListener('click', (event) => {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    });
  }
}

function init() {
  if (STATIC_MODE) {
    document.body.classList.add('static-mode');
    $('#settingsButton').hidden = true;
    $('#cloudStatus').hidden = false;
    $('#updateButton').textContent = '讀取最新結果';
    $('#updateButton').title = '讀取雲端已發布結果；不會啟動證交所資料抓取';
    $('#emptyUpdateButton').textContent = '讀取最新結果';
    $('#exportLink').hidden = true;
  }
  bindEvents();
  loadState();
}

if (typeof document !== 'undefined') init();
