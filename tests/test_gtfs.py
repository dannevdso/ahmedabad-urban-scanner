from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
from shapely.geometry import LineString, box

from ahmedabad_scanner.gtfs import add_transit_isochrone_spatial_index, prepare_gtfs_service_intensity, prepare_transit_route_model, prepare_web_gtfs


def test_gtfs_feed_exports_stops_and_shapes():
    stops, shapes = prepare_web_gtfs(Path("data/external/gtfs_compat.zip"))
    assert len(stops) == 6737
    assert len(shapes) == 876
    assert stops.crs.to_epsg() == 4326
    assert shapes.crs.to_epsg() == 4326
    assert stops.geometry.geom_type.eq("Point").all()
    assert shapes.geometry.geom_type.eq("LineString").all()
    assert shapes["route_id"].map(type).eq(str).all()
    assert shapes["route_label"].notna().all()


def test_service_intensity_exports_whole_day_peak_periods_and_hourly_average(tmp_path):
    feed = tmp_path / "gtfs.zip"
    files = {
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "A,Alpha,23.0,72.5\n"
            "B,Beta,23.1,72.6\n"
        ),
        "trips.txt": (
            "route_id,service_id,trip_id\n"
            "early,all,t1\n"
            "morning-a,all,t2\n"
            "morning-b,all,t3\n"
            "evening,all,t4\n"
            "late,all,t5\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "t1,05:00:00,05:00:00,A,1\n"
            "t2,08:00:00,08:00:00,A,1\n"
            "t3,09:59:59,09:59:59,A,1\n"
            "t3,10:00:00,10:00:00,B,2\n"
            "t4,17:00:00,17:00:00,A,1\n"
            "t5,25:00:00,25:00:00,A,1\n"
        ),
    }
    with ZipFile(feed, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = prepare_gtfs_service_intensity(feed)

    alpha = result.set_index("stop_id").loc["A"]
    beta = result.set_index("stop_id").loc["B"]
    assert alpha["daily_departures"] == 5
    assert alpha["morning_peak_departures"] == 2
    assert alpha["evening_peak_departures"] == 1
    assert alpha["routes_served"] == 5
    assert alpha["departures_per_hour"] == 0.25
    assert beta["daily_departures"] == 1
    assert beta["morning_peak_departures"] == 0
    assert result.attrs["service_day_start"] == "05:00"
    assert result.attrs["service_day_end"] == "25:00"
    assert result.attrs["service_day_hours"] == 20.0
    assert result.crs.to_epsg() == 4326


def test_service_intensity_keeps_stops_with_no_departures(tmp_path):
    feed = tmp_path / "gtfs.zip"
    files = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Alpha,23.0,72.5\n",
        "trips.txt": "route_id,service_id,trip_id\nr1,all,t1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt1,10:00:00,10:00:00,A,1\n",
    }
    with ZipFile(feed, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = prepare_gtfs_service_intensity(feed)

    assert result.loc[0, "daily_departures"] == 1
    assert result.loc[0, "morning_peak_departures"] == 0
    assert result.loc[0, "evening_peak_departures"] == 0
    assert result.loc[0, "routes_served"] == 1
    assert result.loc[0, "departures_per_hour"] == 0


def test_transit_route_model_exports_stop_to_route_and_route_to_stop_indexes(tmp_path):
    feed = tmp_path / "gtfs.zip"
    files = {
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "A,Alpha,23.0,72.5\n"
            "B,Beta,23.01,72.51\n"
            "C,Gamma,23.02,72.52\n"
        ),
        "trips.txt": "route_id,service_id,trip_id\nr1,all,t1\nr2,all,t2\n",
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "t1,07:59:00,07:59:00,A,1\n"
            "t1,08:05:00,08:05:00,B,2\n"
            "t1,08:12:00,08:12:00,C,3\n"
            "t2,08:20:00,08:20:00,C,1\n"
            "t2,08:35:00,08:35:00,A,2\n"
        ),
    }
    with ZipFile(feed, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = prepare_transit_route_model(feed)

    assert [stop["id"] for stop in result["stops"]] == ["A", "B", "C"]
    assert result["route_ids"] == ["r1", "r2"]
    assert result["route_stops"] == [[0, 1, 2], [0, 2]]
    assert result["stop_routes"] == [[0, 1], [0], [0, 1]]


def test_transit_route_model_exports_route_metadata_hourly_departures_and_headways(tmp_path):
    feed = tmp_path / "gtfs.zip"
    files = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Alpha,23.0,72.5\n",
        "routes.txt": "route_id,route_short_name,route_long_name\nr1,1,Route One\nr2,2,Route Two\nr3,3,Route Three\n",
        "trips.txt": (
            "route_id,service_id,trip_id,shape_id\n"
            "r1,all,t1,s1\n"
            "r1,all,t2,s1\n"
            "r2,all,t3,missing-shape\n"
            "r3,all,t4,missing-shape\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "t1,06:00:00,06:00:00,A,1\n"
            "t2,08:00:00,08:00:00,A,1\n"
            "t3,08:30:00,08:30:00,A,1\n"
            "t4,08:30:00,08:30:00,A,1\n"
        ),
        "shapes.txt": (
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
            "s1,23.0,72.5,1\n"
            "s1,23.01,72.51,2\n"
        ),
    }
    with ZipFile(feed, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = prepare_transit_route_model(feed)

    assert result["service_hours"] == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    assert result["routes"] == [
        {"id": "r1", "short_name": "1", "long_name": "Route One", "has_geometry": True},
        {"id": "r2", "short_name": "2", "long_name": "Route Two", "has_geometry": False},
        {"id": "r3", "short_name": "3", "long_name": "Route Three", "has_geometry": False},
    ]
    assert result["stop_route_service"] == [[
        [0, 120.0, [0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
        [1, None, [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
        [2, None, [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ]]


def test_transit_route_model_keeps_extended_gtfs_times_in_hour_24(tmp_path):
    feed = tmp_path / "gtfs.zip"
    files = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Alpha,23.0,72.5\n",
        "routes.txt": "route_id,route_short_name,route_long_name\nr1,1,Route One\n",
        "trips.txt": "route_id,service_id,trip_id\nr1,all,t1\n",
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "t1,24:30:00,24:30:00,A,1\n"
        ),
    }
    with ZipFile(feed, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    result = prepare_transit_route_model(feed)

    assert result["service_hours"][-1] == 24
    assert result["stop_route_service"][0][0][2][-1] == 1


def test_transit_isochrone_cells_include_projected_area_before_wgs84_conversion():
    route_model = {
        "stops": [{"id": "A", "name": "Alpha", "lon": 72.5, "lat": 23.0}],
        "route_ids": ["r1"],
        "route_stops": [[0]],
        "stop_routes": [[0]],
    }
    network = gpd.GeoDataFrame(
        {"node_from": [0], "node_to": [1], "length_m": [100.0]},
        geometry=[LineString([(235000, 2545000), (235100, 2545000)])],
        crs="EPSG:32643",
    )
    stop = gpd.GeoSeries.from_wkt(["POINT (235000 2545000)"], crs="EPSG:32643").to_crs("EPSG:4326").iloc[0]
    route_model["stops"][0]["lon"], route_model["stops"][0]["lat"] = stop.x, stop.y
    result = add_transit_isochrone_spatial_index(
        route_model,
        gpd.GeoSeries([box(234950, 2544950, 235150, 2545050)], crs="EPSG:32643").to_crs("EPSG:4326").iloc[0],
        network=network,
        cell_size_m=100,
    )
    assert result["cells"]
    assert all(cell["area_m2"] > 0 for cell in result["cells"])


def test_transit_isochrone_spatial_index_uses_network_walk_times_for_nearby_stops_and_cells():
    route_model = {
        "stops": [
            {"id": "A", "name": "Alpha", "lon": 72.5, "lat": 23.0},
            {"id": "B", "name": "Beta", "lon": 72.503, "lat": 23.0},
            {"id": "C", "name": "Close but disconnected", "lon": 72.5001, "lat": 23.0001},
        ],
        "route_ids": ["r1"],
        "route_stops": [[0, 1]],
        "stop_routes": [[0], [0], []],
    }
    network = gpd.GeoDataFrame(
        {
            "node_from": [0, 1, 2],
            "node_to": [1, 3, 4],
            "length_m": [300.0, 900.0, 50.0],
        },
        geometry=[
            LineString([(235000, 2545000), (235300, 2545000)]),
            LineString([(235300, 2545000), (236200, 2545000)]),
            LineString([(235010, 2545010), (235060, 2545010)]),
        ],
        crs="EPSG:32643",
    )
    stop_frame = gpd.GeoDataFrame(
        {"stop_index": [0, 1, 2]},
        geometry=gpd.GeoSeries.from_wkt([
            "POINT (235000 2545000)",
            "POINT (235300 2545000)",
            "POINT (235010 2545010)",
        ], crs="EPSG:32643"),
    ).to_crs("EPSG:4326")
    for stop, point in zip(route_model["stops"], stop_frame.geometry, strict=True):
        stop["lon"], stop["lat"] = point.x, point.y

    result = add_transit_isochrone_spatial_index(
        route_model,
        gpd.GeoSeries([box(234900, 2544900, 236300, 2545100)], crs="EPSG:32643").to_crs("EPSG:4326").iloc[0],
        network=network,
        cell_size_m=200,
        nearby_stop_minutes=5,
        catchment_minutes=15,
    )

    assert result["walking_speed_kmh"] == 4.8
    assert result["walking_model"] == "prepared street network"
    assert [0, 1] == result["footpaths"][0][:2]
    assert [0, 2] not in [footpath[:2] for footpath in result["footpaths"]]
    assert result["cells"]
    assert all(cell["links"] for cell in result["cells"])
    assert all(seconds <= 15 * 60 for cell in result["cells"] for _, seconds in cell["links"])
    assert all(cell["geometry"]["type"] in {"Polygon", "MultiPolygon"} for cell in result["cells"])
