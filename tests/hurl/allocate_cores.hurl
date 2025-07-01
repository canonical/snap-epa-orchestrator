# Test EPA Orchestrator snap API via Unix socket
# This test verifies the core allocation functionality

# Test basic core allocation
POST http://localhost/allocate_cores
Content-Type: application/json

{
  "version": "1.0",
  "snap_name": "test-snap",
  "action": "allocate_cores",
  "cores_requested": 2
}

HTTP/1.1 200
Content-Type: application/json

[Asserts]
jsonpath "$.version" == "1.0"
jsonpath "$.snap_name" == "test-snap"
jsonpath "$.cores_requested" == 2
jsonpath "$.cores_allocated" == 2
jsonpath "$.error" == ""
jsonpath "$.allocated_cores" != ""
jsonpath "$.shared_cpus" != ""
jsonpath "$.total_available_cpus" > 0

---

# Test 80% allocation (cores_requested = 0)
POST http://localhost/allocate_cores
Content-Type: application/json

{
  "version": "1.0",
  "snap_name": "test-snap-80",
  "action": "allocate_cores",
  "cores_requested": 0
}

HTTP/1.1 200
Content-Type: application/json

[Asserts]
jsonpath "$.version" == "1.0"
jsonpath "$.snap_name" == "test-snap-80"
jsonpath "$.cores_requested" == 0
jsonpath "$.error" == ""
jsonpath "$.cores_allocated" > 0
jsonpath "$.allocated_cores" != ""
jsonpath "$.shared_cpus" != ""

---

# Test list allocations
POST http://localhost/list_allocations
Content-Type: application/json

{
  "version": "1.0",
  "snap_name": "any-snap",
  "action": "list_allocations"
}

HTTP/1.1 200
Content-Type: application/json

[Asserts]
jsonpath "$.total_allocations" >= 0
jsonpath "$.total_allocated_cpus" >= 0
jsonpath "$.total_available_cpus" > 0
jsonpath "$.remaining_available_cpus" >= 0
jsonpath "$.allocations" != null
jsonpath "$.error" == "" 