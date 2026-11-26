from datetime import datetime, timezone
import math

class BaseAdapter:
    def __init__(self, name: str):
        self.name = name
    
    def now_iso(self):
        return datetime.now(timezone.utc).isoformat()
        
    def haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def fetch_facilities(self, lat: float, lon: float, radius_m: int) -> dict:
        """
        Returns a dict of facilities by category.
        Format:
        {
           "school": [
               {
                   "id": "...",
                   "name": "...",
                   "category": "school",
                   "latitude": 12.33,
                   "longitude": 76.71,
                   "distance_km": 0.8,
                   "distance_type": "calculated" | "source_reported",
                   "source": self.name,
                   "source_type": "...",
                   "source_url": "...",
                   "retrieved_at": self.now_iso(),
                   "confidence": "...",
               }, ...
           ]
        }
        """
        raise NotImplementedError
    
    def check_status(self) -> dict:
        """
        Returns status information for the Data Sources page.
        Format: { "status": "CONNECTED"|"NOT_CONFIGURED"|"UNAVAILABLE", "message": "..." }
        """
        raise NotImplementedError
