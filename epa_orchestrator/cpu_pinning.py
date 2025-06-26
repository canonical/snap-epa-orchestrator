# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Utility methods for calculating dedicated and shared vCPUs."""

import logging

from .utils import to_ranges

ISOLATED_CPUS_PATH = "/sys/devices/system/cpu/isolated"
PRESENT_CPUS_PATH = "/sys/devices/system/cpu/present"
MAX_ALLOCATION_PERCENTAGE = 80  # Maximum percentage of CPUs that can be allocated


def get_isolated_cpus() -> str:
    """Get the list of isolated CPUs from ISOLATED_CPUS_PATH.

    If no isolated CPUs are found, falls back to using all present CPUs.

    Returns:
        str: Comma-separated list of CPU ranges that are isolated or present
    """
    try:
        with open(ISOLATED_CPUS_PATH, "r") as f:
            isolated = f.read().strip()
            if isolated:
                logging.info(f"Found isolated CPUs: {isolated}")
                return isolated

        logging.info("No isolated CPUs found, falling back to present CPUs")
        with open(PRESENT_CPUS_PATH, "r") as f:
            present = f.read().strip()
            if present:
                logging.info(f"Using present CPUs: {present}")
                return present

        logging.error("Could not find any CPUs (neither isolated nor present)")
        return ""
    except Exception as e:
        logging.error(f"Failed to get CPU information: {e}")
        return ""


def calculate_cpu_pinning(cpu_list: str, cores_requested: int = 0) -> "tuple[str, str]":
    """Calculate CPU pinning configuration from isolated CPU list.

    Args:
        cpu_list: Comma-separated list of CPU ranges
        cores_requested: Number of dedicated cores requested. If 0, allocates 80% of total CPUs.

    Returns:
        tuple: (cpu_shared_set, allocated_cores) where each is a comma-separated
              list of CPU ranges.

    Examples:
        >>> calculate_cpu_pinning("0-3", 2)
        ('2-3', '0-1')
        >>> calculate_cpu_pinning("0,2,4,6", 1)
        ('2,4,6', '0')
        >>> calculate_cpu_pinning("0-7", 0)  # Uses 80% default
        ('6-7', '0-5')
        >>> calculate_cpu_pinning("0-5", 4)
        ('4-5', '0-3')
        >>> calculate_cpu_pinning("0-9", 8)
        ('8-9', '0-7')
        >>> calculate_cpu_pinning("0-3", 5)  # More requested than available
        ('', '')
        >>> calculate_cpu_pinning("", 2)  # Empty CPU list
        ('', '')
    """
    if not cpu_list:
        return "", ""

    cpus = set()
    for part in cpu_list.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            cpus.update(range(start, end + 1))
        else:
            cpus.add(int(part))

    cpus = sorted(list(cpus))
    total_cpus = len(cpus)

    if cores_requested == 0:
        # Allocate 80% of total CPUs when 0 is requested
        cores_requested = int(total_cpus * MAX_ALLOCATION_PERCENTAGE / 100)
        logging.info(f"Allocating {cores_requested} cores (80% of {total_cpus} total CPUs)")

    # Validate that we have enough CPUs available
    if cores_requested > total_cpus:
        logging.error(f"Requested {cores_requested} cores but only {total_cpus} available")
        return "", ""

    dedicated_cpus = cpus[:cores_requested]
    shared_cpus = cpus[cores_requested:]

    return to_ranges(shared_cpus), to_ranges(dedicated_cpus)
