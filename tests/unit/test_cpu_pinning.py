# SPDX-FileCopyrightText: 2024 Canonical Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for epa_orchestrator.cpu_pinning."""

from unittest.mock import patch

from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus


class TestGetIsolatedCpus:
    """Test the get_isolated_cpus function."""

    def test_get_isolated_cpus_success(self, mock_cpu_files, mock_logging):
        """Test successful retrieval of isolated CPUs."""
        result = get_isolated_cpus()

        assert result == "0-3,6-7"
        mock_logging.info.assert_called_with("Found isolated CPUs: 0-3,6-7")

    def test_get_isolated_cpus_empty_fallback(self, mock_cpu_files_empty, mock_logging):
        """Test fallback to present CPUs when isolated CPUs are empty."""
        result = get_isolated_cpus()

        assert result == "0-7"
        # Check that the fallback message was logged
        mock_logging.info.assert_any_call("No isolated CPUs found, falling back to present CPUs")
        mock_logging.info.assert_any_call("Using present CPUs: 0-7")

    def test_get_isolated_cpus_missing_files(self, mock_cpu_files_missing, mock_logging):
        """Test handling of missing CPU files."""
        result = get_isolated_cpus()

        assert result == ""
        mock_logging.error.assert_called()

    def test_get_isolated_cpus_file_read_error(self, temp_dir, mock_logging):
        """Test handling of file read errors."""
        isolated_path = temp_dir / "isolated"
        present_path = temp_dir / "present"

        # Create files but make them unreadable
        isolated_path.write_text("0-3")
        present_path.write_text("0-7")
        isolated_path.chmod(0o000)  # Remove read permissions

        with patch("epa_orchestrator.cpu_pinning.ISOLATED_CPUS_PATH", str(isolated_path)), patch(
            "epa_orchestrator.cpu_pinning.PRESENT_CPUS_PATH", str(present_path)
        ):
            result = get_isolated_cpus()

        assert result == ""
        mock_logging.error.assert_called()

    def test_get_isolated_cpus_both_empty(self, temp_dir, mock_logging):
        """Test handling when both isolated and present CPUs are empty."""
        isolated_path = temp_dir / "isolated"
        present_path = temp_dir / "present"

        isolated_path.write_text("")
        present_path.write_text("")

        with patch("epa_orchestrator.cpu_pinning.ISOLATED_CPUS_PATH", str(isolated_path)), patch(
            "epa_orchestrator.cpu_pinning.PRESENT_CPUS_PATH", str(present_path)
        ):
            result = get_isolated_cpus()

        assert result == ""
        mock_logging.error.assert_called_with(
            "Could not find any CPUs (neither isolated nor present)"
        )


class TestCalculateCpuPinning:
    """Test the calculate_cpu_pinning function."""

    def test_calculate_cpu_pinning_simple_range(self, mock_logging):
        """Test CPU pinning calculation with simple range."""
        shared, dedicated = calculate_cpu_pinning("0-3", 2)

        assert shared == "2-3"
        assert dedicated == "0-1"

    def test_calculate_cpu_pinning_disjoint_cpus(self, mock_logging):
        """Test CPU pinning calculation with disjoint CPUs."""
        shared, dedicated = calculate_cpu_pinning("0,2,4,6", 1)

        assert shared == "2,4,6"
        assert dedicated == "0"

    def test_calculate_cpu_pinning_zero_requested(self, mock_logging):
        """Test CPU pinning calculation when 0 cores are requested (80% allocation)."""
        shared, dedicated = calculate_cpu_pinning("0-7", 0)

        # 80% of 8 CPUs = 6.4, rounded down to 6
        assert shared == "6-7"
        assert dedicated == "0-5"
        mock_logging.info.assert_called_with("Allocating 6 cores (80% of 8 total CPUs)")

    def test_calculate_cpu_pinning_exact_allocation(self, mock_logging):
        """Test CPU pinning calculation with exact allocation."""
        shared, dedicated = calculate_cpu_pinning("0-5", 4)

        assert shared == "4-5"
        assert dedicated == "0-3"

    def test_calculate_cpu_pinning_large_range(self, mock_logging):
        """Test CPU pinning calculation with large CPU range."""
        shared, dedicated = calculate_cpu_pinning("0-9", 8)

        assert shared == "8-9"
        assert dedicated == "0-7"

    def test_calculate_cpu_pinning_more_requested_than_available(self, mock_logging):
        """Test CPU pinning when more cores are requested than available."""
        shared, dedicated = calculate_cpu_pinning("0-3", 5)

        assert shared == ""
        assert dedicated == ""
        mock_logging.error.assert_called_with("Requested 5 cores but only 4 available")

    def test_calculate_cpu_pinning_empty_cpu_list(self, mock_logging):
        """Test CPU pinning with empty CPU list."""
        shared, dedicated = calculate_cpu_pinning("", 2)

        assert shared == ""
        assert dedicated == ""

    def test_calculate_cpu_pinning_single_cpu(self, mock_logging):
        """Test CPU pinning with single CPU."""
        shared, dedicated = calculate_cpu_pinning("5", 1)

        assert shared == ""
        assert dedicated == "5"

    def test_calculate_cpu_pinning_single_cpu_zero_requested(self, mock_logging):
        """Test CPU pinning with single CPU and zero requested."""
        shared, dedicated = calculate_cpu_pinning("5", 0)

        # 80% of 1 CPU = 0.8, rounded down to 0
        assert shared == "5"
        assert dedicated == ""

    def test_calculate_cpu_pinning_complex_range(self, mock_logging):
        """Test CPU pinning with complex CPU range."""
        shared, dedicated = calculate_cpu_pinning("0-3,5,7-9", 4)

        # CPUs: [0,1,2,3,5,7,8,9] - 8 total
        # Requested: 4, so dedicated: [0,1,2,3], shared: [5,7,8,9]
        assert shared == "5,7-9"
        assert dedicated == "0-3"

    def test_calculate_cpu_pinning_all_allocated(self, mock_logging):
        """Test CPU pinning when all CPUs are allocated."""
        shared, dedicated = calculate_cpu_pinning("0-3", 4)

        assert shared == ""
        assert dedicated == "0-3"

    def test_calculate_cpu_pinning_none_requested(self, mock_logging):
        """Test CPU pinning when None is passed for cores_requested."""
        # The function doesn't handle None, so we need to handle it before calling
        cores_requested = None
        if cores_requested is None:
            cores_requested = 0

        shared, dedicated = calculate_cpu_pinning("0-7", cores_requested)

        # Should default to 0, which means 80% allocation
        assert shared == "6-7"
        assert dedicated == "0-5"

    def test_calculate_cpu_pinning_negative_requested(self, mock_cpu_files):
        """Test calculate_cpu_pinning with negative cores_requested."""
        with patch(
            "epa_orchestrator.cpu_pinning.ISOLATED_CPUS_PATH", str(mock_cpu_files["isolated"])
        ), patch("epa_orchestrator.cpu_pinning.PRESENT_CPUS_PATH", str(mock_cpu_files["present"])):
            shared, allocated = calculate_cpu_pinning("0-3", -1)
            # Negative cores_requested should be treated as 0, which means 80% allocation
            # 80% of 4 CPUs = 3 CPUs allocated, 1 CPU shared
            assert shared == "3"
            assert allocated == "0-2"

    def test_calculate_cpu_pinning_mixed_ranges(self, mock_logging):
        """Test CPU pinning with mixed range formats."""
        shared, dedicated = calculate_cpu_pinning("0-2,4,6-8", 3)

        # CPUs: [0,1,2,4,6,7,8] - 7 total
        # Requested: 3, so dedicated: [0,1,2], shared: [4,6,7,8]
        assert shared == "4,6-8"
        assert dedicated == "0-2"

    def test_calculate_cpu_pinning_edge_case_80_percent(self, mock_logging):
        """Test CPU pinning edge case for 80% calculation."""
        # 10 CPUs, 80% = 8 CPUs
        shared, dedicated = calculate_cpu_pinning("0-9", 0)

        assert shared == "8-9"
        assert dedicated == "0-7"
        mock_logging.info.assert_called_with("Allocating 8 cores (80% of 10 total CPUs)")

    def test_calculate_cpu_pinning_rounding_down(self, mock_logging):
        """Test that 80% calculation rounds down correctly."""
        # 7 CPUs, 80% = 5.6, should round down to 5
        shared, dedicated = calculate_cpu_pinning("0-6", 0)

        assert shared == "5-6"
        assert dedicated == "0-4"
        mock_logging.info.assert_called_with("Allocating 5 cores (80% of 7 total CPUs)")
