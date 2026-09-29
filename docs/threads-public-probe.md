# Threads 未登入公開頁面驗證

日期：2026-09-29。使用者指定不使用個人 Threads 帳號，僅驗證未登入公開頁面。

## 範圍與實測

以本機 Python urllib 獨立請求公開頁面，不讀 Chrome profile、不建立 CookieJar、不傳帳號 token。共兩個請求，未執行登入、驗證繞過、私有 API 或瀏覽器自動化。

| 分支 | 輸入 | 結果 | 範圍 |
| --- | --- | --- | --- |
| 首頁列表 | https://www.threads.com/ | HTTP 200；靜態 HTML 沒有貼文連結、time 或 JSON-LD，包含登入提示 | live |
| 公開詳情 | https://www.threads.com/@7lathush7/post/DdyP1nUkgVq | HTTP 200；有公開 og:description，沒有發布時間 metadata、time 或 JSON-LD | live |
| 動態瀏覽器搜尋 | 尚未測試 | 目前可控 Chrome 有個人登入環境，未使用；沒有驗證隔離、未登入的瀏覽器執行環境 | uncovered |
| 搜尋分頁／終止、等待、空結果、失敗、恢復 | 尚未測試 | 不宣稱可重複收集；缺少完整原文字段與列表 | uncovered |

本機證據：`logs/threads-anonymous-home.html`、`logs/threads-anonymous-page.html`、`logs/threads-anonymous-probe.json`、`logs/threads_anonymous_probe.py`。這些為忽略的本機取樣檔，不推送完整 HTML。

現有 website-crawler 引擎已為 `stock-volume-public-no-login` 建立 discovery 記錄，尚未註冊／發布 playbook。不得將公開摘要誤稱為已接通的 Threads 排行，也不得將 HTTP 200 當成欄位齊全。

## 結論

只證實部分未登入公開 HTML 可讀。未完成使用隔離瀏覽器的動態搜尋驗證；沒有可直接用於24小時／7天排行的完整發布時間及搜尋樣本。Threads 保留尚未授權狀態，不啟動個人帳號的自動收集。

後續若繼續本機瀏覽器路線，先驗證獨立且未登入的環境，再小量驗證搜尋、發布時間、原文及終止條件；遇登入要求、驗證或封鎖停止。不能保證平台永不限制公開頁面的請求。
