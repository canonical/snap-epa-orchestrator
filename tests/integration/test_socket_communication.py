# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise integration test for socket communication with the daemon functionality."""

import json
import os
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import parse_obj_as

from epa_orchestrator.allocations_db import allocations_db
from epa_orchestrator.cpu_pool import CpuPools
from epa_orchestrator.daemon_handler import handle_daemon_request
from epa_orchestrator.l3_topology import L3Topology
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresPercentRequest,
    AllocateCoresPercentResponse,
    AllocateCoresRequest,
    AllocateCoresResponse,
    CpuPoolName,
    ErrorResponse,
    ListAllocationsRequest,
    ListAllocationsResponse,
)
from epa_orchestrator.utils import to_ranges


def _exchange(socket_path, request):
    """Read a complete response using the daemon's one-request connection."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(socket_path)
        client.sendall(json.dumps(request).encode())
        with client.makefile("rb") as response:
            return response.read()


class TestSocketCommunication:
    """Integration tests for socket communication with the daemon."""

    @pytest.fixture(autouse=True)
    def clear_allocations_db(self):
        """Clear allocations DB before each test."""
        allocations_db.clear_all_allocations()
        yield

    @pytest.fixture
    def socket_path(self, tmp_path):
        """Create a temporary socket path."""
        socket_dir = tmp_path / "data"
        socket_dir.mkdir()
        return str(socket_dir / "epa.sock")

    @pytest.fixture
    def socket_daemon(self, socket_path, monkeypatch, request):
        """Start a socket-based daemon server in a separate thread, with optional patching."""
        # Patch get_isolated_cpus if provided
        patcher = getattr(request, "param", None)
        if patcher is not None:
            patch_ctx = patcher()
            patch_ctx.__enter__()
        else:
            patch_ctx = None

        # Mock the socket path in the daemon
        monkeypatch.setenv("SNAP_DATA", str(Path(socket_path).parent.parent))

        # Create and start server
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        os.chmod(socket_path, 0o666)
        server_sock.listen(5)

        def server_handler():
            """Handle daemon requests (accept multiple connections)."""
            for _ in range(10):
                try:
                    conn, _ = server_sock.accept()
                except OSError:
                    break  # Socket closed
                with conn:
                    data = conn.recv(1024)
                    if data:
                        response_bytes = handle_daemon_request(data)
                        conn.sendall(response_bytes)

        # Start server thread
        server_thread = threading.Thread(target=server_handler, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(0.1)

        yield server_sock

        # Cleanup
        server_sock.close()
        if Path(socket_path).exists():
            Path(socket_path).unlink()
        if patch_ctx is not None:
            patch_ctx.__exit__(None, None, None)

    def test_explicit_pool_all_apis_via_socket(
        self, socket_daemon, socket_path, mock_cpu_files_empty
    ):
        """Count, percentage and NUMA succeed without isolation and persist real IDs."""
        provider = CpuPools("2-5")
        with (
            patch("epa_orchestrator.daemon_handler.get_cpu_pool_provider", return_value=provider),
            patch(
                "epa_orchestrator.daemon_handler.get_numa_node_cpus",
                return_value={0: set(range(8))},
            ),
            patch("epa_orchestrator.utils.get_numa_node_cpus", return_value={0: set(range(8))}),
        ):
            for action, params, field in (
                ("allocate_cores", {"num_of_cores": 2}, "allocated_cores"),
                ("allocate_cores_percent", {"percent": 50}, "allocated_cores"),
                ("allocate_numa_cores", {"num_of_cores": 2, "numa_node": 0}, "cores_allocated"),
            ):
                payload = {
                    "action": action,
                    "service_name": "configured",
                    "pool": "general",
                    **params,
                }
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(socket_path)
                    client.sendall(json.dumps(payload).encode())
                    response = json.loads(client.recv(4096))
                assert response[field] == "2-3"
                assert response["total_available_cpus"] == 4
                assert response["remaining_available_cpus"] == 2
            assert allocations_db.get_allocation("configured") == "2-3"

    def patch_isolated_cpus_valid():
        """Patch get_isolated_cpus to return a valid CPU range string for tests."""
        return patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-7")

    def patch_isolated_cpus_error():
        """Patch get_isolated_cpus to raise a RuntimeError for error scenario tests."""
        return patch(
            "epa_orchestrator.cpu_pinning.get_isolated_cpus",
            side_effect=RuntimeError("No Isolated CPUs configured"),
        )

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_allocate_cores_via_socket(self, socket_daemon, socket_path):
        """Test allocating cores through socket communication."""
        request = AllocateCoresRequest(
            service_name="service1", action=ActionType.ALLOCATE_CORES, num_of_cores=1
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(AllocateCoresResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated == 1

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_allocate_cores_percent_via_socket(self, socket_daemon, socket_path):
        """Test allocating cores by percentage through socket communication."""
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=25,
        )
        # 25% of 8 cores (0-7) = 2 cores
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 2
        assert response.allocated_cores == "0-1"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 6

        # Verify idempotency by allocating again 90% of 8 cores (0-7) = 7.2, ceil -> 8
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=90,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 8
        assert response.allocated_cores == "0-7"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 0

        # Allocate 40% of 8 cores (0-7) = 3.2, ceil -> 4
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=40,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 4
        assert response.allocated_cores == "0-3"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 4

        # Allocate 100% of 8 cores (0-7) = 8 cores
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=100,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 8
        assert response.allocated_cores == "0-7"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 0

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_allocate_cores_percent_multiple_services(self, socket_daemon, socket_path):
        """Test allocating cores by percentage through socket communication."""
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=25,
        )
        # 25% of 8 cores (0-7) = 2 cores
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 2
        assert response.allocated_cores == "0-1"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 6

        # Verify remaining cores are allocated to service2
        request = AllocateCoresPercentRequest(
            service_name="service2",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=75,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service2"
        assert response.cores_allocated_count == 6
        assert response.allocated_cores == "2-7"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 0

        # Verify no cores are available for service3
        request = AllocateCoresPercentRequest(
            service_name="service3",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=40,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(ErrorResponse, json.loads(response_data.decode()))
        assert response.error == "Insufficient CPUs available. Requested: 4, Available: 0"

        # Deallocate service1
        request = AllocateCoresPercentRequest(
            service_name="service1",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=-1,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service1"
        assert response.cores_allocated_count == 0
        assert response.allocated_cores == ""
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 2

        # Verify service3 can allocate now
        request = AllocateCoresPercentRequest(
            service_name="service3",
            action=ActionType.ALLOCATE_CORES_PERCENT,
            percent=25,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)
        response = parse_obj_as(AllocateCoresPercentResponse, json.loads(response_data.decode()))
        assert response.service_name == "service3"
        assert response.cores_allocated_count == 2
        assert response.allocated_cores == "0-1"
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 0

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_list_allocations_via_socket(self, socket_daemon, socket_path):
        """Test listing allocations through socket communication."""
        request = ListAllocationsRequest(
            service_name="any-service", action=ActionType.LIST_ALLOCATIONS
        )

        response = ListAllocationsResponse.model_validate_json(
            _exchange(socket_path, request.model_dump(mode="json"))
        )
        assert response.total_allocations >= 0
        assert response.total_allocated_cpus >= 0
        assert response.total_available_cpus > 0
        assert response.remaining_available_cpus >= 0
        assert isinstance(response.allocations, list)

    def test_two_cpu_strict_placement_stays_in_one_cache(
        self, socket_daemon, socket_path, monkeypatch, mock_cpu_files_empty
    ):
        """Use a layout where ordinary selection crosses an L3 boundary."""
        pools = CpuPools("0-3")
        topology = L3Topology((frozenset({0, 2}), frozenset({1, 3})), frozenset(range(4)))
        monkeypatch.setattr(pools.general, "get_l3_topology", lambda snapshot: topology)
        monkeypatch.setattr("epa_orchestrator.daemon_handler.get_cpu_pool_provider", lambda: pools)
        monkeypatch.setattr(
            "epa_orchestrator.allocations_db.get_thread_siblings_map",
            lambda cpus: {cpu: {cpu} for cpu in cpus},
        )
        request = {
            "action": "allocate_cores",
            "service_name": "placement",
            "pool": "general",
            "num_of_cores": 2,
        }
        ordinary = json.loads(_exchange(socket_path, request))
        assert ordinary["l3_groups"] == ["0", "1"]
        released = json.loads(_exchange(socket_path, {**request, "num_of_cores": -1}))
        assert "error" not in released, released
        placed = json.loads(_exchange(socket_path, {**request, "placement": "single_l3"}))
        assert placed["placement"] == "single_l3"
        assert placed["allocated_cores"] == "0,2"
        assert placed["l3_groups"] == ["0,2"]

    def test_large_l3_listing_is_opt_in(
        self, socket_daemon, socket_path, monkeypatch, mock_cpu_files_empty
    ):
        """Keep legacy listings compact and read larger topology replies through EOF."""
        pools = CpuPools("0-511")
        groups = tuple(
            frozenset(range(start, start + 8)) | frozenset(range(start + 256, start + 264))
            for start in range(0, 256, 8)
        )
        topology = L3Topology(groups, frozenset(range(512)))
        monkeypatch.setattr(pools.general, "get_l3_topology", lambda snapshot: topology)
        monkeypatch.setattr("epa_orchestrator.daemon_handler.get_cpu_pool_provider", lambda: pools)
        mock_cpu_files_empty["online"].write_text("0-511")
        mock_cpu_files_empty["present"].write_text("0-511")
        for index in range(16):
            owned = groups[index * 2] | groups[index * 2 + 1]
            allocations_db.allocate_cores(
                f"ceph-osd.{index}", to_ranges(sorted(owned)), pool=CpuPoolName.GENERAL
            )

        request = {"action": "list_allocations", "pool": "general"}
        default = _exchange(socket_path, request)
        detailed = _exchange(socket_path, {**request, "include_l3_topology": True})
        assert len(default) < 4096 < len(detailed)
        listing = json.loads(default)
        assert "l3_topology" not in listing
        assert len(listing["allocations"]) == 16
        assert all("l3_groups" not in claim for claim in listing["allocations"])
        topology_listing = json.loads(detailed)
        assert len(topology_listing["l3_topology"]) == 32
        assert len(topology_listing["allocations"]) == 16
        assert all(len(claim["l3_groups"]) == 2 for claim in topology_listing["allocations"])

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_error],
        indirect=True,
    )
    def test_no_isolated_cpus_configured(self, socket_daemon, socket_path):
        """Test error response when no isolated CPUs are configured."""
        req = AllocateCoresRequest(
            service_name="service1", action=ActionType.ALLOCATE_CORES, num_of_cores=2
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(req.json().encode())
            resp_data = client.recv(4096)

        resp = parse_obj_as(ErrorResponse, json.loads(resp_data.decode()))
        assert resp.error == "No Isolated CPUs configured"

    @pytest.mark.parametrize("configured_mode", [False, True])
    def test_nonpreemptive_round_trip(
        self, socket_daemon, socket_path, monkeypatch, mock_cpu_files_empty, configured_mode
    ):
        """The socket protocol protects claims with either isolated or ordinary CPUs."""
        if configured_mode:
            provider = CpuPools("0-3")
            monkeypatch.setattr(
                "epa_orchestrator.daemon_handler.get_cpu_pool_provider", lambda: provider
            )
        else:
            monkeypatch.setattr("epa_orchestrator.cpu_pinning.get_isolated_cpus", lambda: "0-3")
        monkeypatch.setattr("epa_orchestrator.utils.get_numa_node_cpus", lambda: {0: {0, 1, 2, 3}})
        monkeypatch.setattr(
            "epa_orchestrator.daemon_handler.get_numa_node_cpus", lambda: {0: {0, 1, 2, 3}}
        )

        def request(action, service="a", **fields):
            payload = {
                "version": "1.0",
                "action": action,
                "service_name": service,
                "pool": "general" if configured_mode else "isolated",
                **fields,
            }
            return json.loads(_exchange(socket_path, payload))

        assert (
            "non-preemptive-allocations" in request("list_allocations")["supported_cpu_features"]
        )
        result = request("allocate_cores_percent", percent=100, preemption_policy="non-preemptive")
        assert result["preemption_policy"] == "non-preemptive"
        assert result["allocated_cores"] == "0-3"
        before = request("list_allocations")
        assert before["cpu_pool"]["source"] == ("configured" if configured_mode else "isolated")
        assert "error" in request("allocate_numa_cores", "b", numa_node=0, num_of_cores=4)
        assert request("list_allocations") == before
        assert request("allocate_cores", num_of_cores=-1)["preemption_policy"] is None
        assert (
            request("allocate_numa_cores", "b", numa_node=0, num_of_cores=4)["preemption_policy"]
            == "legacy"
        )
