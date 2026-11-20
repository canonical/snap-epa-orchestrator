# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

"""L3 topology discovery and placement through the socket API."""

import json
from pathlib import Path

import pytest

from epa_orchestrator import cpu_pool
from epa_orchestrator.allocations_db import allocations_db
from epa_orchestrator.daemon_handler import handle_daemon_request, validate_startup_pool
from epa_orchestrator.schemas import CpuPoolName, PreemptionPolicy
from epa_orchestrator.utils import parse_cpu_ranges, to_ranges


@pytest.fixture
def topology(mock_cpu_files_empty, monkeypatch, tmp_path):
    """Build interchangeable sysfs cache, SMT and NUMA layouts."""

    def build(groups, *, configured=None, nodes=None, siblings=None):
        all_cpus = set().union(*groups)
        online = to_ranges(sorted(all_cpus))
        mock_cpu_files_empty["online"].write_text(online)
        mock_cpu_files_empty["present"].write_text(online)
        monkeypatch.setattr(cpu_pool, "CPU_SYSFS", tmp_path)
        monkeypatch.setattr(
            "epa_orchestrator.cpu_pinning.THREAD_SIBLINGS_LIST_TEMPLATE",
            str(tmp_path / "cpu{cpu}" / "topology" / "thread_siblings_list"),
        )
        nodes = nodes or {0: all_cpus}
        for module in ("utils", "allocations_db", "daemon_handler"):
            monkeypatch.setattr(f"epa_orchestrator.{module}.get_numa_node_cpus", lambda: nodes)
        siblings = siblings or {}
        for group in groups:
            sharing = to_ranges(sorted(group))
            for cpu in group:
                base = tmp_path / f"cpu{cpu}"
                topology = base / "topology"
                topology.mkdir(parents=True)
                (topology / "thread_siblings_list").write_text(
                    to_ranges(sorted(siblings.get(cpu, {cpu})))
                )
                for index, level, kind in (
                    (0, 1, "Data"),
                    (3, 3, "Instruction"),
                    (5, 3, "Unified"),
                ):
                    path = base / "cache" / f"index{index}"
                    path.mkdir(parents=True)
                    (path / "level").write_text(str(level))
                    (path / "type").write_text(kind)
                    (path / "shared_cpu_list").write_text(sharing)
        return cpu_pool.CpuPools(configured or online)

    return build


@pytest.fixture
def bergamo(topology):
    """Model four L3 groups (two per CCD), with SMT thread IDs offset by 256."""
    cores = range(32)
    groups = [set(range(lo, lo + 8)) | set(range(lo + 256, lo + 264)) for lo in (0, 8, 16, 24)]
    siblings = {cpu: {core, core + 256} for core in cores for cpu in (core, core + 256)}
    nodes = {0: groups[0] | groups[1], 1: groups[2] | groups[3]}
    return topology(groups, nodes=nodes, siblings=siblings)


def api(pools, action="list_allocations", name="osd", **fields):
    """Send a request through the normal wire dispatcher."""
    request = {"action": action, "pool": "general", "service_name": name, **fields}
    return json.loads(handle_daemon_request(json.dumps(request).encode(), pools))


def claim(pools, count, *, name="osd", placement="single_l3", **fields):
    """Allocate a logical CPU count using the requested placement."""
    return api(pools, "allocate_cores", name, num_of_cores=count, placement=placement, **fields)


def store_claim(name, ranges, policy=PreemptionPolicy.NON_PREEMPTIVE):
    """Seed CPU IDs that could have been claimed by an older daemon."""
    allocations_db.allocate_cores(name, ranges, policy, pool=CpuPoolName.GENERAL)


def test_wire_discovery_and_grouped_claims(bergamo):
    """Report placement, eligible/free L3 groups and claim membership on all count paths."""
    initial = api(bergamo)
    assert "l3-placement" in initial["supported_cpu_features"]
    assert "l3_topology" not in initial
    assert len(api(bergamo, include_l3_topology=True)["l3_topology"]) == 4

    response = claim(bergamo, 12)
    assert response["placement"] == "single_l3"
    assert response["l3_groups"] == ["0-5,256-261"]
    assert response["allocated_cores"] == "0-5,256-261"
    assert len(parse_cpu_ranges(response["shared_cpus"])) == 52
    default = api(bergamo, include_l3_topology=False)
    assert "l3_topology" not in default
    assert "l3_groups" not in default["allocations"][0]
    listed = api(bergamo, include_l3_topology=True)
    assert listed["allocations"][0]["l3_groups"] == response["l3_groups"]
    assert listed["l3_topology"][0] == {
        "cpus": "0-7,256-263",
        "free": "6-7,262-263",
        "partial": False,
    }

    legacy = api(bergamo, "allocate_cores", "legacy", num_of_cores=4)
    assert legacy["allocated_cores"] == "6-9"
    assert legacy["l3_groups"] == ["6-7", "8-9"]
    assert legacy["placement"] is None
    percent = api(bergamo, "allocate_cores_percent", "percent", percent=1)
    assert percent["l3_groups"] == ["10"]


def test_interleaved_ids_and_socket_l3(topology):
    """Use actual cache membership even when socket CPU IDs interleave."""
    pools = topology([{0, 2, 4, 6}, {1, 3, 5, 7}], nodes={0: {0, 2, 4, 6}, 1: {1, 3, 5, 7}})
    assert claim(pools, 4)["l3_groups"] == ["0,2,4,6"]
    assert claim(pools, 4, name="other")["allocated_cores"] == "1,3,5,7"


def test_best_fit_reclaims_space_in_a_fragmented_group(bergamo):
    """A small re-pin uses the smaller fitting group and leaves an empty one intact."""
    store_claim("large", "8-13,264-269")
    for _ in range(3):
        result = claim(bergamo, 4)
        assert result["allocated_cores"] == "14-15,270-271"
        assert claim(bergamo, -1)["l3_groups"] == []
    assert api(bergamo, include_l3_topology=True)["l3_topology"][0]["free"] == "0-7,256-263"


def test_whole_group_claim(bergamo):
    """A protected whole group remains unavailable to subsequent grants."""
    result = claim(bergamo, 16, preemption_policy="non-preemptive")
    assert result["l3_groups"] == ["0-7,256-263"]
    assert api(bergamo, include_l3_topology=True)["l3_topology"][0]["free"] == ""
    assert claim(bergamo, 2, name="another", preemption_policy="non-preemptive")["l3_groups"] == [
        "8,264"
    ]
    result = api(bergamo, "allocate_numa_cores", "numa", numa_node=0, num_of_cores=16)
    assert "error" in result


def test_strict_no_fit_reports_capacity_without_changes(bergamo):
    """A group can be too small even when a pool has sufficient total space."""
    before = api(bergamo)
    for count in (17, 65):
        result = claim(bergamo, count)
        assert result["code"] == "l3_no_group_fits"
        assert result["error"].endswith(": 16")
    assert api(bergamo) == before


def test_fewest_groups_then_fewest_numa_nodes(topology):
    """Look beyond the globally largest group to minimize NUMA nodes."""
    groups = [set(range(8)), set(range(8, 15)), set(range(15, 21)), set(range(21, 24))]
    pools = topology(groups, nodes={0: groups[0], 1: set().union(*groups[1:])})
    one = claim(pools, 6, placement="fewest_l3")
    assert one["l3_groups"] == ["15-20"]
    claim(pools, -1)
    packed = claim(pools, 12, placement="fewest_l3")
    assert packed["l3_groups"] == ["8-14", "15-19"]
    claim(pools, -1)
    assert len(claim(pools, 22, placement="fewest_l3")["l3_groups"]) == 4


def test_protected_resize_stays_in_place_and_fewest_can_grow(bergamo):
    """Retain exact CPUs on retry and growth, and preserve SMT pairs on shrink."""
    store_claim("osd", "0-5,256-261")
    assert claim(bergamo, 12)["allocated_cores"] == "0-5,256-261"
    assert claim(bergamo, 8)["allocated_cores"] == "0-3,256-259"
    before = api(bergamo)
    assert claim(bergamo, 17)["code"] == "l3_growth_would_spill"
    assert api(bergamo) == before
    assert claim(bergamo, 14)["allocated_cores"] == "0-6,256-262"
    grown = claim(bergamo, 18, placement="fewest_l3")
    assert grown["allocated_cores"] == "0-8,256-264"
    assert grown["l3_groups"] == ["0-7,256-263", "8,264"]

    before = api(bergamo)
    assert claim(bergamo, 4)["code"] == "l3_claim_spans_groups"
    assert api(bergamo) == before
    assert claim(bergamo, 18, placement="fewest_l3")["l3_groups"] == grown["l3_groups"]
    assert claim(bergamo, 20, placement="fewest_l3")["l3_groups"] == [
        "0-7,256-263",
        "8-9,264-265",
    ]


def test_unplaced_protected_shrink_keeps_smt_pairs(bergamo):
    """The stable shrink fix also applies to requests without placement."""
    store_claim("osd", "0-5,256-261")
    response = api(bergamo, "allocate_cores", num_of_cores=8)
    assert response["allocated_cores"] == "0-3,256-259"


def test_numa_prefers_a_group_without_reclamation(bergamo):
    """A preemptive request leaves old owners alone when an unclaimed group fits."""
    store_claim("first", "0-7,256-263", PreemptionPolicy.LEGACY)
    result = api(
        bergamo, "allocate_numa_cores", numa_node=0, num_of_cores=4, placement="single_l3"
    )
    assert result["cores_allocated"] == "8-9,264-265"
    assert allocations_db.get_allocation("first") == "0-7,256-263"
    second = api(
        bergamo, "allocate_numa_cores", numa_node=1, num_of_cores=4, placement="single_l3"
    )
    assert second["l3_groups"] == ["16-17,272-273"]
    listing = api(bergamo, include_l3_topology=True)
    entry = next(entry for entry in listing["allocations"] if entry["service_name"] == "osd")
    assert entry["l3_groups"] == ["8-9,264-265", "16-17,272-273"]


def test_numa_can_reclaim_legacy_claim_when_needed(bergamo):
    """Strict placement applies the ordinary NUMA reclamation policy."""
    store_claim("first", "0-7,256-263", PreemptionPolicy.LEGACY)
    store_claim("second", "8-15,264-271")
    result = api(
        bergamo, "allocate_numa_cores", numa_node=0, num_of_cores=4, placement="fewest_l3"
    )
    assert result["l3_groups"] == ["0-1,256-257"]
    assert allocations_db.get_allocation("first") == "2-7,258-263"
    assert allocations_db.get_allocation("second") == "8-15,264-271"


@pytest.mark.parametrize("placement", ["single_l3", "fewest_l3"])
def test_numa_minimizes_reclamation_across_fitting_groups(topology, placement):
    """Reclaim one CPU instead of three when both caches fit the grant."""
    pools = topology([set(range(4)), set(range(4, 8))])
    store_claim("first", "0-3", PreemptionPolicy.LEGACY)
    store_claim("second", "4-5", PreemptionPolicy.LEGACY)
    result = api(pools, "allocate_numa_cores", numa_node=0, num_of_cores=3, placement=placement)
    assert result["cores_allocated"] == "4,6-7"
    assert allocations_db.get_allocation("first") == "0-3"
    assert allocations_db.get_allocation("second") == "5"


def test_l3_map_refreshes_on_hotplug_and_reports_partial(topology, mock_cpu_files_empty, caplog):
    """Offline siblings shrink the group, while online CPUs outside the pool mark it partial."""
    pools = topology([{0, 1, 2}, {3, 4}], configured="0-1,3-4")
    assert api(pools, include_l3_topology=True)["l3_topology"][0] == {
        "cpus": "0-1",
        "free": "0-1",
        "partial": True,
    }
    validate_startup_pool(pools)
    assert "CPU pool general cuts through L3 groups: 0-1" in caplog.text

    # Simulate sysfs sharing masks being regenerated on CPU removal.
    for cpu in (0, 1):
        shared_list = cpu_pool.CPU_SYSFS / f"cpu{cpu}/cache/index5/shared_cpu_list"
        shared_list.write_text("0-1")
    mock_cpu_files_empty["online"].write_text("0-1,3-4")
    assert api(pools, include_l3_topology=True)["l3_topology"][0] == {
        "cpus": "0-1",
        "free": "0-1",
        "partial": False,
    }
    mock_cpu_files_empty["online"].write_text("0,3-4")
    assert api(pools, include_l3_topology=True)["l3_topology"][0] == {
        "cpus": "0",
        "free": "0",
        "partial": False,
    }


def test_configure_hook_warns_for_partial_group(topology, snap_pool_options, caplog):
    """An accepted partial pool is warned about without rejecting the configuration."""
    topology([{0, 1, 2}, {3, 4}])
    snap_pool_options["cpu-pool"] = "0-1,3-4"
    cpu_pool.validate_snap_configuration()
    assert snap_pool_options["internal.validated-cpu-pool"] == "0-1,3-4"
    assert "CPU pool general cuts through L3 groups: 0-1" in caplog.text


@pytest.mark.parametrize("failure", ["denied", "missing", "inconsistent"])
def test_unreadable_cache_data_fails_closed_but_legacy_can_allocate(bergamo, monkeypatch, failure):
    """An unreadable eligible CPU suppresses the feature and preserves existing claims."""
    read_text = Path.read_text
    broken = cpu_pool.CPU_SYSFS / "cpu287/cache/index5/shared_cpu_list"

    def patched(path, *args, **kwargs):
        if path == broken:
            if failure == "denied":
                raise PermissionError("AppArmor denied")
            if failure == "missing":
                raise FileNotFoundError("not present")
            return "0,287"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", patched)
    store_claim("osd", "0,256")
    listing = api(bergamo, include_l3_topology=True)
    assert "l3-placement" not in listing["supported_cpu_features"]
    assert listing["l3_topology"] is None
    assert listing["allocations"][0]["l3_groups"] is None
    assert claim(bergamo, 4)["code"] == "l3_topology_unavailable"
    assert api(bergamo, include_l3_topology=True) == listing

    fallback = claim(bergamo, 2, name="plain", placement="fewest_l3")
    assert fallback["l3_groups"] is None
    assert fallback["placement"] == "fewest_l3"
    assert fallback["allocated_cores"] == "1-2"
    assert claim(bergamo, -1, name="plain")["l3_groups"] == []

    plain = api(bergamo, "allocate_cores", "plain", num_of_cores=2)
    assert plain["l3_groups"] is None
    assert plain["allocated_cores"] == fallback["allocated_cores"]
    assert claim(bergamo, -1)["l3_groups"] == []


def test_unsupported_requests_return_a_placement_code(bergamo):
    """Default-size and percentage requests cannot silently ignore explicit placement."""
    assert claim(bergamo, 0)["code"] == "placement_not_supported"
    for percent in (0, 100):
        result = api(bergamo, "allocate_cores_percent", percent=percent, placement="single_l3")
        assert result["code"] == "placement_not_supported"
    assert api(bergamo)["allocations"] == []


def test_fewest_l3_shrink_drops_groups_without_moving_cpus(topology):
    """Shrink an interleaved claim using the minimum number of owned groups."""
    pools = topology([{0, 2, 4, 6}, {1, 3, 5, 7}])
    store_claim("other", "0")
    store_claim("osd", "1-7")
    result = claim(pools, 4, placement="fewest_l3")
    assert result["allocated_cores"] == "1,3,5,7"
    assert result["l3_groups"] == ["1,3,5,7"]


@pytest.mark.parametrize(
    "owned,count,expected",
    [("0-1,4-7", 2, ["4,6"]), ("0-2,4-6,8-9", 4, ["4,6", "8-9"])],
)
def test_fewest_l3_protected_shrink_prefers_owned_smt_pairs(topology, owned, count, expected):
    """Keep pairs when multiple placements fit in the minimum number of caches."""
    pools = topology(
        [{0, 1, 2, 3}, {4, 5, 6, 7}, {8, 9}],
        siblings={4: {4, 6}, 6: {4, 6}, 8: {8, 9}, 9: {8, 9}},
    )
    store_claim("osd", owned)
    result = claim(pools, count, placement="fewest_l3")
    assert result["l3_groups"] == expected
    assert parse_cpu_ranges(result["allocated_cores"]) <= parse_cpu_ranges(owned)


@pytest.mark.parametrize(
    "placement,count,selected,remaining",
    [
        ("single_l3", 3, "0,4,6", "1-3"),
        ("fewest_l3", 3, "0,4,6", "1-3"),
        ("fewest_l3", 5, "0,4-7", "1-3"),
    ],
)
def test_placed_numa_reclaims_only_shortfall(topology, placement, count, selected, remaining):
    """Spend unclaimed CPUs before displacing CPUs in the selected groups."""
    pools = topology([{0, 2, 4, 6}, {1, 3, 5, 7}])
    store_claim("legacy", "0-3", PreemptionPolicy.LEGACY)
    result = api(
        pools, "allocate_numa_cores", numa_node=0, num_of_cores=count, placement=placement
    )
    assert result["cores_allocated"] == selected
    assert allocations_db.get_allocation("legacy") == remaining


@pytest.mark.parametrize(
    "action,params", [("allocate_cores", {}), ("allocate_numa_cores", {"numa_node": 0})]
)
def test_strict_placement_reports_unreadable_online_mask(
    bergamo, mock_cpu_files_empty, action, params
):
    """Strict grants preserve their error code and existing state on sysfs failure."""
    store_claim("osd", "0,256")
    before = allocations_db._state_store.read_all()
    mock_cpu_files_empty["online"].unlink()
    result = api(bergamo, action, num_of_cores=4, placement="single_l3", **params)
    assert result["code"] == "l3_topology_unavailable"
    assert str(mock_cpu_files_empty["online"]) in result["error"]
    assert allocations_db._state_store.read_all() == before
