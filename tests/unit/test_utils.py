# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for epa_orchestrator.utils."""

from epa_orchestrator.utils import to_ranges


class TestToRanges:
    """Unit tests for to_ranges utility function."""

    def test_consecutive(self):
        """Test to_ranges with consecutive numbers."""
        assert to_ranges([0, 1, 2, 3]) == "0-3"

    def test_disjoint(self):
        """Test to_ranges with disjoint numbers."""
        assert to_ranges([0, 2, 4, 6]) == "0,2,4,6"

    def test_empty(self):
        """Test to_ranges with empty list."""
        assert to_ranges([]) == ""
