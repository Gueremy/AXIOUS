"""Carga acotada de lecturas v2 contra un entorno de QA, nunca producción por defecto.

SALMO_QA_EMAIL=... SALMO_QA_PASSWORD=... python scripts/load_smoke_v2.py
Opcionales: SALMO_API_URL, SALMO_LOAD_REQUESTS, SALMO_LOAD_CONCURRENCY.
"""
import asyncio
import json
import os
import statistics
import time

import httpx


async def main():
    base_url = os.environ.get("SALMO_API_URL", "http://127.0.0.1:18000")
    requests_per_route = min(int(os.environ.get("SALMO_LOAD_REQUESTS", "100")), 1000)
    concurrency = min(int(os.environ.get("SALMO_LOAD_CONCURRENCY", "10")), 50)
    assert requests_per_route > 0 and concurrency > 0
    routes = (
        "/api/v2/dashboard/gerencia",
        "/api/v2/movimientos/solicitudes?page=1&size=20",
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=20, follow_redirects=True) as client:
        login = await client.post("/auth/login", data={
            "username": os.environ["SALMO_QA_EMAIL"],
            "password": os.environ["SALMO_QA_PASSWORD"],
        })
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        for route in routes:
            warmup = await client.get(route)
            warmup.raise_for_status()

        semaphore = asyncio.Semaphore(concurrency)

        async def sample(route):
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(route)
                    return route, response.status_code, (time.perf_counter() - started) * 1000
                except httpx.HTTPError:
                    return route, 0, (time.perf_counter() - started) * 1000

        results = await asyncio.gather(*(sample(route) for route in routes
                                         for _ in range(requests_per_route)))
    summary = {}
    for route in routes:
        values = [elapsed for path, status, elapsed in results if path == route and status == 200]
        failures = sum(path == route and status != 200 for path, status, _ in results)
        summary[route] = {
            "requests": requests_per_route,
            "failures": failures,
            "p50_ms": round(statistics.median(values), 1) if values else None,
            "p95_ms": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 1) if values else None,
        }
    print(json.dumps({"concurrency": concurrency, "routes": summary}, ensure_ascii=False))
    assert all(result["failures"] == 0 for result in summary.values())


asyncio.run(main())
