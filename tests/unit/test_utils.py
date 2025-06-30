# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for epa_orchestrator.utils."""

from epa_orchestrator.utils import to_ranges


class TestToRanges:
    def test_consecutive(self):
        assert to_ranges([0, 1, 2, 3]) == "0-3"

    def test_disjoint(self):
        assert to_ranges([0, 2, 4, 6]) == "0,2,4,6"

    def test_empty(self):
        assert to_ranges([]) == ""
