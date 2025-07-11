# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""In-memory database for tracking snap CPU allocations."""

import logging
from typing import Dict, Optional, Set

from .schemas import SnapAllocation


class AllocationsDB:
    """In-memory database for tracking snap CPU allocations."""

    def __init__(self) -> None:
        """Initialize the allocations database."""
        self._allocations: Dict[str, str] = {}
        self._allocated_cpus: Set[int] = set()
        logging.info("Allocations database initialized")

    def _parse_cpu_ranges(self, cpu_ranges: str) -> set[int]:
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

        cpus: set[int] = set()
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

    def get_available_cpus(self, total_cpus: str) -> list[int]:
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

    def allocate_cores(self, service_name: str, allocated_cores: str) -> None:
        """Allocate cores to a service.

        Args:
            service_name: Name of the service
            allocated_cores: Comma-separated list of CPU ranges allocated to the service
        """
        if allocated_cores:
            # Remove any existing allocation for this service
            if service_name in self._allocations:
                old_cores = self._allocations[service_name]
                old_cpu_set = self._parse_cpu_ranges(old_cores)
                self._allocated_cpus -= old_cpu_set

            # Add new allocation
            self._allocations[service_name] = allocated_cores
            new_cpu_set = self._parse_cpu_ranges(allocated_cores)
            self._allocated_cpus.update(new_cpu_set)
            logging.info(f"Allocated cores {allocated_cores} to service {service_name}")
        else:
            logging.warning(f"No cores allocated to service {service_name}")

    def get_allocation(self, service_name: str) -> Optional[str]:
        """Get the allocated cores for a specific service.

        Args:
            service_name: Name of the service

        Returns:
            Comma-separated list of CPU ranges allocated to the service, or None if not found
        """
        return self._allocations.get(service_name)

    def get_all_allocations(self) -> list[SnapAllocation]:
        """Get all service allocations.

        Returns:
            List of SnapAllocation objects
        """
        return [
            SnapAllocation(
                service_name=service_name,
                allocated_cores=cores,
                cores_count=len(self._parse_cpu_ranges(cores)),
            )
            for service_name, cores in self._allocations.items()
        ]

    def remove_allocation(self, service_name: str) -> bool:
        """Remove allocation for a specific service.

        Args:
            service_name: Name of the service

        Returns:
            True if allocation was removed, False if not found
        """
        if service_name in self._allocations:
            cores = self._allocations[service_name]
            cpu_set = self._parse_cpu_ranges(cores)
            self._allocated_cpus -= cpu_set
            del self._allocations[service_name]
            logging.info(f"Removed allocation for service {service_name}")
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

    def get_snap_allocation_count(self, service_name: str) -> int:
        """Get the number of CPUs allocated to a specific service.

        Args:
            service_name: Name of the service

        Returns:
            Number of CPUs allocated to the service, or 0 if not found
        """
        allocation = self._allocations.get(service_name)
        if allocation:
            return len(self._parse_cpu_ranges(allocation))
        return 0

    def get_system_stats(self, total_cpus: str) -> dict[str, int]:
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
allocations_db: AllocationsDB = AllocationsDB()
