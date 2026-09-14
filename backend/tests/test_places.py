"""Named OSM places: parsing an Overpass answer, which names reach the map, and merging with named buildings.

Payloads and geometry here are synthetic test fixtures, not data.
"""

from app.data.osm import parse_places
from app.pipeline import _named_features, display_place_name


def test_parse_places_keeps_named_places_with_a_place_tag_at_their_node_or_centre():
    payload = {
        "osm3s": {"timestamp_osm_base": "2026-09-14T00:00:00Z"},
        "elements": [
            {"type": "node", "id": 1, "lat": 18.52, "lon": 73.84, "tags": {"name": "Punjab National Bank", "amenity": "bank"}},
            {"type": "way", "id": 2, "center": {"lat": 18.521, "lon": 73.841}, "tags": {"name:en": "Garware College", "name": "x", "amenity": "college"}},
            {"type": "node", "id": 3, "lat": 18.52, "lon": 73.84, "tags": {"name": "No place tag"}},
            {"type": "node", "id": 4, "lat": 18.52, "lon": 73.84, "tags": {"amenity": "atm"}},
        ],
    }
    parsed = parse_places(payload, "EPSG:32643")
    assert parsed["osm_base"] == "2026-09-14T00:00:00Z"
    assert [(p["id"], p["name"], p["kind"]) for p in parsed["places"]] == [
        ("osm:node/1", "Punjab National Bank", "amenity=bank"),
        ("osm:way/2", "Garware College", "amenity=college"),
    ]
    # 73.84 E, 18.52 N in UTM zone 43N is about 377,500 m E, 2,048,100 m N.
    easting, northing = parsed["places"][0]["point"]
    assert 377_000 < easting < 378_000 and 2_047_500 < northing < 2_048_500


def test_display_place_name_skips_mapper_notes_and_block_codes():
    assert display_place_name("Garware College") == "Garware College"
    assert display_place_name("IRANI CAFE") == "IRANI CAFE"
    assert display_place_name("cs department") is None
    assert display_place_name("b12") is None
    assert display_place_name("B12") is None
    assert display_place_name("A-3") is None
    assert display_place_name(None) is None


def test_named_features_lists_buildings_by_area_then_places_without_duplicates():
    square = lambda side: [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]  # noqa: E731
    buildings = [
        {"tags": {"name": "Small Hall", "building": "yes"}, "rings": [square(10)]},
        {"tags": {"name": "Big College", "building": "university"}, "rings": [square(30)]},
        {"tags": {"name": "b4", "building": "yes"}, "rings": [square(50)]},
    ]
    places = [
        {"name": "Big College", "kind": "amenity=college", "point": [15, 15]},
        {"name": "Corner Bank", "kind": "amenity=bank", "point": [100, 100]},
    ]
    features = _named_features(buildings, places)
    assert [(f.name, f.origin, f.kind, f.footprint_area_m2) for f in features] == [
        ("Big College", "osm_building", "building=university", 900.0),
        ("Small Hall", "osm_building", "building=yes", 100.0),
        ("Corner Bank", "osm_place", "amenity=bank", None),
    ]
