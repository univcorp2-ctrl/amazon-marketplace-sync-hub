# CODEX.md

## Purpose

Maintain a compliance-first Amazon SP-API to Shopee/Qoo10 synchronization system. Never add Amazon page scraping or bypass marketplace approvals, category restrictions, brand authorization, API limits, or content rights.

## Commands

```bash
pip install -e '.[dev]'
ruff check .
pytest
python scripts/build_pages.py
uvicorn app.main:app --reload
```

## Engineering rules

- Keep live API calls behind `API_LIVE_ENABLED=true`; tests use demo or mocked clients.
- Do not log secrets, LWA tokens, Shopee signatures, or Qoo10 passwords.
- Preserve raw API responses for audit without exposing sensitive customer data.
- Treat Amazon availability as inferred, never exact stock quantity.
- Require explicit rights confirmation before sending text or images to another marketplace.
- Respect rate-limit headers, Retry-After, marketplace error codes, and idempotent seller SKUs.
- Update `docs/api-research.md` when API versions or deprecations change.
