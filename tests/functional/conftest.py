# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Functional test fixtures for EPA Orchestrator socket API tests."""

import os

import pytest


@pytest.fixture
def socket_path():
    """Get the socket path from environment or skip test."""
    path = os.environ.get("SOCKET_PATH")
    if not path:
        pytest.skip("SOCKET_PATH environment variable not set")
    return path
