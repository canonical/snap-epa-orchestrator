# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CPU range operations."""


def to_ranges(cpu_list):
    """Convert CPU cores list to CPU range in string format.

    Args:
        cpu_list: List of CPU core numbers

    Returns:
        str: Comma-separated string of CPU ranges

    Raises:
        TypeError: If cpu_list is None or not a list

    Examples:
        >>> to_ranges([0, 1, 2, 4, 5, 7])
        '0-2,4-5,7'
        >>> to_ranges([1, 3, 5])
        '1,3,5'
        >>> to_ranges([])
        ''
        >>> to_ranges([0])
        '0'
        >>> to_ranges([0, 1, 2, 3])
        '0-3'
        >>> to_ranges([1, 1, 2, 3, 3])
        '1-3'
    """
    if cpu_list is None:
        raise TypeError("cpu_list cannot be None")

    if not isinstance(cpu_list, list):
        raise TypeError("cpu_list must be a list")

    if not cpu_list:
        return ""

    # Remove duplicates and sort
    unique_cpus = sorted(list(set(cpu_list)))

    ranges = []
    start = unique_cpus[0]
    prev = start

    for cpu in unique_cpus[1:]:
        if cpu != prev + 1:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = cpu
        prev = cpu

    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")

    return ",".join(ranges)


def _count_cpus_in_ranges(cpu_ranges: str) -> int:
    """Count the number of CPUs in a comma-separated range string.

    Args:
        cpu_ranges: Comma-separated list of CPU ranges (e.g., "0-2,4,6-8")

    Returns:
        Number of CPUs in the ranges
    """
    if not cpu_ranges:
        return 0

    count = 0
    for part in cpu_ranges.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            count += end - start + 1
        else:
            count += 1
    return count
