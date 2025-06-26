# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for epa_orchestrator.schemas."""

import pytest
from pydantic import ValidationError

from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresResponse,
    EpaRequest,
    ListAllocationsResponse,
    SnapAllocation,
)


class TestActionType:
    """Test the ActionType enum."""

    def test_action_type_values(self):
        """Test that ActionType has the expected values."""
        assert ActionType.ALLOCATE_CORES == "allocate_cores"
        assert ActionType.LIST_ALLOCATIONS == "list_allocations"

    def test_action_type_membership(self):
        """Test ActionType enum membership."""
        assert ActionType.ALLOCATE_CORES in ActionType
        assert ActionType.LIST_ALLOCATIONS in ActionType
        # Test that invalid actions are not in the enum
        assert "invalid_action" not in [action.value for action in ActionType]


class TestEpaRequest:
    """Test the EpaRequest model."""

    def test_valid_allocate_cores_request(self):
        """Test valid allocate_cores request."""
        request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        assert request.snap_name == "test-snap"
        assert request.action == ActionType.ALLOCATE_CORES
        assert request.cores_requested == 2
        assert request.version == "1.0"

    def test_valid_list_allocations_request(self):
        """Test valid list_allocations request."""
        request = EpaRequest(snap_name="test-snap", action=ActionType.LIST_ALLOCATIONS)

        assert request.snap_name == "test-snap"
        assert request.action == ActionType.LIST_ALLOCATIONS
        assert request.cores_requested is None
        assert request.version == "1.0"

    def test_allocate_cores_with_none_cores_requested(self):
        """Test allocate_cores with None cores_requested (should default to 0)."""
        request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=None
        )

        assert request.cores_requested == 0

    def test_list_allocations_with_cores_requested(self):
        """Test list_allocations with cores_requested (should be ignored)."""
        request = EpaRequest(
            snap_name="test-snap",
            action=ActionType.LIST_ALLOCATIONS,
            cores_requested=5,  # Should be ignored
        )

        assert request.cores_requested is None

    def test_invalid_version(self):
        """Test request with invalid version."""
        with pytest.raises(ValidationError):
            EpaRequest(
                snap_name="test-snap",
                action=ActionType.ALLOCATE_CORES,
                version="2.0",  # Invalid version
            )

    def test_missing_snap_name(self):
        """Test request with missing snap_name."""
        with pytest.raises(ValidationError):
            EpaRequest(action=ActionType.ALLOCATE_CORES)

    def test_missing_action(self):
        """Test request with missing action."""
        with pytest.raises(ValidationError):
            EpaRequest(snap_name="test-snap")

    def test_negative_cores_requested(self):
        """Test request with negative cores_requested."""
        with pytest.raises(ValidationError):
            EpaRequest(snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=-1)

    def test_empty_snap_name(self):
        """Test request with empty snap_name."""
        request = EpaRequest(snap_name="", action=ActionType.ALLOCATE_CORES)
        assert request.snap_name == ""

    def test_default_values(self):
        """Test default values for EpaRequest."""
        # Test that cores_requested defaults to 0 for ALLOCATE_CORES action
        request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=None
        )

        assert request.version == "1.0"
        assert request.snap_name == "test-snap"
        assert request.action == ActionType.ALLOCATE_CORES
        assert request.cores_requested == 0  # Should be set to 0 by validator


class TestSnapAllocation:
    """Test the SnapAllocation model."""

    def test_valid_snap_allocation(self):
        """Test valid SnapAllocation."""
        allocation = SnapAllocation(snap_name="test-snap", allocated_cores="0-1,3", cores_count=3)

        assert allocation.snap_name == "test-snap"
        assert allocation.allocated_cores == "0-1,3"
        assert allocation.cores_count == 3

    def test_missing_fields(self):
        """Test SnapAllocation with missing fields."""
        with pytest.raises(ValidationError):
            SnapAllocation(
                snap_name="test-snap"
                # Missing allocated_cores and cores_count
            )

    def test_empty_allocated_cores(self):
        """Test SnapAllocation with empty allocated_cores."""
        allocation = SnapAllocation(snap_name="test-snap", allocated_cores="", cores_count=0)

        assert allocation.allocated_cores == ""
        assert allocation.cores_count == 0


class TestAllocateCoresResponse:
    """Test the AllocateCoresResponse model."""

    def test_valid_allocate_cores_response(self):
        """Test valid AllocateCoresResponse."""
        response = AllocateCoresResponse(
            snap_name="test-snap",
            cores_requested=2,
            cores_allocated=2,
            allocated_cores="0-1",
            shared_cpus="2-3",
            total_available_cpus=4,
            remaining_available_cpus=0,
        )

        assert response.snap_name == "test-snap"
        assert response.cores_requested == 2
        assert response.cores_allocated == 2
        assert response.allocated_cores == "0-1"
        assert response.shared_cpus == "2-3"
        assert response.total_available_cpus == 4
        assert response.remaining_available_cpus == 0
        assert response.version == "1.0"
        assert response.error == ""

    def test_allocate_cores_response_with_error(self):
        """Test AllocateCoresResponse with error."""
        response = AllocateCoresResponse(
            snap_name="test-snap",
            cores_requested=5,
            cores_allocated=0,
            allocated_cores="",
            shared_cpus="",
            total_available_cpus=4,
            remaining_available_cpus=4,
            error="Not enough CPUs available",
        )

        assert response.error == "Not enough CPUs available"
        assert response.cores_allocated == 0

    def test_missing_fields(self):
        """Test AllocateCoresResponse with missing fields."""
        with pytest.raises(ValidationError):
            AllocateCoresResponse(
                snap_name="test-snap"
                # Missing required fields
            )

    def test_default_values(self):
        """Test default values for AllocateCoresResponse."""
        response = AllocateCoresResponse(
            snap_name="test-snap",
            cores_requested=0,
            cores_allocated=0,
            allocated_cores="",
            shared_cpus="",
            total_available_cpus=0,
            remaining_available_cpus=0,
        )

        assert response.version == "1.0"
        assert response.error == ""


class TestListAllocationsResponse:
    """Test the ListAllocationsResponse model."""

    def test_valid_list_allocations_response(self):
        """Test valid ListAllocationsResponse."""
        allocations = [
            SnapAllocation(snap_name="snap1", allocated_cores="0-1", cores_count=2),
            SnapAllocation(snap_name="snap2", allocated_cores="2", cores_count=1),
        ]

        response = ListAllocationsResponse(
            total_allocations=2,
            total_allocated_cpus=3,
            total_available_cpus=8,
            remaining_available_cpus=5,
            allocations=allocations,
        )

        assert response.total_allocations == 2
        assert response.total_allocated_cpus == 3
        assert response.total_available_cpus == 8
        assert response.remaining_available_cpus == 5
        assert len(response.allocations) == 2
        assert response.version == "1.0"
        assert response.error == ""

    def test_empty_allocations_list(self):
        """Test ListAllocationsResponse with empty allocations."""
        response = ListAllocationsResponse(
            total_allocations=0,
            total_allocated_cpus=0,
            total_available_cpus=8,
            remaining_available_cpus=8,
            allocations=[],
        )

        assert response.total_allocations == 0
        assert response.total_allocated_cpus == 0
        assert len(response.allocations) == 0

    def test_list_allocations_response_with_error(self):
        """Test ListAllocationsResponse with error."""
        response = ListAllocationsResponse(
            total_allocations=0,
            total_allocated_cpus=0,
            total_available_cpus=0,
            remaining_available_cpus=0,
            allocations=[],
            error="Failed to retrieve allocations",
        )

        assert response.error == "Failed to retrieve allocations"

    def test_missing_fields(self):
        """Test ListAllocationsResponse with missing fields."""
        with pytest.raises(ValidationError):
            ListAllocationsResponse(
                total_allocations=0
                # Missing required fields
            )

    def test_default_values(self):
        """Test default values for ListAllocationsResponse."""
        response = ListAllocationsResponse(
            total_allocations=0,
            total_allocated_cpus=0,
            total_available_cpus=0,
            remaining_available_cpus=0,
            allocations=[],
        )

        assert response.version == "1.0"
        assert response.error == ""


class TestSchemaIntegration:
    """Test integration between different schemas."""

    def test_request_response_flow(self):
        """Test complete request-response flow."""
        # Create request
        request = EpaRequest(
            snap_name="test-snap", action=ActionType.ALLOCATE_CORES, cores_requested=2
        )

        # Create response
        response = AllocateCoresResponse(
            snap_name=request.snap_name,
            cores_requested=request.cores_requested,
            cores_allocated=2,
            allocated_cores="0-1",
            shared_cpus="2-3",
            total_available_cpus=4,
            remaining_available_cpus=0,
        )

        assert response.snap_name == request.snap_name
        assert response.cores_requested == request.cores_requested

    def test_list_allocations_with_snap_allocations(self):
        """Test ListAllocationsResponse containing SnapAllocation objects."""
        snap_allocation = SnapAllocation(
            snap_name="test-snap", allocated_cores="0-1", cores_count=2
        )

        response = ListAllocationsResponse(
            total_allocations=1,
            total_allocated_cpus=2,
            total_available_cpus=8,
            remaining_available_cpus=6,
            allocations=[snap_allocation],
        )

        assert len(response.allocations) == 1
        assert response.allocations[0].snap_name == "test-snap"
        assert response.allocations[0].allocated_cores == "0-1"
        assert response.allocations[0].cores_count == 2
