"""Static map of a report's area: OpenStreetMap tiles, the drawn boundary and parcel dots.

Returns a PNG as a data URI for the report template, or None when tiles can't be
fetched (the report then falls back to the plain outline).
"""

import base64
import io

from staticmap import CircleMarker, Line, StaticMap

TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# OSM's tile policy asks for an identifying User-Agent.
HEADERS = {"User-Agent": "ClimateLensReports/0.1 (hackathon prototype; SBTN screening reports)"}
ATTRIBUTION = "Map data © OpenStreetMap contributors"
RISK, OTHER, BOUNDARY = "#c0392b", "#1f6f8b", "#16302a"


def render(polygons, parcels, width=1400, height=820, runoff_risk=lambda p: False, dot=6, padding=40):
    """polygons: [[outer ring [[lon, lat], …], …], …]; parcels: objects with lon, lat."""
    m = StaticMap(width, height, padding_x=padding, padding_y=padding, url_template=TILES,
                  headers=HEADERS, tile_request_timeout=10)
    for poly in polygons:
        ring = [tuple(pt[:2]) for pt in (poly[0] if poly else [])]
        if len(ring) > 2:
            m.add_line(Line(ring, "white", max(3, dot + 1)))
            m.add_line(Line(ring, BOUNDARY, max(2, dot - 2)))
    located = [p for p in parcels if p.lon is not None and p.lat is not None]
    # Other parcels first, so runoff-risk parcels are drawn on top.
    for p in sorted(located, key=runoff_risk):
        m.add_marker(CircleMarker((p.lon, p.lat), "white", dot + 3))
        m.add_marker(CircleMarker((p.lon, p.lat), RISK if runoff_risk(p) else OTHER, dot))
    if not m.lines and not m.markers:
        return None
    try:
        image = m.render()
    except Exception:
        return None  # no network or tile server refused: the report shows the outline instead
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
