# Production Setup Guide

本番API資格情報は各販売者アカウントに紐づきます。Secretの実値をリポジトリ、Cloudflare Pages、ログ、artifactへ保存しないでください。

## 1. Amazon SP-API

Amazon Solution Provider Portalでprivate seller applicationを登録し、自社Seller Centralでself-authorizationします。

Secrets:

- `AMAZON_LWA_CLIENT_ID`
- `AMAZON_LWA_CLIENT_SECRET`
- `AMAZON_REFRESH_TOKEN`

日本向け既定値:

- endpoint: `https://sellingpartnerapi-fe.amazon.com`
- marketplace ID: `A1VC38T7YXB528`

Catalog ItemsとProduct Pricingに必要なrolesを付与します。

## 2. Shopee Open Platform

Partner Appの承認後、ショップ認可でtokenを取得します。

Secrets:

- `SHOPEE_PARTNER_ID`
- `SHOPEE_PARTNER_KEY`
- `SHOPEE_SHOP_ID`
- `SHOPEE_ACCESS_TOKEN`
- `SHOPEE_REFRESH_TOKEN`（永続バックエンドだけで利用推奨）

Configuration:

- `SHOPEE_DEFAULT_CATEGORY_ID`
- `SHOPEE_LOGISTIC_INFO`（JSON配列）
- `IMAGE_HOST_ALLOWLIST`（自社CDN/Storageのhostname）

Shopee refresh tokenは更新時にローテーションするため、永続バックエンドでは `SHOPEE_TOKEN_STATE_FILE` を非公開永続ボリュームへ向けます。Actions cache/artifactへtoken stateを保存しないでください。

## 3. 価格と在庫

必ず販売国・ショップ通貨に合わせます。

```text
TARGET_CURRENCY=JPY
SOURCE_TO_TARGET_FX_RATE=1.0
MARKETPLACE_FEE_RATE=0.0
SHIPPING_COST=0
PRICE_MARKUP=1.18
MINIMUM_MARGIN=300
PRICE_ROUNDING_STEP=10
STOCK_BUFFER_QUANTITY=1
```

通貨が異なる場合、`SOURCE_TO_TARGET_FX_RATE=1.0` のままでは本番出品を拒否します。

## 4. FastAPI本番URL

公開コントロール画面は `https://marketplace-sync-ops.pages.dev` です。Pages自体にはSecretやAmazon/Shopee API実行権限を置きません。

```text
APP_MODE=production
API_LIVE_ENABLED=true
ENABLE_BACKGROUND_SYNC=true
APP_API_TOKEN=<secret-storeで生成した長いランダム値>
CORS_ORIGINS=https://marketplace-sync-ops.pages.dev
ENABLED_CHANNELS=shopee
ALLOW_SOURCE_CONTENT_REUSE=false
SHOPEE_TOKEN_STATE_FILE=/app/secrets/shopee-token-state.json
```

```bash
docker compose up -d --build
market-sync preflight --channels amazon shopee --asin <検証用ASIN>
```

`data/` と `secrets/` は非公開永続ボリュームにします。`GET /api/health` の `status=ready` と `missing_config=[]` を確認します。

## 5. GitHub Actions

Repository → Settings → Secrets and variables → Actionsで設定します。

Secrets:

- `AMAZON_LWA_CLIENT_ID`
- `AMAZON_LWA_CLIENT_SECRET`
- `AMAZON_REFRESH_TOKEN`
- `SHOPEE_PARTNER_ID`
- `SHOPEE_PARTNER_KEY`
- `SHOPEE_SHOP_ID`
- `SHOPEE_ACCESS_TOKEN`

Variables:

- `SHOPEE_DEFAULT_CATEGORY_ID`
- `SHOPEE_LOGISTIC_INFO`
- `IMAGE_HOST_ALLOWLIST`
- `TARGET_CURRENCY`
- `SOURCE_TO_TARGET_FX_RATE`
- `MARKETPLACE_FEE_RATE`
- `SHIPPING_COST`
- `STOCK_BUFFER_QUANTITY`
- `MARKETPLACE_SYNC_ENABLED`（検証完了までは未設定または `false`）

最初に `Production Preflight` を実行します。実出品は、販売するASIN、権利保有の商品名・説明・画像、Shopee category、初期在庫を確定してから `List Product on Shopee` を実行します。外部 item ID と初回同期を確認した後だけ `MARKETPLACE_SYNC_ENABLED=true` にします。

## 6. 出品前チェック

- 仕入先の購入・配送条件が、受注後の履行と顧客対応に耐えられる
- 画像、商品名、説明、ブランド名をShopeeで利用できる証拠を保管
- category必須属性、ブランド承認、禁制品、危険物、医療・化粧品規制を確認
- 返品、配送日数、関税、消費税、プラットフォーム手数料を価格へ反映
- まず在庫1、1商品で注文から配送・キャンセル・返金まで通し試験
- Amazonオファー消失時にShopee在庫が0へ更新されることを確認
