from .osm_source import fetch_osm_facilities
from .nominatim_source import fetch_locality_coordinates
from .property_source import fetch_property_data
from .government_reference_source import verify_bhoomi_rtc, verify_kaveri_encumbrance

__all__ = [
    'fetch_osm_facilities',
    'fetch_locality_coordinates',
    'fetch_property_data',
    'verify_bhoomi_rtc',
    'verify_kaveri_encumbrance'
]
