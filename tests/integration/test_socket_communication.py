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

from epa_orchestrator.daemon_handler import handle_daemon_request
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresRequest,
    AllocateCoresResponse,
    ErrorResponse,
    ExplicitlyAllocateCoresRequest,
    ExplicitlyAllocateCoresResponse,
    ListAllocationsRequest,
    ListAllocationsResponse,
)


class TestSocketCommunication:
    """Integration tests for socket communication with the daemon."""

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

    def patch_isolated_cpus_valid():
        """Patch get_isolated_cpus to return a valid CPU range string for tests."""
        return patch("epa_orchestrator.daemon_handler.get_isolated_cpus", return_value="0-7")

    def patch_isolated_cpus_error():
        """Patch get_isolated_cpus to raise a RuntimeError for error scenario tests."""
        return patch(
            "epa_orchestrator.daemon_handler.get_isolated_cpus",
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
            service_name="service1", action=ActionType.ALLOCATE_CORES, cores_requested=1
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
    def test_explicitly_allocate_cores_via_socket(self, socket_daemon, socket_path):
        """Test explicit allocation of cores through socket communication."""
        request = ExplicitlyAllocateCoresRequest(
            service_name="service1",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="0-2",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(
            ExplicitlyAllocateCoresResponse, json.loads(response_data.decode())
        )
        assert response.service_name == "service1"
        assert response.cores_allocated == "0-2"
        assert response.total_available_cpus == 8

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_explicit_allocation_conflict_resolution(self, socket_daemon, socket_path):
        """Test conflict resolution when multiple services request overlapping cores explicitly."""
        request1 = ExplicitlyAllocateCoresRequest(
            service_name="service1",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="0-2",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client1:
            client1.connect(socket_path)
            client1.sendall(request1.json().encode())
            response1_data = client1.recv(4096)

        response1 = parse_obj_as(
            ExplicitlyAllocateCoresResponse, json.loads(response1_data.decode())
        )
        assert response1.service_name == "service1"
        assert response1.cores_allocated == "0-2"

        request2 = ExplicitlyAllocateCoresRequest(
            service_name="service2",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="1-2",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client2:
            client2.connect(socket_path)
            client2.sendall(request2.json().encode())
            response2_data = client2.recv(4096)

        err2 = parse_obj_as(ErrorResponse, json.loads(response2_data.decode()))
        assert "Failed to allocate requested explicit cores" in err2.error

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_explicit_allocation_force_reallocation(self, socket_daemon, socket_path):
        """Test that explicit allocation can force reallocate regular allocations."""
        request1 = AllocateCoresRequest(
            service_name="service1", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client1:
            client1.connect(socket_path)
            client1.sendall(request1.json().encode())
            response1_data = client1.recv(4096)

        response1 = parse_obj_as(AllocateCoresResponse, json.loads(response1_data.decode()))
        assert response1.cores_allocated == 2

        request2 = ExplicitlyAllocateCoresRequest(
            service_name="service2",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="1-3",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client2:
            client2.connect(socket_path)
            client2.sendall(request2.json().encode())
            response2_data = client2.recv(4096)

        response2 = parse_obj_as(
            ExplicitlyAllocateCoresResponse, json.loads(response2_data.decode())
        )
        assert response2.service_name == "service2"
        assert response2.cores_allocated == "1-3"

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_explicit_allocation_invalid_cpus(self, socket_daemon, socket_path):
        """Test error response when requesting invalid CPU cores."""
        request = ExplicitlyAllocateCoresRequest(
            service_name="service1",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="0-2,8-9",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(ErrorResponse, json.loads(response_data.decode()))
        assert "Requested cores {8, 9} are not available" in response.error

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

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.json().encode())
            response_data = client.recv(4096)

        response = parse_obj_as(ListAllocationsResponse, json.loads(response_data.decode()))
        assert response.total_allocations >= 0
        assert response.total_allocated_cpus >= 0
        assert response.total_available_cpus > 0
        assert response.remaining_available_cpus >= 0
        assert isinstance(response.allocations, list)

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_valid],
        indirect=True,
    )
    def test_multiple_allocations(self, socket_daemon, socket_path):
        """Test multiple allocations and their tracking."""
        req1 = AllocateCoresRequest(
            service_name="service1", action=ActionType.ALLOCATE_CORES, cores_requested=4
        )
        req2 = AllocateCoresRequest(
            service_name="service2", action=ActionType.ALLOCATE_CORES, cores_requested=4
        )
        req3 = AllocateCoresRequest(
            service_name="service3", action=ActionType.ALLOCATE_CORES, cores_requested=1000
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client1:
            client1.connect(socket_path)
            client1.sendall(req1.json().encode())
            resp1_data = client1.recv(4096)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client2:
            client2.connect(socket_path)
            client2.sendall(req2.json().encode())
            resp2_data = client2.recv(4096)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client3:
            client3.connect(socket_path)
            client3.sendall(req3.json().encode())
            resp3_data = client3.recv(4096)

        # Verify first two succeeded
        resp1 = parse_obj_as(AllocateCoresResponse, json.loads(resp1_data.decode()))
        resp2 = parse_obj_as(AllocateCoresResponse, json.loads(resp2_data.decode()))
        assert resp1.cores_allocated == 4
        assert resp2.cores_allocated == 4

        # Verify third failed
        resp3 = parse_obj_as(ErrorResponse, json.loads(resp3_data.decode()))
        assert "Insufficient CPUs available" in resp3.error

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_error],
        indirect=True,
    )
    def test_no_isolated_cpus_configured(self, socket_daemon, socket_path):
        """Test error response when no isolated CPUs are configured."""
        req = AllocateCoresRequest(
            service_name="service1", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(req.json().encode())
            resp_data = client.recv(4096)

        resp = parse_obj_as(ErrorResponse, json.loads(resp_data.decode()))
        assert resp.error == "No Isolated CPUs configured"

    @pytest.mark.parametrize(
        "socket_daemon",
        [patch_isolated_cpus_error],
        indirect=True,
    )
    def test_explicit_allocation_no_isolated_cpus(self, socket_daemon, socket_path):
        """Test error response when no isolated CPUs are configured for explicit allocation."""
        req = ExplicitlyAllocateCoresRequest(
            service_name="service1",
            action=ActionType.EXPLICITLY_ALLOCATE_CORES,
            cores_requested="0-2",
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(req.json().encode())
            resp_data = client.recv(4096)

        resp = parse_obj_as(ErrorResponse, json.loads(resp_data.decode()))
        assert resp.error == "No Isolated CPUs configured"
