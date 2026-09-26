# tw-stock-lab 分析可信度工具評估（2026-09-26）

## 判斷基準

目前網站涵蓋上市普通股及股票型 ETF，以當日量價特徵尋找同檔歷史相似情境，再按 1／3／5／7／14／30 曆日的成本後平均報酬、獲利比例等排序。這些數字尚未證明能預測未來。現行驗證每檔每期限最多取最近 36 個時間前推點，可能有重疊樣本；歷史母集合以目前上市名單為起點，也有存續偏差。現用未還原價格，股利與部分公司行動尚未計入。

工具應分開解決三件事：**資料有沒有算對**、**排行在未來是否有效**、**每日資料有沒有準時更新**。增加技術指標或使用較複雜模型，不能取代前兩項檢查。

| 優先 | 工具／資料 | 對準確度的作用 | 建議接法與驗收 |
| --- | --- | --- | --- |
| 1 | 現有 NumPy ＋ [scikit-learn](https://scikit-learn.org/stable/modules/calibration.html) | 檢查獲利比例是否可信、排名是否在樣本外仍有效 | 先建立逐日不可回寫的預測與到期結果紀錄。按訊號日向前推進；訓練樣本必須在測試訊號日前**已到期**。六期限分開比較前 15 名實際成本後報酬、命中率、Brier 分數和簡單基準；分股票及 ETF。`TimeSeriesSplit(gap=...)` 只可作切分起點，還需按每筆實際出場日排除穿越邊界的標籤。只有驗證改善後，才把歷史比例改稱「校準機率」。 |
| 2 | [證交所／公開資訊觀測站](https://mops.twse.com.tw/)公司行動資料，並以 [FinMind](https://finmind.github.io/tutor/TaiwanMarket/Fundamental/) 抽樣核對 | 避免除權息、分割、減資等使歷史報酬算錯；補已下市個股以減少存續偏差 | 保留原始成交價供進出場模擬，另建調整價及含息報酬供結果標籤；價差與現金股利須分開核算，避免重複計息。抽查事件前後與 ETF 配息；保存來源版本和當時可得時間。FinMind 有除權息結果、分割、下市和月營收資料集，但月營收 `create_time` 不等於正式公告時間，舊資料亦缺該欄位。下市資料仍不能單獨重建完整的歷史上市母集合。公開再發布前先確認資料權利。 |
| 3 | [TWSE e添富](https://www.twse.com.tw/zh/ETFortune/etfInfo/00645) ETF 淨值／折溢價 | 避免把高溢價 ETF 的短期追價當作一般股票機會 | 先顯示資料時間、市價、淨值及折溢價；海外 ETF 另標示市場與時差。是否設排除門檻需用樣本外結果決定，不能任意加一個固定百分比。 |
| 4 | [Fugle 歷史行情](https://developer.fugle.tw/docs/data/http-api/historical/candles/) | 對照 TWSE 日 K、量與調整價，找抓取或換算錯誤 | 先分層抽樣股票、國內／海外 ETF、公司行動日期及低流動性標的；有差異時保留兩邊原始回應與單位。Fugle 仍取自交易所，屬不同供應商處理路徑，不是完全獨立市場來源。需 API key；其[使用規範](https://developer.fugle.tw/docs/data/intro/)對轉送行情有要求，未釐清前只作內部交叉檢核。 |
| 5 | [Healthchecks](https://healthchecks.io/docs/github_actions/) | 發現 GitHub 排程漏跑或失敗，避免用舊資料研究 | 成功發布後回報心跳；另依交易日曆核對網站共同資料日。休市日不應誤報。這改善資料新鮮度，並不提高模型預測力。 |

## 暫緩導入

- [Pandera](https://pandera.readthedocs.io/en/latest/dataframe_schemas.html) 適合新增多種表格資料後統一檢查欄位、型別與範圍。專案目前以 dict／NumPy 為主，先擴充現有檢查即可。
- [SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html) 可產生區間，但逐日持有結果重疊，不能直接把每筆視為獨立抽樣；應按時間區塊重抽後再評估是否加入依賴。
- Lightweight Charts、Uptime Kuma、FinMind-MCP、domain-modeling／Impeccable Skills，以及 tw-stock-trading、tick-stock-panel，可用於介面、監控或設計參考；它們本身不會讓目前排名更準確。TimesFM、vectorbt 等新模型或大型回測框架應等上述基線驗證完成，再以相同保留集比較。

## 下一個可驗收的開發階段

先做**全市場逐日樣本外報告**，不改動網站現有排行。每個期限輸出：當時前 15 名、到期實際成本後結果、同期簡單基準、獲利比例校準表、資料缺口與樣本數。針對多次嘗試過的參數保留最後一段未使用的歷史作一次性檢驗；若效果不穩定，就維持「歷史情境」標示，不升格為預測機率。後續再以公司行動和 ETF 折溢價資料比較改進前後結果。

補充依據：[scikit-learn 時間切分](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)、[FinMind 還原價資料](https://finmind.github.io/tutor/TaiwanMarket/Technical/)、[證交所 ETF 折溢價風險說明](https://www.twse.com.tw/downloads/zh/ETF/topic11.pdf)。
