# AI Agent Runbook: Amazon → Shopee 本番化

この手順は、認証・販売規約・API負荷の安全条件を満たしながら、ジャンル指定からAmazon候補取得、Shopee出品、在庫・価格同期まで段階的に本番化するための実行順です。

## 1. Amazon側の事前準備

1. Amazon Sellerアカウントを有効化する。
2. Selling Partner APIのDeveloper登録を行う。
3. SP-APIアプリを作成する。
4. Catalog Items / Pricing / Product Fees等、利用APIに必要なRoleを確認する。
5. SellerアカウントからアプリをAuthorizationする。
6. `AMAZON_LWA_CLIENT_ID`、`AMAZON_LWA_CLIENT_SECRET`、`AMAZON_REFRESH_TOKEN`を取得する。
7. 対象マーケットプレイスIDを決める。日本の既定値は `A1VC38T7YXB528`。
8. Secret値はGitHubへコミットせず、本番バックエンドのSecret Storeへ設定する。
9. 1 ASINだけでCatalog取得、価格取得、販売可否取得を確認する。

## 2. Shopee側の事前準備

1. 対象国のShopee Seller Shopを開設し、販売可能状態にする。
2. Shopee Open PlatformでPartner / Appを作成する。
3. Shop Authorizationを実行する。
4. `SHOPEE_PARTNER_ID`、`SHOPEE_PARTNER_KEY`、`SHOPEE_SHOP_ID`、`SHOPEE_ACCESS_TOKEN`を取得する。
5. refresh tokenを利用する構成では更新・永続化方式を確認する。
6. 対象市場 `SHOPEE_MARKET` を明示する。
7. 利用するShopee category_idと、そのカテゴリの必須属性を確認する。
8. Shopで有効なLogistics IDと配送条件を確認し、`SHOPEE_LOGISTIC_INFO`へ設定する。
9. 禁止・制限商品、知財、ブランド承認、輸入規制を確認する。
10. 1商品だけAPI出品し、Shopee管理画面上の商品ID・価格・画像・配送条件を確認する。

## 3. 本番バックエンド

1. FastAPIバックエンドをHTTPSで公開する。
2. `APP_MODE=production`、`API_LIVE_ENABLED=true` を設定する。
3. 32文字以上の `API_ADMIN_KEY` をSecret Storeへ設定する。
4. `CORS_ORIGINS` を管理画面URLだけに制限する。
5. SQLiteを使う場合は永続ボリュームへ置く。可能ならPostgreSQL等の永続DBへ移行する。
6. Pagesの「API設定」画面からBackend API URLと管理APIキーで接続確認する。
7. `/api/health` のreadinessを確認する。Secret値そのものは返さない。

## 4. 商品選定とプレビュー

1. 最初の画面「出品プラン」でジャンル / 検索キーワードを入力する。
2. 件数は最初1〜5件にする。
3. 上乗せ率、固定上乗せ額、最低利益額を設定する。
4. 「候補をプレビュー」を実行する。
5. Amazon Catalog検索結果から、既出品、販売不可、価格なし商品を除外する。
6. Shopeeブラックリストを適用する。
7. deny商品は常に除外する。
8. review商品もstrictモードでは自動出品から除外する。
9. 予定販売価格を確認する。
10. 商品名・説明・画像をShopeeで利用できる権利を確認する。

## 5. 少量出品

1. `BULK_LISTING_ENABLED=false` のままプレビューを繰り返す。
2. 1商品の手動確認が終わってから `BULK_LISTING_ENABLED=true` にする。
3. 初期値は1回5件、1日20件以下にする。
4. 出品は直列実行する。
5. 商品間に待機時間を入れる。
6. HTTP 403は即停止する。
7. HTTP 429はRetry-Afterまたは指数バックオフ＋ジッターを使う。
8. 429が連続したらサーキットブレーカーを開き停止する。
9. 5xxは有限回だけ再試行する。
10. 連続エラーが設定値を超えたらそのバッチを停止する。

## 6. 在庫・価格同期

1. Shopee item_id、ASIN、SKUを永続DBへ保存する。
2. 定期同期時にAmazonの商品状態を再取得する。
3. Amazonで販売不可になった場合はShopee在庫を0にする。
4. ブラックリスト判定がdeny/reviewへ変わった場合も在庫0にし、`policy_blocked` として記録する。
5. Amazon価格から設定済み利益率・固定利益・最低利益を使って販売価格を再計算する。
6. 価格更新と在庫更新はレート制限を守り直列で行う。
7. 同期結果が0件、またはエラーを含む場合は成功扱いにしない。

## 7. ブラックリスト運用

サーバー強制ブラックリストは `data/shopee_blacklist.json` に保存する。UIのローカル補助ブラックリストは運用者の追加メモ用であり、サーバー側判定を置き換えない。

最低限、武器・弾薬・爆発物、違法薬物、タバコ・ニコチン、偽造品、成人向け明示商品をdenyとする。酒類、医薬品・医療機器、危険化学品、電池・エアゾール・香水、生鮮品、監視機器などはreviewとし、strictモードでは自動出品しない。

Shopee各市場の規約変更時は、ブラックリストのversionと該当グループを更新する。

## 8. AIエージェントが自動で進めてよい範囲

AIエージェントは、コード変更、テスト、CI、公開ページ更新、Secret名の設定確認、readiness確認、プレビュー、低件数の出品実行、同期結果確認までを実行できる。

Amazon / ShopeeのDeveloper登録、Seller本人によるAuthorization、KYC、本人確認、規約同意、Shop審査、ブランド承認など、外部サービス側で本人操作や審査が必要な工程は自動代行できない場合がある。その場合は必要な画面と入力項目を示し、完了後の疎通確認から再開する。
