import test from 'node:test';
import assert from 'node:assert/strict';
import {researchMarkup,marketMarkup,initResearch} from '../web/research.js';

test('missing and pending remain explicit, dynamic text escaped',()=>{
  const html=researchMarkup({as_of:'2026-01-01',performance:{},tracking:[{symbol:'<script>',name:'A',rank:1,signal_date:'2026-01-01',status:'pending',elapsed_sessions:2,net_return_pct:null,reasons:['<img>']} ]});
  assert.match(html,/等待到期/);assert.match(html,/—/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('industry coverage and small sample shown',()=>{
  const html=marketMarkup({as_of:'2026-01-01',coverage:{daily_return:{eligible:3,total:5}},market:{equal_weight_return_pct:0},classification_missing:2,industries:[{industry:'<b>',small_sample:true,valid_count:2,total:3,median_return_pct:null}]});
  assert.match(html,/樣本偏少/);assert.match(html,/2\/3/);assert.match(html,/&lt;b&gt;/);assert.match(html,/—/);
});
test('static mode never calls local research API',async()=>{
  let calls=0;const controller=initResearch({staticMode:true,fetchReport:()=>{calls++;throw Error('local request');}});
  await controller.load('a');assert.equal(calls,0);
});
test('performance contains day weighting, baseline and unavailable factor',()=>{
  const summary={mean_net_return_pct:1,median_net_return_pct:null,profit_factor:null,counts:{evaluated:3,pending:2},comparable_signal_dates:1};
  const html=researchMarkup({performance:{stock:{top10:summary,baseline:summary,paired_difference_pct:0}},tracking:[]});
  assert.match(html,/1.00%/);assert.match(html,/同日全部合格/);assert.match(html,/日等權/);assert.match(html,/—/);
});
test('industry counts and classification date are visible without tooltips',()=>{
  const html=marketMarkup({classification_sources:[{url:'official',retrieved_at:'2026-01-21'}],industries:[{industry:'24',total:10,valid_count:10,momentum20_count:1,momentum20_small_sample:true,turnover_count:8,median_20_return_pct:4}]});
  assert.match(html,/2026-01-21/);assert.match(html,/>1\/10 檔/);assert.match(html,/>8\/10 檔/);assert.match(html,/20 日樣本偏少/);
});
