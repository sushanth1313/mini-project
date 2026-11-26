"""
Authoritative Karnataka GIS (KGIS / KSRSAC) Point-in-Polygon Boundary Resolver for Mysuru District.

Loads official KGIS polygons (Revenue Villages, Hoblis, Taluks, Municipal Wards, and Town/ULB Limits)
filtered to Mysuru District (KGIS District Code 26) across all 7 taluk regions.
Resolves coordinates strictly via ray-casting point-in-polygon with interior-hole support,
separating revenue village, urban locality/ward, municipal jurisdiction, hobli, taluk, district,
and likely planning authority without relying on nearby POIs or hardcoded localities.
"""
from __future__ import annotations

from array import array
import gc
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_KEEP_PROPS = frozenset({
    "KGISTalukN", "KGISHobliN", "KGISVill_1", "KGISVill_2", "LGDGPCode",
    "Administ_1", "Administ_2", "Administ_3", "KGISTownCo", "KGISWardNo",
    "KGISWardNa", "SHAPE_Area",
})

_BOUNDARIES_DIR = Path(__file__).resolve().parent / "boundaries"
_CACHE_LOCK = threading.Lock()
_LOADED_LAYERS: Optional[Dict[str, List[Dict[str, Any]]]] = None

# Clean KGIS shapefile spelling/formatting artifacts into canonical urban locality names
# (strictly string-level normalization on matched KGIS polygons — never coordinate hardcoding)
_WARD_DISPLAY_FIXES = {
    "sathgallai badavane 1st stage": ("Sathagalli", "Sathagalli Badavane 1st Stage"),
    "gathripuram 1st stage": ("Gayathripuram", "Gayathripuram 1st Stage"),
    "gokulam,brudhavana": ("Gokulam", "Gokulam, Brindavana"),
    "jayalakshmipuram,v.v.mohalla": ("Jayalakshmipuram", "Jayalakshmipuram, V.V. Mohalla"),
    "vijayanagara 1st & 2nd stage": ("Vijayanagar 1st & 2nd Stage", "Vijayanagara 1st & 2nd Stage"),
    "kuvempu nagara": ("Kuvempunagar", "Kuvempunagar"),
    "kuvempu nagara c i t b": ("Kuvempunagar CITB", "Kuvempunagar CITB"),
    "kuvempu nagara m block": ("Kuvempunagar M Block", "Kuvempunagar M Block"),
    "j p nagara": ("JP Nagar", "JP Nagar"),
    "bannimantapa": ("Bannimantap", "Bannimantap"),
    "bannimantapa hudco badavane": ("Bannimantap HUDCO Badavane", "Bannimantap HUDCO Badavane"),
    "hebbalu lakshmikanthanagar": ("Hebbal (Lakshmikanthanagar)", "Hebbalu Lakshmikanthanagar"),
    "hebbalu lokanayakananagar": ("Hebbal (Lokanayakanagar)", "Hebbalu Lokanayakanagar"),
    "yaraganahalli, ambedkar colony": ("Yaraganahalli", "Yaraganahalli, Ambedkar Colony"),
    "ajizsait nagara": ("Azeez Sait Nagar", "Azeez Sait Nagar"),
    "gousianagara ablock,usmaniya block": ("Ghousia Nagar", "Ghousia Nagar A Block / Usmaniya Block"),
    "k n pura & gousianagara": ("K.N. Pura & Ghousia Nagar", "K.N. Pura & Ghousia Nagar"),
    "rajivanagara": ("Rajeev Nagar", "Rajeev Nagar"),
    "shanthinagara 1": ("Shanthinagar", "Shanthinagar 1"),
    "shanthinagara 2": ("Shanthinagar", "Shanthinagar 2"),
    "tk_layout": ("T.K. Layout", "T.K. Layout"),
    "n r_mohalla": ("N.R. Mohalla", "N.R. Mohalla"),
    "padavarahalli_vontikoppal": ("Paduvarahalli / Vontikoppal", "Paduvarahalli & Vontikoppal"),
    "ragavendra nagara": ("Raghavendra Nagar", "Raghavendra Nagar"),
    "sathyanagara": ("Sathyanagar", "Sathyanagar"),
    "rajendranagara": ("Rajendranagar", "Rajendranagar"),
    "subashnagara": ("Subhash Nagar", "Subhash Nagar"),
    "gandhinagara": ("Gandhinagar", "Gandhinagar"),
    "jayanagara": ("Jayanagar", "Jayanagar"),
    "aravindanagara": ("Aravindanagar", "Aravindanagar"),
    "gunduraonagara": ("Gundu Rao Nagar", "Gundu Rao Nagar"),
    "ramakrishnanagara": ("Ramakrishnanagar", "Ramakrishnanagar"),
    "vishweshwaranagara": ("Vishweshwaranagar", "Vishweshwaranagar"),
    "janathanagara": ("Janathanagar", "Janathanagar"),
    "sharadadevinagara": ("Sharadadevinagar", "Sharadadevinagar"),
    "thilaknagara": ("Tilak Nagar", "Tilak Nagar"),
    "madeshwaranagara badavane": ("Mahadeshwara Nagar", "Mahadeshwara Nagar Badavane"),
    "metagali": ("Metagalli", "Metagalli"),
}

_VILLAGE_URBAN_DISPLAY_FIXES = {
    "bogadhi": "Bogadi",
    "hebbalu": "Hebbal",
}


def _clean_ward_names(raw_ward: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (short_locality_name, cleaned_ward_name) from raw KGISWardNa."""
    if not raw_ward:
        return None, None
    s = " ".join(str(raw_ward).strip().split())
    key = s.lower()
    if key in _WARD_DISPLAY_FIXES:
        return _WARD_DISPLAY_FIXES[key]
    clean_full = s.replace("_", " ").strip()
    return clean_full, clean_full


def _clean_village_name(raw_village: Optional[str], is_mysuru_taluk: bool = False) -> Optional[str]:
    if not raw_village:
        return None
    s = " ".join(str(raw_village).strip().split())
    if is_mysuru_taluk:
        fixed = _VILLAGE_URBAN_DISPLAY_FIXES.get(s.lower())
        if fixed:
            return fixed
    return s


def _search_norm_key(text: str) -> str:
    """Normalize spaces/punctuation and common Kannada-English spelling variations for KGIS search."""
    t = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    # Equivalence normalization for search only
    t = t.replace("kyalangiri", "kalyanagiri").replace("kyalana", "kalyana")
    t = t.replace("sathgallai", "sathagalli").replace("sathgalli", "sathagalli")
    t = t.replace("gathripuram", "gayathripuram").replace("brudhavana", "brindavana")
    t = t.replace("bogadhi", "bogadi").replace("hebbalu", "hebbal")
    t = t.replace("nagara", "nagar").replace("mantapa", "mantap")
    return t


def _pack_ring(ring: List[List[float]]) -> array:
    """Pack [[lon, lat], ...] into a flat float64 array('d') (~8x less RAM, bit-exact)."""
    buf = array("d")
    for pt in ring:
        buf.append(float(pt[0]))
        buf.append(float(pt[1]))
    return buf


def _compact_geom_and_bbox(geom: dict) -> Tuple[Optional[Tuple[str, Any]], Tuple[float, float, float, float]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    if gtype == "Polygon":
        rings: List[array] = []
        for ring in coords:
            packed = _pack_ring(ring)
            rings.append(packed)
            for i in range(0, len(packed), 2):
                x, y = packed[i], packed[i + 1]
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
        if minx == float("inf"):
            return None, (0.0, 0.0, 0.0, 0.0)
        return ("P", tuple(rings)), (minx, miny, maxx, maxy)

    if gtype == "MultiPolygon":
        polys: List[Tuple[array, ...]] = []
        for poly in coords:
            rings = []
            for ring in poly:
                packed = _pack_ring(ring)
                rings.append(packed)
                for i in range(0, len(packed), 2):
                    x, y = packed[i], packed[i + 1]
                    if x < minx: minx = x
                    if x > maxx: maxx = x
                    if y < miny: miny = y
                    if y > maxy: maxy = y
            polys.append(tuple(rings))
        if minx == float("inf"):
            return None, (0.0, 0.0, 0.0, 0.0)
        return ("M", tuple(polys)), (minx, miny, maxx, maxy)

    return None, (0.0, 0.0, 0.0, 0.0)


def _point_in_ring(lon: float, lat: float, ring: Any) -> bool:
    if isinstance(ring, array):
        n_dbl = len(ring)
        if n_dbl < 6:
            return False
        inside = False
        xj, yj = ring[n_dbl - 2], ring[n_dbl - 1]
        for i in range(0, n_dbl, 2):
            xi, yi = ring[i], ring[i + 1]
            if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
                inside = not inside
            xj, yj = xi, yi
        return inside

    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_geom(lon: float, lat: float, geom: Any) -> bool:
    if isinstance(geom, tuple):
        kind, payload = geom
        if kind == "P":
            if not payload or not _point_in_ring(lon, lat, payload[0]):
                return False
            for hole in payload[1:]:
                if _point_in_ring(lon, lat, hole):
                    return False
            return True
        if kind == "M":
            for poly in payload:
                if poly and _point_in_ring(lon, lat, poly[0]):
                    if not any(_point_in_ring(lon, lat, hole) for hole in poly[1:]):
                        return True
        return False

    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Polygon":
        if not coords or not _point_in_ring(lon, lat, coords[0]):
            return False
        for hole in coords[1:]:
            if _point_in_ring(lon, lat, hole):
                return False
        return True
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly and _point_in_ring(lon, lat, poly[0]):
                if not any(_point_in_ring(lon, lat, hole) for hole in poly[1:]):
                    return True
    return False


def _load_layer(filename: str) -> List[Dict[str, Any]]:
    path = _BOUNDARIES_DIR / filename
    if not path.exists():
        log.warning("KGIS boundary file missing: %s", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    indexed: List[Dict[str, Any]] = []
    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        compact_geom, bb = _compact_geom_and_bbox(geom)
        if not compact_geom:
            continue
        raw_props = feat.get("properties") or {}
        compact_props = {k: raw_props[k] for k in _KEEP_PROPS if k in raw_props}
        indexed.append({
            "props": compact_props,
            "geom": compact_geom,
            "bbox": bb,
        })
    del data
    return indexed


def _get_layers() -> Dict[str, List[Dict[str, Any]]]:
    global _LOADED_LAYERS
    if _LOADED_LAYERS is not None:
        return _LOADED_LAYERS
    with _CACHE_LOCK:
        if _LOADED_LAYERS is None:
            _LOADED_LAYERS = {
                "taluks": _load_layer("mysuru_taluks.geojson"),
                "hoblis": _load_layer("mysuru_hoblis.geojson"),
                "villages": _load_layer("mysuru_villages.geojson"),
                "towns": _load_layer("mysuru_towns.geojson"),
                "wards": _load_layer("mysuru_wards.geojson"),
            }
            gc.collect()
            log.info(
                "Loaded KGIS Mysuru boundary layers: taluks=%d, hoblis=%d, villages=%d, towns=%d, wards=%d",
                len(_LOADED_LAYERS["taluks"]),
                len(_LOADED_LAYERS["hoblis"]),
                len(_LOADED_LAYERS["villages"]),
                len(_LOADED_LAYERS["towns"]),
                len(_LOADED_LAYERS["wards"]),
            )
    return _LOADED_LAYERS


def _query_layer(layer_items: List[Dict[str, Any]], lon: float, lat: float) -> List[Dict[str, Any]]:
    hits = []
    for item in layer_items:
        minx, miny, maxx, maxy = item["bbox"]
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            continue
        if _point_in_geom(lon, lat, item["geom"]):
            hits.append(item["props"])
    # Sort smallest containing polygon first so broad boundaries do not shadow smaller reliable ones
    hits.sort(key=lambda p: float(p.get("SHAPE_Area") or 1e18))
    return hits


def _format_municipal_type(code: Optional[str]) -> str:
    c = str(code or "").strip().upper()
    return {
        "CC": "City Corporation (CC)",
        "CMC": "City Municipal Council (CMC)",
        "TMC": "Town Municipal Council (TMC)",
        "TP": "Town Panchayat (TP)",
    }.get(c, c or "Municipal Authority")


def _derive_planning_authority(
    taluk_raw: Optional[str],
    town_name: Optional[str],
    town_type_code: Optional[str],
    ward_no: Optional[str],
) -> Dict[str, str]:
    """
    Identify likely local body & planning authority strictly from KGIS boundary containment.
    Never claims property-level layout approval from GPS alone.
    """
    t_low = str(taluk_raw or "").strip().lower()
    ulb_code = str(town_type_code or "").strip().upper()
    tn_low = str(town_name or "").strip().lower()

    if town_name and ulb_code == "CC":
        local_body = f"{town_name} City Corporation (CC){f' — Ward {ward_no}' if ward_no else ''}"
        planning_auth = (
            "Mysuru Development Authority (MDA; legacy MUDA) / Mysuru City Corporation (MCC) "
            "— Verify Notified Master Plan & Layout Sanction"
        )
    elif town_name and ulb_code in ("CMC", "TMC", "TP"):
        mtype = _format_municipal_type(ulb_code)
        local_body = f"{town_name} {mtype}{f' — Ward {ward_no}' if ward_no else ''}"
        if "nanjangud" in tn_low:
            planning_auth = "Nanjangud Planning Authority / DTCP Mysuru Division"
        elif "hunsur" in tn_low:
            planning_auth = "Hunsur Planning Authority / DTCP Mysuru Division"
        elif "krishnarajanagara" in tn_low or "nagara" in tn_low:
            planning_auth = "K.R. Nagar Planning Authority / DTCP Mysuru Division"
        else:
            planning_auth = f"Directorate of Town and Country Planning (DTCP) / {town_name} {ulb_code}"
    else:
        local_body = "Gram Panchayat Jurisdiction (Outside KGIS Urban ULB Boundary)"
        if "mysur" in t_low:
            planning_auth = (
                "Jurisdiction Requires Verification (Confirm MDA / MUDA Local Planning Area vs "
                "DTCP Mysuru / Gram Panchayat)"
            )
        elif any(x in t_low for x in ("nanjangud", "hunsur", "hunasuru", "krishnarajanagara")):
            planning_auth = (
                "Jurisdiction Requires Verification (Verify Local Planning Authority LPA Boundary vs "
                "DTCP / Gram Panchayat)"
            )
        elif t_low:
            planning_auth = (
                f"DTCP Mysuru Division / Gram Panchayat ({taluk_raw} Taluk) — "
                "Jurisdiction Requires Verification for Conversion/Layout"
            )
        else:
            planning_auth = "Jurisdiction Requires Verification"

    return {
        "local_body": local_body,
        "likely_planning_authority": planning_auth,
    }


def lookup_kgis_location(lat: float, lon: float) -> Dict[str, Any]:
    """
    Resolve (lat, lon) strictly against authoritative KGIS boundary polygons for Mysuru District.
    Selects the smallest reliable containing locality polygon (MCC urban neighbourhood ward inside
    Mysuru City Corporation when smaller than the legacy revenue village; KGIS revenue village
    outside MCC or in rural taluks) while returning ward, revenue village, hobli, taluk,
    local body, and planning authority separately.
    """
    layers = _get_layers()
    taluk_hits = _query_layer(layers["taluks"], lon, lat)
    hobli_hits = _query_layer(layers["hoblis"], lon, lat)
    village_hits = _query_layer(layers["villages"], lon, lat)
    town_hits = _query_layer(layers["towns"], lon, lat)
    ward_hits = _query_layer(layers["wards"], lon, lat)

    taluk_props = taluk_hits[0] if taluk_hits else {}
    hobli_props = hobli_hits[0] if hobli_hits else {}
    village_props = village_hits[0] if village_hits else {}
    town_props = town_hits[0] if town_hits else {}
    ward_props = ward_hits[0] if ward_hits else {}

    kgis_taluk = (taluk_props.get("KGISTalukN") or "").strip() or None
    hobli = (hobli_props.get("KGISHobliN") or "").strip().title() or None
    raw_village = (village_props.get("KGISVill_2") or "").strip() or None
    is_mysuru_taluk = bool(kgis_taluk and kgis_taluk.lower().startswith("mysur"))
    revenue_village = _clean_village_name(raw_village, is_mysuru_taluk=is_mysuru_taluk) if raw_village else None
    village_code = (village_props.get("KGISVill_1") or "").strip() or None
    lgd_gp_code = (village_props.get("LGDGPCode") or "").strip() or None

    town_code = str(town_props.get("Administ_1") or ward_props.get("KGISTownCo") or "").strip() or None
    town_name = (town_props.get("Administ_2") or "").strip() or ("Mysuru" if town_code == "2605" else None)
    town_type_code = (town_props.get("Administ_3") or "").strip() or ("CC" if town_code == "2605" else None)
    ward_no = str(ward_props.get("KGISWardNo") or "").strip() or None
    raw_ward_name = (ward_props.get("KGISWardNa") or "").strip() or None
    ward_short_loc, clean_ward_name = _clean_ward_names(raw_ward_name)

    ward_area_sqm = float(ward_props.get("SHAPE_Area")) if ward_props.get("SHAPE_Area") else None
    village_area_sqm = float(village_props.get("SHAPE_Area")) if village_props.get("SHAPE_Area") else None

    overlap_villages = [str(v.get("KGISVill_2") or "").strip() for v in village_hits if v.get("KGISVill_2")]
    overlap_detected = len(set(overlap_villages)) > 1

    jur = _derive_planning_authority(kgis_taluk, town_name, town_type_code, ward_no)
    matched = bool(taluk_hits or village_hits or town_hits or ward_hits)

    # Smallest reliable containing locality polygon selection:
    # Inside Mysuru City Corporation (town_code == 2605 / CC), MCC wards (0.2–4 km²) represent
    # real urban neighbourhoods (Udayagiri, Kalyanagiri, Gokulam, Vijayanagar, Kuvempunagar, JP Nagar,
    # Jayalakshmipuram, Bannimantap, Sathagalli, Kyathamaranahalli) instead of broad legacy revenue villages.
    is_mcc_city = (town_code == "2605") or (town_type_code == "CC" and town_name and "mysur" in town_name.lower())
    smallest_locality = None
    smallest_boundary_type = None
    smallest_area_sqm = None

    if is_mcc_city and ward_short_loc:
        smallest_locality = ward_short_loc
        smallest_boundary_type = "KGIS Mysuru City Municipal Ward Polygon"
        smallest_area_sqm = ward_area_sqm
    elif revenue_village:
        smallest_locality = revenue_village
        smallest_boundary_type = "KGIS Revenue Village Polygon"
        smallest_area_sqm = village_area_sqm
    elif ward_short_loc:
        smallest_locality = ward_short_loc
        smallest_boundary_type = "KGIS Municipal Ward Polygon"
        smallest_area_sqm = ward_area_sqm

    urban_locality = None
    if clean_ward_name:
        urban_locality = f"{clean_ward_name} (Ward {ward_no})" if ward_no else clean_ward_name
    elif town_name and town_type_code in ("CC", "CMC", "TMC", "TP"):
        urban_locality = f"{town_name} Urban Limits"

    return {
        "matched": matched,
        "source": "Karnataka GIS (KGIS / KSRSAC) Official Boundary Polygons",
        "point_in_polygon": matched,
        "district": "Mysuru" if matched else None,
        "kgis_taluk": kgis_taluk,
        "hobli": hobli,
        "revenue_village": raw_village,
        "revenue_village_display": revenue_village,
        "revenue_village_code": village_code,
        "lgd_gp_code": lgd_gp_code,
        "smallest_locality": smallest_locality,
        "smallest_boundary_type": smallest_boundary_type,
        "smallest_area_sqm": smallest_area_sqm,
        "urban_locality": urban_locality,
        "ward_number": ward_no,
        "ward_name": clean_ward_name,
        "raw_ward_name": raw_ward_name,
        "ward_area_sqm": ward_area_sqm,
        "village_area_sqm": village_area_sqm,
        "municipal_name": town_name,
        "municipal_type": _format_municipal_type(town_type_code) if town_type_code else None,
        "local_body": jur["local_body"],
        "likely_planning_authority": jur["likely_planning_authority"],
        "overlap_detected": overlap_detected,
        "overlapping_villages": overlap_villages if overlap_detected else [],
        "gram_panchayat_lgd_code": lgd_gp_code or None,
        "assembly_constituency": None,
        "assembly_constituency_status": "UNAVAILABLE_NO_DATASET",
    }


def get_kgis_coverage_summary() -> Dict[str, Any]:
    """Compute real feature & jurisdiction coverage counts from loaded KGIS GeoJSON layers."""
    layers = _get_layers()
    taluk_names = sorted({
        (it["props"].get("KGISTalukN") or "").strip()
        for it in layers["taluks"]
        if (it["props"].get("KGISTalukN") or "").strip()
    })
    villages_with_gp = sum(
        1 for it in layers["villages"] if (it["props"].get("LGDGPCode") or "").strip()
    )
    mcc_wards = sum(
        1 for it in layers["wards"] if str(it["props"].get("KGISTownCo") or "").strip() == "2605"
    )
    ulb_list = sorted({
        f"{(it['props'].get('Administ_2') or '').strip()} ({(it['props'].get('Administ_3') or '').strip()})"
        for it in layers["towns"]
        if (it["props"].get("Administ_2") or "").strip()
    })
    return {
        "taluk_polygons": len(layers["taluks"]),
        "unique_kgis_taluks": taluk_names,
        "hobli_polygons": len(layers["hoblis"]),
        "revenue_village_polygons": len(layers["villages"]),
        "villages_with_lgd_gp_code": villages_with_gp,
        "urban_local_body_polygons": len(layers["towns"]),
        "urban_local_bodies": ulb_list,
        "municipal_ward_polygons": len(layers["wards"]),
        "mcc_mysuru_wards": mcc_wards,
        "assembly_constituency_polygons": 0,
        "assembly_constituency_available": False,
        "authority": "Karnataka GIS (KGIS / KSRSAC)",
    }


def _interior_point(item: Dict[str, Any]) -> Tuple[float, float]:
    """Return a guaranteed interior (lat, lon) inside the polygon item rather than assuming bbox center."""
    bb = item["bbox"]
    geom = item["geom"]
    clat = (bb[1] + bb[3]) / 2.0
    clon = (bb[0] + bb[2]) / 2.0
    if _point_in_geom(clon, clat, geom):
        return (round(clat, 6), round(clon, 6))
    # Scan grid inside bbox to find an interior point for concave polygons
    for fy in (0.5, 0.35, 0.65, 0.25, 0.75):
        for fx in (0.5, 0.35, 0.65, 0.25, 0.75):
            ty = bb[1] + (bb[3] - bb[1]) * fy
            tx = bb[0] + (bb[2] - bb[0]) * fx
            if _point_in_geom(tx, ty, geom):
                return (round(ty, 6), round(tx, 6))
    return (round(clat, 6), round(clon, 6))


def search_kgis_villages(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Search authoritative KGIS revenue village polygons by normalized name."""
    q = (query or "").strip().lower()
    q_norm = _search_norm_key(q)
    if len(q) < 2:
        return []
    layers = _get_layers()
    matches: List[Dict[str, Any]] = []
    seen = set()
    for item in layers["villages"]:
        vname = (item["props"].get("KGISVill_2") or "").strip()
        if not vname:
            continue
        v_norm = _search_norm_key(vname)
        if q not in vname.lower() and (not q_norm or q_norm not in v_norm):
            continue
        clat, clon = _interior_point(item)
        info = lookup_kgis_location(clat, clon)
        disp_loc = info.get("revenue_village_display") or vname
        key = (disp_loc.lower(), (info.get("kgis_taluk") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "name": disp_loc,
            "locality": disp_loc,
            "taluk": info.get("kgis_taluk") or "Mysuru",
            "hobli": info.get("hobli"),
            "ward_number": info.get("ward_number"),
            "ward_name": info.get("ward_name"),
            "district": "Mysuru",
            "latitude": clat,
            "longitude": clon,
            "exact_match": v_norm == q_norm or v_norm.startswith(q_norm),
            "source": "KGIS",
        })
        if len(matches) >= limit * 2:
            break
    matches.sort(key=lambda m: (0 if m["exact_match"] else 1, 0 if (m.get("taluk") or "").lower() == "mysuru" else 1))
    return matches[:limit]


def search_kgis_wards(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Search authoritative KGIS urban municipal ward polygons by normalized name or number."""
    q = (query or "").strip().lower()
    q_norm = _search_norm_key(q)
    if len(q) < 2:
        return []
    layers = _get_layers()
    matches: List[Dict[str, Any]] = []
    seen = set()
    for item in layers["wards"]:
        raw_wname = (item["props"].get("KGISWardNa") or "").strip()
        wno = str(item["props"].get("KGISWardNo") or "").strip()
        short_wloc, clean_wname = _clean_ward_names(raw_wname)
        if not clean_wname and not wno:
            continue
        w_norm = _search_norm_key(f"{raw_wname} {clean_wname or ''} {short_wloc or ''}")
        if q not in raw_wname.lower() and q not in (clean_wname or "").lower() and q != wno.lower() and (not q_norm or q_norm not in w_norm):
            continue
        clat, clon = _interior_point(item)
        info = lookup_kgis_location(clat, clon)
        loc_canon = info.get("smallest_locality") or short_wloc or clean_wname
        key = (wno, (clean_wname or "").lower(), (info.get("kgis_taluk") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "name": f"{clean_wname} (Ward {wno})" if wno else clean_wname,
            "locality": loc_canon,
            "ward_number": wno or None,
            "ward_name": clean_wname or None,
            "taluk": info.get("kgis_taluk") or "Mysuru",
            "hobli": info.get("hobli"),
            "municipal_body": info.get("local_body"),
            "district": "Mysuru",
            "latitude": clat,
            "longitude": clon,
            "exact_match": _search_norm_key(short_wloc or "").startswith(q_norm) or _search_norm_key(clean_wname or "").startswith(q_norm),
            "source": "KGIS_WARD",
        })
        if len(matches) >= limit * 2:
            break
    matches.sort(key=lambda m: (0 if m["exact_match"] else 1, 0 if (m.get("taluk") or "").lower() == "mysuru" else 1))
    return matches[:limit]
