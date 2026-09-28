# 社群聲量雲端實作計畫

依使用者選定 GitHub 雲端方案，在現有研究網站增設獨立社群排行。

1. `marketlab/social.py`：純函數辨識代號／名稱、以貼文 ID 去重、發布時間窗統計、來源缺漏以 null 表示；先寫時間窗、代號碰撞、多標的、同篇去重與缺漏測試。
2. `marketlab/social_collect.py`：有上限的 PTT HTML、Dcard 公開 API、Threads 官方搜尋 API adapter。來源各自容錯、不在公開資料保存完整文本或秘密；PTT 使用實際發文時間。解析、錯誤、上限及授權缺漏使用 fixture 測試。
3. `social_update.py` 與 Actions：市場更新後獨立收集、保存標準化記錄與狀態、匯出 social.json；不改變量價排名，社群失敗不阻擋行情發布。Threads token 由 Secret 注入。提供雲端與本機匯出路徑。
4. `web/social.js` 與首頁導覽：新增社群頁籤、24 小時／7 天、來源篩選、十檔分頁、原文依據；載入資料与行情分離，來源狀態及時間窗始終可見。
5. 真實 PTT 小樣本核對，Dcard／Threads 未取得時如實呈現；跑完整測試、瀏覽器檢查及程式審查，再 commit／push。需要授權的來源保持待接入，不能聲稱已完成三來源收集。
