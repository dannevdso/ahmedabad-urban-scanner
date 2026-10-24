from __future__ import annotations

import networkx as nx

from ahmedabad_scanner.accessibility import (
    add_walking_times,
    nearest_facility_times,
    reachable_facility_counts,
)


def directed_test_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_edge(0, 1, length=80.0)
    graph.add_edge(1, 2, length=160.0)
    return graph


def test_add_walking_times_converts_edge_length_to_minutes() -> None:
    graph = add_walking_times(directed_test_graph(), speed_kmh=4.8)

    assert graph.edges[0, 1, 0]["walk_time_min"] == 1.0
    assert graph.edges[1, 2, 0]["walk_time_min"] == 2.0


def test_nearest_facility_times_measure_travel_toward_facility() -> None:
    graph = add_walking_times(directed_test_graph(), speed_kmh=4.8)

    times = nearest_facility_times(graph, facility_nodes=[2], cutoff_min=15)

    assert times == {0: 3.0, 1: 2.0, 2: 0}


def test_reachable_facility_counts_respect_network_thresholds() -> None:
    graph = add_walking_times(directed_test_graph(), speed_kmh=4.8)

    counts = reachable_facility_counts(
        graph,
        facility_nodes=[2],
        thresholds_min=[1, 3],
    )

    assert counts[1][0] == 0
    assert counts[3][0] == 1
    assert counts[1][1] == 0
    assert counts[3][1] == 1
