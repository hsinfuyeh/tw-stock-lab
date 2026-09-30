export const HORIZONS = ['1', '3', '5', '7', '14', '30'];
export const PAGE_SIZE = 15;

export function searchSecurities(rows, query) {
  const clean = value => String(value || '').normalize('NFKC').replaceAll('臺', '台').toLowerCase().trim();
  const q = clean(query);
  return rows.filter(row => clean(row.symbol).includes(q) || clean(row.name).includes(q))
    .sort((a,b) => Number(clean(b.symbol) === q) - Number(clean(a.symbol) === q) || String(a.symbol).localeCompare(String(b.symbol)));
}

export const MARKET_RANKS = {
  amount: {label:'成交金額', metric:'turnover', unit:'amount', note:'依當日成交金額由高到低排序。'},
  gainers: {label:'漲最多', metric:'change_pct', unit:'percent', note:'依相較前一交易日的收盤漲幅排序；只列上漲標的。'},
  losers: {label:'跌最多', metric:'change_pct', unit:'percent', ascending:true, note:'依相較前一交易日的收盤跌幅排序；只列下跌標的。'},
  volume: {label:'量暴增', metric:'relative_volume', unit:'ratio', note:'當日成交量至少為前 20 交易日平均的 1.5 倍，依倍數排序。'},
  high20: {label:'創 20 日新高', metric:'momentum20_pct', unit:'percent', note:'收盤價高於前 20 交易日最高價，依近 20 日漲幅排序。'},
  low20: {label:'創 20 日新低', metric:'momentum20_pct', unit:'percent', ascending:true, note:'收盤價低於前 20 交易日最低價，依近 20 日跌幅排序。'},
  quiet: {label:'波動小', metric:'volatility_pct', unit:'percent', ascending:true, note:'依近 20 個日報酬的標準差由低到高排序；波動小不代表低風險或成交容易。'},
};

export function rankMarketRows(rows, key) {
  const config = MARKET_RANKS[key];
  if (!config) return [];
  return rows.filter(row => {
    const m = row.metrics || {};
    if (row.currency && row.currency !== 'TWD') return false;
    if (finiteNumber(m[config.metric]) === null) return false;
    if (key === 'gainers') return m.change_pct > 0;
    if (key === 'losers') return m.change_pct < 0;
    if (key === 'volume') return m.relative_volume >= 1.5;
    if (key === 'high20') return m.new_high20 === true;
    if (key === 'low20') return m.new_low20 === true;
    return true;
  }).sort((a,b) => (config.ascending ? 1 : -1) * (a.metrics[config.metric] - b.metrics[config.metric])
    || String(a.symbol).localeCompare(String(b.symbol)));
}

export function paginateExplorer(rows, requested = 1) {
  const pages = Math.max(1, Math.ceil(rows.length / 10));
  const page = Math.min(pages, Math.max(1, Number.isFinite(requested) ? Math.trunc(requested) : 1));
  const start = (page-1)*10;
  return {rows:rows.slice(start,start+10),page,pages,start};
}

export function twoWeekRows(report) {
  if (report?.status === 'validated') return { label: '符合樣本外驗證門檻的觀察名單', rows: (report.recommendations || []).slice(0, 10) };
  return { label: '量價排序觀察名單 · 樣本外驗證尚未完成', rows: (report?.research_candidates || []).slice(0, 10) };
}

function trendMarkup(trend) {
  const points = Array.isArray(trend) ? trend.slice(-20).filter((point) => finiteNumber(point?.close) !== null && point?.date) : [];
  if (points.length < 2) return '<span class="trend-empty">資料不足</span>';
  const values = points.map((point) => point.close);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low;
  const coordinates = values.map((value, index) => {
    const x = 2 + index * 128 / (values.length - 1);
    const y = span ? 34 - (value - low) * 30 / span : 19;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const direction = values.at(-1) >= values[0] ? 'up' : 'down';
  const label = `近 ${points.length} 交易日收盤走勢：${points[0].date} 至 ${points.at(-1).date}`;
  return `<svg class="sparkline sparkline-${direction}" viewBox="0 0 132 38" role="img" aria-label="${escapeHtml(label)}" preserveAspectRatio="none"><polyline points="${coordinates.join(' ')}" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
}

export function twoWeekTableMarkup(report) {
  const { rows } = twoWeekRows(report);
  const showRate = report?.status === 'validated';
  return `<table class="two-week-results"><thead><tr>
    <th scope="col">排序</th><th scope="col">標的</th><th scope="col">盤後收盤價</th>
    <th scope="col">近 5 日</th><th scope="col">近 20 日</th><th scope="col">相對量能</th>
    <th scope="col">近 20 交易日收盤走勢</th><th scope="col">量價訊號</th>${showRate ? '<th scope="col">組別保守達標率估計</th>' : ''}<th scope="col">個股資訊</th>
  </tr></thead><tbody>${rows.map((row, index) => {
    const reasons = [...new Set((Array.isArray(row.reasons) ? row.reasons : []).filter(Boolean))];
    const tags = reasons.slice(0, 2).map((reason) => `<span class="signal-tag">${escapeHtml(reason)}</span>`).join('')
      || '<span class="signal-quiet">依綜合量價條件排序</span>';
    const allReasons = reasons.length ? reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join('')
      : '<li>本日未觸發單項量價標記；排序仍綜合相對動能、成交量及波動等因素。</li>';
    const metric = (value) => finiteNumber(value) === null ? '—' : formatPercent(value);
    const metricClass = (value) => finiteNumber(value) === null ? '' : value >= 0 ? ' positive' : ' negative';
    return `<tr>
      <td class="rank" data-label="排序">${index + 1}</td>
      <td class="security-cell" data-label="標的"><div class="primary-security"><b>${escapeHtml(row.symbol)}</b><span>${escapeHtml(row.name || '未提供名稱')}</span><small class="asset-badge">${escapeHtml(kindLabel(row.kind))}</small></div><button class="mobile-row-toggle" type="button" data-mobile-row-toggle aria-expanded="false" aria-label="展開 ${escapeHtml(row.symbol)} ${escapeHtml(row.name || '未提供名稱')} 的完整資訊">展開</button></td>
      <td class="close-cell" data-label="盤後收盤價">${formatDecimal(row.close, 2)}</td>
      <td class="metric-cell${metricClass(row.momentum5_pct)}" data-label="近 5 日">${metric(row.momentum5_pct)}</td>
      <td class="metric-cell${metricClass(row.momentum20_pct)}" data-label="近 20 日">${metric(row.momentum20_pct)}</td>
      <td class="volume-cell" data-label="相對量能">${finiteNumber(row.relative_volume) === null ? '—' : `${formatDecimal(row.relative_volume, 2)} 倍`}</td>
      <td class="trend-cell" data-label="近 20 交易日收盤走勢">${trendMarkup(row.trend)}</td>
      <td class="signals-cell" data-label="量價訊號"><div class="signal-tags">${tags}</div>
        <details class="signal-details"><summary>查看分析依據</summary>
          <p>動能排序分數：${formatDecimal(row.score, 2)}。分數僅用於同日相對排序，並非預測報酬率或達標機率。</p>
          <ul>${allReasons}</ul>
        </details></td>
      ${showRate ? `<td class="group-rate" data-label="組別保守達標率估計">${formatPercent(row.probability, true)}</td>` : ''}
      <td class="explore-action" data-label="個股資訊"><button class="button button-quiet" type="button" data-detail-symbol="${escapeHtml(row.symbol)}">個股詳情</button></td>
    </tr>`;
  }).join('')}</tbody></table>`;
}

export function twoWeekSummary(outcomes) {
  const evaluated = outcomes.filter(row => row.status === 'evaluated');
  const incomparable = outcomes.filter(row => row.status === 'not_comparable').length;
  if (!evaluated.length && !incomparable) return '尚無觀察期滿的可核對資料。';
  return `已核對 ${evaluated.length} 筆：其中 ${evaluated.filter(row => row.touched).length} 筆曾觸及目標價、${evaluated.filter(row => row.potential_fill).length} 筆符合保守可成交條件；另有 ${incomparable} 筆因資料或事件因素無法比較。`;
}

export function twoWeekOutcomesForSnapshot(outcomes,id) {
  return (outcomes || []).filter(row => row.snapshot_id === id);
}

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
  if (route === 'state') return './data/home.json';
  if (route === 'explore') return './data/explore.json';
  if (route === 'social') return './data/social.json';
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
  if (status === 'single_source') return '單一官方來源，尚未完成獨立來源交叉驗證';
  if (status === 'missing_evidence') return '來源佐證不足，尚待核實';
  return '未記錄來源驗證狀態';
}

const METRICS = {
  expected_return: '樣本平均淨報酬',
  p_positive: '樣本到期正報酬率',
  p_recovery: '期間收盤回正率',
  score: '綜合排序分數',
};

const appState = {
  view: 'home', catalog: [], catalogId: null, catalogLoading: null, catalogError: '',
  homeQuery: '', homePage: 1, rankKey: 'amount', rankPage: 1,
  snapshot: null,
  settings: null,
  history: [],
  twoWeekOutcomes: [],
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
    throw Object.assign(new Error(message),{status:response.status});
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
    select.innerHTML = '<option value="">尚無歷史報告</option>';
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
    $('#snapshotStatus').textContent = '尚無可供查閱的研究報告';
    $('#asOf').textContent = '—';
    const researchSize = Array.isArray(appState.settings?.symbols) ? appState.settings.symbols.length : 0;
    $('#universeCount').textContent = researchSize ? `${researchSize} 檔研究標的` : '尚無資料';
    return;
  }
  const latest = appState.history[0];
  $('#snapshotStatus').textContent = `${latest?.id && latest.id !== snapshot.id ? '歷史報告' : '最新報告'}產製於 ${formatDate(snapshot.created_at, true)}`;
  $('#sourceChecked').hidden=!appState.checkedAt;
  $('#sourceChecked').textContent=appState.checkedAt?`來源檢查：${formatDate(appState.checkedAt,true)}`:'';
  $('#asOf').textContent = formatDate(snapshot.as_of);
  $('#universeCount').textContent = snapshot.coverage ? `${snapshot.coverage.universe_count} 檔標的` : `${snapshot.rows?.length || 0} 檔清單`;
  const coverage = snapshot.coverage;
  if (STATIC_MODE) {
    $('#cloudTiming').textContent = `資料檢查時間：${formatDate(appState.checkedAt, true)}`;
    $('#cloudSchedule').textContent = appState.schedule;
    $('#coverageText').textContent = coverage ? `研究母體包含 ${coverage.stocks} 檔上市股票與 ${coverage.etfs} 檔股票型 ETF；其中 ${coverage.analyzed_count} 檔具備本次分析所需資料，${coverage.unavailable_count} 檔資料不足或不適用。排除原因可於下方歷史情境分析查看。` : '';
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
  $('#methodologyText').textContent = snapshot.methodology || '本次報告未附分析方法摘要。';
  $('#qualityStatus').textContent = verificationLabel(snapshot);
  const manifest = snapshot.data_quality?.source_manifest || [];
  const fetched = manifest.map((item) => item.fetched_at).filter(Boolean).sort();
  $('#qualityTiming').textContent = fetched.length
    ? `資料基準日 ${snapshot.as_of}；最後抓取 ${formatDate(fetched.at(-1), true)}。抓取時間不等於公告時間。`
    : '本次報告未附完整資料取得時間紀錄。';
  $('#sourceManifest').innerHTML = manifest.length
    ? manifest.map((item) => `<li><b>${escapeHtml(item.dataset)}</b> · ${escapeHtml(item.source_family)} · ${escapeHtml(item.symbol || '市場')}<br><small>${escapeHtml(item.url)}<br>SHA256 ${escapeHtml(item.sha256 || '未記錄')}</small></li>`).join('')
    : '<li>此歷史報告未附來源與交叉驗證紀錄。</li>';
  const warnings = Array.isArray(snapshot.warnings) ? snapshot.warnings.filter(Boolean) : [];
  $('#warningsList').innerHTML = warnings.length
    ? warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')
    : '<li>本次報告無額外資料警示；分析限制仍請參閱方法說明。</li>';
}

function renderTwoWeek() {
  const report = appState.snapshot?.two_week;
  const { label, rows } = twoWeekRows(report);
  $('#twoWeekStatus').textContent = report ? label : '目前報告尚無短期動能分析資料';
  $('#twoWeekCount').textContent = `${rows.length} 檔標的`;
  $('#twoWeekNote').textContent = report
    ? report.status === 'validated'
      ? '組別達標率根據已封存的逐日訊號進行時間序列驗證，代表排序組別的歷史頻率；日線資料仍不足以確認實際成交。'
      : '目前依價格與成交量進行相對排序。樣本外驗證與機率校準尚未完成，因此不提供個股達標機率；投資區域無法確認的 ETF 暫不納入。'
    : '這份歷史報告產製於短期動能分析啟用前；請選取最新報告。';
  $('#twoWeekTracking').textContent = `本資料日合格標的到期追蹤：${twoWeekSummary(twoWeekOutcomesForSnapshot(appState.twoWeekOutcomes,appState.snapshot?.id))}`;
  $('#twoWeekTable').innerHTML = twoWeekTableMarkup(report);
  $('#twoWeekTable').hidden = !rows.length;
  $('#twoWeekEmpty').hidden = !!rows.length;
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
    $('#emptyTitle').textContent = '尚無盤後分析報告';
    $('#emptyMessage').textContent = STATIC_MODE ? '目前無法載入已發布的報告。請重新讀取，或透過上方連結查看 GitHub Actions 更新狀態。' : '執行更新後，系統會取得臺灣證券交易所行情並產製研究報告。';
    $('#emptyUpdateButton').hidden = Boolean(appState.job?.running);
    summary.textContent = '尚無可供排序的研究資料';
    return;
  }

  if (!ranked.length) {
    shell.hidden = true;
    empty.hidden = false;
    $('#emptyTitle').textContent = '沒有符合目前條件的標的';
    $('#emptyMessage').textContent = rows.length
      ? '可改選「全部標的」或其他觀察期限，查看各標的的排除原因。'
      : '本次報告沒有可顯示的標的資料；請查看資料品質說明或重新執行更新。';
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
      <td data-label="樣本平均淨報酬"><span class="numeric ${toneClass(expected)}">${formatPercent(expected)}</span><small class="sub-value">中位數 ${formatPercent(horizon?.median_return)}</small></td>
      <td data-label="到期正報酬率"><span class="numeric">${formatPercent(horizon?.p_positive, true)}</span></td>
      <td data-label="期間收盤回正率"><span class="numeric">${formatPercent(horizon?.p_recovery, true)}</span><small class="sub-value">中位數 ${finiteNumber(horizon?.median_recovery_days) === null ? '—' : `${formatDecimal(horizon.median_recovery_days, 1)} 日`}</small></td>
      <td data-label="報酬第 10 百分位"><span class="numeric ${toneClass(horizon?.q10)}">${formatPercent(horizon?.q10)}</span><small class="sub-value">期間最低收盤 ${formatPercent(horizon?.worst_close_q10)}</small></td>
      <td data-label="樣本數"><span class="numeric">${formatInteger(horizon?.n)}</span></td>
      <td class="status-cell" data-label="篩選結果"><span class="status-pill ${eligible ? '' : 'excluded'}">${eligible ? '符合條件' : '未納入'}</span></td>
      <td class="row-action"><button class="row-button" type="button" data-detail-symbol="${escapeHtml(row.symbol)}" aria-label="查看 ${escapeHtml(row.symbol)} 詳情">›</button></td>
    </tr>`;
  }).join('');
}

function renderJob() {
  const job = appState.job;
  const panel = $('#jobPanel');
  if (STATIC_MODE && !cloudClient) {
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
    if (button.id === 'updateButton') button.querySelector('.button-label').textContent = STATIC_MODE ? cloudClient ? running ? '雲端更新中' : '雲端更新行情' : '讀取雲端報告' : running ? '更新行情中' : '更新行情資料';
  }
}

function renderAll() {
  renderSnapshotHeader();
  renderJob();
  renderTwoWeek();
  renderView();
  if (!STATIC_MODE) {
    renderHistory();
    renderRows();
    renderNotes();
  }
}

function schedulePoll() {
  clearTimeout(appState.pollTimer);
  if (!appState.job?.running) return;
  appState.pollTimer = setTimeout(async () => {
    try {
      const nextJob = STATIC_MODE ? await cloudClient.status() : (await fetchJSON('/api/job')).job;
      appState.job = STATIC_MODE && nextJob.scope==='social' ? null : nextJob;
      renderJob();
      if (appState.job?.running) schedulePoll();
      else await loadState({ quiet: true });
    } catch (error) {
      showError(error.message);
      schedulePoll();
    }
  }, STATIC_MODE ? 15000 : 1400);
}

async function loadState({ quiet = false } = {}) {
  if (!quiet) $('#snapshotStatus').textContent = STATIC_MODE ? '正在讀取雲端研究資料' : '正在連線本機資料服務';
  try {
    const payload = await fetchJSON(dataURL(STATIC_MODE, 'state'));
    appState.checkedAt = payload.checked_at;
    appState.nextSession = payload.next_session;
    appState.schedule = payload.schedule || '';
    appState.settings = payload.settings ?? appState.settings;
    if (appState.snapshot?.id !== payload.latest?.id) {
      appState.catalog = []; appState.catalogId = null; appState.catalogError = '';
      appState.homePage = 1; appState.rankPage = 1;
      detailLoader.invalidate();
    }
    appState.snapshot = payload.latest ?? null;
    appState.history = payload.history ?? [];
    appState.twoWeekOutcomes = payload.two_week_outcomes ?? [];
    let cloudStatusError='';
    if (STATIC_MODE && cloudClient) {
      try { const job=await cloudClient.status();appState.job=job.scope==='social'?null:job; }
      catch(error){appState.job=null;cloudStatusError=`雲端進度暫時無法讀取：${error.message}`;}
    } else appState.job=payload.job??null;
    appState.universe = payload.universe ?? [];
    clearError();
    renderAll();
    schedulePoll();
    if (cloudStatusError) showError(cloudStatusError);
    return true;
  } catch (error) {
    showError(error.message);
    if (!appState.snapshot) renderAll();
    return false;
  }
}

async function startUpdate() {
  if (STATIC_MODE && cloudClient) {
    setUpdateButtons(true);
    try {
      appState.job = await cloudClient.start('market','7d');
      renderJob(); schedulePoll();
    } catch (error) { showError(error.message); setUpdateButtons(false); }
    return;
  }
  if (STATIC_MODE) {
    setUpdateButtons(true);
    try {
      if (await loadState()) showToast('已載入最新發布報告；請確認資料基準日');
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
  const width = 700, height = 310, left = 56, right = 12, priceTop = 16, priceBottom = 216, volumeTop = 239, volumeBottom = 286;
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
    return `<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" stroke="#ccd1ca" stroke-width="1"/><text x="${left-6}" y="${y+3}" text-anchor="end" fill="#718083" font-size="12" font-family="monospace">${price.toFixed(1)}</text>`;
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
    ${candles}<text x="${left}" y="${height-6}" fill="#718083" font-size="12" font-family="monospace">${firstDate}</text><text x="${width-right}" y="${height-6}" text-anchor="end" fill="#718083" font-size="12" font-family="monospace">${lastDate}</text>
    <circle cx="${width-100}" cy="10" r="3" fill="#c79b4a"/><text x="${width-92}" y="13" fill="#718083" font-size="12">訊號日</text>
  </svg></div>`;
}

function calibrationText(calibration) {
  if (!Array.isArray(calibration) || !calibration.length) return '未提供校準分箱；歷史比例不應視為已校準機率。';
  return calibration.map((bucket) => `n=${formatInteger(bucket.n)}：估計 ${formatPercent(bucket.predicted, true)}／實際 ${formatPercent(bucket.actual, true)}`).join('；');
}

async function ensureCatalog() {
  const snapshotId = appState.snapshot?.id;
  if (!snapshotId || appState.catalogId === snapshotId) return;
  if (appState.catalogLoading) return appState.catalogLoading;
  appState.catalogError = '';
  appState.catalogLoading = (async () => {
    try {
      const payload = await fetchJSON(dataURL(STATIC_MODE, 'explore'));
      if (appState.snapshot?.id !== snapshotId) return;
      if (payload.id !== snapshotId || payload.as_of !== appState.snapshot.as_of || !Array.isArray(payload.rows)) {
        throw new Error('個股資料與報告版本不一致，請重新讀取報告。');
      }
      appState.catalog = payload.rows; appState.catalogId = payload.id;
    } catch (error) { appState.catalogError = error.message; }
    finally {
      appState.catalogLoading = null; renderExplorer();
      if (appState.snapshot?.id !== snapshotId && appState.view !== 'today') ensureCatalog();
    }
  })();
  return appState.catalogLoading;
}

function renderView() {
  const views = {
    home: ['個股查詢', '輸入股票代號或名稱，查看盤後行情、近期走勢與分析資訊。'],
    today: ['今日名單', '依盤後量價排序，追蹤下一交易日進場後十個交易日內的 +5% 價格目標。'],
    rankings: ['其他排行', '從成交金額、漲跌、量能與波動，探索同一資料日的市場表現。'],
    social: ['社群聲量', '觀察 PTT、Dcard、Threads 的公開股票討論，核對來源與提及篇數。'],
  };
  appState.view = Object.hasOwn(views, location.hash.slice(1)) ? location.hash.slice(1) : 'home';
  const [title, copy] = views[appState.view];
  $('#pageTitle').textContent = title;
  $('.hero .lede').textContent = copy;
  document.title = `${title} · 臺股研究台`;
  $('.hero .eyebrow').textContent=appState.view==='social'?'臺股社群研究 · 公開討論觀察':'臺股盤後研究 · 十個交易日觀察期';
  $('#snapshotCard').hidden = appState.view === 'social';
  $$('[data-view]').forEach(el => { el.hidden = el.dataset.view !== appState.view; });
  $$('[data-view-link]').forEach(el => {
    if (el.dataset.viewLink === appState.view) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
  renderExplorer();
  if (appState.view !== 'today') ensureCatalog();
  if (appState.view === 'social') loadSocialView();
  if (appState.view === 'social'&&!appState.job?.running) $('#jobPanel').hidden=true;
}

let socialViewPromise;
async function loadSocialView() {
  if (!socialViewPromise) socialViewPromise = import('./social.js').then(({createSocialView}) => createSocialView($('#socialView'), () => fetchJSON(dataURL(STATIC_MODE,'social')), STATIC_MODE?cloudClient?{
    cloud:true,pollDelay:15000,
    start:window=>cloudClient.start('social',window),
    status:async()=>{const job=await cloudClient.status();return job.scope==='social'?job:{running:false,status:'idle',sources:{}};}
  }:null:{
    start:async window=>(await fetchJSON('/api/social/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({window})})).job,
    status:async()=>(await fetchJSON('/api/social/job')).job
  }));
  try { await (await socialViewPromise).load(); }
  catch { $('#socialView [data-social-summary]').textContent='社群功能載入失敗，請重新整理。'; socialViewPromise=null; }
}

function exploreTable(rows, start, rankConfig = null) {
  if (!rows.length) return '<div class="explore-empty">沒有符合條件的標的，請試試其他名稱或排行。</div>';
  const primary = rankConfig ? rankConfig.unit === 'amount' ? '當日成交金額' : rankConfig.unit === 'ratio' ? '相對量能' : rankConfig.metric === 'volatility_pct' ? '日報酬標準差' : rankConfig.metric === 'momentum20_pct' ? '近 20 日' : '當日漲跌' : '當日漲跌';
  const valueText = row => {
    const v = row.metrics?.[rankConfig?.metric || 'change_pct'];
    if (finiteNumber(v) === null) return '—';
    if (rankConfig?.unit === 'amount') return `${formatDecimal(v / 100000000, 2)} 億`;
    if (rankConfig?.unit === 'ratio') return `${formatDecimal(v, 2)} 倍`;
    if (rankConfig?.metric === 'volatility_pct') return `${formatDecimal(v, 2)}%`;
    return formatPercent(v);
  };
  return `<div class="table-shell"><table class="explore-table"><thead><tr><th scope="col">排序</th><th scope="col">標的</th><th scope="col">盤後收盤價</th><th scope="col">${primary}</th><th scope="col">近 20 交易日走勢</th><th scope="col">個股資訊</th></tr></thead><tbody>${rows.map((row,i) => `<tr>
    <td class="rank" data-label="排序">${start+i+1}</td>
    <td class="security-cell" data-label="標的"><div class="primary-security"><b>${escapeHtml(row.symbol)}</b><span>${escapeHtml(row.name || '未提供名稱')}</span><small class="asset-badge">${kindLabel(row.kind)}</small></div><button class="mobile-row-toggle" type="button" data-mobile-row-toggle aria-expanded="false" aria-label="展開 ${escapeHtml(row.symbol)} ${escapeHtml(row.name || '未提供名稱')} 的完整資訊">展開</button>${row.data_as_of !== appState.snapshot?.as_of ? `<small class="stale-security">行情日 ${escapeHtml(row.data_as_of || '無資料')} · 當日無有效行情</small>` : ''}</td>
    <td class="close-cell" data-label="盤後收盤價">${formatDecimal(row.metrics?.close,2)}</td>
    <td class="metric-cell${!rankConfig || rankConfig.unit === 'percent' && rankConfig.metric !== 'volatility_pct' ? ` ${toneClass(row.metrics?.[rankConfig?.metric || 'change_pct'])}` : ''}" data-label="${primary}">${valueText(row)}</td>
    <td class="trend-cell" data-label="近 20 交易日走勢">${trendMarkup(row.trend)}</td>
    <td class="explore-action" data-label="個股資訊"><button class="button button-quiet" type="button" data-detail-symbol="${escapeHtml(row.symbol)}">個股詳情</button></td>
  </tr>`).join('')}</tbody></table></div>`;
}

function renderExplorer() {
  $('#catalogCount').textContent = appState.catalogId ? `${appState.catalog.length} 檔標的` : '個股資料';
  const ready = appState.catalogId === appState.snapshot?.id && !!appState.catalogId;
  const status = appState.catalogError || (!appState.snapshot ? '尚無盤後報告，請先取得研究資料。' : '正在讀取個股資料…');
  const config = MARKET_RANKS[appState.rankKey];
  $('#marketRankNav').innerHTML = Object.entries(MARKET_RANKS).map(([key,value]) => `<button type="button" data-market-rank="${key}" aria-pressed="${key === appState.rankKey}">${value.label}</button>`).join('');
  $('#marketRankTitle').textContent = config.label;
  $('#marketRankNote').textContent = config.note;
  for (const isHome of [true,false]) {
    if (isHome && !appState.homeQuery.trim()) {
      $('#homeSummary').textContent = '';
      $('#homeSummary').hidden = true;
      $('#homeResults').innerHTML = '';
      $('#homePager').hidden = true;
      continue;
    }
    const rows = isHome ? searchSecurities(appState.catalog,appState.homeQuery) : rankMarketRows(appState.catalog,appState.rankKey);
    const paged = paginateExplorer(rows, isHome ? appState.homePage : appState.rankPage);
    if (isHome) appState.homePage = paged.page; else appState.rankPage = paged.page;
    const prefix = isHome ? 'home' : 'rank';
    const summary = isHome ? $('#homeSummary') : $('#marketRankSummary');
    summary.hidden = false;
    summary.textContent = ready ? `${appState.snapshot.as_of} · 共 ${rows.length} 檔${isHome && !appState.homeQuery ? ' · 依代號排列，非推薦順序' : ''} · 每頁最多 10 檔` : status;
    (isHome ? $('#homeResults') : $('#marketRankResults')).innerHTML = ready ? exploreTable(paged.rows,paged.start,isHome ? null : config) : '';
    $(`#${prefix}Pager`).hidden = !ready || !rows.length;
    $(`#${prefix}PageText`).textContent = `第 ${paged.page} / ${paged.pages} 頁`;
    $(`#${prefix}Prev`).disabled = paged.page === 1;
    $(`#${prefix}Next`).disabled = paged.page === paged.pages;
  }
}

async function openDetail(symbol) {
  let row = appState.snapshot?.rows?.find((item) => String(item.symbol) === String(symbol));
  if (!row) {
    await ensureCatalog();
    row = appState.catalog.find(item => String(item.symbol) === String(symbol));
  }
  if (!row) { showError(appState.catalogError || '找不到這檔個股的資料。'); return; }
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
  $('#detailKind').textContent = `${kindLabel(row.kind)} · 個股資訊`;
  $('#detailTitle').textContent = `${row.symbol} ${row.name || ''}`.trim();
  $('#detailSubtitle').textContent = `研究日 ${formatDate(row.as_of || appState.snapshot?.as_of)} · 行情日 ${formatDate(row.data_as_of || row.bars?.at(-1)?.date)} · ${row.currency || 'TWD'} · ${horizon?.target_date ? `目標交易日 ${formatDate(horizon.target_date)}` : '目標日尚未確定'}`;
  const samplesHtml = samples.length ? `<div class="table-shell"><table class="sample-table"><thead><tr><th>訊號日</th><th>模擬進場日</th><th>模擬出場日</th><th>成本後報酬</th><th>期間收盤曾回正</th></tr></thead><tbody>${samples.map((sample) => `<tr><td>${escapeHtml(sample.signal_date || '—')}</td><td>${escapeHtml(sample.entry_date || '—')}</td><td>${escapeHtml(sample.exit_date || '—')}</td><td class="numeric ${toneClass(sample.return_pct)}">${formatPercent(sample.return_pct)}</td><td>${sample.recovered === true ? '是' : sample.recovered === false ? '否' : '—'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="notice"><p>此期限尚無可顯示的歷史樣本日期。</p></div>';
  const signalsHtml = signals.length
    ? signals.slice().reverse().slice(0, 12).map((signal) => `<span class="reason-chip neutral">${escapeHtml(signal.date)} · ${escapeHtml((signal.labels || []).join('、') || '訊號')}</span>`).join('')
    : '<span class="reason-chip neutral">沒有訊號標記</span>';
  const validationHtml = validation ? `<div class="validation-card">
    <div class="validation-head"><strong>時間前推抽樣檢查</strong><span class="validation-status">${escapeHtml(validation.status || '未標示狀態')}</span></div>
    <div class="validation-grid"><div><small>驗證筆數</small><b>${formatInteger(validation.n)}</b></div><div><small>MAE</small><b>${formatDecimal(validation.mae)}</b></div><div><small>Brier</small><b>${formatDecimal(validation.brier)}</b></div><div><small>基準 Brier</small><b>${formatDecimal(validation.baseline_brier)}</b></div><div><small>平均報酬</small><b>${formatPercent(validation.mean_return)}</b></div><div><small>命中率</small><b>${formatPercent(validation.hit_rate, true)}</b></div><div><small>保留預測</small><b>${formatInteger(Array.isArray(validation.predictions) ? validation.predictions.length : null)}</b></div></div>
    <p class="calibration">${escapeHtml(calibrationText(validation.calibration))}</p>
  </div>` : '<div class="notice"><p>尚無此期限的時間前推檢查結果，不以 0 補值。</p></div>';
  $('#detailContent').innerHTML = `
    <div class="detail-stat-grid market-detail-stats">
      <div class="detail-stat"><small>盤後收盤價</small><b>${formatDecimal(row.bars?.at(-1)?.close,2)}</b></div>
      <div class="detail-stat"><small>近 5 日</small><b>${formatPercent(row.features?.momentum5)}</b></div>
      <div class="detail-stat"><small>近 20 日</small><b>${formatPercent(row.features?.momentum20)}</b></div>
      <div class="detail-stat"><small>相對量能</small><b>${formatDecimal(row.features?.volume_ratio,2)} 倍</b></div>
    </div>
    <p class="search-hint">以下歷史情境分析採 ${appState.horizon} 曆日期限，與今日名單的十個交易日觀察期不同。</p>
    <div class="detail-stat-grid">
      <div class="detail-stat"><small>樣本平均淨報酬</small><b class="${toneClass(horizon?.expected_return)}">${formatPercent(horizon?.expected_return)}</b></div>
      <div class="detail-stat"><small>樣本到期正報酬率</small><b>${formatPercent(horizon?.p_positive, true)}</b></div>
      <div class="detail-stat"><small>期間收盤回正率</small><b>${formatPercent(horizon?.p_recovery, true)}</b></div>
      <div class="detail-stat"><small>綜合排序分數</small><b>${formatDecimal(horizon?.score, 2)}</b></div>
    </div>
    <section class="detail-section"><div class="detail-section-header"><h3>價格與成交量</h3><span>最近 ${Math.min(60, row.bars?.length || 0)} 筆 · 紅漲綠跌</span></div>${chartSvg(row.bars, signals)}</section>
    <section class="detail-section"><div class="detail-section-header"><h3>篩選條件與排除原因</h3><span>期間最低收盤報酬第 10 百分位 ${formatPercent(horizon?.worst_close_q10)}</span></div><div class="reason-list">${reasons.length ? reasons.map((reason) => `<span class="reason-chip">${escapeHtml(reason)}</span>`).join('') : '<span class="reason-chip neutral">此期限未列排除原因</span>'}</div></section>
    <section class="detail-section"><div class="detail-section-header"><h3>近期訊號</h3><span>黃點標在 K 線圖</span></div><div class="reason-list">${signalsHtml}</div></section>
    <section class="detail-section"><div class="detail-section-header"><h3>相似歷史樣本</h3><span>共 ${formatInteger(horizon?.n)} 筆</span></div>${samplesHtml}</section>
    <section class="detail-section"><div class="detail-section-header"><h3>驗證紀錄</h3><span>比例仍屬歷史估計</span></div>${validationHtml}</section>`;
  $('#detailDialog').showModal();
}

function bindEvents() {
  window.addEventListener('hashchange', renderView);
  $('#stockSearch').addEventListener('input', event => {
    appState.homeQuery = event.target.value; appState.homePage = 1; renderExplorer();
  });
  $('#marketRankNav').addEventListener('click', event => {
    const button = event.target.closest('[data-market-rank]');
    if (!button) return;
    appState.rankKey = button.dataset.marketRank; appState.rankPage = 1; renderExplorer();
  });
  for (const prefix of ['home','rank']) for (const [suffix,delta] of [['Prev',-1],['Next',1]]) {
    $(`#${prefix}${suffix}`).addEventListener('click', () => {
      appState[prefix === 'home' ? 'homePage' : 'rankPage'] += delta; renderExplorer();
    });
  }
  document.addEventListener('click', event => {
    const toggle = event.target.closest('[data-mobile-row-toggle]');
    if(toggle){
      const expanded=toggle.closest('tr').classList.toggle('is-expanded');
      toggle.setAttribute('aria-expanded',String(expanded));
      toggle.textContent=expanded?'收合':'展開';
      toggle.setAttribute('aria-label',`${expanded?'收合':'展開'} ${toggle.closest('tr').querySelector('.security-cell b')?.textContent||'標的'} 的完整資訊`);
      return;
    }
    const button = event.target.closest('[data-detail-symbol]');
    if (button) openDetail(button.dataset.detailSymbol);
  });
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
  $$('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => $(`#${button.dataset.closeDialog}`).close()));
  for (const dialog of [$('#detailDialog'), $('#settingsDialog')]) {
    dialog.addEventListener('click', (event) => {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    });
  }
}

let cloudClient = null;
function requestCloudKey() {
  const dialog=$('#cloudAuthDialog'),form=$('#cloudAuthForm'),input=$('#cloudUpdatePassword');
  return new Promise(resolve=>{
    let value=null;
    const submit=event=>{event.preventDefault();value=input.value;dialog.close();};
    const close=()=>{form.removeEventListener('submit',submit);input.value='';resolve(value);};
    form.addEventListener('submit',submit);dialog.addEventListener('close',close,{once:true});
    dialog.showModal();input.focus();
  });
}
async function init() {
  $('#cloudUpdateLink').hidden = !STATIC_MODE;
  if (STATIC_MODE) {
    document.body.classList.add('static-mode');
    $('#settingsButton').hidden = true;
    $('#updateButton .button-label').textContent = '讀取雲端報告';
    $('#updateButton').title = '讀取雲端已發布結果；不會啟動證交所資料抓取';
    $('#emptyUpdateButton').textContent = '讀取最新報告';
    $('#exportLink').hidden = true;
    try {
      const config=await fetchJSON('./cloud-config.json');
      if(config.endpoint){
        const {createCloudClient}=await import('./cloud.js');
        cloudClient=createCloudClient(config.endpoint,requestCloudKey,fetchJSON,window.sessionStorage);
        $('#updateButton .button-label').textContent='雲端更新行情';
        $('#updateButton').title='啟動雲端行情更新，完成發布後自動讀取新資料';
        $('#emptyUpdateButton').textContent='啟動雲端更新';
      }
    }catch(error){showError(`雲端更新設定載入失敗：${error.message}`);}
  } else {
    $('#updateButton .button-label').textContent = '更新行情資料';
    $('#updateButton').title = '立即向官方來源確認並取得行情資料，完成後更新研究結果';
  }
  bindEvents();
  loadState();
}

if (typeof document !== 'undefined') init();
