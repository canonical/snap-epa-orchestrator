# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CPU range operations."""


def to_ranges(cpu_list):
    """Convert CPU cores list to CPU range in string format.

    Args:
        cpu_list: List of CPU core numbers

    Returns:
        str: Comma-separated string of CPU ranges

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
    """
    if not cpu_list:
        return ""

    ranges = []
    start = cpu_list[0]
    prev = start

    for cpu in cpu_list[1:]:
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
