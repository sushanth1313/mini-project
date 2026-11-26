import datetime
from backend.gis.service import get_nearby_facilities

def fetch_osm_facilities(lat: float, lon: float) -> dict:
    try:
        facilities = get_nearby_facilities(lat, lon)
        # Check if the fallback empty struct was returned
        is_unavailable = False
        if facilities and isinstance(facilities, dict):
            first_key = list(facilities.keys())[0]
            if facilities[first_key].get("status") == "UNAVAILABLE":
                is_unavailable = True

        return {
            "source": "OpenStreetMap / Overpass",
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "confidence": "Moderate",
            "data": facilities,
            "status": "UNAVAILABLE" if is_unavailable else "AVAILABLE"
        }
    except Exception as e:
        return {
            "source": "OpenStreetMap / Overpass",
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "confidence": "None",
            "data": {},
            "status": "UNAVAILABLE"
        }
