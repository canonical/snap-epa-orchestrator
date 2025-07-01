# EPA Orchestrator Snap

This repository contains the source for the EPA Orchestrator snap.

**EPA Orchestrator** is designed to provide secure, policy-driven resource orchestration for snaps and workloads on Linux systems. Its vision is to enable fine-grained, dynamic allocation and management of system resources—starting with CPU pinning, but with plans to expand to other resource types and orchestration policies. The orchestrator exposes a secure Unix socket API for resource allocation and introspection, making it easy for other snaps (such as openstack-hypervisor) and workloads to request and manage dedicated or shared resources in a controlled manner.

## Features

- **CPU Pinning and Allocation**: Dynamically allocate isolated and shared CPU sets to snaps and workloads, supporting both dedicated and shared CPU usage models.
- **Resource Introspection**: Query current allocations and available resources via a secure API.
- **Snap Integration**: Designed for seamless integration with other snaps (e.g., openstack-hypervisor) using the slot/plug mechanism.
- **Secure Unix Socket API**: All orchestration actions are performed via a secure, local Unix socket with JSON-based requests and responses.
- **Policy-Driven Design**: Built to support future policy enforcement for resource allocation and isolation.

### Planned Features

- **Memory Pinning and Allocation**: Enable allocation and isolation of memory resources for snaps and workloads.

## Getting Started

To get started with the EPA Orchestrator, install the snap using snapd:

```bash
sudo snap install epa-orchestrator --dangerous --devmode
```

The snap runs a daemon that listens on a Unix domain socket and provides a JSON API for CPU allocation and introspection.

## Configuration Reference

The EPA Orchestrator snap does not require complex configuration for basic operation. However, it can be integrated with other snaps (e.g., openstack-hypervisor) via the slot/plug mechanism for EPA information sharing.

### API Usage

The daemon listens on:

```
$SNAP_DATA/data/epa.sock
```

Clients can connect to this socket and send JSON requests. The supported actions are:

#### 1. Allocate Cores (`allocate_cores`)

Request CPU allocation for a specific snap:

```json
{
  "version": "1.0",
  "snap_name": "my-snap",
  "action": "allocate_cores",
  "cores_requested": 2
}
```

- `cores_requested`: Number of cores to allocate (0 = 80% of total CPUs)

#### 2. List Allocations (`list_allocations`)

Get all current snap allocations:

```json
{
  "version": "1.0",
  "snap_name": "any-snap",
  "action": "list_allocations"
}
```

### Response Example

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

## Build

To build and test the snap, see CONTRIBUTING.md for full details. Typical steps:

```bash
# Build the snap
snapcraft --use-lxd

# Install the snap
sudo snap install --dangerous epa-orchestrator_*.snap
```

## Testing

The project includes unit, integration, and functional tests. To run all tests:

```bash
tox
```

Or run specific test environments:

```bash
tox -e unit
tox -e integration
tox -e lint
tox -e fmt
```

**Note:** Functional tests require sudo privileges for snap installation and management.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
