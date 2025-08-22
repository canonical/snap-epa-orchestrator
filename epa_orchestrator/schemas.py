# SPDX-FileCopyrightText: 2024 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0
"""Pydantic schemas for socket communication."""
from enum import Enum
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

API_VERSION: Literal["1.0"] = "1.0"


class ActionType(str, Enum):
    """Enum for different action types."""

    ALLOCATE_CORES = "allocate_cores"
    LIST_ALLOCATIONS = "list_allocations"
    ALLOCATE_NUMA_CORES = "allocate_numa_cores"


class AllocateCoresRequest(BaseModel):
    """Request model for allocating cores (non-NUMA)."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    action: Literal[ActionType.ALLOCATE_CORES]
    service_name: str = Field(description="Name of the requesting service")
    num_of_cores: int = Field(
        default=0,
        description=("Number of dedicated cores requested. 0 keeps default policy."),
    )
    numa_node: Optional[int] = Field(
        default=None, ge=0, description="NUMA node (must be omitted for allocate_cores)"
    )


class ListAllocationsRequest(BaseModel):
    """Request model for listing allocations."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    action: Literal[ActionType.LIST_ALLOCATIONS]
    service_name: str = Field(description="Name of the requesting service")


class AllocateNumaCoresRequest(BaseModel):
    """Request model for allocating cores from a specific NUMA node.

    Note:
        - num_of_cores > 0: allocate exactly that many cores from the node
        - num_of_cores == -1: deallocate existing cores for this service in the node
        - num_of_cores == 0: invalid
    """

    version: Literal["1.0"] = Field(default=API_VERSION)
    action: Literal[ActionType.ALLOCATE_NUMA_CORES]
    service_name: str = Field(description="Name of the requesting service")
    numa_node: int = Field(ge=0, description="NUMA node to allocate cores from")
    num_of_cores: int = Field(description="Number of cores to allocate (-1 to deallocate)")


EpaRequest = Annotated[
    Union[
        AllocateCoresRequest,
        AllocateNumaCoresRequest,
        ListAllocationsRequest,
    ],
    Field(discriminator="action"),
]


class AllocateCoresResponse(BaseModel):
    """Pydantic model for allocate cores response."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    service_name: str = Field(description="Name of the service that was allocated cores")
    num_of_cores: int = Field(description="Number of cores that were requested")
    cores_allocated: int = Field(description="Number of cores that were actually allocated")
    allocated_cores: str = Field(description="Comma-separated list of allocated CPU ranges")
    shared_cpus: str = Field(description="Comma-separated list of shared CPU ranges")
    total_available_cpus: int = Field(description="Total number of CPUs available in the system")
    remaining_available_cpus: int = Field(
        description="Number of CPUs still available for allocation"
    )


class AllocateNumaCoresResponse(BaseModel):
    """Pydantic model for NUMA allocate cores response."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    service_name: str = Field(description="Name of the service that was allocated cores")
    numa_node: int = Field(description="NUMA node cores were allocated from")
    num_of_cores: int = Field(description="Number of cores that were requested (or -1 to dealloc)")
    cores_allocated: str = Field(description="Cores that were actually allocated")
    total_available_cpus: int = Field(description="Total number of CPUs available in the system")
    remaining_available_cpus: int = Field(
        description="Number of CPUs still available for allocation"
    )


class SnapAllocation(BaseModel):
    """Model for service allocation information."""

    service_name: str = Field(description="Name of the service")
    allocated_cores: str = Field(description="Comma-separated list of allocated CPU ranges")
    cores_count: int = Field(description="Number of cores allocated to this service")
    is_explicit: bool = Field(
        default=False, description="Whether this allocation was made explicitly"
    )


class ListAllocationsResponse(BaseModel):
    """Pydantic model for list allocations response."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    total_allocations: int = Field(description="Total number of service allocations")
    total_allocated_cpus: int = Field(
        description="Total number of CPUs allocated across all services"
    )
    total_available_cpus: int = Field(description="Total number of CPUs available in the system")
    remaining_available_cpus: int = Field(
        description="Number of CPUs still available for allocation"
    )
    allocations: List[SnapAllocation] = Field(description="List of all service allocations")


class ErrorResponse(BaseModel):
    """Pydantic model for error responses."""

    version: Literal["1.0"] = Field(default=API_VERSION)
    error: str
