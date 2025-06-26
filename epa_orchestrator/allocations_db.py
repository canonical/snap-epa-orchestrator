# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""In-memory database for tracking snap CPU allocations."""

import logging
from typing import Dict, List, Optional, Set

from .schemas import SnapAllocation


class AllocationsDB:
    """In-memory database for tracking snap CPU allocations."""

    def __init__(self):
        """Initialize the allocations database."""
        self._allocations: Dict[str, str] = {}
        self._allocated_cpus: Set[int] = set()
        logging.info("Allocations database initialized")

    def _parse_cpu_ranges(self, cpu_ranges: str) -> Set[int]:
        """Parse CPU ranges string into a set of CPU numbers.

        Args:
            cpu_ranges: Comma-separated list of CPU ranges (e.g., "0-2,4,6-8")

        Returns:
            Set of CPU numbers

        Raises:
            ValueError: If CPU ranges are invalid (e.g., reverse ranges like "3-1")
        """
        if not cpu_ranges.strip():
            return set()

        cpus = set()
        for part in cpu_ranges.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = map(int, part.split("-"))
                if start > end:
                    raise ValueError(f"Invalid CPU range: {part} (start > end)")
                cpus.update(range(start, end + 1))
            else:
                cpus.add(int(part))
        return cpus

    def get_available_cpus(self, total_cpus: str) -> List[int]:
        """Get list of available CPUs that haven't been allocated.

        Args:
            total_cpus: Comma-separated list of all available CPU ranges

        Returns:
            List of available CPU numbers
        """
        all_cpus = self._parse_cpu_ranges(total_cpus)
        available_cpus = sorted(list(all_cpus - self._allocated_cpus))
        return available_cpus

    def can_allocate_cpus(self, requested_count: int, total_cpus: str) -> bool:
        """Check if requested number of CPUs can be allocated.

        Args:
            requested_count: Number of CPUs requested
            total_cpus: Comma-separated list of all available CPU ranges

        Returns:
            True if allocation is possible, False otherwise
        """
        available_cpus = self.get_available_cpus(total_cpus)
        return len(available_cpus) >= requested_count

    def allocate_cores(self, snap_name: str, allocated_cores: str) -> None:
        """Allocate cores to a snap.

        Args:
            snap_name: Name of the snap
            allocated_cores: Comma-separated list of CPU ranges allocated to the snap
        """
        if allocated_cores:
            # Remove any existing allocation for this snap
            if snap_name in self._allocations:
                old_cores = self._allocations[snap_name]
                old_cpu_set = self._parse_cpu_ranges(old_cores)
                self._allocated_cpus -= old_cpu_set

            # Add new allocation
            self._allocations[snap_name] = allocated_cores
            new_cpu_set = self._parse_cpu_ranges(allocated_cores)
            self._allocated_cpus.update(new_cpu_set)
            logging.info(f"Allocated cores {allocated_cores} to snap {snap_name}")
        else:
            logging.warning(f"No cores allocated to snap {snap_name}")

    def get_allocation(self, snap_name: str) -> Optional[str]:
        """Get the allocated cores for a specific snap.

        Args:
            snap_name: Name of the snap

        Returns:
            Comma-separated list of CPU ranges allocated to the snap, or None if not found
        """
        return self._allocations.get(snap_name)

    def get_all_allocations(self) -> List[SnapAllocation]:
        """Get all snap allocations.

        Returns:
            List of SnapAllocation objects
        """
        return [
            SnapAllocation(
                snap_name=snap_name,
                allocated_cores=cores,
                cores_count=len(self._parse_cpu_ranges(cores)),
            )
            for snap_name, cores in self._allocations.items()
        ]

    def remove_allocation(self, snap_name: str) -> bool:
        """Remove allocation for a specific snap.

        Args:
            snap_name: Name of the snap

        Returns:
            True if allocation was removed, False if not found
        """
        if snap_name in self._allocations:
            cores = self._allocations[snap_name]
            cpu_set = self._parse_cpu_ranges(cores)
            self._allocated_cpus -= cpu_set
            del self._allocations[snap_name]
            logging.info(f"Removed allocation for snap {snap_name}")
            return True
        return False

    def clear_all_allocations(self) -> None:
        """Clear all allocations."""
        self._allocations.clear()
        self._allocated_cpus.clear()
        logging.info("Cleared all allocations")

    def get_total_allocated_count(self) -> int:
        """Get the total number of allocated CPUs.

        Returns:
            Number of allocated CPUs
        """
        return len(self._allocated_cpus)

    def get_snap_allocation_count(self, snap_name: str) -> int:
        """Get the number of CPUs allocated to a specific snap.

        Args:
            snap_name: Name of the snap

        Returns:
            Number of CPUs allocated to the snap, or 0 if not found
        """
        allocation = self._allocations.get(snap_name)
        if allocation:
            return len(self._parse_cpu_ranges(allocation))
        return 0

    def get_system_stats(self, total_cpus: str) -> dict:
        """Get system statistics for CPU allocation.

        Args:
            total_cpus: Comma-separated list of all available CPU ranges

        Returns:
            Dictionary with system statistics
        """
        total_available = len(self._parse_cpu_ranges(total_cpus))
        total_allocated = len(self._allocated_cpus)
        remaining_available = total_available - total_allocated

        return {
            "total_available_cpus": total_available,
            "total_allocated_cpus": total_allocated,
            "remaining_available_cpus": remaining_available,
            "total_allocations": len(self._allocations),
        }


# Global instance of the allocations database
allocations_db = AllocationsDB()
