# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise integration test for socket communication with the daemon functionality."""

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

from epa_orchestrator.allocations_db import allocations_db
from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.schemas import ActionType, AllocateCoresResponse, EpaRequest


class TestSocketCommunication:
    @pytest.fixture
    def socket_path(self, tmp_path):
        """Create a temporary socket path."""
        socket_dir = tmp_path / "data"
        socket_dir.mkdir()
        return str(socket_dir / "epa.sock")

    @pytest.fixture
    def daemon_server(self, socket_path, monkeypatch):
        """Start a daemon server in a separate thread."""
        # Mock the socket path in the daemon
        monkeypatch.setenv("SNAP_DATA", str(Path(socket_path).parent.parent))

        # Create and start server
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        os.chmod(socket_path, 0o666)
        server_sock.listen(1)

        def server_handler():
            """Handle daemon requests."""
            conn, _ = server_sock.accept()
            with conn:
                data = conn.recv(1024)
                if data:
                    try:
                        request_data = json.loads(data.decode())
                        request = EpaRequest(**request_data)

                        if request.action == ActionType.ALLOCATE_CORES:
                            # Process allocation request
                            isolated = get_isolated_cpus()
                            if not isolated:
                                response = AllocateCoresResponse(
                                    snap_name=request.snap_name,
                                    cores_requested=request.cores_requested or 0,
                                    cores_allocated=0,
                                    allocated_cores="",
                                    shared_cpus="",
                                    total_available_cpus=0,
                                    remaining_available_cpus=0,
                                    error="No CPUs available",
                                )
                            else:
                                shared, dedicated = calculate_cpu_pinning(
                                    isolated, request.cores_requested or 0
                                )
                                if dedicated:
                                    allocations_db.allocate_cores(request.snap_name, dedicated)
                                    stats = allocations_db.get_system_stats(isolated)
                                    response = AllocateCoresResponse(
                                        snap_name=request.snap_name,
                                        cores_requested=request.cores_requested or 0,
                                        cores_allocated=len(
                                            allocations_db._parse_cpu_ranges(dedicated)
                                        ),
                                        allocated_cores=dedicated,
                                        shared_cpus=shared,
                                        total_available_cpus=stats["total_available_cpus"],
                                        remaining_available_cpus=stats["remaining_available_cpus"],
                                    )
                                else:
                                    response = AllocateCoresResponse(
                                        snap_name=request.snap_name,
                                        cores_requested=request.cores_requested or 0,
                                        cores_allocated=0,
                                        allocated_cores="",
                                        shared_cpus="",
                                        total_available_cpus=0,
                                        remaining_available_cpus=0,
                                        error="Failed to allocate cores",
                                    )

                            conn.sendall(response.model_dump_json().encode())
                        else:
                            # Unknown action
                            response = AllocateCoresResponse(
                                snap_name=request.snap_name,
                                cores_requested=request.cores_requested or 0,
                                cores_allocated=0,
                                allocated_cores="",
                                shared_cpus="",
                                total_available_cpus=0,
                                remaining_available_cpus=0,
                                error=f"Unknown action: {request.action}",
                            )
                            conn.sendall(response.model_dump_json().encode())
                    except Exception as e:
                        error_response = AllocateCoresResponse(
                            snap_name="",
                            cores_requested=0,
                            cores_allocated=0,
                            allocated_cores="",
                            shared_cpus="",
                            total_available_cpus=0,
                            remaining_available_cpus=0,
                            error=str(e),
                        )
                        conn.sendall(error_response.model_dump_json().encode())

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

    def test_allocate_cores_via_socket(self, daemon_server, socket_path):
        """Test allocating cores through socket communication."""
        # Prepare request
        request = EpaRequest(
            snap_name="snap1", action=ActionType.ALLOCATE_CORES, cores_requested=1
        )

        # Send request via socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(request.model_dump_json().encode())
            response_data = client.recv(4096)

        # Parse and verify response
        response = AllocateCoresResponse.model_validate_json(response_data.decode())
        assert response.snap_name == "snap1"
        assert response.cores_allocated == 1
        assert response.error == ""
        assert response.allocated_cores != ""
