# Production readiness

The public Cloudflare Pages site is a static control-plane/demo build. Live Amazon SP-API access and Shopee listing operations run only from the FastAPI backend or the explicitly dispatched GitHub Actions workflows.

## Production endpoint

- Static control-plane: `https://marketplace-sync-ops.pages.dev`
- The legacy branded Pages hostname is not used because browser safe-browsing currently blocks it with a dangerous-site warning.
- The Pages bundle contains no marketplace credentials and cannot execute Amazon or Shopee API calls without a separately hosted, authenticated FastAPI backend.

## Production endpoint

- Static control-plane: `https://marketplace-sync-ops.pages.dev`
- The legacy branded Pages hostname is not used because Cloudflare currently serves a suspected-phishing interstitial on that hostname.
- This Pages deployment contains no marketplace credentials and cannot execute Amazon or Shopee API calls. A separately hosted FastAPI backend is required for live operations.

## Required production gates

A backend is configuration-ready when `GET /api/health` reports `status: ready` and `missing_config: []`. The check requires:

- `APP_MODE=production` and `API_LIVE_ENABLED=true`
- `APP_API_TOKEN` stored in the deployment secret store
- a restricted `CORS_ORIGINS` value rather than `*`
- Amazon LWA client ID, client secret, refresh token, and marketplace ID
- Shopee partner ID, partner key, shop ID, and either an access token or refresh token

All catalog, listing, preflight, and sync endpoints require `Authorization: Bearer <APP_API_TOKEN>` or `X-API-Key` in production. The health endpoint returns only configuration names, never secret values.

A live listing additionally requires:

- a valid Shopee category ID and category-specific attributes
- `SHOPEE_LOGISTIC_INFO`
- a seller-controlled `IMAGE_HOST_ALLOWLIST`
- seller-owned title, description, and HTTPS image URLs
- `rights_confirmed=true`
- an explicit target currency, FX rate when currencies differ, fees, shipping cost, and initial stock

## Scheduled synchronization

The `Marketplace Sync` workflow is fail-closed:

- scheduled runs execute only when repository variable `MARKETPLACE_SYNC_ENABLED` is exactly `true`
- manual workflow dispatch remains available for controlled validation
- the non-secret SQLite listing database is restored and saved through an Actions cache
- the workflow exits nonzero when required production configuration is absent, when no persisted listing exists, when any update fails, or when zero listings are updated
- listing and sync workflows share one concurrency group to prevent overlapping marketplace writes

Do not set `MARKETPLACE_SYNC_ENABLED=true` until a rights-confirmed listing has been created, its external Shopee item ID has been verified, and the cached or backend database contains that listing.

## Shopee credential lifecycle

The connector supports Shopee access-token refresh and atomically saves the rotated access and refresh token to `SHOPEE_TOKEN_STATE_FILE`. Use this only on a private, durable backend volume such as `/app/secrets/shopee-token-state.json`.

GitHub-hosted runners do not provide a durable private token-state volume. Actions therefore use `SHOPEE_ACCESS_TOKEN` from repository secrets for controlled runs. Never put a Shopee refresh token or token-state file in the repository, Pages bundle, Actions artifact, or Actions cache.

## Shopee credential lifecycle

Shopee shop access tokens are short-lived. The current connector accepts an access token from the deployment secret store, but it does not yet rotate and durably persist the replacement refresh token. A fixed `SHOPEE_ACCESS_TOKEN` therefore supports controlled validation only, not unattended 24-hour operation.

Before enabling continuous synchronization, run the FastAPI service on a backend with an encrypted, durable secret store and implement atomic access-token/refresh-token rotation. Never write a Shopee refresh token to the public repository, an Actions artifact, an Actions cache, or the Pages bundle.

## Operational limits before real listings

- Amazon SP-API does not expose exact retail stock quantity. The implementation treats offer availability as sellable/not sellable and publishes only the configured safety quantity.
- Product images, descriptions, and brand assets must be independently licensed for reuse outside Amazon. `rights_confirmed=true` is a technical gate, not proof of permission.
- Shopee category attributes, logistics, restricted-item rules, local currency conversion, fees, taxes, shipping, returns, and delivery time must be validated for the destination shop before listing.
- The Actions cache stores non-secret listing state but is not a transactional production database. For continuous operation, run FastAPI with persistent storage or replace SQLite with a managed database.
- Start with one authorized product and stock 1, then verify listing, order, cancellation, refund, and source-offer disappearance before enabling scheduled synchronization.
