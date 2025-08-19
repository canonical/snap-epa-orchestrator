# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for EPA Orchestrator socket API: testing with real daemon.

This suite exercises live socket interactions. Some assertions tolerate older
installed daemons that may not yet recognize newer actions (like explicit
allocation), to keep tests robust across environments.
"""

import json
import socket


def _is_unknown_action_error(err: str) -> bool:
    """Return True if error indicates daemon doesn't recognize the explicit action schema."""
    markers = [
        "union_tag_invalid",
        "tagged-union",
        "does not match any of the expected tags",
    ]
    return any(marker in err for marker in markers)


def test_allocate_cores_via_socket_api(socket_path):
    """Test that allocate_cores works with real daemon."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)

    request = {
        "version": "1.0",
        "service_name": "test-service",
        "action": "allocate_cores",
        "cores_requested": 2,
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    if "error" in result:
        # Acceptable if no isolated CPUs are configured
        assert "No Isolated CPUs configured" in result["error"]
    else:
        assert result["version"] == "1.0"
        assert result["service_name"] == "test-service"
        assert result["cores_requested"] == 2

        # Check for successful allocation (no error)
        assert not result.get("error"), f"Unexpected error in response: {result.get('error')}"

        # Check that cores were actually allocated
        assert result["cores_allocated"] == 2
        assert result["allocated_cores"] != ""
        assert result["total_available_cpus"] > 0
        assert "shared_cpus" in result

    sock.close()


def test_explicitly_allocate_cores_via_socket_api(socket_path):
    """Test that explicitly_allocate_cores works with real daemon."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)

    request = {
        "version": "1.0",
        "service_name": "test-explicit-service",
        "action": "explicitly_allocate_cores",
        "cores_requested": "0-2",
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    if "error" in result:
        assert "No Isolated CPUs configured" in result["error"] or _is_unknown_action_error(
            result["error"]
        )
    else:
        assert result["version"] == "1.0"
        assert result["service_name"] == "test-explicit-service"
        assert result["cores_requested"] == "0-2"

        assert not result.get("error"), f"Unexpected error in response: {result.get('error')}"

        assert result["cores_allocated"] == "0-2"
        assert result["cores_rejected"] == ""
        assert result["total_available_cpus"] > 0

    sock.close()


def test_explicit_allocation_conflict_resolution(socket_path):
    """Test conflict resolution when multiple services request overlapping cores explicitly."""
    sock1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock1.connect(socket_path)

    request1 = {
        "version": "1.0",
        "service_name": "conflict-service-1",
        "action": "explicitly_allocate_cores",
        "cores_requested": "0-2",
    }

    sock1.sendall(json.dumps(request1).encode())
    response1 = sock1.recv(4096).decode()
    result1 = json.loads(response1)
    sock1.close()

    if "error" in result1:
        if "No Isolated CPUs configured" in result1["error"] or _is_unknown_action_error(
            result1["error"]
        ):
            return
        else:
            assert False, f"Unexpected error in response: {result1.get('error')}"

    sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock2.connect(socket_path)

    request2 = {
        "version": "1.0",
        "service_name": "conflict-service-2",
        "action": "explicitly_allocate_cores",
        "cores_requested": "1-4",
    }

    sock2.sendall(json.dumps(request2).encode())
    response2 = sock2.recv(4096).decode()
    result2 = json.loads(response2)
    sock2.close()

    if "error" in result2:
        if "No Isolated CPUs configured" in result2["error"] or _is_unknown_action_error(
            result2["error"]
        ):
            return
        else:
            assert False, f"Unexpected error in response: {result2.get('error')}"

    assert result2["version"] == "1.0"
    assert result2["service_name"] == "conflict-service-2"

    assert result2["cores_allocated"] in ["3-4", "3", "4"]
    assert result2["cores_rejected"] in ["1-2", "1", "2"]


def test_explicit_allocation_force_reallocation(socket_path):
    """Test that explicit allocation can force reallocate regular allocations."""
    sock1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock1.connect(socket_path)

    request1 = {
        "version": "1.0",
        "service_name": "force-realloc-service-1",
        "action": "allocate_cores",
        "cores_requested": 2,
    }

    sock1.sendall(json.dumps(request1).encode())
    response1 = sock1.recv(4096).decode()
    result1 = json.loads(response1)
    sock1.close()

    if "error" in result1:
        if "No Isolated CPUs configured" in result1["error"]:
            return
        else:
            assert False, f"Unexpected error in response: {result1.get('error')}"

    sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock2.connect(socket_path)

    request2 = {
        "version": "1.0",
        "service_name": "force-realloc-service-2",
        "action": "explicitly_allocate_cores",
        "cores_requested": "1-3",
    }

    sock2.sendall(json.dumps(request2).encode())
    response2 = sock2.recv(4096).decode()
    result2 = json.loads(response2)
    sock2.close()

    if "error" in result2:
        if "No Isolated CPUs configured" in result2["error"] or _is_unknown_action_error(
            result2["error"]
        ):
            return
        else:
            assert False, f"Unexpected error in response: {result2.get('error')}"

    assert result2["version"] == "1.0"
    assert result2["service_name"] == "force-realloc-service-2"
    assert result2["cores_allocated"] == "1-3"
    assert result2["cores_rejected"] == ""


def test_list_allocations_via_socket_api(socket_path):
    """Test that list_allocations works with real daemon."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)

    request = {
        "version": "1.0",
        "service_name": "any-service",
        "action": "list_allocations",
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    assert result["version"] == "1.0"

    # Check for successful response (no error)
    assert not result.get("error"), f"Unexpected error in response: {result.get('error')}"

    # Accept both cases: no isolated CPUs (0) or isolated CPUs (>0)
    assert result["total_available_cpus"] >= 0
    assert result["total_allocations"] >= 0
    assert result["total_allocated_cpus"] >= 0
    assert result["remaining_available_cpus"] >= 0
    assert "allocations" in result
    assert isinstance(result["allocations"], list)

    for allocation in result["allocations"]:
        assert "is_explicit" in allocation
        assert isinstance(allocation["is_explicit"], bool)

    sock.close()
