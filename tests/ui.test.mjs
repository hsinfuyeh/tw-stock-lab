import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../web/app.js', import.meta.url), 'utf8');
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;

test('social pages exclude unavailable sources, use per-platform ranks, and cap at ten', async () => {
  const {socialPage}=await import('../web/social.js');
  const rows=Array.from({length:23},(_,i)=>({symbol:String(i),total:23-i,counts:{ptt:23-i,dcard:null,threads:null}}));
  const report={windows:{'24h':rows}};
  assert.equal(socialPage(report,'24h','all').rows.length,10);
  assert.equal(socialPage(report,'24h','dcard').total,0);
  assert.equal(socialPage(report,'24h','ptt',99).rows.length,3);
  assert.equal(socialPage(report,'24h','ptt',99).page,3);
});
test('social update starts collection, prevents duplicate clicks, polls then reloads', async () => {
  const {createSocialUpdater}=await import('../web/social.js');
  let starts=0,reloads=0,nextPoll; const states=[];
  const updater=createSocialUpdater({start:async window=>{starts++; assert.equal(window,'24h'); return {id:'j',running:true};},status:async()=>({id:'j',running:false,status:'partial'})},
    job=>states.push(job),async()=>{reloads++;},error=>assert.fail(error),fn=>{nextPoll=fn;});
  await updater.start('24h'); await updater.start('24h');
  assert.equal(starts,1); assert.equal(reloads,0);
  await nextPoll(); assert.equal(reloads,1); assert.equal(states.at(-1).status,'partial');
});
test('temporary social polling errors do not mark the remote job failed',async()=>{
  const {createSocialUpdater}=await import('../web/social.js');
  let polls=0,nextPoll,reloads=0;const states=[],errors=[];
  const updater=createSocialUpdater({pollDelay:1,start:async()=>({id:'42',running:true,status:'queued'}),status:async()=>{
    polls++;if(polls<=4)throw Error('temporary outage');
    return {id:'42',running:false,status:'success'};
  }},job=>states.push(job),async()=>{reloads++;},message=>errors.push(message),fn=>{nextPoll=fn;});
  await updater.start('24h');
  for(let i=0;i<5;i++)await nextPoll();
  assert.equal(reloads,1);
  assert.ok(states.slice(0,-1).every(job=>job.running));
  assert.equal(states.at(-1).status,'success');
});
const { filterRows, signalDatesWithLabels, sortRows, verificationLabel, paginateRows, dataAgeWarning, dataURL, createDetailLoader, updateRanking, formatDate, twoWeekRows, twoWeekTableMarkup, twoWeekSummary, twoWeekOutcomesForSnapshot } = await import(moduleUrl);

test('individual search matches both 台 and 臺 names and exact code comes first', async () => {
  const { searchSecurities } = await import(moduleUrl);
  assert.equal(typeof searchSecurities, 'function');
  const rows=[{symbol:'23301',name:'台灣公司'},{symbol:'2330',name:'台積電'},{symbol:'0050',name:'元大台灣50'}];
  assert.deepEqual(searchSecurities(rows,'2330').map(r=>r.symbol),['2330','23301']);
  assert.deepEqual(searchSecurities(rows,'臺積電').map(r=>r.symbol),['2330']);
});

test('market ranks discard missing values and distinguish rises, falls and breakouts', async () => {
  const { rankMarketRows } = await import(moduleUrl);
  assert.equal(typeof rankMarketRows, 'function');
  const rows=[{symbol:'A',metrics:{change_pct:2,turnover:50,new_high20:true,momentum20_pct:5}},
    {symbol:'B',metrics:{change_pct:-3,turnover:100,new_high20:false}},
    {symbol:'C',metrics:{change_pct:null,turnover:null,new_high20:null}}];
  assert.deepEqual(rankMarketRows(rows,'gainers').map(r=>r.symbol),['A']);
  assert.deepEqual(rankMarketRows(rows,'losers').map(r=>r.symbol),['B']);
  assert.deepEqual(rankMarketRows(rows,'amount').map(r=>r.symbol),['B','A']);
  assert.deepEqual(rankMarketRows(rows,'high20').map(r=>r.symbol),['A']);
});

test('explorer never shows more than ten securities and clamps the last page', async () => {
  const { paginateExplorer } = await import(moduleUrl);
  assert.equal(typeof paginateExplorer, 'function');
  const rows=Array.from({length:23},(_,symbol)=>({symbol}));
  assert.equal(paginateExplorer(rows,1).rows.length,10);
  assert.deepEqual(paginateExplorer(rows,99).rows.map(r=>r.symbol),[20,21,22]);
});

test('two-week main ranking shows at most ten validated picks, or clearly marked research candidates', () => {
  assert.deepEqual(twoWeekRows({ status: 'validated', recommendations: [{symbol:'A',score:3}], research_candidates: [{symbol:'B',score:9}] }),
    {label:'符合樣本外驗證門檻的觀察名單',rows:[{symbol:'A',score:3}]});
  assert.deepEqual(twoWeekRows({ status: 'insufficient_validation', recommendations: [], research_candidates: [{symbol:'B',score:9}] }),
    {label:'量價排序觀察名單 · 樣本外驗證尚未完成',rows:[{symbol:'B',score:9}]});
});

test('matured two-week tracking distinguishes touched and potential fills', () => {
  assert.equal(twoWeekSummary([{status:'evaluated',touched:true,potential_fill:false},{status:'evaluated',touched:true,potential_fill:true},{status:'not_comparable'}]),
    '已核對 2 筆：其中 2 筆曾觸及目標價、1 筆符合保守可成交條件；另有 1 筆因資料或事件因素無法比較。');
});

test('unvalidated ranking omits unavailable probability and labels every mobile cell', () => {
  const markup = twoWeekTableMarkup({
    status: 'insufficient_validation',
    research_candidates: [{ symbol: '2330', name: '台積電', kind: 'stock', score: 121.35,
      reasons: ['相對強勢', '成交量擴大', '突破前20日高點'] }],
  });
  assert.doesNotMatch(markup, /組別保守達標率估計/);
  assert.match(markup, /data-label="排序"/);
  assert.match(markup, /data-label="標的"/);
  assert.match(markup, /class="asset-badge">股票/);
  assert.match(markup, /data-label="量價訊號"/);
  assert.match(markup, /相對強勢/);
  assert.match(markup, /成交量擴大/);
  assert.match(markup, /<details[^>]*>.*突破前20日高點/s);
  assert.match(markup, /121\.35/);
});
test('candidate rows include an accessible collapsed mobile disclosure',()=>{
  const html=twoWeekTableMarkup({status:'insufficient_validation',research_candidates:[{symbol:'2305',name:'全友',kind:'stock',close:68.7}]});
  assert.match(html,/data-mobile-row-toggle/);
  assert.match(html,/aria-expanded="false"/);
  assert.match(html,/展開 2305 全友/);
});

test('validated ranking identifies group rate as an estimate', () => {
  const markup = twoWeekTableMarkup({status:'validated',recommendations:[
    {symbol:'A',name:'示例',kind:'etf',score:10,probability:0.43,reasons:[]},
  ]});
  assert.match(markup, /組別保守達標率估計/);
  assert.match(markup, /data-label="組別保守達標率估計">43\.0%/);
});

test('candidate row shows historical market metrics and an accessible closing-price trend', () => {
  const trend = Array.from({length:20}, (_, index) => ({date:`2026-09-${String(index+1).padStart(2,'0')}`,close:100+index}));
  const markup = twoWeekTableMarkup({status:'insufficient_validation',research_candidates:[
    {symbol:'2330',name:'台積電',kind:'stock',score:10,close:119,momentum5_pct:3.25,
      momentum20_pct:19,relative_volume:1.8,trend,reasons:[]},
  ]});
  assert.match(markup, /盤後收盤價/);
  assert.match(markup, /近 5 日/);
  assert.match(markup, /近 20 日/);
  assert.match(markup, /相對量能/);
  assert.match(markup, /1\.80 倍/);
  assert.match(markup, /<svg[^>]+role="img"[^>]+aria-label="近 20 交易日收盤走勢：2026-09-01 至 2026-09-20"/);
  assert.match(markup, /119\.00/);
  assert.doesNotMatch(markup, /預測漲幅/);
});

test('candidate row handles an older snapshot without trend metrics', () => {
  const markup = twoWeekTableMarkup({status:'insufficient_validation',research_candidates:[
    {symbol:'2330',name:'台積電',kind:'stock',score:10,reasons:[]},
  ]});
  assert.match(markup, /資料不足/);
  assert.doesNotMatch(markup, /NaN|undefined|<svg/);
});

test('tracking beside a daily list includes only that snapshot', () => {
  assert.deepEqual(twoWeekOutcomesForSnapshot([{snapshot_id:'a'},{snapshot_id:'b'}],'b'),[{snapshot_id:'b'}]);
});

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
  assert.match(verificationLabel({ data_quality: { verification_status: 'missing_evidence' } }), /佐證不足/);
  assert.match(verificationLabel({ data_quality: { verification_status: 'single_source', source_families: ['TWSE'] } }), /尚未完成獨立來源交叉驗證/);
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
  assert.equal(new URL(dataURL(true, 'state'), 'https://example.github.io/tw-stock-lab/').pathname, '/tw-stock-lab/data/home.json');
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
