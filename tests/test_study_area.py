from shapely.geometry import Point

from ahmedabad_scanner.study_area import digitised_study_area


def test_digitised_study_area_matches_black_line_and_contains_requested_places():
    polygon = digitised_study_area()

    assert polygon.is_valid
    assert len(polygon.exterior.coords) == 40
    assert polygon.bounds == (
        72.41546685809394,
        22.917600868878278,
        72.73880381629021,
        23.26728899071171,
    )
    assert polygon.contains(Point(72.4587752, 23.0385802))  # Bopal
    assert polygon.contains(Point(72.4705270, 23.0235385))  # South Bopal
    assert polygon.contains(Point(72.6369, 23.2156))  # Gandhinagar
