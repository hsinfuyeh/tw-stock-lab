import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../web/app.js', import.meta.url), 'utf8');
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const { filterRows, signalDatesWithLabels, sortRows, verificationLabel, paginateRows, dataAgeWarning, dataURL, createDetailLoader, updateRanking, formatDate } = await import(moduleUrl);

test('changing ranking criteria returns to the first page and retains other filters', () => {
  assert.equal(typeof updateRanking, 'function');
  for (const changes of [{sort:'p_recovery'},{horizon:'30'},{kind:'etf'},{eligibility:'all'},{positiveAll:true},{query:'2330'}]) {
    const state = {page:3,sort:'expected_return',horizon:'7',query:'',kind:'all'};
    updateRanking(state, changes);
    assert.equal(state.page, 1);
    for (const [key, value] of Object.entries(changes)) assert.equal(state[key], value);
    if (!('horizon' in changes)) assert.equal(state.horizon, '7');
  }
});

test('market dates and update timestamps use Taipei time even on an overseas device', () => {
  assert.equal(typeof formatDate, 'function');
  const original = process.env.TZ;
  try {
    process.env.TZ = 'America/Los_Angeles';
    assert.equal(formatDate('2026-09-21'), '2026/09/21');
    assert.match(formatDate('2026-09-21T11:15:00Z', true), /2026\/09\/21.*07:15/);
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});

test('verification label distinguishes missing evidence, legacy and one upstream', () => {
  assert.equal(typeof verificationLabel, 'function');
  assert.match(verificationLabel({}), /未記錄/);
  assert.match(verificationLabel({ data_quality: { verification_status: 'missing_evidence' } }), /證據不足/);
  assert.match(verificationLabel({ data_quality: { verification_status: 'single_source', source_families: ['TWSE'] } }), /未完成跨來源/);
  assert.match(verificationLabel({ data_quality: { verification_status: 'unknown_future_status' } }), /未記錄/);
});

const row = (symbol, kind, values) => ({
  symbol,
  kind,
  horizons: {
    1: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    3: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    5: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    7: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    14: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    30: { eligible: true, expected_return: 1, p_positive: 0.5, p_recovery: 0.6 },
    ...values,
  },
});

test('sortRows keeps zero as a real value and sends null or invalid values last', () => {
  const rows = [
    row('NULL', 'stock', { 7: { eligible: true, expected_return: null } }),
    row('ZERO', 'stock', { 7: { eligible: true, expected_return: 0 } }),
    row('HIGH', 'stock', { 7: { eligible: true, expected_return: 2.4 } }),
    row('TEXT', 'stock', { 7: { eligible: true, expected_return: '9.9' } }),
  ];

  assert.deepEqual(
    sortRows(rows, '7', 'expected_return').map(({ symbol }) => symbol),
    ['HIGH', 'ZERO', 'NULL', 'TEXT'],
  );
});

test('sortRows supports both historical probability rankings without mutating input', () => {
  const rows = [
    row('A', 'stock', { 7: { eligible: true, p_positive: 0.91, p_recovery: 0.2 } }),
    row('B', 'etf', { 7: { eligible: true, p_positive: 0.42, p_recovery: 0.88 } }),
  ];
  const original = [...rows];

  assert.deepEqual(sortRows(rows, 7, 'p_positive').map(({ symbol }) => symbol), ['A', 'B']);
  assert.deepEqual(sortRows(rows, 7, 'p_recovery').map(({ symbol }) => symbol), ['B', 'A']);
  assert.deepEqual(rows, original);
});

test('sortRows ranks composite score as a numeric metric', () => {
  const rows = [
    row('LOW', 'stock', { 7: { eligible: true, score: -0.5 } }),
    row('HIGH', 'stock', { 7: { eligible: true, score: 1.8 } }),
    row('NONE', 'stock', { 7: { eligible: true, score: null } }),
  ];

  assert.deepEqual(sortRows(rows, 7, 'score').map(({ symbol }) => symbol), ['HIGH', 'LOW', 'NONE']);
});

test('signalDatesWithLabels omits backend signal rows with no labels', () => {
  const signals = [
    { date: '2026-09-10', labels: [] },
    { date: '2026-09-11', labels: ['長紅'] },
    { date: '2026-09-12', labels: null },
  ];

  assert.deepEqual([...signalDatesWithLabels(signals)], ['2026-09-11']);
});

test('filterRows applies stock and ETF filters plus explicit eligibility views', () => {
  const rows = [
    row('2330', 'stock', { 7: { eligible: true, expected_return: 1 } }),
    row('2317', 'stock', { 7: { eligible: false, expected_return: -1 } }),
    row('0050', 'etf', { 7: { eligible: true, expected_return: 0.5 } }),
  ];

  assert.deepEqual(filterRows(rows, { horizon: 7, kind: 'stock', eligibility: 'eligible' }).map(r => r.symbol), ['2330']);
  assert.deepEqual(filterRows(rows, { horizon: 7, kind: 'etf', eligibility: 'all' }).map(r => r.symbol), ['0050']);
  assert.deepEqual(filterRows(rows, { horizon: 7, kind: 'all', eligibility: 'excluded' }).map(r => r.symbol), ['2317']);
});

test('filterRows can require positive expected return across all six horizons', () => {
  const rows = [
    row('PASS', 'stock', {}),
    row('ZERO', 'stock', { 30: { eligible: true, expected_return: 0 } }),
    row('MISSING', 'stock', { 14: null }),
    row('TEXT', 'stock', { 5: { eligible: true, expected_return: '1.2' } }),
  ];

  assert.deepEqual(
    filterRows(rows, { horizon: 7, kind: 'all', eligibility: 'all', positiveAll: true }).map(r => r.symbol),
    ['PASS'],
  );
});

test('filterRows treats a missing selected horizon as excluded rather than eligible', () => {
  const rows = [row('MISSING', 'stock', { 7: null }), row('VALID', 'stock', {})];

  assert.deepEqual(filterRows(rows, { horizon: 7, kind: 'all', eligibility: 'eligible' }).map(r => r.symbol), ['VALID']);
  assert.deepEqual(filterRows(rows, { horizon: 7, kind: 'all', eligibility: 'excluded' }).map(r => r.symbol), ['MISSING']);
});

test('search matches trimmed ticker or name, including active ETF suffix, while preserving filters', () => {
  const rows = [{ ...row('00981A', 'etf', {}), name: '主動統一台股增長' }, { ...row('2330', 'stock', {}), name: '台積電' }];
  assert.deepEqual(filterRows(rows, { query: ' 981a ' }).map(r => r.symbol), ['00981A']);
  assert.deepEqual(filterRows(rows, { query: '台積' }).map(r => r.symbol), ['2330']);
  assert.deepEqual(filterRows(rows, { query: '台積', kind: 'etf' }), []);
});

test('pagination caps each page at 15 and clamps pages after filtering', () => {
  assert.equal(typeof paginateRows, 'function');
  const rows = Array.from({ length: 41 }, (_, i) => i);
  assert.deepEqual(paginateRows(rows, 2), { rows: rows.slice(15, 30), page: 2, pages: 3, start: 15 });
  assert.equal(paginateRows(rows, 99).page, 3);
  assert.deepEqual(paginateRows(rows, 3), { rows: rows.slice(30), page: 3, pages: 3, start: 30 });
  assert.deepEqual(paginateRows(rows.slice(0, 15), 2), { rows: rows.slice(0, 15), page: 1, pages: 1, start: 0 });
  assert.deepEqual(paginateRows([], 4), { rows: [], page: 1, pages: 1, start: 0 });
});

test('static data and CSV routes remain inside the project subpath; local API routes remain available', () => {
  assert.equal(typeof dataURL, 'function');
  assert.equal(new URL(dataURL(true, 'state'), 'https://example.github.io/tw-stock-lab/').pathname, '/tw-stock-lab/data/state.json');
  assert.equal(dataURL(true, 'snapshot', { id: 'snap1' }), './data/snapshots/snap1.json');
  assert.equal(dataURL(true, 'export', { id: 'snap1', horizon: '14', sort: 'score' }), './data/csv/snap1-14-score.csv');
  assert.equal(dataURL(false, 'state'), '/api/state');
});

test('age warning follows Taipei 20:00 and known next trading date, with explicit conservative weekday fallback', () => {
  assert.equal(typeof dataAgeWarning, 'function');
  assert.equal(dataAgeWarning('2026-09-18', '2026-09-21', new Date('2026-09-21T11:59:00Z')), '');
  assert.match(dataAgeWarning('2026-09-18', '2026-09-21', new Date('2026-09-21T12:00:00Z')), /更新/);
  assert.equal(dataAgeWarning('2026-09-21', '2026-09-22', new Date('2026-09-21T14:00:00Z')), '');
  assert.equal(dataAgeWarning('2026-09-18', null, new Date('2026-09-20T13:00:00Z')), '');
  assert.match(dataAgeWarning('2026-09-18', null, new Date('2026-09-21T12:00:00Z')), /平日.*休市/);
});

test('detail loading discards obsolete symbol responses and invalidated horizon or snapshot requests', async () => {
  assert.equal(typeof createDetailLoader, 'function');
  const pending = new Map();
  const loader = createDetailLoader(url => new Promise(resolve => pending.set(url, resolve)));
  const first = loader.load({ detail_url: 'a.json' });
  const second = loader.load({ detail_url: 'b.json' });
  pending.get('b.json')({ symbol: 'B' });
  assert.deepEqual(await second, { symbol: 'B' });
  pending.get('a.json')({ symbol: 'A' });
  assert.equal(await first, null);
  const third = loader.load({ detail_url: 'c.json' });
  loader.invalidate();
  pending.get('c.json')({ symbol: 'C' });
  assert.equal(await third, null);
});

test('detail failures propagate for a useful error and obsolete failures are ignored', async () => {
  assert.equal(typeof createDetailLoader, 'function');
  const loader = createDetailLoader(async () => { throw new Error('詳情檔案讀取失敗'); });
  await assert.rejects(loader.load({ detail_url: 'bad.json' }), /詳情檔案讀取失敗/);
});
