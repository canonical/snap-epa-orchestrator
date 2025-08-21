# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Daemon handler for EPA Orchestrator."""

import json
import logging
from typing import Union

from pydantic import ValidationError

from epa_orchestrator.allocations_db import allocations_db
from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.schemas import (
    ActionType,
    AllocateCoresRequest,
    AllocateCoresResponse,
    ErrorResponse,
    ExplicitlyAllocateCoresRequest,
    ExplicitlyAllocateCoresResponse,
    ExplicitlyAllocateNumaCoresRequest,
    ExplicitlyAllocateNumaCoresResponse,
    ListAllocationsRequest,
    ListAllocationsResponse,
    SnapAllocation,
)
from epa_orchestrator.utils import _count_cpus_in_ranges

from .utils import parse_cpu_ranges

logging.basicConfig(level=logging.INFO)


def handle_allocate_cores(request: AllocateCoresRequest) -> AllocateCoresResponse:
    """Handle allocate cores action.

    Args:
        request: The EPA request

    Returns:
        AllocateCoresResponse with detailed allocation information
    """
    try:
        isolated = get_isolated_cpus()
    except RuntimeError as e:
        raise ValueError("No Isolated CPUs configured") from e
    if not isolated:
        raise ValueError("No CPUs available")

    # Get system statistics
    stats = allocations_db.get_system_stats(isolated)

    # Get cores requested (default to 0 if None)
    cores_requested = request.cores_requested or 0

    # Check if we can allocate the requested CPUs
    if cores_requested > 0:
        if not allocations_db.can_allocate_cpus(cores_requested, isolated):
            available_cpus = allocations_db.get_available_cpus(isolated)
            raise ValueError(
                f"Insufficient CPUs available. Requested: {cores_requested}, Available: {len(available_cpus)}"
            )

    # Calculate CPU allocation
    shared, dedicated = calculate_cpu_pinning(isolated, cores_requested)

    if not dedicated:
        raise ValueError(f"Failed to allocate {cores_requested} cores")

    # Store the allocation in the database
    allocations_db.allocate_cores(request.service_name, dedicated)

    # Get updated statistics after allocation
    updated_stats = allocations_db.get_system_stats(isolated)
    cores_allocated = _count_cpus_in_ranges(dedicated)

    return AllocateCoresResponse(
        service_name=request.service_name,
        cores_requested=cores_requested,
        cores_allocated=cores_allocated,
        allocated_cores=dedicated,
        shared_cpus=shared,
        total_available_cpus=stats["total_available_cpus"],
        remaining_available_cpus=updated_stats["remaining_available_cpus"],
    )


def handle_explicitly_allocate_cores(
    request: ExplicitlyAllocateCoresRequest,
) -> ExplicitlyAllocateCoresResponse:
    """Handle explicit allocate cores action.

    Args:
        request: The EPA request for explicit core allocation

    Returns:
        ExplicitlyAllocateCoresResponse with allocation results
    """
    try:
        isolated = get_isolated_cpus()
    except RuntimeError as e:
        raise ValueError("No Isolated CPUs configured") from e
    if not isolated:
        raise ValueError("No CPUs available")

    stats = allocations_db.get_system_stats(isolated)

    requested_cpu_set = parse_cpu_ranges(request.cores_requested)
    isolated_cpu_set = parse_cpu_ranges(isolated)

    invalid_cpus = requested_cpu_set - isolated_cpu_set
    if invalid_cpus:
        raise ValueError(
            f"Requested cores {invalid_cpus} are not available in isolated CPUs: {isolated}"
        )

    allocated_cores, rejected_cores = allocations_db.explicitly_allocate_cores(
        request.service_name, request.cores_requested
    )

    if not allocated_cores:
        raise ValueError(
            f"Failed to allocate requested explicit cores; conflicts with existing explicit allocations: {rejected_cores}"
        )

    updated_stats = allocations_db.get_system_stats(isolated)

    return ExplicitlyAllocateCoresResponse(
        service_name=request.service_name,
        cores_requested=request.cores_requested,
        cores_allocated=allocated_cores,
        total_available_cpus=stats["total_available_cpus"],
        remaining_available_cpus=updated_stats["remaining_available_cpus"],
    )


def handle_explicitly_allocate_numa_cores(
    request: ExplicitlyAllocateNumaCoresRequest,
) -> ExplicitlyAllocateNumaCoresResponse:
    """Handle explicit NUMA allocate cores action.

    Args:
        request: The EPA request for explicit NUMA core allocation

    Returns:
        ExplicitlyAllocateNumaCoresResponse with allocation results
    """
    from epa_orchestrator.utils import get_cpus_in_numa_node, get_numa_node_cpus

    isolated = get_isolated_cpus()
    stats = allocations_db.get_system_stats(isolated)
    numa_cpus = get_numa_node_cpus()

    if request.numa_node not in numa_cpus:
        raise ValueError(f"NUMA node {request.numa_node} does not exist")
    available_numa_cpus = get_cpus_in_numa_node(request.numa_node, isolated)

    if not available_numa_cpus:
        raise ValueError(f"No isolated CPUs available in NUMA node {request.numa_node}")

    if len(available_numa_cpus) < request.num_of_cores and request.num_of_cores != 0:
        raise ValueError(
            f"NUMA node {request.numa_node} only has {len(available_numa_cpus)} "
            f"isolated CPUs, but {request.num_of_cores} were requested"
        )

    allocated_cores, _ = allocations_db.explicitly_allocate_numa_cores(
        request.service_name, request.numa_node, request.num_of_cores
    )

    # For deallocation (num_of_cores==0), we return empty cores_allocated as success
    if request.num_of_cores != 0 and not allocated_cores:
        raise ValueError(
            f"Failed to allocate cores from NUMA node {request.numa_node}. "
            f"All requested cores may be explicitly allocated to other services."
        )

    updated_stats = allocations_db.get_system_stats(isolated)

    return ExplicitlyAllocateNumaCoresResponse(
        service_name=request.service_name,
        numa_node=request.numa_node,
        num_of_cores=request.num_of_cores,
        cores_allocated=allocated_cores,
        total_available_cpus=stats["total_available_cpus"],
        remaining_available_cpus=updated_stats["remaining_available_cpus"],
    )


def handle_list_allocations(request: ListAllocationsRequest) -> ListAllocationsResponse:
    """Handle list allocations action.

    Returns:
        ListAllocationsResponse with detailed allocation information
    """
    try:
        isolated = get_isolated_cpus()
    except RuntimeError:
        # Return empty response when no isolated CPUs are configured
        return ListAllocationsResponse(
            total_allocations=0,
            total_allocated_cpus=0,
            total_available_cpus=0,
            remaining_available_cpus=0,
            allocations=[],
        )
    if not isolated:
        # Return empty response when no isolated CPUs are available
        return ListAllocationsResponse(
            total_allocations=0,
            total_allocated_cpus=0,
            total_available_cpus=0,
            remaining_available_cpus=0,
            allocations=[],
        )

    # Get system statistics
    stats = allocations_db.get_system_stats(isolated)

    # Build detailed allocation list
    allocations = []
    for service_name, allocated_cores in allocations_db._allocations.items():
        cores_count = allocations_db.get_snap_allocation_count(service_name)
        is_explicit = allocations_db.is_explicit_allocation(service_name)
        allocations.append(
            SnapAllocation(
                service_name=service_name,
                allocated_cores=allocated_cores,
                cores_count=cores_count,
                is_explicit=is_explicit,
            )
        )

    return ListAllocationsResponse(
        total_allocations=stats["total_allocations"],
        total_allocated_cpus=stats["total_allocated_cpus"],
        total_available_cpus=stats["total_available_cpus"],
        remaining_available_cpus=stats["remaining_available_cpus"],
        allocations=allocations,
    )


def handle_daemon_request(data: bytes) -> bytes:
    """Handle daemon request.

    Args:
        data: The request data

    Returns:
        The response data
    """
    try:
        request_data = json.loads(data.decode())
        action_value = request_data.get("action")

        response: Union[
            AllocateCoresResponse,
            ExplicitlyAllocateCoresResponse,
            ExplicitlyAllocateNumaCoresResponse,
            ListAllocationsResponse,
            ErrorResponse,
        ]

        if action_value in (
            ActionType.ALLOCATE_CORES,
            ActionType.ALLOCATE_CORES.value,
            "allocate_cores",
        ):
            ac_req: AllocateCoresRequest = AllocateCoresRequest.parse_obj(request_data)
            response = handle_allocate_cores(ac_req)
        elif action_value in (
            ActionType.EXPLICITLY_ALLOCATE_CORES,
            ActionType.EXPLICITLY_ALLOCATE_CORES.value,
            "explicitly_allocate_cores",
        ):
            ex_req: ExplicitlyAllocateCoresRequest = ExplicitlyAllocateCoresRequest.parse_obj(
                request_data
            )
            response = handle_explicitly_allocate_cores(ex_req)
        elif action_value in (
            ActionType.EXPLICITLY_ALLOCATE_NUMA_CORES,
            ActionType.EXPLICITLY_ALLOCATE_NUMA_CORES.value,
            "explicitly_allocate_numa_cores",
        ):
            numa_req: ExplicitlyAllocateNumaCoresRequest = (
                ExplicitlyAllocateNumaCoresRequest.parse_obj(request_data)
            )
            response = handle_explicitly_allocate_numa_cores(numa_req)
        elif action_value in (
            ActionType.LIST_ALLOCATIONS,
            ActionType.LIST_ALLOCATIONS.value,
            "list_allocations",
        ):
            la_req: ListAllocationsRequest = ListAllocationsRequest.parse_obj(request_data)
            response = handle_list_allocations(la_req)
        else:
            response = ErrorResponse(
                error=f"Unknown action: {action_value}",
                version="1.0",
            )

        return response.json().encode()
    except (ValidationError, json.JSONDecodeError) as e:
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.json().encode()
    except ValueError as e:
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.json().encode()
    except Exception as e:
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.json().encode()
