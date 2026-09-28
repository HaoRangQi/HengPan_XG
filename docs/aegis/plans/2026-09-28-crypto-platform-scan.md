# Goal

Implement the crypto-U platform scan page for local crypto data, with both `perpetual` and `tradifi` categories selected by default. Reuse the A-share platform scan behavior where the data shape permits, while keeping A-share routes and APIs unchanged.

# Architecture

Add a crypto-specific local scanner owner under `api/crypto/`, expose an isolated `/api/crypto/platform/scan/*` task contract, and render an isolated `CryptoScanView.vue` at `/crypto-u`. The existing A-share `ScanView.vue` and `/api/scan/*` remain compatibility paths and are not repurposed.

# Tech Stack

Vue 3 + Vite frontend, FastAPI/Pydantic backend, SQLite crypto.db, pandas/numpy analysis, Node test runner, Python unittest.

# Baseline/Authority Refs

- `PRODUCT.md`
- `src/views/ScanView.vue`
- `api/platform_scanner.py`
- `api/platform_analyzer.py`
- `api/crypto/db.py`
- `api/crypto/reader.py`

# Compatibility Boundary

- Existing A-share platform scanner, legacy scanner, local A-share scanner, and crypto data-management endpoints keep their routes and behavior.
- Crypto-U reads only the local crypto database while scanning; Binance remains limited to the existing synchronization flow.
- Both crypto categories are selected by default; users can deselect either category or symbols.

# Verification

- Add backend unit tests for local crypto scan analysis and category selection.
- Add frontend source tests for route wiring and crypto defaults.
- Run all frontend tests, backend tests, `npm run build`, and `git diff --check`.
- Start/restart the backend and verify the new OpenAPI routes and a bounded local scan request.

# Plan Pressure Test

- Owner / contract / retirement: new crypto scanner and router own the new contract; A-share owners remain active for A-share compatibility.
- Verification scope: backend pure scan + API contract + frontend route/build/runtime.
- Task executability: existing local reader, task manager, analyzer, chart, and history patterns provide all required primitives.
- Pressure result: proceed.

# Plan-Time Complexity Check

- Target files: new `api/crypto/platform_scan.py`, new `api/crypto/platform_router.py`, new `src/views/CryptoScanView.vue`, `src/App.vue`.
- Existing size / shape signals: `ScanView.vue` is large and A-share-specific; copying it wholesale would duplicate unrelated fields.
- Owner fit: keep crypto source/contract in `api/crypto/`; keep crypto UI in its own component.
- Recommendation: add a focused crypto owner and reuse stable chart/task primitives; do not expand the A-share component.

# Tasks

1. Add failing tests for crypto local scan analysis and API request validation; implement the focused scanner and router contract.
2. Add the crypto-U Vue page with category/symbol controls, A-share-compatible task lifecycle, results, history, and charts.
3. Wire `/crypto-u`, add frontend regression tests, and run full verification/runtime checks.

# Risks

- Crypto data may be empty or have fewer bars than the selected window; return a clear local-data message and skip insufficient symbols.
- Crypto does not have A-share industry/fundamental fields; result cards use category and quote volume instead.
- Existing crypto database currently stores 1-hour data only; the page exposes 60-minute scanning and does not invent daily data.

# Retirement

No old crypto scan owner exists. The A-share `/api/scan/*` path is intentionally retained for comparison and is not retired.
