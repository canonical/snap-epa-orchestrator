# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""In-memory database for tracking snap CPU allocations."""

import logging
from typing import Dict, Optional, Set, Tuple

from .schemas import SnapAllocation
from .utils import to_ranges


class AllocationsDB:
    """In-memory database for tracking snap CPU allocations."""

    def __init__(self) -> None:
        """Initialize the allocations database."""
        self._allocations: Dict[str, str] = {}
        self._allocated_cpus: Set[int] = set()
        self._explicit_allocations: Dict[str, str] = {}
        self._explicitly_allocated_cpus: Set[int] = set()
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

    def _remove_service_allocation(self, service_name: str) -> set[int]:
        """Remove any allocation for a service and return removed CPU set."""
        removed: set[int] = set()
        if service_name in self._allocations:
            old_cores = self._allocations.pop(service_name)
            removed = self._parse_cpu_ranges(old_cores)
            self._allocated_cpus -= removed
        if service_name in self._explicit_allocations:
            old_explicit = self._parse_cpu_ranges(self._explicit_allocations.pop(service_name))
            self._explicitly_allocated_cpus -= old_explicit
        return removed

    def _apply_allocation(self, service_name: str, cpu_set: set[int], explicit: bool) -> None:
        """Apply an allocation to a service, updating all tracking structures."""
        if not cpu_set:
            return
        cores_str = to_ranges(sorted(cpu_set))
        self._allocations[service_name] = cores_str
        self._allocated_cpus.update(cpu_set)
        if explicit:
            self._explicit_allocations[service_name] = cores_str
            self._explicitly_allocated_cpus.update(cpu_set)
        elif service_name in self._explicit_allocations:
            del self._explicit_allocations[service_name]

    def _subtract_cpus_from_service(self, service_name: str, cpus_to_remove: set[int]) -> None:
        """Subtract given CPUs from a service allocation, remove entry if empty."""
        if service_name not in self._allocations:
            return
        current_set = self._parse_cpu_ranges(self._allocations[service_name])
        if not (current_set & cpus_to_remove):
            return
        remaining = current_set - cpus_to_remove
        # Update global allocated CPUs
        self._allocated_cpus -= current_set & cpus_to_remove
        # Handle explicit tracking if needed
        if service_name in self._explicit_allocations:
            explicit_set = self._parse_cpu_ranges(self._explicit_allocations[service_name])
            explicit_remaining = explicit_set - cpus_to_remove
            self._explicitly_allocated_cpus -= explicit_set & cpus_to_remove
            if explicit_remaining:
                self._explicit_allocations[service_name] = to_ranges(sorted(explicit_remaining))
            else:
                del self._explicit_allocations[service_name]
        if remaining:
            self._allocations[service_name] = to_ranges(sorted(remaining))
        else:
            del self._allocations[service_name]

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
        if not allocated_cores:
            logging.warning(f"No cores allocated to service {service_name}")
            return
        self._remove_service_allocation(service_name)
        new_cpu_set = self._parse_cpu_ranges(allocated_cores)
        self._apply_allocation(service_name, new_cpu_set, explicit=False)
        logging.info(f"Allocated cores {allocated_cores} to service {service_name}")

    def explicitly_allocate_cores(
        self, service_name: str, requested_cores: str
    ) -> Tuple[str, str]:
        """Explicitly allocate specific cores to a service, overriding existing allocations.

        Args:
            service_name: Name of the requesting service
            requested_cores: Comma-separated list of specific CPU ranges to allocate

        Returns:
            Tuple of (allocated_cores, rejected_cores) where each is a comma-separated
            list of CPU ranges. Rejected cores are those already explicitly allocated
            to another service.
        """
        if not requested_cores.strip():
            return "", ""

        requested_cpu_set = self._parse_cpu_ranges(requested_cores)
        if not requested_cpu_set:
            return "", ""

        own_explicit_set = self._parse_cpu_ranges(self._explicit_allocations.get(service_name, ""))
        other_explicit_cpus = self._explicitly_allocated_cpus - own_explicit_set
        rejected_cpus = requested_cpu_set & other_explicit_cpus
        allocatable_cpus = requested_cpu_set - rejected_cpus

        if allocatable_cpus:
            self._remove_service_allocation(service_name)
            for existing_service in list(self._allocations.keys()):
                if existing_service == service_name:
                    continue
                self._subtract_cpus_from_service(existing_service, allocatable_cpus)
            self._apply_allocation(service_name, allocatable_cpus, explicit=True)
            logging.info(
                f"Explicitly allocated cores {to_ranges(sorted(allocatable_cpus))} to service {service_name}"
            )

        allocated_cores_str = to_ranges(sorted(allocatable_cpus)) if allocatable_cpus else ""
        rejected_cores_str = to_ranges(sorted(rejected_cpus)) if rejected_cpus else ""
        return allocated_cores_str, rejected_cores_str

    def get_allocation(self, service_name: str) -> Optional[str]:
        """Get the allocated cores for a specific service.

        Args:
            service_name: Name of the service

        Returns:
            Comma-separated list of CPU ranges allocated to the service, or None if not found
        """
        return self._allocations.get(service_name)

    def is_explicit_allocation(self, service_name: str) -> bool:
        """Check if a service has an explicit allocation.

        Args:
            service_name: Name of the service

        Returns:
            True if the service has an explicit allocation, False otherwise
        """
        return service_name in self._explicit_allocations

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
                is_explicit=service_name in self._explicit_allocations,
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
        if service_name in self._allocations or service_name in self._explicit_allocations:
            self._remove_service_allocation(service_name)
            logging.info(f"Removed allocation for service {service_name}")
            return True
        return False

    def clear_all_allocations(self) -> None:
        """Clear all allocations."""
        self._allocations.clear()
        self._allocated_cpus.clear()
        self._explicit_allocations.clear()
        self._explicitly_allocated_cpus.clear()
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


allocations_db: AllocationsDB = AllocationsDB()
