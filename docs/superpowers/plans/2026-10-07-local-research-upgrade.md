# Local Research Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本機提供成本後績效、市場與產業摘要，以及每日候選追蹤。

**Architecture:** Python 純計算模組分別處理交易結果與市場摘要；MarketService 聚合已保存快照，HTTP API 供本機網頁讀取。新報告與原始候選隔離版本，獨立資料目錄提供預覽。

**Tech Stack:** Python 3.12+、NumPy、SQLite、現有 HTTP server、原生 JavaScript／CSS、Node 22+。

**Spec:** `docs/superpowers/specs/2026-10-07-local-research-upgrade-design.md`

## Global Constraints

- 分支 `local/research-upgrade`；僅本機開發與 Git 提交，不 push、不觸發 Actions、不部署 Pages、不修改 Cloudflare。
- 伺服器綁定 127.0.0.1；開發資料放在已忽略的 `data/local-research-dev/`，日誌放 `logs/local-research/`。
- 不使用兩個參考工具的程式碼或資料服務。原量價排名與 two-week-v2 結果保持可追溯。
- trade-policy-v1：次日開盤進場、十交易日、毛 +5%、無停損；股票／ETF 成本沿用 analytics.net_return。
- 缺資料顯示不可計算，不以零替代。不新增統計優勢認證、投資組合回撤或個股機率。

## Review Focus

1. 同一日期重新分析不得重複算訊號，或以新排名覆蓋原候選。
2. 出場後才發生的日低不能算成持有期間不利變動；同日出場的盤中順序未知。
3. 未成熟、缺日、未成交及公司行動記錄不得進入完成绩效分母。
4. 舊快照缺分類、不同指標有不同有效集合時，分母與缺漏需獨立呈現。
5. 本機與靜態模式分流，靜態頁面不能呼叫本機 API，本機不能觸發 Worker。

## Task 1: 固定交易模擬與績效統計

**Files:** 新增 `marketlab/performance.py`、`tests/test_performance.py`。

**Interfaces:** `simulate_trade(rows, signal_date, kind, calendar, as_of) -> dict`；`summarize_performance(records) -> dict`。records 保存 signal_date、symbol、kind、etf_style、rank、status、net_return_pct、target_filled、policy_version。模組使用 two_week.target_price／_tick、analytics.net_return／complete_window／adjusted；不改其既有行为。

- [ ] 寫失敗測試：100 元進場、日高僅 105 時未達保守成交條件；日高 105.5 時出場 105；後續日開盤 107 時出場 107；未達標十日收盤 98；淨報酬等於 net_return 的單次結果。
- [ ] 補失敗測試：ETF 費率、尚未成熟、缺實際交易日、進場鎖價、調整標記、無虧損的獲利因子為 None；出場當日低點不混入不利變動。
- [ ] 執行 `python -m unittest discover -s tests -p test_performance.py -v`，確認缺少新功能造成失敗。
- [ ] 實作 trade-policy-v1 與分組彙總；先按訊號日平均，再跨日等權平均。績效候選限定 rank <= 10，基準使用同日全部合格標的；差額只比較双方都有可比較結果的日期。
- [ ] 測試日期等權：第一日兩筆 +10%、第二日一筆 -10%，跨日平均為 0%，不是 +3.33%；未成熟紀錄只列覆蓋數，不進報酬／達標分母。
- [ ] 重跑該測試及既有 test_two_week.py／test_analytics.py，通過後本機提交。

## Task 2: 市場與產業摘要

**Files:** 新增 `marketlab/market_summary.py`、`tests/test_market_summary.py`；修改 `marketlab/data.py`、`marketlab/service.py`、`tests/test_market.py`。

**Interfaces:** `build_market_summary(snapshot) -> dict`，輸出 as_of、coverage、market、industries。標的新增 industry、industry_source、industry_retrieved_at；舊資料不推測分類。

- [ ] 寫失敗測試：股票 +10%、-10%、0% 的漲跌家數為 1／1／1、等權日報酬為 0%；ETF 不入分母；產業報酬取中位數；不足五檔顯示 small_sample。
- [ ] 補測試：缺昨日價格仍可計當日成交金額；缺二十日窗口不入均線分母；無分類進入未記錄；行情錯日與調整窗口排除相應指標。
- [ ] 執行 `python -m unittest discover -s tests -p test_market_summary.py -v`，確認失敗。
- [ ] 實作純計算摘要。二十日成交值倍數以同時具備當日與完整前二十日成交值的固定股票集合計算，輸出集合大小。產業成交值占比分母為同日有效普通股總成交值。
- [ ] 公司資料解析保留官方產業別；取得時間來源為本次公司清單的來源證據，不以資料期別冒充公布時間。
- [ ] 更新資料簽章包含摘要版本與分類版本；同日已有候選使用其封存順位，不因重算摘要建立第二份訊號。
- [ ] 執行摘要、市場與既有服務測試；通過後本機提交。

## Task 3: 歷史聚合、追蹤與本機 API

**Files:** 修改 `marketlab/service.py`、`marketlab/server.py`；新增 `tests/test_research_report.py`，修改 `tests/test_http.py`。

**Interfaces:** `MarketService.research_report(snapshot_id=None) -> dict`；GET `/api/research?id=<snapshot_id>` 回 market_summary、performance、tracking、as_of、policy_version。不存在的明確 snapshot_id 回 404；無快照回缺資料狀態。GET 不啟動抓取或寫入研究資料。

- [ ] 寫失敗測試：兩份同訊號日快照的紀錄只算一次；使用首次封存候選順位；不同 ranker 版本分開；API id 切換與不存在 id 回應；GET 前後原快照一致。
- [ ] 補測試：最新資料不足以核對舊候選時顯示原因；pending 顯示 elapsed_sessions 而不提供完成報酬；全部缺資料仍可載入報告。
- [ ] 執行 `python -m unittest discover -s tests -p test_research_report.py -v`，確認失敗。
- [ ] 聚合同一 ranker 版本、訊號日不晚於選定快照日期的封存資料；模擬行情與交易日都截斷至該日期。從選定及更早已保存快照取得可用日線，不使用更晚快照數值。
- [ ] 以 `(signal_date, symbol, ranker_version)` 去重；保留 snapshot_id 及來源證據識別。報告標示可核對與不足資料，不給推測結果。
- [ ] 新增只讀 API、loopback 主機檢查與舊資料相容回應；執行研究報告及 HTTP 測試，通過後本機提交。

## Task 4: 本機頁面與獨立資料啟動

**Files:** 新增 `web/research.js`、`tests/research-ui.test.mjs`、`scripts/seed_local_research.py`；修改 `web/index.html`、`web/app.js`、`web/style.css`、`marketlab/server.py`；新增 `launch-local-research.ps1`、`tests/test_local_seed.py`。

**Interfaces:** research.js 輸出 `researchMarkup(report) -> string` 及 `initResearch({fetchReport, openSecurity})`。啟動腳本使用 bundled Python，`app.py serve --port 8771 --data-dir data/local-research-dev`，先核對連接埠未被別的服務占用。

- [ ] 寫失敗測試：淨報酬 None 顯示「—」，小樣本與 pending 明示；動態資料 HTML 轉義；產業與績效行可讀；靜態模式不要求 `/api/research`。
- [ ] 執行 `node --test tests/research-ui.test.mjs`，確認失敗。
- [ ] 加入本機首頁市場摘要與產業表、本機績效／追蹤入口；保留既有搜尋、排行及社群。說明沿用懸浮提示，樣本數與資料日可見。
- [ ] 新增 seed 測試：將既有 dist 靜態快照和逐檔 details 合併到新的 SQLite；目標有資料時拒絕覆蓋；無有效快照時報錯；不寫入來源 data／dist。
- [ ] 執行 `python -m unittest discover -s tests -p test_local_seed.py -v`，確認失敗後實作只讀來源、寫入獨立資料目錄的匯入工具；匯入保留原資料日與分類缺漏。
- [ ] 啟動腳本預設不自動抓全市場；隱藏背景視窗，保存 PID 與日誌。首頁本機更新使用現有本機 API，不使用 Cloudflare。
- [ ] 執行 UI、seed 與 HTTP 測試，通過後本機提交。

## Task 5: 本機完整驗收與交付

**Files:** 修改 `README.md`，更新本計畫進度；其他檔案僅修復驗收確認的問題。

- [ ] 執行 `python -m unittest discover -s tests -v`、`node --test tests/*.test.mjs`，保存結果。
- [ ] 匯入真實既有快照並啟動 127.0.0.1:8771，核對 API 真實資料日與來源、無快照／缺產業狀態；禁止以測試資料冒充實際績效。
- [ ] 瀏覽器核對桌面與手機尺寸：市場、產業、績效、追蹤、既有搜尋／排行，確認沒有頁面溢出與錯誤載入。保存可供使用者查看的預覽截圖。
- [ ] 需要新資料時只在獨立開發目錄執行本機官方更新；先檢查既有快取可否續用，遇外部來源阻擋明示限制，不把未完成初始化稱作完成。
- [ ] 依 executing-plans 做一次全分支獨立審查，修復重要問題並完成所需測試。
- [ ] 記錄本機啟動／停止方法、實際測試結果、資料缺口與分支狀態；保持開發分支，交付本機預覽網址。不得合併 main 或發布遠端。
