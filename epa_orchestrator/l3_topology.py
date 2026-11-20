# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Shared L3 topology and placement across cache groups."""

from dataclasses import dataclass
from typing import AbstractSet

from .schemas import L3GroupInfo
from .utils import parse_cpu_ranges, to_ranges


class PlacementError(ValueError):
    """A CPU placement failure with a stable API error code."""

    def __init__(self, code: str, message: str) -> None:
        """Provide both the wire error code and the diagnostic message."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class L3Topology:
    """Shared L3 CPU lists, retaining members outside the pool."""

    groups: tuple[frozenset[int], ...]
    online: frozenset[int]

    def claim_groups(self, ranges: str) -> list[str] | None:
        """Describe a claim when the map accounts for all its CPUs."""
        claim = parse_cpu_ranges(ranges)
        groups = [group & claim for group in self.groups]
        if sum(map(len, groups)) != len(claim):
            return None
        return [to_ranges(sorted(group)) for group in groups if group]

    def pool_groups(
        self, configured: AbstractSet[int], claimed: AbstractSet[int]
    ) -> list[L3GroupInfo]:
        """Report eligible and free CPUs, and flag online sharing outside the pool."""
        result: list[L3GroupInfo] = []
        for group in self.groups:
            online = group & self.online
            eligible = online & configured
            if eligible:
                result.append(
                    L3GroupInfo(
                        cpus=to_ranges(sorted(eligible)),
                        free=to_ranges(sorted(eligible - claimed)),
                        partial=bool(online - configured),
                    )
                )
        return result


def choose_group(
    groups: list[set[int]], count: int, without_reclamation: AbstractSet[int]
) -> set[int]:
    """Best fit, favoring placements that can avoid reclaiming CPUs."""
    fits = sorted(
        (group for group in groups if len(group) >= count),
        key=lambda group: (len(group), min(group)),
    )
    for group in fits:
        free = group & without_reclamation
        if len(free) >= count:
            return free
    return fits[0] if fits else set()


def pack_groups(
    groups: list[set[int]],
    count: int,
    numa_cpus: dict[int, set[int]],
    retained: AbstractSet[int],
) -> list[set[int]]:
    """Minimize group count, then new NUMA nodes, then prefer more capacity."""
    fullest = sorted(groups, key=lambda group: (-len(group), min(group)))
    capacity = 0
    for group_count, group in enumerate(fullest, 1):
        capacity += len(group)
        if capacity >= count:
            break
    else:
        raise ValueError(f"Insufficient CPUs available to place {count} CPUs")

    # A node contributes its largest groups for any fixed number of groups.
    node_by_cpu = {cpu: node for node, cpus in numa_cpus.items() for cpu in cpus}
    buckets: dict[int, list[int]] = {}
    for index, group in enumerate(fullest):
        nodes = {node_by_cpu.get(cpu) for cpu in group}
        if len(nodes) != 1 or None in nodes:
            # Keep optimal L3 packing if the host does not expose nested NUMA/L3 topology.
            return fullest[:group_count]
        node = node_by_cpu[min(group)]
        buckets.setdefault(node, []).append(index)
    if len(buckets) <= 1:
        return fullest[:group_count]

    retained_nodes = {node_by_cpu.get(cpu) for cpu in retained}
    indices = _pack_by_node(fullest, buckets, group_count, count, retained_nodes)
    return [fullest[index] for index in indices]


def _pack_by_node(
    groups: list[set[int]],
    buckets: dict[int, list[int]],
    group_count: int,
    count: int,
    retained_nodes: set[int | None],
) -> tuple[int, ...]:
    """Track the best capacity for each number of groups and added nodes."""
    plans: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {(0, 0): (0, ())}
    for node, indices in buckets.items():
        updated = plans.copy()
        added_node = int(node not in retained_nodes)
        for (used, nodes), (capacity, selected) in plans.items():
            new_capacity = capacity
            for take, index in enumerate(indices[: group_count - used], 1):
                new_capacity += len(groups[index])
                key = (used + take, nodes + added_node)
                new_selected = tuple(sorted((*selected, *indices[:take])))
                old_capacity, old_selected = updated.get(key, (0, ()))
                if new_capacity > old_capacity or (
                    new_capacity == old_capacity and new_selected < old_selected
                ):
                    updated[key] = (new_capacity, new_selected)
        plans = updated
    return min(
        (nodes, selected)
        for (used, nodes), (capacity, selected) in plans.items()
        if used == group_count and capacity >= count
    )[1]
