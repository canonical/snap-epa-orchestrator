# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Success-required tests for a disposable guest with a configured ordinary pool.

Set EPA_TEST_CPU_POOL to the active canonical CPU list (at least two online CPUs
on node 0). The guest must have no isolated CPUs. These tests never reconfigure
the machine and release their own allocation on completion.
"""

import json
import os
import socket
from pathlib import Path

import pytest


def _ids(value):
    cpus = set()
    for part in value.split(","):
        bounds = part.split("-")
        cpus.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    return cpus


def _request(socket_path, action, **params):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(socket_path)
        client.sendall(
            json.dumps(
                {
                    "action": action,
                    "service_name": "test-configured-pool",
                    **params,
                }
            ).encode()
        )
        response = json.loads(b"".join(iter(lambda: client.recv(4096), b"")))
    if "error" not in response:
        assert response.get("pool") == params.get("pool", "isolated"), response
    return response


@pytest.fixture
def configured_pool(socket_path):
    """Require explicit opt-in and confirm the daemon's active configured pool."""
    value = os.environ.get("EPA_TEST_CPU_POOL")
    if not value:
        pytest.skip("EPA_TEST_CPU_POOL not set (disposable configured-pool guest only)")
    assert Path("/sys/devices/system/cpu/isolated").read_text().strip() == ""
    default = _request(socket_path, "list_allocations")
    assert "error" not in default, default
    assert "cpu-pools" in default.get("supported_cpu_features", []), default
    assert default["cpu_pool"]["source"] == "isolated"
    assert default["cpu_pool"]["eligible_cpus"] == ""
    assert default["total_available_cpus"] == 0
    info = _request(socket_path, "list_allocations", pool="general")
    assert "error" not in info, info
    assert info["cpu_pool"]["source"] == "configured"
    assert info["cpu_pool"]["configured_cpus"] == value
    assert info["cpu_pool"]["eligible_cpus"] == value
    cpus = _ids(value)
    assert len(cpus) >= 2
    try:
        yield cpus
    finally:
        result = _request(socket_path, "allocate_cores", pool="general", num_of_cores=-1)
        assert "error" not in result


@pytest.mark.parametrize(
    "action,params,field",
    [
        ("allocate_cores", {"num_of_cores": 1}, "allocated_cores"),
        ("allocate_cores_percent", {"percent": 1}, "allocated_cores"),
        ("allocate_numa_cores", {"num_of_cores": 1, "numa_node": 0}, "cores_allocated"),
    ],
)
def test_configured_pool_success(socket_path, configured_pool, action, params, field):
    """All allocation APIs must grant IDs in the configured pool, never accept errors."""
    result = _request(socket_path, action, pool="general", **params)
    assert "error" not in result, result
    selected = _ids(result[field])
    expected_count = (
        (len(configured_pool) * params["percent"] + 99) // 100
        if action == "allocate_cores_percent"
        else params["num_of_cores"]
    )
    assert len(selected) == expected_count
    assert selected <= configured_pool
    assert result["total_available_cpus"] == len(configured_pool)
    listing = _request(socket_path, "list_allocations", pool="general")
    assert "error" not in listing, listing
    assert all(entry.get("pool") == "general" for entry in listing["allocations"]), listing
    owner = next(e for e in listing["allocations"] if e["service_name"] == "test-configured-pool")
    assert _ids(owner["allocated_cores"]) == selected


def test_strict_snap_l3_placement(socket_path, configured_pool):
    """Read real kernel cache topology and place CPUs through the confined daemon."""
    online = _ids(Path("/sys/devices/system/cpu/online").read_text().strip())
    listing = _request(socket_path, "list_allocations", pool="general", include_l3_topology=True)
    assert "error" not in listing, listing
    kernel_groups = set()
    for cpu in configured_pool:
        cache = Path(f"/sys/devices/system/cpu/cpu{cpu}/cache")
        entry = next(
            (
                index
                for index in cache.glob("index*")
                if (index / "level").read_text().strip() == "3"
                and (index / "type").read_text().strip() == "Unified"
            ),
            None,
        )
        if entry is None:
            assert "l3-placement" not in listing["supported_cpu_features"], listing
            assert listing["l3_topology"] is None
            response = _request(
                socket_path,
                "allocate_cores",
                pool="general",
                num_of_cores=2,
                placement="single_l3",
            )
            assert response.get("code") == "l3_topology_unavailable", response
            return
        kernel_groups.add(frozenset(_ids((entry / "shared_cpu_list").read_text().strip())))
    expected = {
        frozenset(group & configured_pool): bool((group & online) - configured_pool)
        for group in kernel_groups
    }
    assert "l3-placement" in listing["supported_cpu_features"], listing
    observed = {
        frozenset(_ids(group["cpus"])): group["partial"] for group in listing["l3_topology"]
    }
    assert observed == expected

    response = _request(
        socket_path,
        "allocate_cores",
        pool="general",
        num_of_cores=2,
        placement="single_l3",
        preemption_policy="non-preemptive",
    )
    if max(map(len, expected)) < 2:
        assert response.get("code") == "l3_no_group_fits", response
        return
    assert response.get("placement") == "single_l3", response
    assert response["l3_groups"] == [response["allocated_cores"]]
    selected = _ids(response["allocated_cores"])
    assert len(selected) == 2
    assert any(selected <= group for group in expected)
