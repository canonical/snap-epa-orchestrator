# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for epa_orchestrator.utils."""

import pytest

from epa_orchestrator.utils import to_ranges


class TestToRanges:
    """Test the to_ranges utility function."""

    def test_consecutive_cpus(self, sample_cpu_lists):
        """Test converting consecutive CPU numbers to ranges."""
        result = to_ranges(sample_cpu_lists["consecutive"])
        assert result == "0-3"

    def test_disjoint_cpus(self, sample_cpu_lists):
        """Test converting disjoint CPU numbers to ranges."""
        result = to_ranges(sample_cpu_lists["disjoint"])
        assert result == "0,2,4,6"

    def test_mixed_cpus(self, sample_cpu_lists):
        """Test converting mixed consecutive and disjoint CPU numbers."""
        result = to_ranges(sample_cpu_lists["mixed"])
        assert result == "0-2,4,6-8"

    def test_single_cpu(self, sample_cpu_lists):
        """Test converting a single CPU number."""
        result = to_ranges(sample_cpu_lists["single"])
        assert result == "5"

    def test_empty_list(self, sample_cpu_lists):
        """Test converting an empty list."""
        result = to_ranges(sample_cpu_lists["empty"])
        assert result == ""

    def test_complex_cpu_list(self, sample_cpu_lists):
        """Test converting a complex list with multiple ranges."""
        result = to_ranges(sample_cpu_lists["complex"])
        assert result == "0-3,5,7-9,12,15-17"

    def test_single_element_list(self):
        """Test converting a list with single element."""
        result = to_ranges([42])
        assert result == "42"

    def test_two_consecutive_elements(self):
        """Test converting two consecutive elements."""
        result = to_ranges([10, 11])
        assert result == "10-11"

    def test_two_disjoint_elements(self):
        """Test converting two disjoint elements."""
        result = to_ranges([10, 12])
        assert result == "10,12"

    def test_unsorted_list(self):
        """Test to_ranges with unsorted list."""
        result = to_ranges([3, 1, 5, 2, 4])
        assert result == "1-5"  # Should be sorted and converted to range

    def test_large_numbers(self):
        """Test to_ranges with large numbers."""
        result = to_ranges([1000, 1001, 1002, 1005, 1006])
        assert result == "1000-1002,1005-1006"

    def test_zero_based(self):
        """Test to_ranges with zero-based numbering."""
        result = to_ranges([0, 1, 2, 4, 5])
        assert result == "0-2,4-5"

    def test_negative_numbers(self):
        """Test to_ranges with negative numbers."""
        result = to_ranges([-3, -2, -1, 1, 2])
        assert result == "-3--1,1-2"

    def test_duplicate_numbers(self):
        """Test to_ranges with duplicate numbers."""
        result = to_ranges([1, 1, 2, 3, 3])
        assert result == "1-3"  # Duplicates should be removed

    def test_none_input(self):
        """Test to_ranges with None input."""
        with pytest.raises(TypeError):
            to_ranges(None)

    def test_string_input(self):
        """Test to_ranges with string input (should fail)."""
        with pytest.raises(TypeError):
            to_ranges("1,2,3")

    def test_dict_input(self):
        """Test to_ranges with dict input (should fail)."""
        with pytest.raises(TypeError):
            to_ranges({"a": 1, "b": 2})
