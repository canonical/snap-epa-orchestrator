# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional test script to list allocations."""

import json
import os
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect(os.environ["SOCKET_PATH"])

request = {"version": "1.0", "snap_name": "any-snap", "action": "list_allocations"}

sock.sendall(json.dumps(request).encode())
response = sock.recv(4096).decode()
result = json.loads(response)

print("Response:", result)
assert result["total_allocations"] >= 0
assert result["total_allocated_cpus"] >= 0
assert result["total_available_cpus"] > 0
assert result["remaining_available_cpus"] >= 0
assert "allocations" in result
if "error" in result:
    assert False, f"Unexpected error in response: {result['error']}"

sock.close()
print("List allocations test passed!")
