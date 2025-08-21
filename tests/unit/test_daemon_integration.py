# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for daemon integration functionality."""

import json
from unittest.mock import patch

import pytest
from pydantic import parse_obj_as

from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.daemon_handler import (
    handle_daemon_request,
    handle_explicitly_allocate_cores,
)
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresRequest,
    AllocateCoresResponse,
    ErrorResponse,
    ExplicitlyAllocateCoresRequest,
    ExplicitlyAllocateCoresResponse,
)
from epa_orchestrator.utils import parse_cpu_ranges


class TestDaemonIntegration:
    """Unit tests for daemon integration logic."""

    def test_allocate_cores_request(self, fresh_allocations_db, mock_cpu_files):
        """Test allocation of cores via daemon request."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request = AllocateCoresRequest(
                service_name="service1", action=ActionType.ALLOCATE_CORES, cores_requested=2
            )
            isolated = get_isolated_cpus()
            shared, allocated = calculate_cpu_pinning(isolated, request.cores_requested)
            fresh_allocations_db.allocate_cores(request.service_name, allocated)
            stats = fresh_allocations_db.get_system_stats(isolated)
            response = AllocateCoresResponse(
                version="1.0",
                service_name="service1",
                cores_requested=request.cores_requested,
                cores_allocated=len(parse_cpu_ranges(allocated)),
                allocated_cores=allocated,
                shared_cpus=shared,
                total_available_cpus=stats["total_available_cpus"],
                remaining_available_cpus=stats["remaining_available_cpus"],
            )
            assert response.service_name == "service1"
            assert response.cores_allocated == 2

    def test_explicitly_allocate_cores_request(self, fresh_allocations_db, mock_cpu_files):
        """Test explicit allocation of cores via daemon request."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request = ExplicitlyAllocateCoresRequest(
                service_name="service1",
                action=ActionType.EXPLICITLY_ALLOCATE_CORES,
                cores_requested="0-2",
            )
            response = handle_explicitly_allocate_cores(request)
            assert response.service_name == "service1"
            assert response.cores_allocated == "0-2"
            assert response.total_available_cpus == 6
            assert response.remaining_available_cpus == 3

    def test_explicitly_allocate_cores_invalid_cpus(self, fresh_allocations_db, mock_cpu_files):
        """Test explicit allocation with invalid CPU cores."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request = ExplicitlyAllocateCoresRequest(
                service_name="service1",
                action=ActionType.EXPLICITLY_ALLOCATE_CORES,
                cores_requested="0-2,5,8-9",
            )
            with pytest.raises(ValueError, match="Requested cores .* are not available"):
                handle_explicitly_allocate_cores(request)

    def test_explicitly_allocate_cores_conflict(self, fresh_allocations_db, mock_cpu_files):
        """Test explicit allocation with conflicting explicit allocations."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request1 = ExplicitlyAllocateCoresRequest(
                service_name="service1",
                action=ActionType.EXPLICITLY_ALLOCATE_CORES,
                cores_requested="0-2",
            )
            response1 = handle_explicitly_allocate_cores(request1)
            assert response1.cores_allocated == "0-2"

            request2 = ExplicitlyAllocateCoresRequest(
                service_name="service2",
                action=ActionType.EXPLICITLY_ALLOCATE_CORES,
                cores_requested="1-2",
            )

            with pytest.raises(ValueError, match="Failed to allocate requested explicit cores"):
                handle_explicitly_allocate_cores(request2)

    def test_error_handling(self):
        """Test error handling in daemon integration."""
        with pytest.raises(Exception):
            AllocateCoresRequest(service_name="service1", action="bad_action", cores_requested=2)

    def test_allocate_cores_no_isolated_cpus(self):
        """Test error response when no isolated CPUs are configured in daemon handler."""
        with patch(
            "epa_orchestrator.cpu_pinning.get_isolated_cpus",
            side_effect=RuntimeError("No Isolated CPUs configured"),
        ):
            request = {
                "version": "1.0",
                "service_name": "service1",
                "action": "allocate_cores",
                "cores_requested": 2,
            }
            response_bytes = handle_daemon_request(bytes(str(request).replace("'", '"'), "utf-8"))
            resp = parse_obj_as(ErrorResponse, json.loads(response_bytes.decode()))
            assert resp.error == "No Isolated CPUs configured"

    def test_explicitly_allocate_cores_no_isolated_cpus(self):
        """Test error response when no isolated CPUs are configured for explicit allocation."""
        with patch(
            "epa_orchestrator.cpu_pinning.get_isolated_cpus",
            side_effect=RuntimeError("No Isolated CPUs configured"),
        ):
            request = {
                "version": "1.0",
                "service_name": "service1",
                "action": "explicitly_allocate_cores",
                "cores_requested": "0-2",
            }
            response_bytes = handle_daemon_request(bytes(str(request).replace("'", '"'), "utf-8"))
            resp = parse_obj_as(ErrorResponse, json.loads(response_bytes.decode()))
            assert resp.error == "No Isolated CPUs configured"

    def test_explicitly_allocate_cores_via_socket(self, fresh_allocations_db, mock_cpu_files):
        """Test explicit allocation via socket communication."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-7"):
            request = {
                "version": "1.0",
                "service_name": "service1",
                "action": "explicitly_allocate_cores",
                "cores_requested": "0-2",
            }
            response_bytes = handle_daemon_request(bytes(str(request).replace("'", '"'), "utf-8"))
            response = parse_obj_as(
                ExplicitlyAllocateCoresResponse, json.loads(response_bytes.decode())
            )
            assert response.service_name == "service1"
            assert response.cores_allocated == "0-2"
