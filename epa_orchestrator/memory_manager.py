# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Memory management utilities for EPA Orchestrator."""

import logging
import os
import re
from typing import Dict, List, Optional, TypedDict

from epa_orchestrator.hugepages_db import list_allocations_for_node

NODES_BASE_PATH = "/sys/devices/system/node"
_HUGEPAGES_DIR_RE = re.compile(r"^hugepages-(\d+)kB$")


class HugepageStats(TypedDict):
    """Per-size hugepage stats structure."""

    total: int
    free: int
    used: int
    surplus: int


def _list_node_dirs() -> List[str]:
    """List available NUMA node directories."""
    if not os.path.exists(NODES_BASE_PATH):
        return []
    try:
        return [d for d in os.listdir(NODES_BASE_PATH) if d.startswith("node") and d[4:].isdigit()]
    except Exception:
        return []


def _read_hugepage_count(file_path: str) -> int:
    """Read hugepage count from a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _process_hugepage_entry(entry_path: str) -> Optional[HugepageStats]:
    """Process a single hugepage entry and return stats."""
    if not os.path.exists(entry_path):
        return None

    nr_path = os.path.join(entry_path, "nr_hugepages")
    free_path = os.path.join(entry_path, "free_hugepages")
    surplus_path = os.path.join(entry_path, "surplus_hugepages")

    if not os.path.exists(nr_path):
        return None

    total = _read_hugepage_count(nr_path)
    free = _read_hugepage_count(free_path) if os.path.exists(free_path) else 0
    surplus = _read_hugepage_count(surplus_path) if os.path.exists(surplus_path) else 0
    used = max(total - free, 0)

    return HugepageStats(total=total, free=free, used=used, surplus=surplus)


def _get_node_hugepage_sizes(hugepages_dir: str) -> Dict[str, HugepageStats]:
    """Get hugepage sizes information for a specific node."""
    sizes: Dict[str, HugepageStats] = {}
    try:
        for entry in os.listdir(hugepages_dir):
            match = _HUGEPAGES_DIR_RE.match(entry)
            if not match:
                continue
            size_key = match.group(1)

            entry_path = os.path.join(hugepages_dir, entry)
            result = _process_hugepage_entry(entry_path)
            if result:
                sizes[size_key] = result
    except Exception as e:
        logging.error(
            f"Unexpected error while reading hugepages directory {hugepages_dir}: {e}",
            exc_info=True,
        )
    return sizes


def _get_node_allocations(node_id: int) -> Dict[str, Dict[str, int]]:
    """Get allocations for a specific node."""
    allocations_list = list_allocations_for_node(node_id)
    allocations: Dict[str, Dict[str, int]] = {}
    for item in allocations_list:
        service = str(item.get("service_name", ""))
        size_key = str(item.get("size_kb", 0))
        count = int(item.get("count", 0))
        if service not in allocations:
            allocations[service] = {}
        allocations[service][size_key] = allocations[service].get(size_key, 0) + count
    return allocations


def get_numa_hugepages_info() -> Dict[str, Dict[str, object]]:
    """Get hugepage information per NUMA node from sysfs in refactored format.

    Returns a dict keyed by node name (e.g., "node0") with:
    - usage: list of {total, free, size}
    - allocations: per-service allocations per size
    """
    nodes: Dict[str, Dict[str, object]] = {}
    node_dirs = _list_node_dirs()

    for node_dir in sorted(node_dirs, key=lambda n: int(n[4:])):
        node_id = int(node_dir[4:])
        node_key = f"node{node_id}"
        hugepages_dir = os.path.join(NODES_BASE_PATH, node_dir, "hugepages")

        if not os.path.exists(hugepages_dir):
            nodes[node_key] = {"capacity": [], "allocations": {}}
            continue

        sizes = _get_node_hugepage_sizes(hugepages_dir)
        allocations = _get_node_allocations(node_id)

        tracked_per_size: Dict[str, int] = {}
        for service_alloc in allocations.values():
            for size_key, count in service_alloc.items():
                tracked_per_size[size_key] = tracked_per_size.get(size_key, 0) + int(count)

        for size_key, stats in sizes.items():
            tracked = tracked_per_size.get(size_key, 0)
            if tracked <= 0:
                continue
            total = int(stats.get("total", 0))
            free_raw = int(stats.get("free", 0))
            used_raw = int(stats.get("used", 0))
            to_overlay = max(tracked - used_raw, 0)
            free_adj = max(free_raw - to_overlay, 0)
            used_adj = min(used_raw + (free_raw - free_adj), total)
            stats["free"] = free_adj
            stats["used"] = used_adj

        capacity = []
        for size_key, stats in sizes.items():
            capacity.append(
                {
                    "total": int(stats.get("total", 0)),
                    "free": int(stats.get("free", 0)),
                    "size": int(size_key),
                }
            )

        nodes[node_key] = {"capacity": capacity, "allocations": allocations}

    return nodes


def get_memory_summary() -> Dict[str, object]:
    """Get NUMA hugepage summary only (no /proc/meminfo global stats)."""
    try:
        numa_hugepages = get_numa_hugepages_info()
        return {
            "numa_hugepages": numa_hugepages if numa_hugepages else {},
        }
    except Exception as e:
        logging.error(f"Failed to get memory summary: {e}")
        return {
            "numa_hugepages": {},
            "error": str(e),
        }
