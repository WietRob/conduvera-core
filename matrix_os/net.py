from __future__ import annotations
import asyncio
import ipaddress
from typing import Iterable, List, Tuple

DEFAULT_TIMEOUT = 1.0
DEFAULT_CONCURRENCY = 500

COMMON_PORTS = [21,22,23,25,53,80,110,139,143,443,445,3306,3389,5900,8080]


def parse_ports(spec: str | None) -> List[int]:
    if not spec:
        return list(range(1, 1025))
    ports: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ports.update(range(int(a), int(b) + 1))
        else:
            ports.add(int(part))
    return sorted(p for p in ports if 1 <= p <= 65535)


async def _scan_port(host: str, port: int, timeout: float) -> Tuple[int, bool]:
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        if hasattr(writer, "wait_closed"):
            await writer.wait_closed()
        return port, True
    except Exception:
        return port, False


async def scan_host(host: str, ports: Iterable[int], timeout: float = DEFAULT_TIMEOUT, concurrency: int = DEFAULT_CONCURRENCY) -> List[int]:
    sem = asyncio.Semaphore(concurrency)

    async def sem_scanner(p: int):
        async with sem:
            return await _scan_port(host, p, timeout)

    tasks = [asyncio.create_task(sem_scanner(p)) for p in ports]
    results: List[int] = []
    for task in asyncio.as_completed(tasks):
        port, is_open = await task
        if is_open:
            results.append(port)
    return sorted(results)
