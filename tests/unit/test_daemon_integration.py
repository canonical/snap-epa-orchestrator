# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for daemon integration functionality."""

from unittest.mock import patch

import pytest

from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresRequest,
    AllocateCoresResponse,
)


class TestDaemonIntegration:
    """Unit tests for daemon integration logic."""

    def test_allocate_cores_request(self, fresh_allocations_db, mock_cpu_files):
        """Test allocation of cores via daemon request."""
        with patch("epa_orchestrator.cpu_pinning.get_isolated_cpus", return_value="0-3,6-7"):
            request = AllocateCoresRequest(
                snap_name="snap1", action=ActionType.ALLOCATE_CORES, cores_requested=2
            )
            isolated = get_isolated_cpus()
            shared, allocated = calculate_cpu_pinning(isolated, request.cores_requested)
            fresh_allocations_db.allocate_cores(request.snap_name, allocated)
            stats = fresh_allocations_db.get_system_stats(isolated)
            response = AllocateCoresResponse(
                snap_name=request.snap_name,
                cores_requested=request.cores_requested,
                cores_allocated=len(fresh_allocations_db._parse_cpu_ranges(allocated)),
                allocated_cores=allocated,
                shared_cpus=shared,
                total_available_cpus=stats["total_available_cpus"],
                remaining_available_cpus=stats["remaining_available_cpus"],
            )
            assert response.snap_name == "snap1"
            assert response.cores_allocated == 2

    def test_error_handling(self):
        """Test error handling in daemon integration."""
        with pytest.raises(Exception):
            AllocateCoresRequest(snap_name="snap1", action="bad_action", cores_requested=2)
