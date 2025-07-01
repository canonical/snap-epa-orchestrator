# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional test script to allocate cores."""

import json
import os
import socket

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect(os.environ["SOCKET_PATH"])

request = {
    "version": "1.0",
    "snap_name": "test-snap",
    "action": "allocate_cores",
    "cores_requested": 2,
}

sock.sendall(json.dumps(request).encode())
response = sock.recv(4096).decode()
result = json.loads(response)

print("Response:", result)
assert result["version"] == "1.0"
assert result["snap_name"] == "test-snap"
assert result["cores_requested"] == 2
assert result["error"] == ""
assert result["allocated_cores"] != ""
assert result["total_available_cpus"] > 0
# shared_cpus can be empty if all CPUs are allocated
assert "shared_cpus" in result

sock.close()
print("Basic allocation test passed!")
