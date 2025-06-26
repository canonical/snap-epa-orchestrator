# EPA Orchestrator Tests

This directory contains comprehensive tests for the EPA Orchestrator snap project.

## Test Structure

```
tests/
├── README.md                    # This file
├── conftest.py                  # Shared pytest fixtures
├── unit/                        # Unit tests
│   ├── __init__.py
│   ├── test_utils.py            # Tests for utils module
│   ├── test_cpu_pinning.py      # Tests for cpu_pinning module
│   ├── test_schemas.py          # Tests for schemas module
│   ├── test_allocations_db.py   # Tests for allocations_db module
│   └── test_daemon_integration.py # Tests for daemon integration
└── integration/                 # Integration tests
    ├── __init__.py
    └── test_socket_communication.py # Socket communication tests
```

## Running Tests

### Quick Start

Run all tests and checks:

```bash
tox
```

### Individual Test Types

Run only unit tests:

```bash
tox -e unit
```

Run only integration tests:

```bash
tox -e integration
```

Run linting checks:

```bash
tox -e lint
```

Format code:

```bash
tox -e fmt
```

### Using Pytest Directly

Run specific test file:

```bash
pytest tests/unit/test_cpu_pinning.py -v
```

Run tests with coverage:

```bash
pytest tests/unit/ --cov=epa_orchestrator --cov-report=html
```

## Test Categories

### Unit Tests (`tests/unit/`)

- **test_utils.py**: Tests for utility functions like `to_ranges()`
- **test_cpu_pinning.py**: Tests for CPU pinning logic and system file reading
- **test_schemas.py**: Tests for Pydantic schema validation and serialization
- **test_allocations_db.py**: Tests for in-memory database operations
- **test_daemon_integration.py**: Tests for daemon integration logic

### Integration Tests (`tests/integration/`)

- **test_socket_communication.py**: Tests for Unix socket communication

## Test Patterns

### Fixtures

Common fixtures are defined in `conftest.py`:

- `temp_dir`: Temporary directory for testing
- `mock_cpu_files`: Mock CPU system files
- `fresh_allocations_db`: Clean AllocationsDB instance
- `populated_allocations_db`: AllocationsDB with test data
- `snap_env`: Mock snap environment variables
- `sample_cpu_ranges`: Sample CPU range strings
- `sample_cpu_lists`: Sample CPU number lists

### Test Structure

Tests follow the AAA pattern (Arrange, Act, Assert):

```python
def test_function_name(self, fixture_name):
    """Test description of what this test validates."""
    # Arrange
    expected = "expected_value"

    # Act
    result = function_under_test()

    # Assert
    assert result == expected
```

### Mocking

External dependencies are mocked using `unittest.mock`:

```python
@patch("module.external_function")
def test_with_mock(self, mock_function):
    """Test with mocked external dependency."""
    mock_function.return_value = "mocked_result"
    result = function_under_test()
    assert result == "expected"
```

## Coverage

The test suite aims for high coverage of:

- CPU pinning logic and calculations
- Schema validation and serialization
- Database operations and state management
- Socket communication patterns
- Error handling and edge cases

## Continuous Integration

Tests are automatically run in CI/CD pipelines using tox configurations defined in `tox.ini`.

## Adding New Tests

1. Create test file in appropriate directory (`unit/` or `integration/`)
2. Follow naming convention: `test_<module_name>.py`
3. Use descriptive test method names
4. Add appropriate fixtures to `conftest.py` if needed
5. Include docstrings for all test methods
6. Test both success and failure scenarios
7. Test edge cases and boundary conditions

## Test Data

Test data is externalized when appropriate:

- CPU range strings in fixtures
- Mock system files for CPU information
- Sample request/response objects

## Best Practices

1. **Isolation**: Each test should be independent
2. **Descriptive Names**: Test names should clearly describe what is being tested
3. **Minimal Setup**: Use fixtures to reduce code duplication
4. **Comprehensive Coverage**: Test both happy path and error conditions
5. **Fast Execution**: Tests should run quickly (< 1 second per test)
6. **Clear Assertions**: Use specific assertions with meaningful error messages
