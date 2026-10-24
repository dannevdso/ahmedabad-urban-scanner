import hashlib
import json
from pathlib import Path


FLOOD_RISK_ASSET = Path("web/public/data/ahm-urban-flood-risk-zones.geojson")


def test_published_flood_risk_asset_retains_verified_vedas_attributes():
    payload = FLOOD_RISK_ASSET.read_bytes()
    data = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == "e38118adbe808076ce81b4db02ca8a7689afec6c10ef2cd3a1fdde9bd3b3f54c"
    assert len(data["features"]) == 7020
    assert {feature["geometry"]["type"] for feature in data["features"]} == {"Polygon", "MultiPolygon"}
    assert {feature["properties"]["uf_risk"] for feature in data["features"]} == {
        "Very High Risk Areas",
        "High Risk Areas",
        "Moderate Risk Areas",
    }