import logging
import math
import re
from .adapters.osm import OSMAdapter
from .adapters.arcgis import ArcGISGeocodeAdapter, ARCGIS_CATEGORY_SPEC
from .adapters.google import GooglePlacesAdapter
from .adapters.web import PropertyWebAdapter

log = logging.getLogger(__name__)

_GENERIC_NAME_PREFIXES = (
    "police station / outpost",
    "unnamed facility",
    "hospital / health center",
    "clinic / medical practice",
    "pharmacy / chemist",
    "educational institution",
    "public park / garden",
    "bus stop",
    "railway station / halt",
    "supermarket / department store",
    "marketplace / commercial market",
    "bank branch",
    "local atm",
    "irrigation canal",
)


def _is_generic_name(item: dict) -> bool:
    if item.get("is_generic_name") is True:
        return True
    nm = (item.get("name") or "").strip().lower()
    if not nm:
        return True
    return nm in _GENERIC_NAME_PREFIXES


class LocationEnrichment:
    def __init__(self):
        self.osm = OSMAdapter()
        self.arcgis = ArcGISGeocodeAdapter()
        self.google = GooglePlacesAdapter()
        self.web = PropertyWebAdapter()

    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""
        s = re.sub(r"[^a-zA-Z0-9\s]", "", name).lower()
        for w in ["school", "hospital", "clinic", "pharmacy", "bank", "atm", "park", "police station", "station"]:
            s = s.replace(w, "")
        return " ".join(s.split())

    def _deduplicate(self, facilities: list) -> list:
        """
        Deduplicate same-spot nodes/ways cleanly while NEVER letting an unnamed building
        outline replace a properly named feature at the same physical site.
        """
        unique: list[dict] = []
        seen_ids: set = set()
        seen_items: list[tuple[int, str, float, float, bool]] = []  # (idx, norm_name, lat, lon, is_generic)

        def get_priority(f):
            st = f.get("source_type")
            if st == "osm":
                return 1
            if st == "google_places":
                return 2
            if st == "arcgis":
                return 2
            return 3

        def _haversine(la1, lo1, la2, lo2):
            r = 6371.0
            p1, p2 = math.radians(la1), math.radians(la2)
            dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
            a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
            return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        # Sort explicit non-generic names first at similar distances (<120m), then source priority & distance
        ordered = sorted(
            facilities,
            key=lambda x: (
                get_priority(x),
                1 if _is_generic_name(x) else 0,
                x.get("distance_km") if x.get("distance_km") is not None else 999,
            ),
        )

        for f in ordered:
            osm_id = f.get("osm_id") or f.get("id")
            if osm_id and osm_id in seen_ids:
                continue

            is_gen = _is_generic_name(f)
            norm_name = "" if is_gen else self._normalize_name(f.get("name") or "")
            lat, lon = f.get("latitude"), f.get("longitude")

            dup_idx = None
            if lat is not None and lon is not None:
                for idx, sname, slat, slon, sgen in seen_items:
                    if slat is None or slon is None:
                        continue
                    dist_between = _haversine(lat, lon, slat, slon)
                    # Same physical site (<120m) or matching name within 350m
                    if dist_between < 0.12:
                        dup_idx = idx
                        break
                    if norm_name and sname and dist_between <= 0.35 and (
                        norm_name == sname or norm_name in sname or sname in norm_name
                    ):
                        dup_idx = idx
                        break

            if dup_idx is not None:
                # If existing record had a generic fallback name and the new one has an explicit name, upgrade it
                if not is_gen and seen_items[dup_idx][4]:
                    unique[dup_idx] = f
                    seen_items[dup_idx] = (dup_idx, norm_name, lat, lon, False)
                    if osm_id:
                        seen_ids.add(osm_id)
                continue

            new_idx = len(unique)
            unique.append(f)
            if osm_id:
                seen_ids.add(osm_id)
            seen_items.append((new_idx, norm_name, lat, lon, is_gen))

        return unique

    def get_facilities(self, lat: float, lon: float, radius_m: int = 5000, locality: str = "", district: str = "") -> dict:
        """
        District-wide multi-source facility discovery (concurrent):
        1. Primary OpenStreetMap Overpass (+ Nominatim partial fallback).
        2. Google Places (when configured) — run concurrently with OSM.
        3. Secondary ArcGIS World Geocoder for categories that returned NO_DATA,
           timed out, or only had distant matches (> 2.5 km) in OSM — keeping exact
           real coordinates and honest source provenance.

        All external sources have bounded wallclock timeouts so a single slow/down
        provider never blocks the entire evaluation pipeline.
        """
        import concurrent.futures as _cf

        cats = [
            "school", "hospital", "clinic", "supermarket", "market",
            "pharmacy", "bus_stop", "railway_station", "bank", "police", "atm", "park",
            "waterbody", "canal",
        ]
        all_facilities = {cat: [] for cat in cats}

        # 1 + 2. Primary OSM and Google Places run CONCURRENTLY (bounded: 40 s each; never block on stuck threads)
        osm_res = None
        google_res = None
        _pool = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="gis_primary")
        try:
            _fut_osm = _pool.submit(self.osm.fetch_facilities, lat, lon, radius_m)
            _fut_google = _pool.submit(self.google.fetch_facilities, lat, lon, radius_m)
            _done, _not_done = _cf.wait((_fut_osm, _fut_google), timeout=40)
            if _fut_osm in _done:
                try:
                    osm_res = _fut_osm.result()
                except Exception as _exc:
                    log.warning("OSM facility fetch failed: %s", _exc)
            else:
                log.warning("OSM facility fetch timed out (>40 s) — continuing with partial/fallback results")
            if _fut_google in _done:
                try:
                    google_res = _fut_google.result()
                except Exception as _exc:
                    log.warning("Google Places fetch failed: %s", _exc)
            else:
                log.warning("Google Places fetch timed out (>40 s)")
        finally:
            _pool.shutdown(wait=False, cancel_futures=True)

        if osm_res:
            for cat, items in osm_res.items():
                if cat in all_facilities:
                    all_facilities[cat].extend(
                        [i for i in items if i.get("latitude") is not None and i.get("longitude") is not None]
                    )
        if google_res:
            for cat, items in google_res.items():
                if cat in all_facilities:
                    all_facilities[cat].extend(
                        [i for i in items if i.get("latitude") is not None and i.get("longitude") is not None]
                    )

        # 3. Secondary ArcGIS POI supplement for empty or distant (> 2.5 km) categories
        osm_cat_status = dict(getattr(self.osm, "last_category_status", {}) or {})
        supplement_cats = []
        for cat in cats:
            if cat not in ARCGIS_CATEGORY_SPEC:
                continue
            cur_items = all_facilities[cat]
            nearest_d = min((i.get("distance_km") for i in cur_items if i.get("distance_km") is not None), default=None)
            if not cur_items or nearest_d is None or nearest_d > 2.5 or osm_cat_status.get(cat) in ("PARTIAL", "SOURCE_UNAVAILABLE"):
                supplement_cats.append(cat)

        arcgis_res = {}
        arcgis_cat_status = {}
        if supplement_cats:
            _apool = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="gis_arcgis")
            try:
                _afut = _apool.submit(self.arcgis.fetch_categories, lat, lon, supplement_cats, radius_m)
                _adone, _ = _cf.wait((_afut,), timeout=14)
                if _afut in _adone:
                    arcgis_res = _afut.result() or {}
                    arcgis_cat_status = dict(getattr(self.arcgis, "last_category_status", {}) or {})
                else:
                    log.warning("ArcGIS secondary fetch timed out (>14 s)")
            except Exception as _exc:
                log.warning("ArcGIS secondary fetch failed: %s", _exc)
                arcgis_res = {}
            finally:
                _apool.shutdown(wait=False, cancel_futures=True)
            for cat, items in arcgis_res.items():
                if cat in all_facilities and items:
                    all_facilities[cat].extend(items)

        results = {}
        cat_status = {}
        has_google_data = bool(google_res and any(google_res.values()))
        for cat, items in all_facilities.items():
            deduped = self._deduplicate(items)
            deduped.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 999)
            results[cat] = deduped

            raw_osm_st = osm_cat_status.get(cat) or ("SOURCE_UNAVAILABLE" if osm_res is None else "NO_DATA")
            raw_arc_st = arcgis_cat_status.get(cat)
            has_primary_verified = any(
                (i.get("source_type") == "osm" and i.get("coverage") != "partial_nominatim_fallback")
                or i.get("source_type") == "google_places"
                for i in deduped
            )
            if deduped:
                if has_primary_verified or (raw_osm_st in ("SUCCESS", "NO_DATA") and (has_google_data or raw_osm_st == "SUCCESS")):
                    cat_status[cat] = "SUCCESS"
                elif raw_osm_st in ("PARTIAL", "SOURCE_UNAVAILABLE"):
                    # Overpass failed or only Nominatim/ArcGIS returned results -> honest PARTIAL
                    cat_status[cat] = "PARTIAL"
                else:
                    cat_status[cat] = "SUCCESS"
            elif raw_osm_st == "SOURCE_UNAVAILABLE" and raw_arc_st in (None, "SOURCE_UNAVAILABLE"):
                cat_status[cat] = "SOURCE_UNAVAILABLE"
            elif raw_osm_st == "PARTIAL" or raw_arc_st == "SOURCE_UNAVAILABLE":
                cat_status[cat] = "PARTIAL"
            elif osm_res is None and google_res is None and not arcgis_res:
                cat_status[cat] = "SOURCE_UNAVAILABLE"
            else:
                cat_status[cat] = "NO_DATA"

        if osm_res is None and google_res is None and not any(cat_status[c] == "SUCCESS" for c in cats):
            status = "SOURCE_UNAVAILABLE"
        elif any(st in ("SOURCE_UNAVAILABLE", "PARTIAL") for st in cat_status.values()):
            status = "PARTIAL"
        else:
            status = "SUCCESS"

        return {"data": results, "status": status, "category_status": cat_status}

    def check_sources(self) -> dict:
        return {
            "osm": self.osm.check_status(),
            "arcgis": self.arcgis.check_status(),
            "google": self.google.check_status(),
            "web": self.web.check_status(),
        }
