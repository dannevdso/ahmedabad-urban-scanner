"""Offline decoding of full Open Location Codes (Google Plus Codes)."""

from __future__ import annotations

from dataclasses import dataclass

ALPHABET = "23456789CFGHJMPQRVWX"
SEPARATOR = "+"
SEPARATOR_POSITION = 8
PAIR_RESOLUTIONS = (20.0, 1.0, 0.05, 0.0025, 0.000125)
GRID_ROWS = 5
GRID_COLUMNS = 4


@dataclass(frozen=True)
class PlusCodeArea:
    """Decoded latitude/longitude area in WGS84 degrees."""

    south: float
    west: float
    north: float
    east: float

    @property
    def latitude(self) -> float:
        return (self.south + self.north) / 2

    @property
    def longitude(self) -> float:
        return (self.west + self.east) / 2


def _validate_full_code(code: str) -> str:
    value = code.strip().upper()
    if not value or SEPARATOR not in value:
        raise ValueError("Plus Code must be a full code containing '+'")
    if value.count(SEPARATOR) != 1 or value.index(SEPARATOR) != SEPARATOR_POSITION:
        raise ValueError("Only full Plus Codes with '+' at position 8 are supported")
    compact = value.replace(SEPARATOR, "")
    if len(compact) < 2 or len(compact) > 15:
        raise ValueError("Plus Code length must be between 2 and 15 characters")
    if any(character not in ALPHABET for character in compact):
        raise ValueError("Plus Code contains a character outside the OLC alphabet")
    return compact


def decode_full_plus_code(code: str) -> PlusCodeArea:
    """Decode a full Plus Code without network access or a geocoder."""
    compact = _validate_full_code(code)
    pair_length = min(len(compact), 10)
    latitude = -90.0
    longitude = -180.0
    lat_resolution = PAIR_RESOLUTIONS[0]
    lon_resolution = PAIR_RESOLUTIONS[0]
    for index in range(0, pair_length, 2):
        lat_digit = ALPHABET.index(compact[index])
        lon_digit = ALPHABET.index(compact[index + 1])
        resolution = PAIR_RESOLUTIONS[index // 2]
        latitude += lat_digit * resolution
        longitude += lon_digit * resolution
        lat_resolution = resolution
        lon_resolution = resolution
    if len(compact) > 10:
        lat_resolution /= GRID_ROWS
        lon_resolution /= GRID_COLUMNS
        for character in compact[10:]:
            digit = ALPHABET.index(character)
            row, column = divmod(digit, GRID_COLUMNS)
            latitude += row * lat_resolution
            longitude += column * lon_resolution
            lat_resolution /= GRID_ROWS
            lon_resolution /= GRID_COLUMNS
    return PlusCodeArea(
        south=latitude,
        west=longitude,
        north=latitude + lat_resolution,
        east=longitude + lon_resolution,
    )
