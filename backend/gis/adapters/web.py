import logging
from duckduckgo_search import DDGS
from .base import BaseAdapter
import re

log = logging.getLogger(__name__)

class PropertyWebAdapter(BaseAdapter):
    def __init__(self):
        super().__init__("Web / Property Sites")
        self.allowed_domains = ["housing.com", "magicbricks.com", "realestateindia.com", "99acres.com"]

    def check_status(self) -> dict:
        try:
            with DDGS() as ddgs:
                list(ddgs.text("test", max_results=1))
            return {"status": "CONNECTED", "message": "Search available"}
        except Exception as e:
            return {"status": "UNAVAILABLE", "message": str(e)}

    def fetch_facilities(self, lat: float, lon: float, locality_name: str, district: str) -> dict:
        # If we don't have locality, we can't do a good web search
        if not locality_name:
            return None
            
        results = {
            "school": [],
            "hospital": [],
            "pharmacy": [],
            "bank": [],
            "park": [],
            "bus_stop": []
        }
        
        # We only want to search a few categories to avoid rate limits
        search_cats = {
            "school": "schools",
            "hospital": "hospitals",
            "pharmacy": "pharmacies",
            "bank": "banks",
            "park": "parks",
            "bus_stop": "bus stops"
        }
        
        with DDGS() as ddgs:
            for cat, term in search_cats.items():
                query = f'"{locality_name}" "{district}" {term}'
                try:
                    search_results = list(ddgs.text(query, max_results=5))
                    
                    for r in search_results:
                        url = r.get("href", "").lower()
                            
                        title = r.get("title", "")
                        snippet = r.get("body", "")
                        
                        # Very simple mock extraction from snippet
                        # Try to find something like "2.1 km" or "1.5km"
                        dist_match = re.search(r'(\d+(?:\.\d+)?)\s*km', snippet, re.IGNORECASE)
                        dist_val = float(dist_match.group(1)) if dist_match else 2.5 # default fallback if mentioned
                        
                        # Extract a potential facility name (just a heuristic, typically the title of a page or part of snippet)
                        # We will use the title as the facility name, or if we can't extract, skip.
                        # Real NLP is better here, but we will approximate.
                        name = title.split("|")[0].split("-")[0].strip()
                        
                        results[cat].append({
                            "id": f"web_{hash(url)}",
                            "name": name,
                            "category": cat,
                            "latitude": None,
                            "longitude": None,
                            "distance_km": dist_val,
                            "distance_type": "source_reported",
                            "source": self._get_domain(url),
                            "source_type": "property_web",
                            "source_url": r.get("href"),
                            "retrieved_at": self.now_iso(),
                            "confidence": "secondary"
                        })
                except Exception as e:
                    log.warning(f"PropertyWebAdapter error for {cat}: {e}")
                    
        return results

    def _get_domain(self, url):
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return "Web Source"
