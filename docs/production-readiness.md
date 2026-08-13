# Production readiness

The public Cloudflare Pages site is a static control-plane/demo build. Live Amazon SP-API access and Shopee listing operations run only from the FastAPI backend.

## Required production gates

A backend is considered ready for live Shopee listing only when `GET /api/health` reports `ready_for_live_listing: true`. The check requires:

- `APP_MODE=production` and `API_LIVE_ENABLED=true`
- `API_ADMIN_KEY` with at least 32 characters
- a restricted `CORS_ORIGINS` value rather than `*`
- Amazon LWA client ID, client secret, refresh token, and marketplace ID
- Shopee partner ID, partner key, shop ID, and access token
- a valid Shopee category ID and logistics configuration
- the rights-confirmation gate enabled

All catalog, listing, and sync endpoints require the `X-Admin-Key` header in production. The health endpoint never returns secret values.

## Scheduled synchronization

The `Marketplace Sync` workflow is fail-closed:

- scheduled runs execute only when the repository variable `MARKETPLACE_SYNC_ENABLED` is exactly `true`
- manual workflow dispatch remains available for validation
- the SQLite database is restored and saved through an Actions cache
- a run fails when Amazon/Shopee configuration is absent, when no persisted listing exists, when any listing update errors, or when zero listings are updated
- overlapping sync runs are prevented

Do not enable the schedule until a rights-confirmed listing has been created, its external Shopee item ID has been verified, and the database has been placed in persistent storage.

## Operational limits before real listings

- Amazon SP-API does not expose exact retail stock quantity. The implementation treats offer availability as sellable/not sellable and publishes only the configured safety quantity.
- Product images, descriptions, and brand assets must be independently licensed for reuse outside Amazon. `rights_confirmed=true` is a technical gate, not proof of permission.
- Shopee category attributes, logistics, restricted-item rules, local currency conversion, fees, taxes, and shipping cost must be validated for the destination shop before listing.
- Mount persistent storage for SQLite or replace it with a managed database. An ephemeral CI workspace is not a production database.
- Store all credentials in the deployment platform's secret store. Never commit them to GitHub or embed them in the public Pages bundle.
