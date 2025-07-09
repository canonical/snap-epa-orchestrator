# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for EPA Orchestrator socket API: error handling when no isolated CPUs."""

import json
import socket


def test_allocate_cores_error_when_no_isolated_cpus(socket_path):
    """Test that allocate_cores returns an error when no isolated CPUs are configured."""
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
    assert result.get("error"), "Expected error response when no isolated CPUs configured"
    assert "No Isolated CPUs configured" in result["error"]

    sock.close()


def test_list_allocations_error_when_no_isolated_cpus(socket_path):
    """Test that list_allocations returns an error when no isolated CPUs are configured."""
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

    assert result["version"] == "1.0"
    assert result.get("error"), "Expected error response when no isolated CPUs configured"
    assert "No Isolated CPUs configured" in result["error"]

    sock.close()
