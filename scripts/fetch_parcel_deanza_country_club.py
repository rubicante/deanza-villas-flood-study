"""CLI entry point — fetch the De Anza Country Club boundary from OSM.

    python -m scripts.fetch_parcel_deanza_country_club

Delegates to deliverable.parcels.generate_deanza_country_club.
Delete data/raw/vectors/deanza_country_club_boundary.geojson to force re-fetch.
"""

import sys
from deliverable.parcels import generate_deanza_country_club

if __name__ == "__main__":
    generate_deanza_country_club()
    sys.exit(0)
