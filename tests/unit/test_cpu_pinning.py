# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Concise unit tests for epa_orchestrator.cpu_pinning."""

from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus


class TestCpuPinning:
    def test_calculate_cpu_pinning_basic(self, mock_logging):
        shared, dedicated = calculate_cpu_pinning("0-3", 2)
        assert shared == "2-3"
        assert dedicated == "0-1"

    def test_calculate_cpu_pinning_too_many(self, mock_logging):
        shared, dedicated = calculate_cpu_pinning("0-3", 5)
        assert shared == ""
        assert dedicated == ""
        mock_logging.error.assert_called()

    def test_get_isolated_cpus_success(self, mock_cpu_files, mock_logging):
        result = get_isolated_cpus()
        assert result == "0-3,6-7"
        mock_logging.info.assert_called()
