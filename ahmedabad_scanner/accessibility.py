"""Pedestrian-network accessibility calculations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

import networkx as nx


def add_walking_times(
    graph: nx.MultiDiGraph, *, speed_kmh: float
) -> nx.MultiDiGraph:
    """Add edge walking times in minutes from metric edge lengths."""
    if speed_kmh <= 0:
        raise ValueError("Walking speed must be positive")
    metres_per_minute = speed_kmh * 1000 / 60
    for _, _, _, data in graph.edges(keys=True, data=True):
        data["walk_time_min"] = float(data["length"]) / metres_per_minute
    return graph


def nearest_facility_times(
    graph: nx.MultiDiGraph,
    *,
    facility_nodes: Iterable[int],
    cutoff_min: float,
) -> dict[int, float]:
    sources = set(facility_nodes)
    if not sources:
        return {}
    reverse_graph = graph.reverse(copy=False)
    return dict(
        nx.multi_source_dijkstra_path_length(
            reverse_graph,
            sources,
            cutoff=cutoff_min,
            weight="walk_time_min",
        )
    )


def reachable_facility_counts(
    graph: nx.MultiDiGraph,
    *,
    facility_nodes: Iterable[int],
    thresholds_min: Iterable[int],
) -> dict[int, dict[int, int]]:
    thresholds = sorted(set(int(value) for value in thresholds_min))
    counts = {
        threshold: {node: 0 for node in graph.nodes}
        for threshold in thresholds
    }
    if not thresholds:
        return counts

    reverse_graph = graph.reverse(copy=False)
    for facility_node, multiplicity in Counter(facility_nodes).items():
        lengths = nx.single_source_dijkstra_path_length(
            reverse_graph,
            facility_node,
            cutoff=max(thresholds),
            weight="walk_time_min",
        )
        for node, travel_time in lengths.items():
            for threshold in thresholds:
                if travel_time <= threshold:
                    counts[threshold][node] += multiplicity
    return counts
