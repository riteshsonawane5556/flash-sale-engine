# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run server (dev)
uv run uvicorn main:app --reload

# Run server (prod-like, used by load test)
uv run python main.py

# Concurrency/oversell load test (server must be running first)
uv run python scripts/load_test.py
```

No test suite exists yet. The load test in `scripts/load_test.py` is the primary correctness check — it fires 1000 concurrent buys against a 10-unit sale and asserts exactly 10 reservations with no overselling.

## Environment

Copy `.env.example` to `.env`. Redis must be running locally on port 6379. Redis keyspace notifications (`notify-keyspace-events = Ex`) are configured automatically at startup.

## Architecture

**Request flow:** `sale_routes.py` (FastAPI router) → `SaleController` (orchestration) → `InventoryService` / `WaitlistService` (Redis ops) + `SaleRepository` (SQLite persistence).

**Two databases, one role each:**
- Redis — source of truth for live stock counts, reservations, distributed locks, waitlist (sorted set), and pub/sub channels.
- SQLite via SQLAlchemy async — durable record of products and confirmed orders only. Not consulted for buy/stock decisions.

**Buy flow:**
1. `BUY_LUA` Lua script atomically decrements stock (returns -1 if out of stock — no race).
2. On success: sets `reservation:{product_id}:{user_id}` key with `PAYMENT_TTL_MS` expiry.
3. On failure: user joins waitlist (Redis sorted set, score = timestamp ms).

**Payment expiry → waitlist promotion** (entirely event-driven, no polling):
- At startup, `expiry_service` subscribes to Redis keyspace channel `__keyevent@{db}__:expired`.
- When a reservation key expires, `InventoryService.restock_and_promote` runs under `DistributedLock`: increments stock, pops next waitlist user, decrements stock, sets their reservation.
- `restock_and_promote` does incr then decr (not a swap) so stock briefly reads +1 under the lock — this is intentional to avoid going negative if the waitlist is empty.

**Distributed lock** (`DistributedLock` in `helpers.py`): token-based Redis lock (SET NX PX) with Lua-guarded release. Used during `confirm_payment` and `restock_and_promote` to prevent double-promotion.

**SSE stock stream** (`GET /sale/{product_id}/stream`): each connection spawns its own Redis pubsub client subscribed to `stock:{product_id}`. Stock is published after every buy, confirm, or restock. Each SSE connection owns its own `aioredis` client — not the shared singleton.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sale/{product_id}/init` | Create/reset product with stock count |
| `POST` | `/sale/{product_id}/buy` | Attempt purchase; returns `reserved` or `waitlisted` |
| `POST` | `/sale/{product_id}/confirm` | Confirm payment for a reservation |
| `GET` | `/sale/{product_id}/stock` | Current stock + waitlist length |
| `GET` | `/sale/{product_id}/waitlist/{user_id}` | User's waitlist position (1-indexed) |
| `GET` | `/sale/{product_id}/stream` | SSE stream of stock updates |
| `GET` | `/health` | Health check |

## Redis key schema

| Key pattern | Type | Purpose |
|---|---|---|
| `sale:{product_id}:stock` | string (int) | live stock count |
| `reservation:{product_id}:{user_id}` | string | pending payment; expires after `PAYMENT_TTL_MS` |
| `waitlist:{product_id}` | sorted set | waitlist; score = join timestamp ms |
| `lock:sale:{product_id}` | string | distributed lock token |
| `stock:{product_id}` | pub/sub channel | stock update broadcast |

`parse_reservation_key` in `helpers.py` parses expiry events to extract `product_id` and `user_id`. It only matches keys with exactly 3 colon-separated parts starting with `reservation` — other expired keys (e.g. lock keys) are silently ignored.

## Settings

All settings live in `src/config/settings.py` via pydantic-settings, loaded from `.env`:

- `PAYMENT_TTL_MS` — reservation window before auto-expiry (default 10 min)
- `LOCK_TTL_MS` — distributed lock TTL (default 5s)
- `LOCK_RETRY_ATTEMPTS` / `LOCK_RETRY_DELAY_MS` — lock spin config
- `REDIS_URL` — default `redis://localhost:6379/0`
- `REDIS_DB` — used to construct the keyspace notification channel (must match the DB in `REDIS_URL`)

## SQLite models

`SaleRepository` owns two SQLAlchemy models: `Product` (id, name, total_units) and `Order` (uuid pk, product_id, user_id, status=confirmed). `upsert_product` updates name/units if product already exists. Orders are append-only — no update path.
