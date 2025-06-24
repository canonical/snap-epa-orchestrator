# EPA orchestrator

This snap provides CPU pinning information to other snaps (such as openstack-hypervisor) via a Unix socket interface.

## Purpose

The `epa-orchestrator` snap exposes logic to determine isolated and shared CPU sets for pinning, which can be consumed by other snaps through a slot/plug interface.

## How it works

- The snap runs a daemon that listens on a Unix domain socket.
- When a client connects and sends the message for pinned CPUs (Schema present in schemas.py), the daemon responds with the shared and dedicated CPU set.
- The logic for determining CPU pinning is in `cpu_pinning.py`.

## Integration

- The consuming snap (e.g., openstack-hypervisor) should connect to the socket and request CPU pinning info as needed.
- The two snaps should be connected via the slot/plug mechanism in their respective snapcraft.yaml files.

## Development

- See `cpu_pinning.py` for the logic.
- See `daemon.py` for the socket server implementation.
