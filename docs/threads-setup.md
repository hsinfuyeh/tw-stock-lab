# Threads 雲端收集設定

## 目前狀態

2026-09-29：程式已介接官方 `keyword_search`，GitHub 尚無 `THREADS_ACCESS_TOKEN`。使用者尚未註冊 Meta 開發者帳號。Dcard 已依要求暫緩。

## 使用者先完成

1. 開啟 https://developers.facebook.com/apps/ 。若尚未註冊，會進入 Get Started。
2. 自行閱讀並同意 Meta 平台條款與開發者政策，完成帳號驗證、聯絡資料及 About you。不要把密碼或驗證碼貼到對話。
3. 回到 Apps，建立供本專案使用的應用程式；依目前介面選 Threads API 使用案例。名稱可用 `tw-stock-lab`。
4. 在應用程式的 Threads 設定確認帳號角色／測試者、授權與公開關鍵字搜尋所需權限。公開搜尋是否可用須以目前 Meta 介面與官方規範為準；僅取得基本帳號 token 不保證能搜尋其他人的貼文。遇到審查、驗證或授權同意時，由使用者完成。
5. 取得有效 Threads User Access Token，並按 Meta 官方 Authorization 說明使用適合排程的長效授權。記錄到期日；過期／撤銷後需要更新 GitHub Secret，程式不會自動建立或擴張授權。
6. 到 https://github.com/hsinfuyeh/tw-stock-lab/settings/secrets/actions ，新增 repository secret：Name 為 `THREADS_ACCESS_TOKEN`，Secret 填 token。不要提交到 Git，也不要貼到對話。

## 設定後確認

手動執行 Daily market research and Pages workflow，或等待既有排程。頁面讀取已發布資料；按「重新讀取」不會啟動 API 收集。

核對正式網站 `data/social.json`：Threads 的 `checked_at` 更新，狀態為 `partial`（有限搜尋取樣），並且有掃描結果。若回傳失敗或完全沒有資料，需要確認 token、搜尋權限及帳號角色；不能只因為 Secret 存在就說授權成功。將有效原文連結與提及結果核對後才視為接通。

本機同流程：`python social_update.py --skip-dcard`；token 由執行環境提供，勿放在命令參數或輸出記錄。若僅顯示「尚未授權」，表示目前執行環境沒有 token。

官方來源：Meta 開發者入口 https://developers.facebook.com/ 、Meta 的 Threads API / Authorization 集合 https://www.postman.com/meta/threads/overview 。
