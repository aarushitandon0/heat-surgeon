"""Cross-section templates, band layout and right-of-way measurement against hand-checked values.

Geometry here is synthetic test fixtures, not data.
"""

import numpy as np

from app import config
from app.data.cross_section import (
    band_masks,
    default_cross_section,
    measure_right_of_way_m,
    plantable_mask,
    template_for,
    usdg_cross_section,
)


def test_every_template_sums_to_its_right_of_way():
    for name, bands in config.USDG_TEMPLATES.items():
        assert np.isclose(sum(w for _, w in bands), float(name.rstrip("A")))


def test_template_is_the_widest_no_wider_than_the_right_of_way():
    assert template_for(20.0) == "18A"      # USDG example: a 20 m street uses the 18 m template
    assert template_for(21.0) == "21A"
    assert template_for(8.0) is None


def test_12a_band_offsets_hand_checked():
    # 12A: footway 2, tree pit 1, carriageway 6, tree pit 1, footway 2; carriageway centred on 0.
    section = usdg_cross_section(6.0, 6.0)
    bands = [(b.kind, b.offset_from_m, b.offset_to_m) for b in section.bands if b.kind != "private_property"]
    assert bands == [("footway", -6.0, -4.0), ("tree_pit", -4.0, -3.0), ("carriageway", -3.0, 3.0),
                     ("tree_pit", 3.0, 4.0), ("footway", 4.0, 6.0)]
    assert section.source == "published_design"


def test_spare_width_goes_to_the_outer_footways():
    # 14 m right of way uses 12A; the 2 m spare is split 1 m onto each outer footway.
    section = usdg_cross_section(7.0, 7.0)
    footways = [b for b in section.bands if b.kind == "footway"]
    assert [(b.offset_from_m, b.offset_to_m) for b in footways] == [(-7.0, -4.0), (4.0, 7.0)]


def test_plantable_mask_and_band_masks_on_cell_centres():
    section = usdg_cross_section(6.0, 6.0)
    across = np.array([-5.0, -3.5, 0.0, 3.5, 5.0, 10.0])
    assert plantable_mask(section, across).tolist() == [False, True, False, True, False, False]
    assert band_masks(section, across)["private_property"].tolist() == [False, False, False, False, False, True]


def test_default_cross_section_has_no_plantable_band():
    section = default_cross_section({"highway": "tertiary"})
    assert section.source == "default_assumption"
    assert not any(b.plantable for b in section.bands)


def test_right_of_way_measured_to_building_lines():
    # Street along +y from (0, 0); buildings 5 m to the left (x < -5) and 7 m to the right (x > 7).
    left = [[-15.0, -10.0], [-5.0, -10.0], [-5.0, 60.0], [-15.0, 60.0], [-15.0, -10.0]]
    right = [[7.0, -10.0], [17.0, -10.0], [17.0, 60.0], [7.0, 60.0], [7.0, -10.0]]
    buildings = [{"rings": [left]}, {"rings": [right]}]
    assert np.allclose(measure_right_of_way_m(buildings, np.array([0.0, 0.0]), np.array([0.0, 1.0]), 50.0), (5.0, 7.0))


def test_right_of_way_unknown_without_buildings_on_one_side():
    left = [[-15.0, -10.0], [-5.0, -10.0], [-5.0, 60.0], [-15.0, 60.0], [-15.0, -10.0]]
    assert measure_right_of_way_m([{"rings": [left]}], np.array([0.0, 0.0]), np.array([0.0, 1.0]), 50.0) is None
