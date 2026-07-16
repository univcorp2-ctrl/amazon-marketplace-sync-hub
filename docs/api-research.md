# API Research — 2026-07-16

## Amazon

### 採用: Selling Partner API

- Catalog Items API v2022-04-01: attributes、classifications、dimensions、identifiers、images、productTypes、relationships、salesRanks、summaries。
- Product Pricing v2022-05-01 `getCompetitiveSummary`: featured buying options、reference prices、lowest priced offers。最大20 ASINのbatch requestに対応。
- Product Pricing v0 item offers: 新品オファー、価格、配送・販売者関連情報。
- 認証: LWA refresh tokenをaccess tokenへ交換し、`x-amz-access-token`を送信。
- 実装レート: Catalog 0.55秒、Competitive Summary 30.5秒、Offers 2.1秒。429時は`Retry-After`を尊重。

公式資料:

- https://developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api
- https://developer-docs.amazon.com/sp-api/docs/catalog-items-api-v2022-04-01-reference
- https://developer-docs.amazon.com/sp-api/docs/catalog-items-api-rate-limits
- https://developer-docs.amazon.com/sp-api/reference/getcompetitivesummary
- https://developer-docs.amazon.com/sp-api/reference/product-pricing-v0

### 旧PA-API / Creators API

旧PA-APIは2026-05-15に廃止され、Creators APIへ移行しました。ただしAssociates向けProgram ContentはAmazonへの送客用途を前提とするため、Shopee/Qoo10への画像・説明転載元としては使いません。

- https://affiliate-program.amazon.com/creatorsapi/docs/
- https://affiliate-program.amazon.com/help/operating/policies

### 在庫の解釈

Amazon一般販売商品の正確な残数は公開APIで取得できません。オファー/featured buying optionの存在をavailabilityとして保存し、他モールは安全在庫数へ変換します。

## Shopee Open Platform v2

利用operations:

- `POST /api/v2/media_space/upload_image`
- `POST /api/v2/product/add_item`
- `POST /api/v2/product/update_price`
- `POST /api/v2/product/update_stock`

shop endpoint署名はpartner_id、path、timestamp、access_token、shop_idからHMAC-SHA256を生成します。カテゴリー・属性・物流チャネルは国/ショップごとに異なるため設定値で上書きします。

- https://open.shopee.com/documents/v2/v2.product.add_item?module=89&type=1
- https://open.shopee.com/documents/v2/v2.product.update_price?module=89&type=1
- https://open.shopee.com/documents/v2/v2.product.update_stock?module=89&type=1
- https://open.shopee.com/documents/v2/v2.media_space.upload_image?module=91&type=1

## Qoo10 QAPI

利用operations:

- `Certification.api/CreateCertificationKey`
- `GoodsBasicService.api/SetNewGoods`
- `GoodsOrderService.api/SetGoodsPrice`
- 拡張候補 `GoodsBasicService.api/GetItemDetailInfo`

QAPIはlegacy form/XML APIです。seller authorization keyはAPI呼び出し時に取得します。

- https://api.qoo10.jp/GMKT.INC.Front.QAPIService/Document/QAPIGuideIndex.aspx
- https://api.qoo10.jp/GMKT.INC.Front.OpenApiService/APIList/CreateCertificationKey.aspx
- https://api.qoo10.jp/GMKT.INC.Front.OpenApiService/APIList/SetNewGoods.aspx
- https://api.qoo10.jp/GMKT.INC.Front.OpenApiService/APIList/SetGoodsPrice.aspx

## 保存情報

ASIN、商品名、ブランド、識別子、画像、商品/梱包寸法、分類、variation、sales rank、価格候補、オファー、販売可否、生catalog/pricing/offers JSON、取得時刻、出品request/response、同期結果を保存します。
