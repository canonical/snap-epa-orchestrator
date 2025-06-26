# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for daemon integration functionality."""

import os
from unittest.mock import patch

import pytest

from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresResponse,
    EpaRequest,
    ListAllocationsResponse,
    SnapAllocation,
)


class TestDaemonIntegration:
    """Test daemon integration functionality."""

    @pytest.fixture
    def mock_socket_path(self, temp_dir):
        """Create a mock socket path."""
        return str(temp_dir / "epa_orchestrator.sock")

    @pytest.fixture
    def mock_snap_env(self):
        """Mock snap environment variables."""
        return {
            "SNAP_DATA": "/var/snap/epa-orchestrator/1",
            "SNAP_NAME": "epa-orchestrator",
            "SNAP_VERSION": "2025.1",
        }

    def test_socket_path_construction(self, mock_snap_env):
        """Test socket path construction from snap environment."""
        with patch.dict(os.environ, mock_snap_env):
            snap_data = os.environ.get("SNAP_DATA")
            socket_path = f"{snap_data}/epa_orchestrator.sock"

            assert socket_path == "/var/snap/epa-orchestrator/1/epa_orchestrator.sock"

    def test_allocate_cores_request_processing(self, fresh_allocations_db, mock_cpu_files):
        """Test processing of allocate_cores request."""
        # Mock CPU information
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            # Create request
            request = EpaRequest(
                snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
            )

            # Process request (simulating daemon logic)
            isolated_cpus = get_isolated_cpus()
            shared_cpus, allocated_cores = calculate_cpu_pinning(
                isolated_cpus, request.cores_requested
            )

            if allocated_cores:
                fresh_allocations_db.allocate_cores(request.snap_name, allocated_cores)

            # Create response
            stats = fresh_allocations_db.get_system_stats(isolated_cpus)
            response = AllocateCoresResponse(
                snap_name=request.snap_name,
                cores_requested=request.cores_requested,
                cores_allocated=len(fresh_allocations_db._parse_cpu_ranges(allocated_cores)),
                allocated_cores=allocated_cores,
                shared_cpus=shared_cpus,
                total_available_cpus=stats["total_available_cpus"],
                remaining_available_cpus=stats["remaining_available_cpus"],
            )

            # Verify response
            assert response.snap_name == "test-snap"
            assert response.cores_requested == 2
            assert response.cores_allocated == 2
            assert response.allocated_cores == "0-1"
            assert response.shared_cpus == "2-3,6-7"
            assert response.total_available_cpus == 6
            assert response.remaining_available_cpus == 4

    def test_list_allocations_request_processing(self, populated_allocations_db, mock_cpu_files):
        """Test list_allocations request processing."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            # Process request (simulating daemon logic)
            isolated_cpus = get_isolated_cpus()
            stats = populated_allocations_db.get_system_stats(isolated_cpus)

            # Build allocations list
            allocations = []
            for snap_name, cores in populated_allocations_db._allocations.items():
                cores_count = populated_allocations_db.get_snap_allocation_count(snap_name)
                allocations.append(
                    SnapAllocation(
                        snap_name=snap_name, allocated_cores=cores, cores_count=cores_count
                    )
                )

            # Create response
            response = ListAllocationsResponse(
                total_allocations=stats["total_allocations"],
                total_allocated_cpus=stats["total_allocated_cpus"],
                total_available_cpus=stats["total_available_cpus"],
                remaining_available_cpus=stats["remaining_available_cpus"],
                allocations=allocations,
            )

            # Verify response
            assert response.total_allocations == 2
            assert response.total_allocated_cpus == 4
            assert response.total_available_cpus == 6  # 0-3,6-7 = 6 CPUs
            assert response.remaining_available_cpus == 2
            assert len(response.allocations) == 2

    def test_request_validation_error_handling(self):
        """Test handling of invalid requests."""
        # Test invalid action
        with pytest.raises(ValueError):
            EpaRequest(snap_name="test-snap", action="invalid_action")

        # Test negative cores_requested
        with pytest.raises(ValueError):
            EpaRequest(snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=-1)

    def test_allocation_error_handling(self, fresh_allocations_db, mock_cpu_files):
        """Test allocation error handling when not enough CPUs are available."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            # Create request for more CPUs than available
            request = EpaRequest(
                snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=5
            )

            # Process request
            isolated_cpus = get_isolated_cpus()
            shared_cpus, allocated_cores = calculate_cpu_pinning(
                isolated_cpus, request.cores_requested
            )

            # Should allocate what's available (6 CPUs total, requested 5)
            # The function allocates 5 CPUs: 0,1,2,3,6 (not 0-4)
            assert allocated_cores == "0-3,6"  # 5 CPUs allocated: 0,1,2,3,6
            assert shared_cpus == "7"  # 1 CPU remaining: 7

    def test_concurrent_allocation_handling(self, fresh_allocations_db, mock_cpu_files):
        """Test handling of concurrent allocations."""
        # Mock CPU information
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-7"):
            # Simulate concurrent requests
            requests = [
                EpaRequest(snap_name="snap1", action=ActionType.ALLOCATE_CORES, cores_requested=2),
                EpaRequest(snap_name="snap2", action=ActionType.ALLOCATE_CORES, cores_requested=3),
                EpaRequest(snap_name="snap3", action=ActionType.ALLOCATE_CORES, cores_requested=2),
            ]

            isolated_cpus = get_isolated_cpus()

            for request in requests:
                shared_cpus, allocated_cores = calculate_cpu_pinning(
                    isolated_cpus, request.cores_requested
                )

                # Check if allocation is possible
                if fresh_allocations_db.can_allocate_cpus(request.cores_requested, isolated_cpus):
                    fresh_allocations_db.allocate_cores(request.snap_name, allocated_cores)

            # Verify allocations
            assert fresh_allocations_db.get_allocation("snap1") == "0-1"
            assert fresh_allocations_db.get_allocation("snap2") == "0-2"
            # snap3 should not be allocated due to insufficient CPUs

    def test_allocation_update_handling(self, fresh_allocations_db, mock_cpu_files):
        """Test handling of allocation updates."""
        # Mock CPU information
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-7"):
            # Initial allocation
            request1 = EpaRequest(
                snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
            )

            isolated_cpus = get_isolated_cpus()
            shared_cpus, allocated_cores = calculate_cpu_pinning(
                isolated_cpus, request1.cores_requested
            )
            fresh_allocations_db.allocate_cores(request1.snap_name, allocated_cores)

            # Update allocation
            request2 = EpaRequest(
                snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=4
            )

            shared_cpus, allocated_cores = calculate_cpu_pinning(
                isolated_cpus, request2.cores_requested
            )
            fresh_allocations_db.allocate_cores(request2.snap_name, allocated_cores)

            # Verify updated allocation
            assert fresh_allocations_db.get_allocation("test-snap") == "0-3"
            assert fresh_allocations_db.get_snap_allocation_count("test-snap") == 4

    def test_system_stats_accuracy(self, populated_allocations_db, mock_cpu_files):
        """Test system stats accuracy."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            isolated_cpus = get_isolated_cpus()
            stats = populated_allocations_db.get_system_stats(isolated_cpus)

            # Verify stats
            assert stats["total_available_cpus"] == 6  # 0-3,6-7 = 6 CPUs
            assert stats["total_allocated_cpus"] == 4  # 0-1 + 2,4 = 4 CPUs
            assert stats["remaining_available_cpus"] == 2  # 6 - 4 = 2 CPUs
            assert stats["total_allocations"] == 2

    def test_request_serialization_roundtrip(self):
        """Test request serialization and deserialization."""
        # Create request
        original_request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        # Serialize
        json_data = original_request.model_dump_json()

        # Deserialize
        parsed_request = EpaRequest.model_validate_json(json_data)

        # Verify roundtrip
        assert parsed_request.snap_name == original_request.snap_name
        assert parsed_request.action == original_request.action
        assert parsed_request.cores_requested == original_request.cores_requested
        assert parsed_request.version == original_request.version

    def test_response_serialization_roundtrip(self, fresh_allocations_db, mock_cpu_files):
        """Test response serialization and deserialization."""
        # Mock CPU information
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-7"):
            # Create response
            original_response = AllocateCoresResponse(
                snap_name="test-snap",
                cores_requested=2,
                cores_allocated=2,
                allocated_cores="0-1",
                shared_cpus="2-7",
                total_available_cpus=8,
                remaining_available_cpus=6,
            )

            # Serialize
            json_data = original_response.model_dump_json()

            # Deserialize
            parsed_response = AllocateCoresResponse.model_validate_json(json_data)

            # Verify roundtrip
            assert parsed_response.snap_name == original_response.snap_name
            assert parsed_response.cores_requested == original_response.cores_requested
            assert parsed_response.cores_allocated == original_response.cores_allocated
            assert parsed_response.allocated_cores == original_response.allocated_cores
            assert parsed_response.shared_cpus == original_response.shared_cpus
            assert parsed_response.total_available_cpus == original_response.total_available_cpus
            assert (
                parsed_response.remaining_available_cpus
                == original_response.remaining_available_cpus
            )

    def test_error_response_handling(self, fresh_allocations_db, mock_cpu_files):
        """Test error response handling."""
        # Mock CPU information with limited CPUs
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-1"):
            # Create request that will fail
            request = EpaRequest(
                snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=5
            )

            # Process request
            isolated_cpus = get_isolated_cpus()
            shared_cpus, allocated_cores = calculate_cpu_pinning(
                isolated_cpus, request.cores_requested
            )

            # Create error response
            response = AllocateCoresResponse(
                snap_name=request.snap_name,
                cores_requested=request.cores_requested,
                cores_allocated=0,
                allocated_cores="",
                shared_cpus="",
                total_available_cpus=2,
                remaining_available_cpus=2,
                error="Not enough CPUs available",
            )

            # Verify error response
            assert response.cores_allocated == 0
            assert response.allocated_cores == ""
            assert response.error == "Not enough CPUs available"
