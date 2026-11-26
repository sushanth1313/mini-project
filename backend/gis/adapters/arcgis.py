"""
Secondary Coordinate-Backed Geospatial Discovery Adapter (ArcGIS World Geocoder).
Used strictly as a non-hardcoded secondary POI source when OpenStreetMap Overpass
returns NO_DATA, times out, or has sparse rural/peri-urban mapping (>2.5 km gap).

All retrieved POIs are:
  - Coordinate-backed (WGS-84 lat/lon validated inside Mysuru District polygon)
  - Strictly filtered by Haversine distance <= category radius
  - Filtered by returned POI Type and anti-noise rules
  - Attributed transparently as "ArcGIS World Geocoder (Secondary POI)"
"""
import concurrent.futures
import json
import logging
import threading
import urllib.parse
import urllib.request
from .base import BaseAdapter

log = logging.getLogger(__name__)

# Mapping from our 13 internal categories to ArcGIS World GeocodeServer categories & accepted Type tokens
ARCGIS_CATEGORY_SPEC = {
    "school": ("School", {"school", "college", "university", "education"}, 10000),
    "hospital": ("Hospital", {"hospital", "medical center"}, 10000),
    "clinic": ("Medical Clinic", {"medical clinic", "clinic", "hospital", "doctor"}, 10000),
    "pharmacy": ("Pharmacy", {"pharmacy", "drugstore"}, 10000),
    "police": ("Police Station", {"police station", "government office"}, 10000),
    "bank": ("Bank", {"bank"}, 10000),
    "atm": ("ATM", {"atm"}, 5000),
    "supermarket": ("Grocery", {"grocery", "supermarket", "department store", "shopping"}, 10000),
    "market": ("Shopping Center", {"shopping center", "market", "grocery", "department store"}, 10000),
    "park": ("Park", {"park", "garden", "recreation area"}, 10000),
    "railway_station": ("Train Station", {"train station", "railway station"}, 10000),
    "bus_stop": ("Bus Station", {"bus station", "transit", "bus stop"}, 5000),
}

_BANK_POSITIVE_TOKENS = (
    "bank", "sbi", "hdfc", "icici", "axis", "canara", "union", "karnataka bank",
    "syndicate", "corporation", "pnb", "bob", "baroda", "idbi", "kotak", "indusind",
    "federal", "uco", "indian bank", "grameena", "pragathi", "gramin", "co-op",
    "cooperative", "credit society", "dcc", "vijaya", "dena",
)
_NOISE_NAME_TOKENS = (
    "digital studio", "photo studio", "xerox", "tours", "travels", "motors",
    "garage", "driving school", "internet cafe", "cyber cafe", "mobile store",
    "baby sitting", "tuitions", "tuition", "coaching centre", "coaching center",
)

ARCGIS_CACHE: dict = {}
ARCGIS_STATUS_CACHE: dict = {}
_ARCGIS_LOCK = threading.Lock()


class ArcGISGeocodeAdapter(BaseAdapter):
    SEARCH_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

    def __init__(self, timeout: int = 8):
        super().__init__("ArcGIS World Geocoder")
        self.timeout = timeout
        self.last_category_status: dict = {}

    def check_status(self) -> dict:
        params = urllib.parse.urlencode({
            "f": "json",
            "category": "Police Station",
            "location": "76.6552,12.3052",
            "distance": 5000,
            "maxLocations": 1,
        })
        try:
            req = urllib.request.Request(
                f"{self.SEARCH_URL}?{params}",
                headers={"User-Agent": "SmartLandEvaluation/1.0"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    return {"status": "CONNECTED", "message": "Connected to ArcGIS World Geocoder"}
        except Exception as exc:
            return {"status": "UNAVAILABLE", "message": f"ArcGIS Geocoder unreachable: {exc}"}
        return {"status": "UNAVAILABLE", "message": "ArcGIS Geocoder unavailable"}

    @staticmethod
    def _is_valid_poi(cat: str, name: str, poi_type: str) -> bool:
        n_low = (name or "").strip().lower()
        t_low = (poi_type or "").strip().lower()
        if not n_low or any(bad in n_low for bad in _NOISE_NAME_TOKENS):
            return False

        _, valid_types, _ = ARCGIS_CATEGORY_SPEC.get(cat, ("", set(), 10000))
        if valid_types and t_low and t_low not in valid_types:
            return False

        if cat == "bank":
            if not any(tok in n_low for tok in _BANK_POSITIVE_TOKENS):
                return False
        elif cat == "police":
            if not any(tok in n_low for tok in ("police", "outpost", "thana", "circle inspector", "dy.sp", "dsp", "sp office", "home guard")):
                return False
        elif cat == "bus_stop":
            if not any(tok in n_low for tok in ("bus", "stand", "stop", "depot", "ksrtc", "terminal")):
                return False
        elif cat == "park":
            if any(tok in n_low for tok in ("lake", "dam", "reservoir", "kere")) and "park" not in n_low:
                return False
        return True

    def fetch_categories(self, lat: float, lon: float, categories: list[str], radius_m: int = 5000) -> dict:
        """Query only the requested missing/sparse categories concurrently."""
        from gis.geo_utils import is_in_mysuru_district

        results = {cat: [] for cat in categories}
        cat_status = {}
        to_fetch = []

        cache_prefix = f"{round(lat, 3)}_{round(lon, 3)}_{int(radius_m)}"
        with _ARCGIS_LOCK:
            for cat in categories:
                ck = f"{cache_prefix}_{cat}"
                if ck in ARCGIS_CACHE:
                    _, _, def_r = ARCGIS_CATEGORY_SPEC.get(cat, ("", set(), 5000))
                    max_km = max(int(radius_m or def_r), def_r) / 1000.0
                    recomp = []
                    for it in ARCGIS_CACHE[ck]:
                        d_new = self.haversine(lat, lon, it["latitude"], it["longitude"])
                        if d_new <= max_km:
                            it_c = dict(it)
                            it_c["distance_km"] = round(d_new, 3)
                            recomp.append(it_c)
                    recomp.sort(key=lambda x: x["distance_km"])
                    results[cat] = recomp
                    cat_status[cat] = "SUCCESS" if recomp else "NO_DATA"
                elif cat in ARCGIS_CATEGORY_SPEC:
                    to_fetch.append(cat)
                else:
                    cat_status[cat] = "NO_DATA"

        if not to_fetch:
            self.last_category_status = cat_status
            return results

        def _query_cat(cat: str):
            arc_cat, _, def_r = ARCGIS_CATEGORY_SPEC[cat]
            eff_r = max(int(radius_m or def_r), def_r)
            max_km = eff_r / 1000.0
            params = urllib.parse.urlencode({
                "f": "json",
                "category": arc_cat,
                "location": f"{lon},{lat}",
                "distance": eff_r,
                "maxLocations": 10,
                "outFields": "PlaceName,Place_addr,Type,Score",
            })
            url = f"{self.SEARCH_URL}?{params}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SmartLandEvaluation/1.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                log.warning(f"ArcGISGeocodeAdapter failed for {cat}: {exc}")
                return cat, [], "SOURCE_UNAVAILABLE"

            found = []
            seen_coords = set()
            for idx, cand in enumerate(payload.get("candidates", [])):
                loc = cand.get("location") or {}
                elat, elon = loc.get("y"), loc.get("x")
                if elat is None or elon is None:
                    continue
                elat_f, elon_f = float(elat), float(elon)
                if not is_in_mysuru_district(elat_f, elon_f):
                    continue
                dist = self.haversine(lat, lon, elat_f, elon_f)
                if dist > max_km:
                    continue

                attrs = cand.get("attributes") or {}
                name = str(attrs.get("PlaceName") or cand.get("address") or "").strip()
                poi_type = str(attrs.get("Type") or "").strip()
                if not self._is_valid_poi(cat, name, poi_type):
                    continue

                coord_key = (round(elat_f, 4), round(elon_f, 4))
                if coord_key in seen_coords:
                    continue
                seen_coords.add(coord_key)

                found.append({
                    "id": f"arcgis_{cat}_{idx}_{round(elat_f, 5)}_{round(elon_f, 5)}",
                    "name": name,
                    "category": cat,
                    "latitude": elat_f,
                    "longitude": elon_f,
                    "distance_km": round(dist, 3),
                    "distance_type": "calculated",
                    "source": "ArcGIS World Geocoder (Secondary POI)",
                    "source_type": "arcgis",
                    "source_url": "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer",
                    "retrieved_at": self.now_iso(),
                    "confidence": "secondary_gis",
                    "coverage": "secondary_geocoder",
                    "is_generic_name": False,
                })

            found.sort(key=lambda x: x["distance_km"])
            status = "SUCCESS" if found else "NO_DATA"
            return cat, found, status

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(_query_cat, cat) for cat in to_fetch]
            for fut in concurrent.futures.as_completed(futs):
                cat, items, st = fut.result()
                results[cat] = items
                cat_status[cat] = st
                if st != "SOURCE_UNAVAILABLE":
                    ck = f"{cache_prefix}_{cat}"
                    with _ARCGIS_LOCK:
                        ARCGIS_CACHE[ck] = list(items)
                        ARCGIS_STATUS_CACHE[ck] = st

        self.last_category_status = cat_status
        return results

    def fetch_facilities(self, lat: float, lon: float, radius_m: int = 5000) -> dict:
        return self.fetch_categories(lat, lon, list(ARCGIS_CATEGORY_SPEC.keys()), radius_m=radius_m)
