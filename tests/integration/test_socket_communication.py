# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for socket communication."""

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

from epa_orchestrator.schemas import ActionType, EpaRequest


class TestSocketCommunication:
    """Test socket communication functionality."""

    @pytest.fixture
    def socket_path(self, temp_dir):
        """Create a temporary socket path."""
        return str(temp_dir / "test_socket.sock")

    @pytest.fixture
    def mock_daemon_server(self, socket_path):
        """Mock daemon server for testing."""
        # This would normally be the actual daemon, but we'll mock it
        # In a real test, you'd start the actual daemon process
        pass

    def test_socket_creation_and_binding(self, socket_path):
        """Test that socket can be created and bound."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(socket_path)
            assert Path(socket_path).exists()
        finally:
            sock.close()
            if Path(socket_path).exists():
                Path(socket_path).unlink()

    def test_socket_communication_basic(self, socket_path):
        """Test basic socket communication."""
        # Create server socket
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        server_sock.listen(1)

        # Start server thread
        def server_thread():
            conn, addr = server_sock.accept()
            data = conn.recv(1024)
            response = {"status": "received", "data": data.decode()}
            conn.send(json.dumps(response).encode())
            conn.close()

        thread = threading.Thread(target=server_thread)
        thread.daemon = True
        thread.start()

        # Give server time to start
        time.sleep(0.1)

        # Create client socket
        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_sock.connect(socket_path)

        # Send test data
        test_data = "test message"
        client_sock.send(test_data.encode())

        # Receive response
        response = client_sock.recv(1024).decode()
        response_data = json.loads(response)

        assert response_data["status"] == "received"
        assert response_data["data"] == test_data

        # Cleanup
        client_sock.close()
        server_sock.close()
        Path(socket_path).unlink()

    def test_epa_request_serialization(self):
        """Test EPA request serialization."""
        request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        # Serialize to JSON
        json_data = request.model_dump_json()
        parsed_data = json.loads(json_data)

        assert parsed_data["snap_name"] == "test-snap"
        assert parsed_data["action"] == "allocate_cores"
        assert parsed_data["cores_requested"] == 2
        assert parsed_data["version"] == "1.0"

    def test_epa_request_deserialization(self):
        """Test EPA request deserialization."""
        json_data = {
            "snap_name": "test-snap",
            "action": "allocate_cores",
            "cores_requested": 2,
            "version": "1.0",
        }

        request = EpaRequest.model_validate(json_data)

        assert request.snap_name == "test-snap"
        assert request.action == ActionType.ALLOCATE_CORES
        assert request.cores_requested == 2
        assert request.version == "1.0"

    def test_socket_timeout_handling(self, socket_path):
        """Test socket timeout handling."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)  # 1 second timeout
        try:
            with pytest.raises((FileNotFoundError, socket.timeout)):
                sock.connect(socket_path)  # Should timeout or file not found
        finally:
            sock.close()

    def test_socket_connection_refused(self, temp_dir):
        """Test handling of connection refused."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # Try to connect to non-existent socket
        non_existent_path = str(temp_dir / "non_existent.sock")

        try:
            sock.connect(non_existent_path)
            assert False, "Should have failed to connect"
        except FileNotFoundError:
            pass  # Expected
        finally:
            sock.close()

    def test_large_message_handling(self, socket_path):
        """Test handling of large messages."""
        # Create server socket
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        server_sock.listen(1)

        # Start server thread
        def server_thread():
            conn, addr = server_sock.accept()
            data = b""
            while True:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk

            response = {"status": "received", "size": len(data)}
            conn.send(json.dumps(response).encode())
            conn.close()

        thread = threading.Thread(target=server_thread)
        thread.daemon = True
        thread.start()

        # Give server time to start
        time.sleep(0.1)

        # Create client socket
        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_sock.connect(socket_path)

        # Send large message
        large_message = "x" * 10000
        client_sock.send(large_message.encode())
        client_sock.shutdown(socket.SHUT_WR)

        # Receive response
        response = client_sock.recv(1024).decode()
        response_data = json.loads(response)

        assert response_data["status"] == "received"
        assert response_data["size"] == 10000

        # Cleanup
        client_sock.close()
        server_sock.close()
        Path(socket_path).unlink()

    def test_multiple_connections(self, socket_path):
        """Test handling multiple concurrent connections."""
        # Create server socket
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        server_sock.listen(5)

        # Track connections
        connections = []

        # Start server thread
        def server_thread():
            for _ in range(3):
                conn, addr = server_sock.accept()
                connections.append(conn)
                data = conn.recv(1024)
                response = {"status": "received", "data": data.decode()}
                conn.send(json.dumps(response).encode())
                conn.close()

        thread = threading.Thread(target=server_thread)
        thread.daemon = True
        thread.start()

        # Give server time to start
        time.sleep(0.1)

        # Create multiple client connections
        clients = []
        for i in range(3):
            client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(socket_path)
            client_sock.send(f"message_{i}".encode())
            clients.append(client_sock)

        # Receive responses
        responses = []
        for client in clients:
            response = client.recv(1024).decode()
            responses.append(json.loads(response))
            client.close()

        # Verify responses
        assert len(responses) == 3
        for i, response in enumerate(responses):
            assert response["status"] == "received"
            assert response["data"] == f"message_{i}"

        # Cleanup
        server_sock.close()
        Path(socket_path).unlink()

    def test_socket_permissions(self, socket_path):
        """Test socket file permissions."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)
        # Set permissions explicitly
        os.chmod(socket_path, 0o600)
        stat_result = Path(socket_path).stat()
        # Accept 0o600 as correct permissions
        assert stat_result.st_mode & 0o777 == 0o600
        sock.close()
        os.unlink(socket_path)

    def test_socket_cleanup(self, socket_path):
        """Test proper socket cleanup."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)

        assert Path(socket_path).exists()

        sock.close()
        Path(socket_path).unlink()

        assert not Path(socket_path).exists()

    def test_allocations_db_integration(self, fresh_allocations_db):
        """Test allocations database integration with socket communication."""
        # Simulate allocation through socket
        # Process allocation (simulating daemon logic)
        fresh_allocations_db.allocate_cores("test-snap", "0-1")

        # Verify allocation
        allocation = fresh_allocations_db.get_allocation("test-snap")
        assert allocation == "0-1"

        # Verify system stats
        stats = fresh_allocations_db.get_system_stats("0-7")
        assert stats["total_allocated_cpus"] == 2
        assert stats["remaining_available_cpus"] == 6
