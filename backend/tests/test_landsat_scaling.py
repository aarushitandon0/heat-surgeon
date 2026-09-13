"""Landsat C2 L2 ST_B10 digital number to degrees Celsius (SPEC.md §4.4).

Hand-checked expected values, worked by hand before the function existed:

  DN 44947 (the USGS scale-factor FAQ example, stated there as 302.6 K):
    44947 * 0.00341802 = 153.62974494
    153.62974494 + 149.0 = 302.62974494 K
    302.62974494 - 273.15 = 29.47974494 C

  DN 50000:
    50000 * 0.00341802 = 170.901
    170.901 + 149.0 = 319.901 K
    319.901 - 273.15 = 46.751 C
"""

import numpy as np

from app.data.sources import st_b10_to_celsius


def test_usgs_faq_example_converts_to_hand_checked_celsius():
    assert np.isclose(st_b10_to_celsius(np.array([44947], dtype=np.uint16))[0], 29.47974494, atol=1e-6)


def test_round_number_converts_to_hand_checked_celsius():
    assert np.isclose(st_b10_to_celsius(np.array([50000], dtype=np.uint16))[0], 46.751, atol=1e-6)


def test_fill_value_zero_becomes_nan_not_a_temperature():
    result = st_b10_to_celsius(np.array([0, 44947], dtype=np.uint16))
    assert np.isnan(result[0])
    assert not np.isnan(result[1])


def test_uint16_input_does_not_overflow():
    result = st_b10_to_celsius(np.array([[65535, 44947]], dtype=np.uint16))
    assert np.isclose(result[0, 0], 65535 * 0.00341802 + 149.0 - 273.15, atol=1e-6)
