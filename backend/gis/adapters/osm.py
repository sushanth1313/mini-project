import logging
import urllib.request
import urllib.parse
import urllib.error
import json
import math
import concurrent.futures
from datetime import datetime, timezone
from .base import BaseAdapter

log = logging.getLogger(__name__)

# 13 facility categories with explicit node/way tag definitions and search radii
# 13 facility categories with explicit node/way tag definitions and search radii.
# Radii extend to 10 km for major civic/medical/policing services so peri-urban & rural
# properties across all 7 Mysuru taluks discover their actual nearest mapped facility
# instead of returning NO_DATA beyond 5 km (counts <=1/3/5 km remain strictly filtered by distance).
FACILITY_CONFIG = {
    "school": ([("amenity", "school")], 10000),
    "hospital": ([("amenity", "hospital"), ("healthcare", "hospital")], 10000),
    "clinic": ([
        ("amenity", "clinic"), ("healthcare", "clinic"), ("amenity", "doctors"),
        ("healthcare", "doctor"), ("healthcare", "health_centre"),
        ("healthcare", "centre"), ("amenity", "health_post"),
    ], 10000),
    "supermarket": ([("shop", "supermarket"), ("shop", "convenience")], 10000),
    "market": ([("amenity", "marketplace"), ("shop", "mall"), ("shop", "market"), ("shop", "wholesale")], 10000),
    "pharmacy": ([("amenity", "pharmacy"), ("healthcare", "pharmacy"), ("shop", "chemist")], 10000),
    "bus_stop": ([("highway", "bus_stop"), ("amenity", "bus_station"), ("highway", "bus_station")], 5000),
    "railway_station": ([("railway", "station"), ("railway", "halt"), ("railway", "tram_stop")], 10000),
    "bank": ([("amenity", "bank"), ("amenity", "bureau_de_change")], 10000),
    "police": ([
        ("amenity", "police"), ("police", "station"), ("police", "checkpoint"),
        ("office", "police"), ("building", "police"),
    ], 10000),
    "atm": ([("amenity", "atm")], 5000),
    "park": ([("leisure", "park"), ("leisure", "garden"), ("leisure", "playground")], 10000),
    "waterbody": ([("natural", "water"), ("waterway", "river"), ("landuse", "reservoir"), ("natural", "lake")], 5000),
    "canal": ([("waterway", "canal"), ("waterway", "drain")], 5000),
}

# Nominatim query terms for fallback when Overpass is slow/unavailable.
# Concise, high-signal queries avoid 429 rate throttling.
NOMINATIM_TERMS = {
    "school": ["[amenity=school]", "school"],
    "hospital": ["[amenity=hospital]", "hospital"],
    "clinic": ["[amenity=clinic]", "[healthcare=centre]", "clinic"],
    "supermarket": ["[shop=supermarket]", "supermarket"],
    "market": ["[amenity=marketplace]", "marketplace"],
    "pharmacy": ["[amenity=pharmacy]", "pharmacy"],
    "bus_stop": ["[amenity=bus_station]", "[highway=bus_stop]", "bus station", "bus stop"],
    "railway_station": ["[railway=station]", "railway station"],
    "bank": ["[amenity=bank]", "bank"],
    "police": ["[amenity=police]", "police station"],
    "atm": ["[amenity=atm]", "atm"],
    "park": ["[leisure=park]", "park"],
    "waterbody": ["[natural=water]", "[waterway=river]", "lake"],
    "canal": ["[waterway=canal]", "irrigation canal"],
}

import threading
import time as _time

# Cache for GIS queries: key = f"{round(lat, 3)}_{round(lon, 3)}"
GIS_CACHE = {}
GIS_STATUS_CACHE = {}
_GIS_CACHE_LOCK = threading.Lock()
_GIS_CACHE_TTL_SECONDS = 3600  # 1 hour

# Circuit breaker shared with utility_service so a single evaluation never wastes 2x40s retrying dead Overpass
_OVERPASS_CIRCUIT_UNTIL = 0.0
_OVERPASS_CIRCUIT_LOCK = threading.Lock()


def is_overpass_circuit_open() -> bool:
    with _OVERPASS_CIRCUIT_LOCK:
        return _time.monotonic() < _OVERPASS_CIRCUIT_UNTIL


def trip_overpass_circuit(cooldown_seconds: int = 90) -> None:
    global _OVERPASS_CIRCUIT_UNTIL
    with _OVERPASS_CIRCUIT_LOCK:
        _OVERPASS_CIRCUIT_UNTIL = max(_OVERPASS_CIRCUIT_UNTIL, _time.monotonic() + cooldown_seconds)


def reset_overpass_circuit() -> None:
    global _OVERPASS_CIRCUIT_UNTIL
    with _OVERPASS_CIRCUIT_LOCK:
        _OVERPASS_CIRCUIT_UNTIL = 0.0


OVERPASS_ENDPOINTS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Allowed OSM (class, type) validation for Nominatim keyword fallback to prevent unrelated POIs
_NOMINATIM_ALLOWED_CLASSES = {
    "school": {"amenity": {"school", "college", "university", "kindergarten"}, "building": {"school"}},
    "hospital": {"amenity": {"hospital", "clinic"}, "healthcare": {"hospital", "clinic"}, "building": {"hospital"}},
    "clinic": {"amenity": {"clinic", "doctors", "hospital", "health_post"}, "healthcare": {"clinic", "doctor", "centre", "health_centre"}},
    "supermarket": {"shop": {"supermarket", "convenience", "department_store", "general"}},
    "market": {"amenity": {"marketplace"}, "shop": {"mall", "market", "wholesale", "supermarket"}},
    "pharmacy": {"amenity": {"pharmacy"}, "healthcare": {"pharmacy"}, "shop": {"chemist"}},
    "bus_stop": {"highway": {"bus_stop", "bus_station", "platform"}, "amenity": {"bus_station", "bus_stop"}, "public_transport": {"platform", "stop_position", "station"}},
    "railway_station": {"railway": {"station", "halt", "tram_stop"}, "public_transport": {"station"}},
    "bank": {"amenity": {"bank", "bureau_de_change"}},
    "police": {"amenity": {"police"}, "office": {"police"}, "police": {"station", "checkpoint"}, "building": {"police"}},
    "atm": {"amenity": {"atm"}},
    "park": {"leisure": {"park", "garden", "playground", "recreation_ground"}},
    "waterbody": {"natural": {"water", "lake", "pond"}, "waterway": {"river", "stream"}, "landuse": {"reservoir", "basin"}, "water": {"lake", "pond", "reservoir"}},
    "canal": {"waterway": {"canal", "drain", "ditch"}},
}


class OSMAdapter(BaseAdapter):
    def __init__(self, overpass_url=None, timeout=12):
        super().__init__("OpenStreetMap")
        self.endpoints = [overpass_url] if overpass_url else OVERPASS_ENDPOINTS
        self.timeout = timeout
        self.last_category_status = {}
        
    def _post_overpass(self, url: str, query: str, timeout: int) -> dict | None:
        """Post an Overpass QL query using urllib.request. Returns dict or None."""
        payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
        # Note: overpass.openstreetmap.fr returns HTTP 403 for User-Agents containing parentheses/email
        headers = {
            "User-Agent": "SmartLandEvaluation/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            log.warning(f"Overpass request to {url} failed: {e}")
        return None

    def check_status(self) -> dict:
        """Check availability: fast Overpass check (3s), then Nominatim (3s)."""
        for url in self.endpoints:
            result = self._post_overpass(
                url,
                "[out:json][timeout:3];node(12.3,76.7,12.31,76.71);out 1;",
                timeout=3,
            )
            if result is not None:
                return {"status": "CONNECTED", "message": f"Connected to {url}"}
        
        # Test Nominatim
        nom_url = "https://nominatim.openstreetmap.org/search?format=json&q=Mysuru&limit=1"
        try:
            req = urllib.request.Request(
                nom_url,
                headers={"User-Agent": "SmartLandEvaluation/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return {"status": "CONNECTED", "message": "Connected to OpenStreetMap (Nominatim)"}
        except Exception:
            pass

        return {"status": "UNAVAILABLE", "message": "All OpenStreetMap endpoints unreachable"}

    def _match_categories(self, tags: dict) -> list[str]:
        matched = []
        for cat, (tag_specs, _) in FACILITY_CONFIG.items():
            for k, v in tag_specs:
                if tags.get(k) == v:
                    matched.append(cat)
                    break
        return matched

    def _match_category(self, tags: dict) -> str:
        cats = self._match_categories(tags)
        return cats[0] if cats else None
        return None

    def _explicit_tag_name(self, tags: dict) -> str:
        for key in ("name", "name:en", "official_name", "alt_name", "short_name"):
            val = (tags.get(key) or "").strip()
            if val:
                return val
        return ""

    def _default_name_for_cat(self, cat: str, tags: dict) -> str:
        name = self._explicit_tag_name(tags)
        if name:
            return name
        
        operator = tags.get("operator", "")
        if cat == "atm":
            return f"{operator} ATM".strip() if operator else "Local ATM"
        elif cat == "bank":
            return f"{operator} Bank Branch".strip() if operator else "Bank Branch"
        elif cat == "bus_stop":
            return "Bus Stop"
        elif cat == "railway_station":
            return "Railway Station / Halt"
        elif cat == "canal":
            return "Irrigation Canal"
        elif cat == "waterbody":
            if tags.get("waterway") == "canal":
                return "Irrigation Canal"
            wtype = tags.get("water", tags.get("natural", tags.get("waterway", "Waterbody")))
            return f"{str(wtype).title()} (Lake/Pond/River)"
        elif cat == "park":
            return "Public Park / Garden"
        elif cat == "school":
            return "Educational Institution"
        elif cat == "hospital":
            return "Hospital / Health Center"
        elif cat == "clinic":
            return "Clinic / Medical Practice"
        elif cat == "pharmacy":
            return "Pharmacy / Chemist"
        elif cat == "supermarket":
            return "Supermarket / Department Store"
        elif cat == "market":
            return "Marketplace / Commercial Market"
        elif cat == "police":
            return "Police Station / Outpost"
        return "Unnamed Facility"

    def _fetch_from_nominatim(self, lat: float, lon: float, radius_m: int = 5000) -> dict | None:
        """
        Query OpenStreetMap via Nominatim bounded viewbox search for all 13 categories.
        Note: Nominatim keyword search is an incomplete fallback when Overpass is unavailable,
        so found categories are marked PARTIAL (never complete SUCCESS).
        """
        results = {k: [] for k in FACILITY_CONFIG.keys()}
        headers = {"User-Agent": "SmartLandEvaluation/1.0"}

        def _fetch_cat(cat: str, terms: list):
            import time
            found_for_cat = []
            seen_ids = set()
            seen_coords = set()
            _, default_r = FACILITY_CONFIG.get(cat, ([], 5000))
            cat_radius_m = max(radius_m, default_r)
            cat_d = (cat_radius_m / 1000.0) / 111.0 * 1.15
            c_left, c_top, c_right, c_bottom = lon - cat_d, lat + cat_d, lon + cat_d, lat - cat_d
            success_count = 0
            error_count = 0

            for term in terms:
                params = urllib.parse.urlencode({
                    "format": "json",
                    "q": term,
                    "viewbox": f"{c_left},{c_top},{c_right},{c_bottom}",
                    "bounded": 1,
                    "limit": 8
                })
                url = f"https://nominatim.openstreetmap.org/search?{params}"
                items = None
                for attempt in range(2):
                    try:
                        req = urllib.request.Request(url, headers=headers)
                        with urllib.request.urlopen(req, timeout=6) as resp:
                            items = json.loads(resp.read().decode("utf-8"))
                            success_count += 1
                            break
                    except Exception as ex:
                        if attempt == 0:
                            time.sleep(0.35)
                        else:
                            error_count += 1
                            log.warning(f"Nominatim query failed for {cat}/{term}: {ex}")
                if items:
                    allowed_map = _NOMINATIM_ALLOWED_CLASSES.get(cat, {})
                    for item in items:
                        try:
                            iclass = str(item.get("class") or "").strip().lower()
                            itype = str(item.get("type") or "").strip().lower()
                            # Strictly validate category match for free-text queries (prevents stadiums/offices leaking into POIs)
                            if not term.startswith("[") and allowed_map:
                                valid_types = allowed_map.get(iclass)
                                if valid_types is None or (valid_types and itype not in valid_types):
                                    continue

                            raw_osm_id = item.get("osm_id", 0)
                            raw_osm_type = item.get("osm_type", "node")
                            osm_id = f"{raw_osm_type}_{raw_osm_id}"
                            if osm_id in seen_ids:
                                continue
                            seen_ids.add(osm_id)

                            elat = float(item["lat"])
                            elon = float(item["lon"])
                            coord_key = (round(elat, 4), round(elon, 4))
                            if coord_key in seen_coords:
                                continue
                            seen_coords.add(coord_key)

                            dist = self.haversine(lat, lon, elat, elon)
                            if dist > (cat_radius_m / 1000.0) * 1.2:
                                continue

                            explicit_name = (item.get("name") or "").strip()
                            if explicit_name:
                                raw_name = explicit_name
                                if cat == "bus_stop" and itype == "bus_station" and "bus" not in raw_name.lower():
                                    raw_name = f"{raw_name} Bus Station"
                            else:
                                hint = item.get("display_name", "").split(",")[0].strip()
                                fallback = self._default_name_for_cat(cat, {})
                                raw_name = f"{fallback} ({hint})" if hint else fallback

                            found_for_cat.append({
                                "id": f"osm_nom_{osm_id}",
                                "osm_id": raw_osm_id,
                                "osm_type": raw_osm_type,
                                "tags": {
                                    "class": iclass,
                                    "type": itype,
                                },
                                "name": raw_name,
                                "category": cat,
                                "latitude": elat,
                                "longitude": elon,
                                "distance_km": round(dist, 3),
                                "distance_type": "calculated",
                                "source": "OpenStreetMap (Nominatim Fallback)",
                                "source_type": "osm",
                                "source_url": "https://nominatim.openstreetmap.org",
                                "retrieved_at": self.now_iso(),
                                "confidence": "unverified_nominatim_geocoder",
                                "is_confirmed_poi": False,
                                "coverage": "partial_nominatim_fallback",
                            })
                        except Exception:
                            continue
                time.sleep(0.1)

            found_for_cat.sort(key=lambda x: x["distance_km"])
            if success_count == 0:
                cat_status = "SOURCE_UNAVAILABLE"
            elif found_for_cat or error_count > 0:
                # Nominatim keyword fallback cannot guarantee exhaustive spatial recall
                cat_status = "PARTIAL"
            else:
                cat_status = "NO_DATA"
            return cat, found_for_cat, cat_status

        try:
            cat_statuses = {}
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            try:
                future_to_cat = {
                    executor.submit(_fetch_cat, cat, terms): cat
                    for cat, terms in NOMINATIM_TERMS.items()
                }
                done, not_done = concurrent.futures.wait(future_to_cat.keys(), timeout=26)
                for future in done:
                    try:
                        cat, items, c_status = future.result()
                        results[cat] = items
                        cat_statuses[cat] = c_status
                    except Exception as _fe:
                        log.warning("Nominatim category future error: %s", _fe)
                for future in not_done:
                    cat = future_to_cat[future]
                    cat_statuses.setdefault(cat, "SOURCE_UNAVAILABLE")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            self.last_category_status = cat_statuses
            if all(st == "SOURCE_UNAVAILABLE" for st in cat_statuses.values()):
                log.error("Nominatim: All 14 category queries failed.")
                return None
            return results
        except Exception as e:
            log.error(f"Nominatim pool error: {e}")
            return None

    def fetch_facilities(self, lat: float, lon: float, radius_m: int = 5000) -> dict | None:
        """
        Fetch real facilities from OpenStreetMap around the given coordinates.
        1. Queries Overpass API endpoints concurrently (bounded <= 12 s).
        2. Trips shared Overpass circuit breaker if all fail so downstream steps skip waiting.
        3. If Overpass fails/times out, falls back to OpenStreetMap Nominatim API.
        """
        cache_key = f"{round(lat, 3)}_{round(lon, 3)}"
        now_m = _time.monotonic()
        with _GIS_CACHE_LOCK:
            cached = GIS_CACHE.get(cache_key)
            if cached is not None:
                cached_ts = GIS_STATUS_CACHE.get(f"{cache_key}__ts", 0.0)
                is_partial_cache = bool(GIS_STATUS_CACHE.get(f"{cache_key}__is_partial", False))
                ttl = 45 if is_partial_cache else _GIS_CACHE_TTL_SECONDS
                if (now_m - cached_ts) < ttl:
                    log.info(f"OSMAdapter: Returning GIS results from cache for {cache_key} (recomputing distances).")
                    self.last_category_status = dict(GIS_STATUS_CACHE.get(cache_key, {}))
                    recomputed_map = {}
                    for cat, items in cached.items():
                        _, default_r = FACILITY_CONFIG.get(cat, ([], 5000))
                        max_km = max(radius_m, default_r) / 1000.0 * 1.05 if radius_m else (default_r / 1000.0 * 1.05)
                        recomp_items = []
                        for it in items:
                            elat, elon = it.get("latitude"), it.get("longitude")
                            if elat is None or elon is None:
                                continue
                            d_new = self.haversine(lat, lon, elat, elon)
                            if d_new <= max_km:
                                c_it = dict(it)
                                c_it["distance_km"] = round(d_new, 3)
                                recomp_items.append(c_it)
                        recomp_items.sort(key=lambda x: x["distance_km"])
                        recomputed_map[cat] = recomp_items
                    return recomputed_map

        results = {k: [] for k in FACILITY_CONFIG.keys()}
        query_parts = []
        cat_radii_km = {}
        for cat, (tag_specs, default_r) in FACILITY_CONFIG.items():
            r = max(radius_m, default_r) if radius_m else default_r
            cat_radii_km[cat] = r / 1000.0
            for k, v in tag_specs:
                query_parts.append(f'  node["{k}"="{v}"](around:{r},{lat},{lon});')
                query_parts.append(f'  way["{k}"="{v}"](around:{r},{lat},{lon});')
                if cat in ("park", "waterbody", "canal"):
                    query_parts.append(f'  relation["{k}"="{v}"](around:{r},{lat},{lon});')

        query_body = "\n".join(query_parts)
        overpass_q_timeout = max(6, min(self.timeout, 10))
        cat_query = f"""[out:json][timeout:{overpass_q_timeout}];
(
{query_body}
);
out center tags;
"""
        data = None
        used_endpoint = None
        using_default_eps = (self.endpoints == OVERPASS_ENDPOINTS)
        if using_default_eps and is_overpass_circuit_open():
            log.info("Overpass circuit breaker OPEN — skipping Overpass and using Nominatim fallback directly.")
        else:
            # Query endpoints concurrently; take first valid JSON response within 11 s
            ep_pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(self.endpoints) or 1)
            try:
                ep_futs = {
                    ep_pool.submit(self._post_overpass, ep, cat_query, overpass_q_timeout + 1): ep
                    for ep in self.endpoints
                }
                pending = set(ep_futs.keys())
                deadline = _time.monotonic() + (overpass_q_timeout + 2)
                while pending:
                    rem = max(0.1, deadline - _time.monotonic())
                    done, pending = concurrent.futures.wait(
                        pending, timeout=rem, return_when=concurrent.futures.FIRST_COMPLETED
                    )
                    if not done:
                        break
                    for fut in done:
                        ep = ep_futs[fut]
                        try:
                            resp_data = fut.result()
                            if resp_data is not None and "elements" in resp_data:
                                data = resp_data
                                used_endpoint = ep
                                log.info(f"Overpass success at {ep}, got {len(resp_data['elements'])} elements")
                                break
                        except Exception as e:
                            log.warning(f"Overpass query to {ep} failed: {e}")
                    if data is not None:
                        break
            finally:
                ep_pool.shutdown(wait=False, cancel_futures=True)

            if data is None and using_default_eps:
                trip_overpass_circuit(90)

        if data is not None and "elements" in data:
            if using_default_eps:
                reset_overpass_circuit()
            seen_per_cat = {k: set() for k in FACILITY_CONFIG.keys()}
            for elem in data["elements"]:
                tags = elem.get("tags", {})
                matched_cats = self._match_categories(tags)
                if not matched_cats:
                    continue

                if elem["type"] == "node":
                    elat, elon = elem.get("lat"), elem.get("lon")
                elif elem["type"] in ("way", "relation") and "center" in elem:
                    elat, elon = elem["center"]["lat"], elem["center"]["lon"]
                else:
                    continue

                if elat is None or elon is None:
                    continue

                elem_id = elem.get("id", 0)
                dist = self.haversine(lat, lon, elat, elon)

                for cat in matched_cats:
                    if elem_id in seen_per_cat[cat]:
                        continue
                    if dist > cat_radii_km.get(cat, 10.0) * 1.05:
                        continue
                    seen_per_cat[cat].add(elem_id)

                    explicit_nm = self._explicit_tag_name(tags)
                    name = self._default_name_for_cat(cat, tags)
                    results[cat].append({
                        "id": f"osm_{elem.get('type')}_{elem_id}",
                        "osm_id": elem_id,
                        "osm_type": elem.get("type"),
                        "tags": dict(tags),
                        "name": name,
                        "is_generic_name": not bool(explicit_nm),
                        "category": cat,
                        "latitude": elat,
                        "longitude": elon,
                        "distance_km": round(dist, 3),
                        "distance_type": "calculated",
                        "source": "OpenStreetMap (Overpass)",
                        "source_type": "osm",
                        "source_url": used_endpoint or "https://overpass.openstreetmap.fr",
                        "retrieved_at": self.now_iso(),
                        "confidence": "primary_gis",
                        "coverage": "complete_overpass",
                    })

            for k in results.keys():
                results[k].sort(key=lambda x: x["distance_km"])

            self.last_category_status = {
                k: ("SUCCESS" if results[k] else "NO_DATA") for k in results.keys()
            }
            with _GIS_CACHE_LOCK:
                GIS_CACHE[cache_key] = results
                GIS_STATUS_CACHE[cache_key] = dict(self.last_category_status)
                GIS_STATUS_CACHE[f"{cache_key}__ts"] = _time.monotonic()
                GIS_STATUS_CACHE[f"{cache_key}__is_partial"] = False
            return results

        # Overpass unavailable -> Use OpenStreetMap Nominatim fallback (always PARTIAL / NO_DATA)
        log.info("Overpass unavailable; querying OpenStreetMap via Nominatim POI engine...")
        nom_results = self._fetch_from_nominatim(lat, lon, radius_m)
        if nom_results is not None:
            with _GIS_CACHE_LOCK:
                GIS_CACHE[cache_key] = nom_results
                GIS_STATUS_CACHE[cache_key] = dict(self.last_category_status)
                GIS_STATUS_CACHE[f"{cache_key}__ts"] = _time.monotonic()
                GIS_STATUS_CACHE[f"{cache_key}__is_partial"] = True
            return nom_results

        self.last_category_status = {k: "SOURCE_UNAVAILABLE" for k in FACILITY_CONFIG.keys()}
        log.error("OSMAdapter: All OpenStreetMap data sources (Overpass + Nominatim) failed.")
        return None
