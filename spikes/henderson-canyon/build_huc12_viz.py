"""Rebuild: only Borrego Palm Canyon HUC12 + community bbox + D∞ watershed."""
import json
from pathlib import Path

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")

wbd = json.loads((ROOT / "data/vectors/wbd_huc12_borrego.geojson").read_text())
watershed = json.loads((ROOT / "data/vectors/henderson_watershed_boundary.geojson").read_text())
community = json.loads((ROOT / "outputs/maps/deanza_community_poi.geojson").read_text())

# Extract only Borrego Palm Canyon
palm = None
for f in wbd["features"]:
    if f["properties"]["huc12"] == "181002030302":
        palm = f
        break

palm_fc = json.dumps({"type": "FeatureCollection", "features": [palm]})

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Borrego Palm Canyon — HUC12 181002030302</title>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; font-family:-apple-system,sans-serif; }}
  #map {{ position:absolute; top:0; bottom:0; width:100%; }}
  #info {{ position:absolute; bottom:8px; left:8px; color:#666; font-size:10px; z-index:10; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="info">Borrego Palm Canyon · HUC12 181002030302 · 149.1 km² · USGS WBD</div>

<script>
const palm = {palm_fc};
const watershed = {json.dumps(watershed)};
const community = {json.dumps(community)};

const map = new maplibregl.Map({{
  container: 'map',
  style: {{
    version: 8,
    sources: {{ 'esri': {{ type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'], tileSize: 256 }} }},
    layers: [{{ id: 'sat', type: 'raster', source: 'esri', paint: {{ 'raster-opacity': 0.55 }} }}]
  }},
  center: [-116.39, 33.29],
  zoom: 11,
  maxZoom: 17
}});

map.on('load', () => {{
  // Borrego Palm Canyon HUC12
  map.addSource('palm', {{ type: 'geojson', data: palm }});
  map.addLayer({{ id: 'palm-fill', type: 'fill', source: 'palm', paint: {{ 'fill-color': '#ff4444', 'fill-opacity': 0.10 }} }});
  map.addLayer({{ id: 'palm-line', type: 'line', source: 'palm', paint: {{ 'line-color': '#ff4444', 'line-width': 3, 'line-opacity': 0.85 }} }});

  // D∞ watershed
  map.addSource('ws', {{ type: 'geojson', data: watershed }});
  map.addLayer({{ id: 'ws-fill', type: 'fill', source: 'ws', paint: {{ 'fill-color': '#00ff88', 'fill-opacity': 0.06 }} }});
  map.addLayer({{ id: 'ws-line', type: 'line', source: 'ws', paint: {{ 'line-color': '#00ff88', 'line-width': 3, 'line-opacity': 0.9 }} }});

  // Community bbox
  map.addSource('comm', {{ type: 'geojson', data: community }});
  map.addLayer({{ id: 'comm-fill', type: 'fill', source: 'comm', paint: {{ 'fill-color': '#ffaa00', 'fill-opacity': 0.18 }} }});
  map.addLayer({{ id: 'comm-line', type: 'line', source: 'comm', paint: {{ 'line-color': '#ffaa00', 'line-width': 2.5, 'line-dasharray': [3,2] }} }});

  // Label
  map.addSource('label', {{
    type: 'geojson',
    data: {{ type: 'Feature', properties: {{}}, geometry: {{ type: 'Point', coordinates: [-116.45, 33.31] }} }}
  }});
  map.addLayer({{
    id: 'label', type: 'symbol', source: 'label',
    layout: {{ 'text-field': 'Borrego Palm Canyon', 'text-size': 14, 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Bold'] }},
    paint: {{ 'text-color': '#ff4444', 'text-halo-color': '#000000', 'text-halo-width': 3, 'text-opacity': 0.9 }}
  }});

  map.fitBounds([-116.55, 33.20, -116.20, 33.38], {{ padding: 40 }});
}});
</script>
</body>
</html>"""

out = ROOT / "outputs/maps/wbd_huc12_borrego.html"
out.write_text(html)
print(f"Saved: {out} ({len(html):,} bytes)")
