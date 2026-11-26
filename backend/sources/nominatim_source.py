import datetime
from backend.gis.service import geocode_locality

def fetch_locality_coordinates(village: str, taluk: str, district: str = "Mysuru") -> dict:
    try:
        res = geocode_locality(village, taluk, district)
        if res:
            return {
                "source": "Nominatim",
                "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "confidence": "High",
                "data": res,
                "status": "AVAILABLE"
            }
        return {
            "source": "Nominatim",
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "confidence": "None",
            "data": {},
            "status": "UNAVAILABLE"
        }
    except Exception as e:
        return {
            "source": "Nominatim",
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "confidence": "None",
            "data": {},
            "status": "UNAVAILABLE"
        }
