# Contributing

## Overview

This document explains the processes and practices recommended for contributing enhancements to
the EPA Orchestrator snap.

- Generally, before developing enhancements to this snap, you should consider [opening an issue
  ](https://github.com/canonical/snap-epa-orchestrator/issues) explaining your use case.
- If you would like to chat with us about your use-cases or proposed implementation, you can reach
  us at [Canonical Mattermost public channel](https://chat.canonical.com/canonical/channels/sunbeam)
- Familiarising yourself with [Snaps and Snapcraft](https://snapcraft.io/docs) documentation
  will help you a lot when working on new features or bug fixes.
- All enhancements require review before being merged. Code review typically examines
  - code quality
  - test coverage
- Please help us out in ensuring easy to review branches by rebasing your pull request branch onto
  the `main` branch. This also avoids merge commits and creates a linear Git commit history.

## Developing

You can use the environments created by `tox` for development:

```shell
tox --notest -e unit
source .tox/unit/bin/activate
```

### Testing

The project includes a comprehensive test suite with both unit and integration tests:

```shell
tox -e fmt           # update your code according to linting rules
tox -e lint          # code style
tox -e unit          # run unit tests
tox -e integration   # run integration tests
tox                  # runs 'lint' and 'unit' environments
```

#### Test Structure

- **Unit Tests** (`tests/unit/`): 16 tests covering core functionality

  - `test_allocations_db.py`: Database operations and CPU allocation tracking
  - `test_cpu_pinning.py`: CPU pinning logic and isolated CPU detection
  - `test_schemas.py`: Request/response schema validation
  - `test_utils.py`: Utility functions
  - `test_daemon_integration.py`: Daemon request processing logic

- **Integration Tests** (`tests/integration/`): 1 test covering end-to-end functionality
  - `test_socket_communication.py`: Real socket communication with daemon functionality

#### Running Tests Directly

```shell
# Run all tests
pytest tests/ -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/ --cov=epa_orchestrator --cov-report=html
```

## Build Snap

Build the snap in this git repository using:

```shell
snapcraft --use-lxd
```

### Deploy

```bash
# Install the development snap
sudo snap install --devmode epa-orchestrator_*.snap

# The daemon will start automatically and listen on the Unix socket
# Socket path: $SNAP_DATA/data/epa.sock
```

## Canonical Contributor Agreement

Canonical welcomes contributions to the EPA Orchestrator snap. Please check
out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're
interested in contributing to the solution.
