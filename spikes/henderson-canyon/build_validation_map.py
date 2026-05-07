"""Generate corrected watershed_boundary_validation.html with old vs new comparison."""
import json
from pathlib import Path

ROOT = Path("/home/hermes/workspace/deanza-villas-flood-study")

# Load GeoJSON data
corrected = json.loads((ROOT / "data/vectors/henderson_watershed_boundary.geojson").read_text())
old = json.loads((ROOT / "data/vectors/henderson_watershed_boundary_WRONG_107km2.geojson").read_text())
parcel = json.loads((ROOT / "data/vectors/deanza_villas_complex_boundary.geojson").read_text())
community = json.loads((ROOT / "outputs/maps/deanza_community_poi.geojson").read_text())

# Get extents for fitBounds — handle MultiPolygon properly
c_geom = corrected["features"][0]["geometry"]
if c_geom["type"] == "MultiPolygon":
    all_lons, all_lats = [], []
    for poly in c_geom["coordinates"]:
        for ring in poly:
            for pt in ring:
                all_lons.append(pt[0])
                all_lats.append(pt[1])
elif c_geom["type"] == "Polygon":
    pts = c_geom["coordinates"][0]
    all_lons = [p[0] for p in pts]
    all_lats = [p[1] for p in pts]

fit_bounds = [min(all_lons), min(all_lats), max(all_lons), max(all_lats)]
print(f"Fit bounds: {fit_bounds}")
print(f"Corrected area: {corrected['features'][0]['properties']['area_km2']} km²")
print(f"Old area: {old['features'][0]['properties']['area_km2']} km²")

# Build HTML
corrected_json = json.dumps(corrected)
old_json = json.dumps(old)
parcel_json = json.dumps(parcel)
community_json = json.dumps(community)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Watershed Boundary Validation — Corrected</title>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; }}
  #map {{ position:absolute; top:0; bottom:0; width:100%; }}
  #info {{ position:absolute; top:10px; left:10px; background:rgba(0,0,0,0.8); color:#fff; padding:10px 14px; border-radius:6px; font-family:monospace; font-size:13px; z-index:10; max-width:380px; }}
  #info b {{ font-size:14px; }}
  .legend-item {{ margin:4px 0; }}
  .swatch {{ display:inline-block; width:20px; height:3px; margin-right:6px; vertical-align:middle; }}
</style>
</head>
<body>
<div id="info">
  <b>Watershed Boundary — CORRECTED</b><br>
  <div class="legend-item"><span class="swatch" style="background:#00ff88;height:4px;"></span> Corrected watershed (<strong>4.2 km²</strong>)</div>
  <div class="legend-item"><span class="swatch" style="background:#ff4444;border:2px dashed #ff4444;background:none;height:0;"></span> Old WBT result (<strong>107 km²</strong> — wrong)</div>
  <div class="legend-item"><span class="swatch" style="background:#ffaa00;"></span> Community bbox (pour points)</div>
  <div class="legend-item"><span class="swatch" style="background:#ff66cc;"></span> De Anza Villas parcel</div>
  <br>
  <div style="font-size:11px;color:#aaa;">WBT watershed() produced a 26x overestimate.<br>
  Corrected via BFS upstream trace on D8 pointer.</div>
</div>
<div id="map"></div>
<script>
const corrected = {corrected_json};
const old_ws = {old_json};
const parcel = {parcel_json};
const community = {community_json};

const map = new maplibregl.Map({{
  container: 'map',
  style: {{
    version: 8,
    sources: {{
      'esri-satellite': {{
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'],
        tileSize: 256,
        attribution: 'Esri World Imagery'
      }}
    }},
    layers: [{{
      id: 'satellite',
      type: 'raster',
      source: 'esri-satellite',
      paint: {{ 'raster-opacity': 0.6 }}
    }}]
  }},
  center: [-116.390, 33.290],
  zoom: 13,
  maxZoom: 18
}});

map.on('load', () => {{
  // Old (wrong) watershed — dashed red
  map.addSource('old-ws', {{ type: 'geojson', data: old_ws }});
  map.addLayer({{
    id: 'old-ws-fill', type: 'fill', source: 'old-ws',
    paint: {{ 'fill-color': '#ff4444', 'fill-opacity': 0.05 }}
  }});
  map.addLayer({{
    id: 'old-ws-line', type: 'line', source: 'old-ws',
    paint: {{ 'line-color': '#ff4444', 'line-width': 2, 'line-dasharray': [4, 3] }},
    layout: {{ 'line-cap': 'round' }}
  }});

  // Corrected watershed — solid green
  map.addSource('corrected', {{ type: 'geojson', data: corrected }});
  map.addLayer({{
    id: 'corrected-fill', type: 'fill', source: 'corrected',
    paint: {{ 'fill-color': '#00ff88', 'fill-opacity': 0.12 }}
  }});
  map.addLayer({{
    id: 'corrected-line', type: 'line', source: 'corrected',
    paint: {{ 'line-color': '#00ff88', 'line-width': 3.5 }}
  }});

  // Community bbox
  map.addSource('community', {{ type: 'geojson', data: community }});
  map.addLayer({{
    id: 'community-fill', type: 'fill', source: 'community',
    paint: {{ 'fill-color': '#ffaa00', 'fill-opacity': 0.15 }}
  }});
  map.addLayer({{
    id: 'community-line', type: 'line', source: 'community',
    paint: {{ 'line-color': '#ffaa00', 'line-width': 2.5, 'line-dasharray': [3, 2] }}
  }});

  // Parcel
  map.addSource('parcel', {{ type: 'geojson', data: parcel }});
  map.addLayer({{
    id: 'parcel-fill', type: 'fill', source: 'parcel',
    paint: {{ 'fill-color': '#ff66cc', 'fill-opacity': 0.3 }}
  }});
  map.addLayer({{
    id: 'parcel-line', type: 'line', source: 'parcel',
    paint: {{ 'line-color': '#ff66cc', 'line-width': 2.5 }}
  }});

  // Fit to corrected watershed
  map.fitBounds({fit_bounds}, {{ padding: 60 }});
}});
</script>
</body>
</html>"""

out_path = ROOT / "outputs/maps/watershed_boundary_validation.html"
out_path.write_text(html)
print(f"Saved: {out_path} ({len(html):,} bytes)")
