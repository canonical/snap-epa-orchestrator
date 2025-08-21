# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for epa_orchestrator.allocations_db."""


class TestAllocationsDB:
    """Unit tests for AllocationsDB class."""

    def test_allocate_and_get_allocation(self, fresh_allocations_db):
        """Test allocation and retrieval of CPU cores."""
        fresh_allocations_db.allocate_cores("snap1", "0-1")
        assert fresh_allocations_db.get_allocation("snap1") == "0-1"
        assert fresh_allocations_db._allocated_cpus == {0, 1}

    def test_remove_allocation(self, fresh_allocations_db):
        """Test removal of a CPU allocation."""
        fresh_allocations_db.allocate_cores("snap1", "0-1")
        assert fresh_allocations_db.remove_allocation("snap1") is True
        assert fresh_allocations_db.get_allocation("snap1") is None
        assert fresh_allocations_db._allocated_cpus == set()

    def test_get_system_stats(self, fresh_allocations_db):
        """Test retrieval of system statistics."""
        fresh_allocations_db.allocate_cores("snap1", "0-1")
        stats = fresh_allocations_db.get_system_stats("0-3")
        assert stats["total_available_cpus"] == 4
        assert stats["total_allocated_cpus"] == 2
        assert stats["remaining_available_cpus"] == 2
        assert stats["total_allocations"] == 1

    def test_can_allocate_cpus(self, fresh_allocations_db):
        """Test checking if CPUs can be allocated."""
        assert fresh_allocations_db.can_allocate_cpus(2, "0-3") is True
        fresh_allocations_db.allocate_cores("snap1", "0-3")
        assert fresh_allocations_db.can_allocate_cpus(1, "0-3") is False

    def test_explicit_allocation_basic(self, fresh_allocations_db):
        """Test basic explicit allocation functionality."""
        allocated, rejected = fresh_allocations_db.explicitly_allocate_cores("snap1", "0-2")
        assert allocated == "0-2"
        assert rejected == ""
        assert fresh_allocations_db.get_allocation("snap1") == "0-2"
        assert fresh_allocations_db.is_explicit_allocation("snap1") is True
        assert fresh_allocations_db._explicitly_allocated_cpus == {0, 1, 2}

    def test_explicit_allocation_conflict_prevention(self, fresh_allocations_db):
        """Test that explicit allocations prevent conflicts with other explicit allocations."""
        allocated1, rejected1 = fresh_allocations_db.explicitly_allocate_cores("snap1", "0-2")
        assert allocated1 == "0-2"
        assert rejected1 == ""

        allocated2, rejected2 = fresh_allocations_db.explicitly_allocate_cores("snap2", "1-3")
        assert allocated2 == ""
        assert rejected2 == "1-2"

        assert fresh_allocations_db.get_allocation("snap1") == "0-2"
        assert fresh_allocations_db.is_explicit_allocation("snap1") is True

        assert (
            fresh_allocations_db.get_allocation("snap2") is None
        )  # No allocation due to rejection
        assert fresh_allocations_db.is_explicit_allocation("snap2") is False

    def test_explicit_allocation_force_reallocation(self, fresh_allocations_db):
        """Test that explicit allocation can force reallocate non-explicit allocations."""
        fresh_allocations_db.allocate_cores("snap1", "0-2")
        assert fresh_allocations_db.get_allocation("snap1") == "0-2"
        assert fresh_allocations_db.is_explicit_allocation("snap1") is False

        allocated, rejected = fresh_allocations_db.explicitly_allocate_cores("snap2", "1-3")
        assert allocated == "1-3"
        assert rejected == ""

        assert fresh_allocations_db.get_allocation("snap1") == "0"
        assert fresh_allocations_db.is_explicit_allocation("snap1") is False

        assert fresh_allocations_db.get_allocation("snap2") == "1-3"
        assert fresh_allocations_db.is_explicit_allocation("snap2") is True

    def test_explicit_allocation_self_conflict(self, fresh_allocations_db):
        """Test that explicit allocation doesn't conflict with self."""
        allocated1, rejected1 = fresh_allocations_db.explicitly_allocate_cores("snap1", "0-2")
        assert allocated1 == "0-2"
        assert rejected1 == ""

        allocated2, rejected2 = fresh_allocations_db.explicitly_allocate_cores("snap1", "1-4")
        assert allocated2 == "1-4"
        assert rejected2 == ""

        assert fresh_allocations_db.get_allocation("snap1") == "1-4"
        assert fresh_allocations_db.is_explicit_allocation("snap1") is True

    def test_explicit_allocation_empty_request(self, fresh_allocations_db):
        """Test explicit allocation with empty request."""
        allocated, rejected = fresh_allocations_db.explicitly_allocate_cores("snap1", "")
        assert allocated == ""
        assert rejected == ""
        assert fresh_allocations_db.get_allocation("snap1") is None

    def test_explicit_allocation_whitespace_request(self, fresh_allocations_db):
        """Test explicit allocation with whitespace-only request."""
        allocated, rejected = fresh_allocations_db.explicitly_allocate_cores("snap1", "   ")
        assert allocated == ""
        assert rejected == ""
        assert fresh_allocations_db.get_allocation("snap1") is None

    def test_explicit_allocation_override_regular_allocation(self, fresh_allocations_db):
        """Test that explicit allocation can override regular allocation."""
        fresh_allocations_db.allocate_cores("snap1", "0-2")
        assert fresh_allocations_db.get_allocation("snap1") == "0-2"
        allocated, rejected = fresh_allocations_db.explicitly_allocate_cores("snap2", "1-3")
        assert allocated == "1-3"
        assert rejected == ""
        assert fresh_allocations_db.get_allocation("snap1") == "0"
        assert fresh_allocations_db.get_allocation("snap2") == "1-3"
        assert fresh_allocations_db.is_explicit_allocation("snap2") is True

    def test_explicit_allocation_clear_all(self, fresh_allocations_db):
        """Test that clear_all_allocations clears explicit allocations."""
        fresh_allocations_db.explicitly_allocate_cores("snap1", "0-2")
        fresh_allocations_db.allocate_cores("snap2", "3-4")

        assert len(fresh_allocations_db._explicit_allocations) == 1
        assert len(fresh_allocations_db._allocations) == 2

        fresh_allocations_db.clear_all_allocations()

        assert len(fresh_allocations_db._explicit_allocations) == 0
        assert len(fresh_allocations_db._allocations) == 0
        assert len(fresh_allocations_db._explicitly_allocated_cpus) == 0
        assert len(fresh_allocations_db._allocated_cpus) == 0

    def test_explicit_allocation_remove_allocation(self, fresh_allocations_db):
        """Test that remove_allocation properly handles explicit allocations."""
        fresh_allocations_db.explicitly_allocate_cores("snap1", "0-2")
        assert fresh_allocations_db.is_explicit_allocation("snap1") is True
        assert len(fresh_allocations_db._explicitly_allocated_cpus) == 3

        fresh_allocations_db.remove_allocation("snap1")
        assert fresh_allocations_db.get_allocation("snap1") is None
        assert fresh_allocations_db.is_explicit_allocation("snap1") is False
        assert len(fresh_allocations_db._explicitly_allocated_cpus) == 0

    def test_get_all_allocations_with_explicit_flag(self, fresh_allocations_db):
        """Test that get_all_allocations includes explicit allocation flags."""
        fresh_allocations_db.allocate_cores("snap1", "0-1")
        fresh_allocations_db.explicitly_allocate_cores("snap2", "2-3")

        allocations = fresh_allocations_db.get_all_allocations()
        assert len(allocations) == 2

        snap1_alloc = next(a for a in allocations if a.service_name == "snap1")
        assert snap1_alloc.is_explicit is False

        snap2_alloc = next(a for a in allocations if a.service_name == "snap2")
        assert snap2_alloc.is_explicit is True
