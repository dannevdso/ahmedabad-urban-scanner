from __future__ import annotations

import pytest

from ahmedabad_scanner.plus_codes import decode_full_plus_code


def test_full_plus_code_decodes_to_local_area_without_network() -> None:
    area = decode_full_plus_code("7JJJMX4V+FP4G")
    assert area.latitude == pytest.approx(22.6561355, abs=0.00001)
    assert area.longitude == pytest.approx(72.9943291, abs=0.00001)
    assert area.north > area.south
    assert area.east > area.west


def test_short_code_is_rejected_for_safe_address_enrichment() -> None:
    with pytest.raises(ValueError, match="full"):
        decode_full_plus_code("H92+22")


def test_invalid_plus_code_is_rejected() -> None:
    with pytest.raises(ValueError):
        decode_full_plus_code("7JMM2H92+ZZ")
