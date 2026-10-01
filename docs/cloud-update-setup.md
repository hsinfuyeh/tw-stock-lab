# 線上按鈕啟動雲端更新

## 設計與目前部署狀態

GitHub Pages → Cloudflare Worker → GitHub Actions → 抓取／分析 → Pages 發布 → 頁面重新讀取。

行情與社群可分別啟動。社群接受24小時／7天；原本19:15、22:47排程保留。Cloudflare只處理觸發與進度，爬取在GitHub標準Linux runner執行。採Workers Free與SQLite Durable Object，避免同時點擊重複派送；不啟用付費方案。

程式完成後仍需部署 Worker、設定 `GITHUB_TOKEN` Secret，再把正式網址填進 `web/cloud-config.json`。endpoint 空白表示尚未接通，網站明示「雲端更新待設定」，不能宣稱已可由網站啟動。

## 執行順序

1. 完成Worker與範圍驗證測試。
2. 完成公開觸發、任務編號續查、進度輪詢與發布後重讀。
3. 推送GitHub工作流程，確認scope與window輸入。
4. 使用者登入Cloudflare並授權Wrangler；部署免費Worker。
5. 使用者將專用 GitHub 授權設成 Worker Secret。
6. 填入正式Worker網址並發布網站；實際按社群／行情按鈕，核對工作ID與發布結果。

## 帳號與授權

在 `cloud` 目錄使用Cloudflare官方Wrangler（本次驗證版本4.143.1）：

```powershell
npx wrangler login
npx wrangler deploy
npx wrangler secret put GITHUB_TOKEN
```

登入／OAuth 授權由使用者完成。GitHub 建立 fine-grained personal access token，儲存庫只選 `hsinfuyeh/tw-stock-lab`，僅需 Actions read/write，加上預設 Metadata read；設定到期日。這個 token 只進 Cloudflare Secret，不能貼對話或寫入 Git。網站按鈕不要求密碼；所有訪客都可觸發更新。

部署回傳 `https://tw-stock-lab-update.<帳號子網域>.workers.dev`，填 `web/cloud-config.json` 的endpoint，推送與等待Pages部署。網站只允許HTTPS workers.dev 根網址，不接受任意外站。

## 安全與資料一致性

- Worker 的瀏覽器 CORS 只允許 `https://hsinfuyeh.github.io` 網站來源；此設定不是身分驗證，非瀏覽器請求可自行指定 Origin。更新觸發公開，無每日次數或間隔限制；固定儲存庫、main 分支與工作流程，不能傳任意 URL 或儲存庫。
- GitHub token 僅存 Worker Secret；sessionStorage 只存工作 ID、scope 與 window，重新整理可續查。
- Durable Object串行觸發並暫存剛派送的工作；GitHub 執行清單尚未顯示時會沿用原工作編號，派送結果不明時暫停再次送出。已有主分支工作先等待。GitHub工作流程沿用同一concurrency群組，市場與社群使用同一份備份／快取。
- 15秒查詢工作狀態，工作含Pages部署步驟；部署成功才稱已發布，失敗保留既有已發布資料。
- 社群單獨更新使用最近行情快照辨識，不重做全市場分析；若沒有完整快照則失敗並要求先更新行情。
- 手動社群更新重試Dcard公開API（可能403）；Threads只走未登入公開路線，目前搜尋尚未接通，回傳unavailable。雲端搬遷不會解除平台限制。
- 手動工作整批社群失敗會中止發布；每日自動排程社群失敗仍可發布行情，保留原社群結果及原收集時間。

## 參考

- [Workers免費額度](https://developers.cloudflare.com/workers/platform/limits/)
- [SQLite Durable Objects免費方案](https://developers.cloudflare.com/durable-objects/platform/pricing/)
- [Cloudflare Secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [GitHub手動觸發API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [GitHub Actions費用](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
