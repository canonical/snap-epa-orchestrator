# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for epa_orchestrator.allocations_db."""

import pytest

from epa_orchestrator.schemas import SnapAllocation


class TestAllocationsDB:
    """Test the AllocationsDB class."""

    def test_init(self, fresh_allocations_db):
        """Test AllocationsDB initialization."""
        assert fresh_allocations_db._allocations == {}
        assert fresh_allocations_db._allocated_cpus == set()

    def test_parse_cpu_ranges_simple(self, fresh_allocations_db):
        """Test parsing simple CPU ranges."""
        result = fresh_allocations_db._parse_cpu_ranges("0-3")
        assert result == {0, 1, 2, 3}

    def test_parse_cpu_ranges_disjoint(self, fresh_allocations_db):
        """Test parsing disjoint CPU ranges."""
        result = fresh_allocations_db._parse_cpu_ranges("0,2,4,6")
        assert result == {0, 2, 4, 6}

    def test_parse_cpu_ranges_mixed(self, fresh_allocations_db):
        """Test parsing mixed CPU ranges."""
        result = fresh_allocations_db._parse_cpu_ranges("0-2,4,6-8")
        assert result == {0, 1, 2, 4, 6, 7, 8}

    def test_parse_cpu_ranges_single(self, fresh_allocations_db):
        """Test parsing single CPU."""
        result = fresh_allocations_db._parse_cpu_ranges("5")
        assert result == {5}

    def test_parse_cpu_ranges_empty(self, fresh_allocations_db):
        """Test parsing empty CPU ranges."""
        result = fresh_allocations_db._parse_cpu_ranges("")
        assert result == set()

    def test_parse_cpu_ranges_complex(self, fresh_allocations_db):
        """Test parsing complex CPU ranges."""
        result = fresh_allocations_db._parse_cpu_ranges("0-3,5,7-9,12,15-17")
        assert result == {0, 1, 2, 3, 5, 7, 8, 9, 12, 15, 16, 17}

    def test_get_available_cpus_empty_db(self, fresh_allocations_db):
        """Test getting available CPUs from empty database."""
        result = fresh_allocations_db.get_available_cpus("0-7")
        assert result == [0, 1, 2, 3, 4, 5, 6, 7]

    def test_get_available_cpus_with_allocations(self, populated_allocations_db):
        """Test getting available CPUs with existing allocations."""
        result = populated_allocations_db.get_available_cpus("0-7")
        # test-snap-1 has 0-1, test-snap-2 has 2,4
        # So available: 3,5,6,7
        assert result == [3, 5, 6, 7]

    def test_get_available_cpus_no_available(self, fresh_allocations_db):
        """Test getting available CPUs when all are allocated."""
        fresh_allocations_db.allocate_cores("test-snap", "0-7")
        result = fresh_allocations_db.get_available_cpus("0-7")
        assert result == []

    def test_can_allocate_cpus_success(self, fresh_allocations_db):
        """Test successful CPU allocation check."""
        result = fresh_allocations_db.can_allocate_cpus(4, "0-7")
        assert result is True

    def test_can_allocate_cpus_failure(self, fresh_allocations_db):
        """Test failed CPU allocation check."""
        result = fresh_allocations_db.can_allocate_cpus(10, "0-7")
        assert result is False

    def test_can_allocate_cpus_partial_available(self, populated_allocations_db):
        """Test CPU allocation check with partial availability."""
        # 4 CPUs available (3,5,6,7), requesting 3
        result = populated_allocations_db.can_allocate_cpus(3, "0-7")
        assert result is True

        # 4 CPUs available, requesting 5
        result = populated_allocations_db.can_allocate_cpus(5, "0-7")
        assert result is False

    def test_allocate_cores_new_allocation(self, fresh_allocations_db):
        """Test allocating cores for new snap."""
        fresh_allocations_db.allocate_cores("test-snap", "0-1")

        assert fresh_allocations_db._allocations["test-snap"] == "0-1"
        assert fresh_allocations_db._allocated_cpus == {0, 1}

    def test_allocate_cores_update_existing(self, fresh_allocations_db):
        """Test updating existing allocation."""
        fresh_allocations_db.allocate_cores("test-snap", "0-1")
        fresh_allocations_db.allocate_cores("test-snap", "2-3")

        assert fresh_allocations_db._allocations["test-snap"] == "2-3"
        assert fresh_allocations_db._allocated_cpus == {2, 3}

    def test_allocate_cores_empty_cores(self, fresh_allocations_db):
        """Test allocating empty cores."""
        fresh_allocations_db.allocate_cores("test-snap", "")

        assert "test-snap" not in fresh_allocations_db._allocations
        assert fresh_allocations_db._allocated_cpus == set()

    def test_allocate_cores_multiple_snaps(self, fresh_allocations_db):
        """Test allocating cores to multiple snaps."""
        fresh_allocations_db.allocate_cores("snap1", "0-1")
        fresh_allocations_db.allocate_cores("snap2", "2-3")

        assert fresh_allocations_db._allocations["snap1"] == "0-1"
        assert fresh_allocations_db._allocations["snap2"] == "2-3"
        assert fresh_allocations_db._allocated_cpus == {0, 1, 2, 3}

    def test_get_allocation_existing(self, populated_allocations_db):
        """Test getting existing allocation."""
        result = populated_allocations_db.get_allocation("test-snap-1")
        assert result == "0-1"

    def test_get_allocation_nonexistent(self, fresh_allocations_db):
        """Test getting nonexistent allocation."""
        result = fresh_allocations_db.get_allocation("nonexistent-snap")
        assert result is None

    def test_get_all_allocations_empty(self, fresh_allocations_db):
        """Test getting all allocations from empty database."""
        result = fresh_allocations_db.get_all_allocations()
        assert result == []

    def test_get_all_allocations_populated(self, populated_allocations_db):
        """Test getting all allocations from populated database."""
        result = populated_allocations_db.get_all_allocations()

        assert len(result) == 2
        assert isinstance(result[0], SnapAllocation)
        assert isinstance(result[1], SnapAllocation)

        snap_names = [alloc.snap_name for alloc in result]
        assert "test-snap-1" in snap_names
        assert "test-snap-2" in snap_names

        # Check that cores_count is calculated correctly
        for allocation in result:
            if allocation.snap_name == "test-snap-1":
                assert allocation.cores_count == 2  # 0-1 = 2 CPUs
            elif allocation.snap_name == "test-snap-2":
                assert allocation.cores_count == 2  # 2,4 = 2 CPUs

    def test_remove_allocation_existing(self, populated_allocations_db):
        """Test removing existing allocation."""
        result = populated_allocations_db.remove_allocation("test-snap-1")

        assert result is True
        assert "test-snap-1" not in populated_allocations_db._allocations
        assert 0 not in populated_allocations_db._allocated_cpus
        assert 1 not in populated_allocations_db._allocated_cpus

    def test_remove_allocation_nonexistent(self, fresh_allocations_db):
        """Test removing nonexistent allocation."""
        result = fresh_allocations_db.remove_allocation("nonexistent-snap")
        assert result is False

    def test_clear_all_allocations(self, populated_allocations_db):
        """Test clearing all allocations."""
        populated_allocations_db.clear_all_allocations()

        assert populated_allocations_db._allocations == {}
        assert populated_allocations_db._allocated_cpus == set()

    def test_get_total_allocated_count_empty(self, fresh_allocations_db):
        """Test getting total allocated count from empty database."""
        result = fresh_allocations_db.get_total_allocated_count()
        assert result == 0

    def test_get_total_allocated_count_populated(self, populated_allocations_db):
        """Test getting total allocated count from populated database."""
        result = populated_allocations_db.get_total_allocated_count()
        # test-snap-1: 0-1 (2 CPUs), test-snap-2: 2,4 (2 CPUs)
        assert result == 4

    def test_get_snap_allocation_count_existing(self, populated_allocations_db):
        """Test getting allocation count for existing snap."""
        result = populated_allocations_db.get_snap_allocation_count("test-snap-1")
        assert result == 2  # 0-1 = 2 CPUs

    def test_get_snap_allocation_count_nonexistent(self, fresh_allocations_db):
        """Test getting allocation count for nonexistent snap."""
        result = fresh_allocations_db.get_snap_allocation_count("nonexistent-snap")
        assert result == 0

    def test_get_snap_allocation_count_complex(self, fresh_allocations_db):
        """Test get_snap_allocation_count with complex CPU ranges."""
        fresh_allocations_db.allocate_cores("test-snap", "0-3,5,7-9")
        result = fresh_allocations_db.get_snap_allocation_count("test-snap")
        assert result == 8  # 0,1,2,3,5,7,8,9 = 8 CPUs

    def test_get_system_stats_empty(self, fresh_allocations_db):
        """Test getting system stats from empty database."""
        result = fresh_allocations_db.get_system_stats("0-7")

        assert result["total_available_cpus"] == 8
        assert result["total_allocated_cpus"] == 0
        assert result["remaining_available_cpus"] == 8
        assert result["total_allocations"] == 0

    def test_get_system_stats_populated(self, populated_allocations_db):
        """Test getting system stats from populated database."""
        result = populated_allocations_db.get_system_stats("0-7")

        assert result["total_available_cpus"] == 8
        assert result["total_allocated_cpus"] == 4
        assert result["remaining_available_cpus"] == 4
        assert result["total_allocations"] == 2

    def test_get_system_stats_complex_cpu_range(self, fresh_allocations_db):
        """Test getting system stats with complex CPU range."""
        fresh_allocations_db.allocate_cores("test-snap", "0-2")
        result = fresh_allocations_db.get_system_stats("0-3,5,7-9")

        # Total: 0,1,2,3,5,7,8,9 = 8 CPUs
        # Allocated: 0,1,2 = 3 CPUs
        assert result["total_available_cpus"] == 8
        assert result["total_allocated_cpus"] == 3
        assert result["remaining_available_cpus"] == 5
        assert result["total_allocations"] == 1

    def test_allocation_overlap_prevention(self, fresh_allocations_db):
        """Test that allocations don't overlap."""
        fresh_allocations_db.allocate_cores("snap1", "0-3")
        fresh_allocations_db.allocate_cores("snap2", "2-5")  # Overlaps with snap1

        # snap2 should replace snap1's allocation
        assert fresh_allocations_db._allocations["snap1"] == "0-3"
        assert fresh_allocations_db._allocations["snap2"] == "2-5"
        # Allocated CPUs should be 0,1,2,3,4,5 (no duplicates)
        assert fresh_allocations_db._allocated_cpus == {0, 1, 2, 3, 4, 5}

    def test_update_allocation_removes_old_cpus(self, fresh_allocations_db):
        """Test that updating allocation removes old CPUs from tracking."""
        fresh_allocations_db.allocate_cores("test-snap", "0-3")
        fresh_allocations_db.allocate_cores("test-snap", "5-7")

        # Old CPUs (0-3) should be removed, new CPUs (5-7) should be added
        assert fresh_allocations_db._allocated_cpus == {5, 6, 7}
        assert 0 not in fresh_allocations_db._allocated_cpus
        assert 1 not in fresh_allocations_db._allocated_cpus
        assert 2 not in fresh_allocations_db._allocated_cpus
        assert 3 not in fresh_allocations_db._allocated_cpus

    def test_parse_cpu_ranges_invalid_format(self, fresh_allocations_db):
        """Test parsing invalid CPU range format."""
        with pytest.raises(ValueError):
            fresh_allocations_db._parse_cpu_ranges("0-3-5")  # Invalid format

    def test_parse_cpu_ranges_non_numeric(self, fresh_allocations_db):
        """Test parsing non-numeric CPU ranges."""
        with pytest.raises(ValueError):
            fresh_allocations_db._parse_cpu_ranges("0-a,3")  # Non-numeric

    def test_parse_cpu_ranges_empty_range(self, fresh_allocations_db):
        """Test parsing empty range."""
        with pytest.raises(ValueError):
            fresh_allocations_db._parse_cpu_ranges("0-")  # Empty range

    def test_parse_cpu_ranges_reverse_range(self, fresh_allocations_db):
        """Test _parse_cpu_ranges with reverse range (should raise ValueError)."""
        with pytest.raises(ValueError):
            fresh_allocations_db._parse_cpu_ranges("3-1")
