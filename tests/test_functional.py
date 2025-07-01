# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import subprocess

from .test_base import BaseTestCase


class FunctionalTest(BaseTestCase):
    def test_snap_service_status(self):
        result = subprocess.run(
            ["snap", "services", "epa-orchestrator"], capture_output=True, text=True, check=True
        )
        self.assertIn("active", result.stdout)

    def test_allocate_cores_api(self):
        request = {
            "version": "1.0",
            "snap_name": "test-snap",
            "action": "allocate_cores",
            "cores_requested": 2,
        }
        # Use the default socket path for epa-orchestrator
        socket_path = "/var/snap/epa-orchestrator/common/epa-orchestrator.sock"
        if not os.path.exists(socket_path):
            self.skipTest(f"Socket {socket_path} does not exist")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(socket_path)
            sock.sendall((json.dumps(request) + "\n").encode())
            data = sock.recv(4096)
            response = json.loads(data.decode())
            self.assertEqual(response["cores_allocated"], 2)
            self.assertEqual(response["error"], "")
