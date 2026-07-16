# Production Setup Guide

本番API資格情報は各販売者アカウントに紐づくため、その発行と認可だけは各社画面で必要です。コード、GitHub、CI、Docker、Pages設定は作成済みです。

## Amazon SP-API

Amazon Solution Provider Portalでprivate seller applicationを登録し、自社Seller Centralでself-authorizationします。

Secrets:

- `AMAZON_LWA_CLIENT_ID`
- `AMAZON_LWA_CLIENT_SECRET`
- `AMAZON_REFRESH_TOKEN`

日本向け既定値:

- endpoint: `https://sellingpartnerapi-fe.amazon.com`
- marketplace ID: `A1VC38T7YXB528`

Catalog ItemsとProduct Pricingに必要なrolesを付与します。

## Shopee Open Platform

Partner appの承認後、ショップ認可でaccess tokenを取得します。

- Secret `SHOPEE_PARTNER_ID`
- Secret `SHOPEE_PARTNER_KEY`
- Secret `SHOPEE_SHOP_ID`
- Secret `SHOPEE_ACCESS_TOKEN`
- Variable `SHOPEE_DEFAULT_CATEGORY_ID`
- Variable `SHOPEE_LOGISTIC_INFO`（JSON配列）

長期運用ではrefresh token保存とaccess token更新処理を追加してください。本リリースは取得済みtokenを利用します。

## Qoo10 QAPI

Qoo10へQAPI利用申請し、API認証キーを取得します。

- Secret `QOO10_API_KEY`
- Secret `QOO10_USER_ID`
- Secret `QOO10_PASSWORD`
- Variable `QOO10_DEFAULT_CATEGORY_ID`
- Variable `QOO10_SHIPPING_NO`
- Variable `QOO10_CONTACT_TEL`

Qoo10 passwordをブラウザ、Pages、リポジトリへ置かないでください。

## GitHub Actions

Repository → Settings → Secrets and variables → Actionsで上記を設定します。`Marketplace Sync` workflowを手動実行し、artifact `marketplace-sync-result` を確認します。

## FastAPI本番URL

Dockerfileを利用できるHTTPSホスティングへ配置します。

```bash
docker compose up -d --build
```

本番環境変数:

```text
APP_MODE=production
API_LIVE_ENABLED=true
ENABLE_BACKGROUND_SYNC=true
CORS_ORIGINS=https://amazon-marketplace-sync-hub.pages.dev
```

Cloudflare Pagesのbuild variable `PUBLIC_API_BASE_URL=https://<fastapi-domain>` を設定し再デプロイします。Pages自体はSecretsを保持しません。

## 出品前チェック

- 自社が画像・説明文・ブランド名を各モールで利用できる証拠を保管
- Shopee/Qoo10カテゴリー、必須属性、配送、返品、税、禁制品を確認
- 価格ルールへモール手数料、送料、為替、安全マージンを反映
- `STOCK_BUFFER_QUANTITY` を1〜2から開始
- Amazonのオファー消失時に0在庫へ更新されることをテスト
