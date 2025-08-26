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
)
from epa_orchestrator.hugepages_db import list_allocations_for_node
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresRequest,
    AllocateCoresResponse,
    AllocateHugepagesResponse,
    ErrorResponse,
)
from epa_orchestrator.utils import parse_cpu_ranges


class TestDaemonIntegration:
    """Unit tests for daemon integration logic."""

    def test_allocate_cores_request(self, fresh_allocations_db, mock_cpu_files):
        """Test allocation of cores via daemon request."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request = AllocateCoresRequest(
                service_name="service1", action=ActionType.ALLOCATE_CORES, num_of_cores=2
            )
            isolated = get_isolated_cpus()
            shared, allocated = calculate_cpu_pinning(isolated, request.num_of_cores)
            fresh_allocations_db.allocate_cores(request.service_name, allocated)
            stats = fresh_allocations_db.get_system_stats(isolated)
            response = AllocateCoresResponse(
                version="1.0",
                service_name="service1",
                num_of_cores=request.num_of_cores,
                cores_allocated=len(parse_cpu_ranges(allocated)),
                allocated_cores=allocated,
                shared_cpus=shared,
                total_available_cpus=stats["total_available_cpus"],
                remaining_available_cpus=stats["remaining_available_cpus"],
            )
            assert response.service_name == "service1"
            assert response.cores_allocated == 2

    def test_error_handling(self):
        """Test error handling in daemon integration."""
        with pytest.raises(Exception):
            AllocateCoresRequest(service_name="service1", action="bad_action", num_of_cores=2)

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
                "num_of_cores": 2,
            }
            response_bytes = handle_daemon_request(bytes(str(request).replace("'", '"'), "utf-8"))
            resp = parse_obj_as(ErrorResponse, json.loads(response_bytes.decode()))
            assert resp.error == "No Isolated CPUs configured"

    @patch("epa_orchestrator.daemon_handler.get_memory_summary")
    def test_allocate_hugepages_track_positive(self, mock_summary):
        """Test hugepages recording (>0) with sufficient capacity present."""
        mock_summary.return_value = {
            "numa_hugepages": {
                "node0": {"capacity": [{"total": 10, "free": 10, "size": 2048}], "allocations": {}}
            }
        }
        request = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 3,
            "node_id": 0,
            "size_kb": 2048,
        }
        response_bytes = handle_daemon_request(json.dumps(request).encode())
        resp = parse_obj_as(AllocateHugepagesResponse, json.loads(response_bytes.decode()))
        assert resp.allocation_successful is True
        assert resp.hugepages_requested == 3
        assert resp.node_id == 0
        assert resp.size_kb == 2048

    def test_allocate_hugepages_deallocate_minus_one(self):
        """-1 should remove record and succeed with message."""
        # First add a record, then deallocate
        add_req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 2,
            "node_id": 1,
            "size_kb": 2048,
        }
        _ = handle_daemon_request(json.dumps(add_req).encode())

        del_req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": -1,
            "node_id": 1,
            "size_kb": 2048,
        }
        response_bytes = handle_daemon_request(json.dumps(del_req).encode())
        resp = parse_obj_as(AllocateHugepagesResponse, json.loads(response_bytes.decode()))
        assert resp.allocation_successful is True
        assert resp.hugepages_requested == -1
        assert resp.node_id == 1
        assert resp.size_kb == 2048
        assert "Removed" in resp.message or "No existing record" in resp.message

    def test_allocate_hugepages_zero_invalid(self):
        """0 is invalid and should return an ErrorResponse."""
        bad_req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 0,
            "node_id": 0,
            "size_kb": 2048,
        }
        response_bytes = handle_daemon_request(json.dumps(bad_req).encode())
        resp = parse_obj_as(ErrorResponse, json.loads(response_bytes.decode()))
        assert "hugepages_requested=0 is invalid" in resp.error

    @patch("epa_orchestrator.daemon_handler.get_memory_summary")
    def test_hp_capacity_node_missing(self, mock_summary):
        """Error when NUMA node is not found in memory summary."""
        mock_summary.return_value = {"numa_hugepages": {}}
        req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 2,
            "node_id": 9,
            "size_kb": 2048,
        }
        resp_b = handle_daemon_request(json.dumps(req).encode())
        resp = parse_obj_as(ErrorResponse, json.loads(resp_b.decode()))
        assert resp.error == "NUMA node 9 not found"

    @patch("epa_orchestrator.daemon_handler.get_memory_summary")
    def test_hp_capacity_size_missing(self, mock_summary):
        """Error when hugepage size is not available on the node."""
        mock_summary.return_value = {
            "numa_hugepages": {
                "node0": {"capacity": [{"total": 10, "free": 10, "size": 4096}], "allocations": {}}
            }
        }
        req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 2,
            "node_id": 0,
            "size_kb": 2048,
        }
        resp_b = handle_daemon_request(json.dumps(req).encode())
        resp = parse_obj_as(ErrorResponse, json.loads(resp_b.decode()))
        assert resp.error == "Hugepage size 2048 KB not found on node 0"

    @patch("epa_orchestrator.daemon_handler.get_memory_summary")
    def test_hp_capacity_insufficient_free(self, mock_summary):
        """Error when free hugepages are fewer than requested."""
        mock_summary.return_value = {
            "numa_hugepages": {
                "node0": {"capacity": [{"total": 10, "free": 1, "size": 2048}], "allocations": {}}
            }
        }
        req = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 3,
            "node_id": 0,
            "size_kb": 2048,
        }
        resp_b = handle_daemon_request(json.dumps(req).encode())
        resp = parse_obj_as(ErrorResponse, json.loads(resp_b.decode()))
        assert resp.error == "NUMA node 0 size 2048 KB only has 1 free hugepages, requested 3"

    @patch("epa_orchestrator.daemon_handler.get_memory_summary")
    def test_hp_capacity_success(self, mock_summary):
        """Success when sufficient free hugepages are available on node/size."""
        mock_summary.return_value = {
            "numa_hugepages": {
                "node0": {"capacity": [{"total": 10, "free": 5, "size": 2048}], "allocations": {}}
            }
        }
        req1 = {
            "version": "1.0",
            "service_name": "svc",
            "action": "allocate_hugepages",
            "hugepages_requested": 2,
            "node_id": 0,
            "size_kb": 2048,
        }
        _ = handle_daemon_request(json.dumps(req1).encode())
        # Increase mocked free capacity for the second request so it passes capacity checks
        mock_summary.return_value = {
            "numa_hugepages": {
                "node0": {"capacity": [{"total": 10, "free": 10, "size": 2048}], "allocations": {}}
            }
        }
        req2 = dict(req1)
        req2["hugepages_requested"] = 7
        resp_bytes = handle_daemon_request(json.dumps(req2).encode())
        resp2 = parse_obj_as(AllocateHugepagesResponse, json.loads(resp_bytes.decode()))
        assert resp2.allocation_successful is True
        assert resp2.hugepages_requested == 7

        # After replacement, node0 should show only the latest count for svc
        flattened = list_allocations_for_node(0)
        # Expect svc to be present with size 2048 and count 7
        assert any(
            e["service_name"] == "svc" and e["size_kb"] == 2048 and e["count"] == 7
            for e in flattened
        )
        # Ensure no duplicate entry for svc/2048 remains
        counts = [
            e["count"] for e in flattened if e["service_name"] == "svc" and e["size_kb"] == 2048
        ]
        assert counts.count(7) == 1
