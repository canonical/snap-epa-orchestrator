# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for EPA Orchestrator socket API: core allocation and listing allocations."""

import json
import socket


def test_allocate_cores_via_socket_api(socket_path):
    """Test allocating cores via the socket API."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)

    request = {
        "version": "1.0",
        "snap_name": "test-snap",
        "action": "allocate_cores",
        "cores_requested": 2,
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    assert result["version"] == "1.0"
    assert result["snap_name"] == "test-snap"
    assert result["cores_requested"] == 2
    assert not result.get("error"), f"Unexpected error in response: {result.get('error')}"
    assert result["allocated_cores"] != ""
    assert result["total_available_cpus"] > 0
    assert "shared_cpus" in result
    sock.close()


def test_list_allocations_via_socket_api(socket_path):
    """Test listing allocations via the socket API."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)

    request = {
        "version": "1.0",
        "snap_name": "any-snap",
        "action": "list_allocations",
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    assert result["total_allocations"] >= 0
    assert result["total_allocated_cpus"] >= 0
    assert result["total_available_cpus"] > 0
    assert result["remaining_available_cpus"] >= 0
    assert "allocations" in result
    sock.close()
