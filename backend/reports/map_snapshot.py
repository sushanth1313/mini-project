"""
Generate a crisp PNG map snapshot centered on the evaluated property using
real OpenStreetMap raster tiles (tile.openstreetmap.org) with fallback grid
if network tiles are unreachable. Used for embedding in the PDF report.
"""
import concurrent.futures
import io
import math
import os
import tempfile
import urllib.request
from PIL import Image, ImageDraw, ImageFont

# Bounded in-memory tile cache: {(z, x, y): bytes}
_TILE_CACHE = {}
_TILE_CACHE_MAX = 32

# Category marker colors (RGB) and short codes for clean legibility on OSM maps
_CAT_STYLES = {
    "school": ((37, 99, 235), "SC"),
    "hospital": ((220, 38, 38), "HO"),
    "clinic": ((239, 68, 68), "CL"),
    "pharmacy": ((217, 70, 239), "PH"),
    "bus_stop": ((5, 150, 105), "BS"),
    "railway_station": ((15, 118, 110), "RW"),
    "supermarket": ((217, 119, 6), "SM"),
    "market": ((180, 83, 9), "MK"),
    "bank": ((79, 70, 229), "BK"),
    "atm": ((99, 102, 241), "AT"),
    "police": ((30, 58, 138), "PL"),
    "park": ((22, 163, 74), "PK"),
    "waterbody": ((14, 165, 233), "WB"),
}


def _latlon_to_world_px(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    n = 2.0 ** zoom
    tx = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(max(-85.05, min(85.05, lat)))
    ty = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return tx * 256.0, ty * 256.0


def _fetch_tile(z: int, x: int, y: int) -> Image.Image | None:
    n = 2 ** z
    x_wrapped = x % n
    if y < 0 or y >= n:
        return None
    key = (z, x_wrapped, y)
    if key in _TILE_CACHE:
        try:
            return Image.open(io.BytesIO(_TILE_CACHE[key])).convert("RGBA")
        except Exception:
            pass

    url = f"https://tile.openstreetmap.org/{z}/{x_wrapped}/{y}.png"
    headers = {
        "User-Agent": "SmartLandEvaluation/1.0",
        "Accept": "image/png,image/*,*/*;q=0.8",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                raw = resp.read()
                if len(_TILE_CACHE) >= _TILE_CACHE_MAX:
                    _TILE_CACHE.pop(next(iter(_TILE_CACHE)))
                _TILE_CACHE[key] = raw
                return Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    return None


def _get_font(size: int = 12, bold: bool = False):
    candidates = (
        ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
    )
    for name in candidates:
        for base in [
            "C:\\Windows\\Fonts",
            "/usr/share/fonts/truetype/dejavu",
            "",
        ]:
            path = os.path.join(base, name) if base else name
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_property_map_snapshot(
    lat: float,
    lon: float,
    property_name: str = "Evaluated Property",
    coordinate_status: str = "USER_ENTERED",
    precision_label: str = "",
    facilities: dict | None = None,
    zoom: int = 14,
    width: int = 900,
    height: int = 490,
) -> dict:
    """
    Create a stitched OpenStreetMap PNG snapshot centered on (lat, lon) with
    property marker, nearby facility markers, scale bar, and attribution.
    Returns dict with 'path', 'tiles_loaded', 'tiles_total', 'zoom', 'markers_plotted'.
    """
    lat = float(lat)
    lon = float(lon)
    cx, cy = _latlon_to_world_px(lat, lon, zoom)
    px0 = cx - width / 2.0
    py0 = cy - height / 2.0

    tx_min = math.floor(px0 / 256.0)
    tx_max = math.floor((px0 + width - 1) / 256.0)
    ty_min = math.floor(py0 / 256.0)
    ty_max = math.floor((py0 + height - 1) / 256.0)

    tile_coords = [
        (tx, ty)
        for tx in range(tx_min, tx_max + 1)
        for ty in range(ty_min, ty_max + 1)
    ]

    canvas = Image.new("RGBA", (width, height), (241, 245, 249, 255))
    tiles_loaded = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_fetch_tile, zoom, tx, ty): (tx, ty) for tx, ty in tile_coords}
        for fut in concurrent.futures.as_completed(futs):
            tx, ty = futs[fut]
            tile_img = fut.result()
            if tile_img is not None:
                tiles_loaded += 1
                dx = int(round(tx * 256.0 - px0))
                dy = int(round(ty * 256.0 - py0))
                canvas.paste(tile_img, (dx, dy))

    draw = ImageDraw.Draw(canvas)
    font_sm = _get_font(11, bold=False)
    font_md = _get_font(12, bold=True)
    font_xs = _get_font(10, bold=True)

    # Clean vector grid if base tiles failed to load
    if tiles_loaded == 0:
        for gx in range(0, width, 60):
            draw.line([(gx, 0), (gx, height)], fill=(215, 224, 234, 255), width=1)
        for gy in range(0, height, 60):
            draw.line([(0, gy), (width, gy)], fill=(215, 224, 234, 255), width=1)

    # 1 km reference ring around property (radius in world pixels at this latitude)
    meters_per_px = 156543.03392 * math.cos(math.radians(lat)) / (2.0 ** zoom)
    r_1km = 1000.0 / meters_per_px
    draw.ellipse(
        [width / 2 - r_1km, height / 2 - r_1km, width / 2 + r_1km, height / 2 + r_1km],
        outline=(29, 78, 216, 170),
        width=2,
    )

    # Plot nearest facilities that fall inside map viewport
    markers_plotted = []
    if isinstance(facilities, dict):
        for cat, fdata in facilities.items():
            if not isinstance(fdata, dict):
                continue
            nearest = fdata.get("nearest")
            if not isinstance(nearest, dict):
                continue
            flat = nearest.get("latitude") or nearest.get("lat")
            flon = nearest.get("longitude") or nearest.get("lon")
            if flat is None or flon is None:
                continue
            fx, fy = _latlon_to_world_px(float(flat), float(flon), zoom)
            sx = fx - px0
            sy = fy - py0
            if 18 <= sx <= width - 18 and 36 <= sy <= height - 38:
                color, code = _CAT_STYLES.get(cat, ((71, 85, 105), "FD"))
                r = 10
                draw.ellipse([sx - r - 1, sy - r - 1, sx + r + 1, sy + r + 1], fill=(255, 255, 255, 240))
                draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color + (245,))
                draw.text((sx - 6, sy - 6), code, fill=(255, 255, 255, 255), font=font_xs)
                fname = (nearest.get("name") or cat.replace("_", " ").title())[:20]
                markers_plotted.append((cat, code, fname, fdata.get("nearest_distance_km")))

    # Draw center property marker (diamond/circle halo + red target pin)
    mx, my = width / 2.0, height / 2.0
    draw.ellipse([mx - 15, my - 15, mx + 15, my + 15], fill=(239, 68, 68, 55), outline=(220, 38, 38, 200), width=2)
    draw.ellipse([mx - 8, my - 8, mx + 8, my + 8], fill=(255, 255, 255, 255))
    draw.ellipse([mx - 6, my - 6, mx + 6, my + 6], fill=(220, 38, 38, 255))

    label_txt = f"{(property_name or 'Property')[:28]} ({lat:.5f} N, {lon:.5f} E)"
    bbox = draw.textbbox((0, 0), label_txt, font=font_md)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bx = mx - tw / 2 - 8
    by = my - 34 - th
    draw.rounded_rectangle([bx, by, bx + tw + 16, by + th + 8], radius=5, fill=(15, 23, 42, 220))
    draw.text((bx + 8, by + 4), label_txt, fill=(255, 255, 255, 255), font=font_md)

    # Top-left coordinate precision banner
    status_str = precision_label or coordinate_status or "USER_ENTERED"
    banner_txt = f"Source Precision: {status_str} | 1 km Radius Ring | Zoom {zoom}"
    if tiles_loaded == 0:
        banner_txt += " (OSM tiles unavailable; grid plot shown)"
    b2 = draw.textbbox((0, 0), banner_txt, font=font_sm)
    draw.rectangle([8, 8, 8 + (b2[2] - b2[0]) + 16, 30], fill=(255, 255, 255, 230), outline=(148, 163, 184, 255))
    draw.text((16, 12), banner_txt, fill=(15, 23, 42, 255), font=font_sm)

    # Top-right North arrow
    nx, ny = width - 30, 30
    draw.ellipse([nx - 16, ny - 16, nx + 16, ny + 16], fill=(255, 255, 255, 230), outline=(100, 116, 139, 255))
    draw.polygon([(nx, ny - 11), (nx - 6, ny + 7), (nx, ny + 2), (nx + 6, ny + 7)], fill=(15, 23, 42, 255))
    draw.text((nx - 3, ny + 8), "N", fill=(15, 23, 42, 255), font=font_xs)

    # Bottom bar: 500m scale bar + legend + OSM attribution
    draw.rectangle([0, height - 26, width, height], fill=(255, 255, 255, 232))
    px_500m = int(round(500.0 / meters_per_px))
    sx0, sy0 = 14, height - 10
    draw.line([(sx0, sy0), (sx0 + px_500m, sy0)], fill=(15, 23, 42, 255), width=3)
    draw.line([(sx0, sy0 - 5), (sx0, sy0 + 1)], fill=(15, 23, 42, 255), width=2)
    draw.line([(sx0 + px_500m, sy0 - 5), (sx0 + px_500m, sy0 + 1)], fill=(15, 23, 42, 255), width=2)
    draw.text((sx0 + px_500m + 8, height - 20), "500 m", fill=(15, 23, 42, 255), font=font_xs)

    codes_txt = "Markers inside view: " + (", ".join(f"{c}={n}" for _, c, n, _ in markers_plotted[:4]) or "Property pin (1 km ring)")
    draw.text((sx0 + px_500m + 60, height - 20), codes_txt[:68], fill=(51, 65, 85, 255), font=font_sm)
    draw.text((width - 215, height - 20), "© OpenStreetMap contributors", fill=(71, 85, 105, 255), font=font_sm)

    fd, out_path = tempfile.mkstemp(prefix="osm_snapshot_", suffix=".png")
    os.close(fd)
    canvas.convert("RGB").save(out_path, format="PNG", optimize=True)

    return {
        "path": out_path,
        "tiles_loaded": tiles_loaded,
        "tiles_total": len(tile_coords),
        "zoom": zoom,
        "markers_plotted": markers_plotted,
        "source": "OpenStreetMap Raster Tiles" if tiles_loaded > 0 else "Offline Coordinate Plot",
    }
