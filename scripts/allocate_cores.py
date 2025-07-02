# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional test script to allocate cores."""

import argparse
import json
import os
import socket


def main():
    """Allocate cores via EPA Orchestrator socket API."""
    parser = argparse.ArgumentParser(description="Allocate cores via EPA Orchestrator")
    parser.add_argument("--snap", default="test-snap", help="Snap name to allocate cores to")
    parser.add_argument("--cores", type=int, default=2, help="Number of cores to allocate")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(os.environ["SOCKET_PATH"])

    request = {
        "version": "1.0",
        "snap_name": args.snap,
        "action": "allocate_cores",
        "cores_requested": args.cores,
    }

    sock.sendall(json.dumps(request).encode())
    response = sock.recv(4096).decode()
    result = json.loads(response)

    print("Response:", result)
    assert result["version"] == "1.0"
    assert result["snap_name"] == args.snap
    assert result["cores_requested"] == args.cores
    if "error" in result:
        assert False, f"Unexpected error in response: {result['error']}"
    assert result["allocated_cores"] != ""
    assert result["total_available_cpus"] > 0
    # shared_cpus can be empty if all CPUs are allocated
    assert "shared_cpus" in result

    sock.close()
    print("Basic allocation test passed!")


if __name__ == "__main__":
    main()
