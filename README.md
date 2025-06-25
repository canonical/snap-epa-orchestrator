# EPA orchestrator

This snap provides CPU pinning information to other snaps (such as openstack-hypervisor) via a Unix socket interface.

## Purpose

The `epa-orchestrator` snap exposes logic to determine isolated and shared CPU sets for pinning, which can be consumed by other snaps through a slot/plug interface. It also tracks CPU allocations per snap in an in-memory database.

## How it works

- The snap runs a daemon that listens on a Unix domain socket.
- When a client connects and sends a request (Schema present in schemas.py), the daemon responds with the shared and dedicated CPU set.
- The logic for determining CPU pinning is in `cpu_pinning.py`.
- CPU allocations are tracked per snap name in an in-memory database.

## CPU Allocation Logic

The EPA orchestrator implements the following CPU allocation rules:

1. **When `cores_requested = 0`**: Allocates 80% of the total available CPUs (e.g., if 20 CPUs are available, 16 will be allocated)
2. **When `cores_requested > 0`**: Allocates exactly the requested number of cores
3. **Error handling**: If insufficient CPUs are available, returns an error message
4. **Tracking**: All allocations are tracked to prevent overallocation

## Request Schema

The EPA orchestrator supports two actions:

### 1. Allocate Cores (`allocate_cores`)
Request CPU allocation for a specific snap:

```json
{
    "version": "1.0",
    "snap_name": "my-snap",
    "action": "allocate_cores",
    "cores_requested": 2
}
```

**Field Usage:**
- `cores_requested`: **Required** for `allocate_cores` action
  - `0`: Allocates 80% of total CPUs
  - `> 0`: Allocates exactly the requested number of cores
  - If omitted, defaults to `0` (80% allocation)

**Examples:**
- `cores_requested: 0` → Allocates 80% of total CPUs
- `cores_requested: 2` → Allocates exactly 2 CPUs
- `cores_requested: 25` → Returns error if only 20 CPUs available

**Success Response:**
```json
{
    "version": "1.0",
    "snap_name": "my-snap",
    "cores_requested": 2,
    "cores_allocated": 2,
    "allocated_cores": "0-1",
    "shared_cpus": "2-19",
    "total_available_cpus": 20,
    "remaining_available_cpus": 18,
    "error": ""
}
```

**Error Response (insufficient CPUs):**
```json
{
    "version": "1.0",
    "snap_name": "my-snap",
    "cores_requested": 25,
    "cores_allocated": 0,
    "allocated_cores": "",
    "shared_cpus": "",
    "total_available_cpus": 20,
    "remaining_available_cpus": 4,
    "error": "Insufficient CPUs available. Requested: 25, Available: 4"
}
```

### 2. List Allocations (`list_allocations`)
Get all current snap allocations:

```json
{
    "version": "1.0",
    "snap_name": "any-snap",
    "action": "list_allocations"
}
```

**Note:** The `cores_requested` field is optional for `list_allocations` and will be ignored if provided.

**Response:**
```json
{
    "version": "1.0",
    "total_allocations": 2,
    "total_allocated_cpus": 18,
    "total_available_cpus": 20,
    "remaining_available_cpus": 2,
    "allocations": [
        {
            "snap_name": "my-snap",
            "allocated_cores": "0-15",
            "cores_count": 16
        },
        {
            "snap_name": "another-snap",
            "allocated_cores": "16-17",
            "cores_count": 2
        }
    ],
    "error": ""
}
```

## Response Field Descriptions

### Allocate Cores Response
- `snap_name`: Name of the snap that was allocated cores
- `cores_requested`: Number of cores that were requested
- `cores_allocated`: Number of cores that were actually allocated
- `allocated_cores`: Comma-separated list of allocated CPU ranges
- `shared_cpus`: Comma-separated list of shared CPU ranges
- `total_available_cpus`: Total number of CPUs available in the system
- `remaining_available_cpus`: Number of CPUs still available for allocation

### List Allocations Response
- `total_allocations`: Total number of snap allocations
- `total_allocated_cpus`: Total number of CPUs allocated across all snaps
- `total_available_cpus`: Total number of CPUs available in the system
- `remaining_available_cpus`: Number of CPUs still available for allocation
- `allocations`: List of all snap allocations with details

## Integration

- The consuming snap (e.g., openstack-hypervisor) should connect to the socket and request CPU pinning info as needed.
- The two snaps should be connected via the slot/plug mechanism in their respective snapcraft.yaml files.
- Each snap should provide its name when requesting CPU allocations.

## Development

- See `cpu_pinning.py` for the CPU pinning logic.
- See `bin/daemon` for the socket server implementation.
- See `allocations_db.py` for the in-memory database implementation.
