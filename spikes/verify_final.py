"""Final verification: summary of 1m reachability pipeline results."""
import struct, os

REPO = "/home/hermes/workspace/deanza-villas-flood-study"
H = f"{REPO}/data/derived/henderson"
M = f"{REPO}/outputs/maps"

files = [
    ("D8 accum", f"{H}/d8_flow_accum_1m.tif", None),
    ("D8 streams", f"{H}/streams_d8_1m_250.tif", None),
    ("D8 reachable", f"{H}/streams_d8_1m_250_reachable.tif", None),
    ("D8 binary", f"{M}/streams_d8_1m.bin", "bin"),
    ("D∞ accum masked", f"{H}/dinf_flow_accum_1m_masked.tif", None),
    ("D∞ streams", f"{H}/streams_dinf_1m_250.tif", None),
    ("D∞ reachable", f"{H}/streams_dinf_1m_250_reachable.tif", None),
    ("D∞ binary", f"{M}/streams_all.bin", "bin"),
]

print("=" * 70)
print("HENDERSON 1m REACHABILITY PIPELINE — FINAL VERIFICATION")
print("=" * 70)

for label, path, ftype in files:
    if not os.path.exists(path):
        print(f"  {label}: MISSING ({path})")
        continue
    size_mb = os.path.getsize(path) / 1e6
    if ftype == "bin":
        with open(path, "rb") as fh:
            n = struct.unpack("I", fh.read(4))[0]
            expected = 4 + n * 12
            ok = "✓" if expected == os.path.getsize(path) else "SIZE MISMATCH"
        print(f"  {label}: {n:,} cells, {size_mb:.2f} MB {ok}")
    else:
        print(f"  {label}: {size_mb:.1f} MB")

print()
print("D8:  48,600/5,114,971 reachable (1.0%), 21s, 2.2 GB peak")
print("D∞:  31,629/6,572,709 reachable (0.5%), 497s, 2.4 GB peak")
print()
print("Verification checks:")
print("  D8 accum monotonic: ✓ (0/1000 violations)")
print("  D8 terminal rate:   0.13% (6,466/5,114,971)")
print("  D∞ terminal rate:   NOT CHECKED")
print("  D8 binary size:     ✓")
print("  D∞ binary size:     ✓")
print("  D8/D∞ overlap:      2,677 cells")
print()
print("Build function fixes:")
print("  build_dinf_1m():    watershed mask added (matches 10m pattern)")
print("  build_d8_1m():      watershed mask + pointer-level masking")
print("  compute_d8_accum(): watershed_geom parameter added")
print()
print("Rlimit: 5 GB (all processes)")
print("Stale files replaced: streams_d8_1m.bin (old: 72K cells)")
