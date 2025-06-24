# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Utility methods for calculating dedicated and shared vCPUs."""

import logging

ISOLATED_CPUS_PATH = "/sys/devices/system/cpu/isolated"
PRESENT_CPUS_PATH = "/sys/devices/system/cpu/present"
CPU_SHARED_PERCENTAGE = 50  # Percentage of CPUs to be used for shared set


def _to_ranges(cpu_list):
    """Convert CPU cores list to CPU range in string format."""
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


def calculate_cpu_pinning(cpu_list: str, cores_requested: int = 0) -> tuple[str, str]:
    """Calculate CPU pinning configuration from isolated CPU list.

    Args:
        cpu_list: Comma-separated list of CPU ranges
        cores_requested: Number of dedicated cores requested. If 0, uses a percentage.

    Returns:
        tuple: (cpu_shared_set, vcpu_pin_set) where each is a comma-separated
              list of CPU ranges.
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

    if cores_requested > 0:
        split_point = min(cores_requested, len(cpus))
    else:
        split_point = int(len(cpus) * (100 - CPU_SHARED_PERCENTAGE) / 100)

    dedicated_cpus = cpus[:split_point]
    shared_cpus = cpus[split_point:]

    return _to_ranges(shared_cpus), _to_ranges(dedicated_cpus)
