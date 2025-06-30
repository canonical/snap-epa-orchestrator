# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for epa_orchestrator.schemas."""

import pytest
from pydantic import ValidationError

from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresResponse,
    EpaRequest,
    SnapAllocation,
)


class TestSchemas:
    def test_epa_request_valid(self):
        req = EpaRequest(snap_name="snap1", action=ActionType.ALLOCATE_CORES, cores_requested=2)
        assert req.snap_name == "snap1"
        assert req.action == ActionType.ALLOCATE_CORES
        assert req.cores_requested == 2

    def test_epa_request_invalid(self):
        with pytest.raises(ValidationError):
            EpaRequest(snap_name="snap1", action="invalid_action")

    def test_allocate_cores_response(self):
        resp = AllocateCoresResponse(
            snap_name="snap1",
            cores_requested=2,
            cores_allocated=2,
            allocated_cores="0-1",
            shared_cpus="2-3",
            total_available_cpus=4,
            remaining_available_cpus=2,
        )
        assert resp.snap_name == "snap1"
        assert resp.cores_allocated == 2

    def test_snap_allocation(self):
        alloc = SnapAllocation(snap_name="snap1", allocated_cores="0-1", cores_count=2)
        assert alloc.snap_name == "snap1"
        assert alloc.allocated_cores == "0-1"
        assert alloc.cores_count == 2
