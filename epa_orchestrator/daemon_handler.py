# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""Daemon handler for EPA Orchestrator."""

import json
import logging
from typing import Union

from pydantic import TypeAdapter, ValidationError

from epa_orchestrator.allocations_db import allocations_db
from epa_orchestrator.cpu_pinning import calculate_cpu_pinning, get_isolated_cpus
from epa_orchestrator.schemas import (
    AllocateCoresRequest,
    AllocateCoresResponse,
    EpaRequest,
    ErrorResponse,
    ListAllocationsRequest,
    ListAllocationsResponse,
    SnapAllocation,
)
from epa_orchestrator.utils import _count_cpus_in_ranges

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
    allocations_db.allocate_cores(request.snap_name, dedicated)

    # Get updated statistics after allocation
    updated_stats = allocations_db.get_system_stats(isolated)
    cores_allocated = _count_cpus_in_ranges(dedicated)

    return AllocateCoresResponse(
        snap_name=request.snap_name,
        cores_requested=cores_requested,
        cores_allocated=cores_allocated,
        allocated_cores=dedicated,
        shared_cpus=shared,
        total_available_cpus=stats["total_available_cpus"],
        remaining_available_cpus=updated_stats["remaining_available_cpus"],
    )


def handle_list_allocations(request: ListAllocationsRequest) -> ListAllocationsResponse:
    """Handle list allocations action.

    Returns:
        ListAllocationsResponse with detailed allocation information
    """
    isolated = get_isolated_cpus()
    if not isolated:
        raise ValueError("No CPUs available")

    # Get system statistics
    stats = allocations_db.get_system_stats(isolated)

    # Build detailed allocation list
    allocations = []
    for snap_name, allocated_cores in allocations_db._allocations.items():
        cores_count = allocations_db.get_snap_allocation_count(snap_name)
        allocations.append(
            SnapAllocation(
                snap_name=snap_name, allocated_cores=allocated_cores, cores_count=cores_count
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
        request: Union[AllocateCoresRequest, ListAllocationsRequest] = TypeAdapter(
            EpaRequest
        ).validate_python(request_data)
        response: Union[AllocateCoresResponse, ListAllocationsResponse, ErrorResponse]
        if isinstance(request, AllocateCoresRequest):
            response = handle_allocate_cores(request)
        elif isinstance(request, ListAllocationsRequest):
            response = handle_list_allocations(request)
        else:
            response = ErrorResponse(
                error=f"Unknown action: {getattr(request, 'action', None)}",
                version="1.0",
            )
        return response.model_dump_json().encode()
    except (ValidationError, json.JSONDecodeError) as e:
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.model_dump_json().encode()
    except ValueError as e:
        if str(e) == "No Isolated CPUs configured":
            error_response = ErrorResponse(
                error="No Isolated CPUs configured",
                version="1.0",
            )
            return error_response.model_dump_json().encode()
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.model_dump_json().encode()
    except Exception as e:
        error_response = ErrorResponse(
            error=str(e),
            version="1.0",
        )
        return error_response.model_dump_json().encode()
