# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise integration test for socket communication with the daemon functionality."""

import os
import socket
import threading
import time
from pathlib import Path

import pytest

from epa_orchestrator.daemon_handler import handle_daemon_request
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
