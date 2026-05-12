"""CLI entry point — fetch and derive the De Anza Villas parcel boundary.

    python -m scripts.fetch_parcel_deanza_villas

Delegates to deliverable.parcels.generate_deanza_villas.
Delete data/raw/vectors/deanza_villas_parcel_polygons.geojson to force re-fetch.
"""

import sys
from deliverable.parcels import generate_deanza_villas

if __name__ == "__main__":
    generate_deanza_villas()
    sys.exit(0)
