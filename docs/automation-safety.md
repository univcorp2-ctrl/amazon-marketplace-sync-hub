# Amazon category to Shopee automation safety

## What is automated

`POST /api/automation/shopee` accepts a user keyword/category query. It searches Amazon Catalog Items, fetches the candidate product data, runs the Shopee policy gate, removes duplicates/unavailable/no-price candidates, and returns a preview. `execute=true` can create Shopee listings only after all production gates pass.

## Fail-closed product policy

`data/shopee_blacklist.json` is a conservative cross-border baseline dated 2026-08-13. `deny` categories are always blocked. In the default strict mode, `review` categories are also blocked from automatic listing. Unknown/unspecified Shopee markets are blocked. This is intentionally more restrictive than any single destination-market policy.

The baseline covers weapons/explosives, illegal or controlled drugs, tobacco/nicotine, counterfeit goods, explicit adult products, alcohol, pharmaceuticals/medical devices/supplements, hazardous chemicals, batteries/aerosols/perfume/liquids, perishables, gambling/surveillance items, and other regulated/sensitive goods. Destination-market law and the current Shopee Seller Education prohibited/restricted policy remain authoritative, so the policy file must be reviewed whenever Shopee changes its rules.

## API and account protection layers

1. Production endpoints require `X-Admin-Key`.
2. Bulk execution is disabled by default (`BULK_LISTING_ENABLED=false`).
3. An explicit supported `SHOPEE_MARKET` is mandatory.
4. Rights confirmation is mandatory.
5. Per-run listings default to 5; daily listings default to 20.
6. Listings are serial, with an 8-second pause between products.
7. Shopee calls are serial and rate-limited to one request per 1.5 seconds by default.
8. 429 responses use bounded exponential backoff with jitter; repeated throttling opens a circuit breaker.
9. HTTP 403 immediately opens the circuit breaker and stops automatic Shopee calls.
10. Server errors are retried only a bounded number of times.
11. A per-process Shopee API call budget stops runaway loops.
12. Images are capped at four uploads per listing.
13. Existing ASINs are not bulk-listed again.
14. Inventory synchronization re-runs the policy gate. Newly blocked items are set to stock zero and marked `policy_blocked`.
15. Sync stops if the Shopee circuit breaker opens.

## Rollout

Keep bulk execution disabled until Amazon and Shopee credentials, Shopee destination market, category, logistics, persistent database, pricing assumptions, content/image rights, and one manual listing have all been validated. Then enable a low daily cap first and increase it only after reviewing seller health and API errors.
