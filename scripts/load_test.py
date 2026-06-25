"""
Concurrency test: 1000 simultaneous buy requests against 10-unit flash sale.
Asserts no overselling. Run with: uv run python scripts/load_test.py

Requirements: pip install httpx
Server must be running: uv run python main.py
"""

import asyncio
import sys

import httpx

BASE_URL = "http://localhost:8000"
PRODUCT_ID = "iphone15"
TOTAL_UNITS = 10
TOTAL_BUYERS = 1000


async def seed() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        resp = await client.post(
            f"/sale/{PRODUCT_ID}/init",
            json={"name": "iPhone 15", "units": TOTAL_UNITS},
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"seeded: stock={data['stock']}")


_sem = asyncio.Semaphore(100)


async def buy(client: httpx.AsyncClient, user_id: str) -> str:
    async with _sem:
        try:
            resp = await client.post(
                f"/sale/{PRODUCT_ID}/buy",
                json={"user_id": user_id},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["status"]
        except Exception as exc:
            return f"error:{exc}"


async def run() -> None:
    await seed()

    print(f"firing {TOTAL_BUYERS} concurrent buy requests...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        tasks = [buy(client, f"user_{i}") for i in range(TOTAL_BUYERS)]
        results = await asyncio.gather(*tasks)

    reserved = results.count("reserved")
    waitlisted = results.count("waitlisted")
    errors = [r for r in results if r.startswith("error")]

    print(f"\nresults:")
    print(f"  reserved  : {reserved}")
    print(f"  waitlisted: {waitlisted}")
    print(f"  errors    : {len(errors)}")

    assert reserved == TOTAL_UNITS, f"FAIL: expected {TOTAL_UNITS} reserved, got {reserved}"
    assert waitlisted == TOTAL_BUYERS - TOTAL_UNITS, (
        f"FAIL: expected {TOTAL_BUYERS - TOTAL_UNITS} waitlisted, got {waitlisted}"
    )
    assert not errors, f"FAIL: {len(errors)} request errors"

    print(f"\nPASS: exactly {TOTAL_UNITS} reserved, {waitlisted} waitlisted — no overselling")


if __name__ == "__main__":
    asyncio.run(run())
