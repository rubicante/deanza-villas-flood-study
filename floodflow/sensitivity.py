"""`floodflow sensitivity`: one-at-a-time input sensitivity of the 8 m flood run.

Each case changes one input from the default `FloodParams` (100-year 1-hour,
n = 0.045, no losses, centred peak). All cases run at once on Modal, one
machine each, then every case is written as a normal flood run
(data/derived/runs/<parcel>/flood/<tag>/) and the batch is tabulated in
data/derived/runs/<parcel>/flood/sensitivity_<res>m.{csv,md}.

The channel-roughness cases need the default run's max_depth.tif (see
`flood.channel_mask`); `--local` runs the batch here, one case at a time.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import replace

from floodflow.config import PARCELS, Layout
from floodflow.flood import FloodParams, finish, grid_for, inputs
from floodflow.hydraulics import simulate


def cases(base: FloodParams) -> list[tuple[str, str, FloodParams]]:
    """(group, label, params). Losses: desert fan soils are mostly sandy
    (HSG A/B), so the range runs up to a 20 mm initial loss and 25 mm/h."""
    c = [("baseline", "default", base)]
    for il in (5, 10, 20):
        c.append(("losses", f"initial {il} mm", replace(base, initial_loss_mm=il)))
    for cl in (5, 10, 25):
        c.append(("losses", f"constant {cl} mm/h", replace(base, loss_rate_mm_h=cl)))
    for il, cl in ((10, 10), (15, 20)):
        c.append(("losses", f"{il} mm + {cl} mm/h",
                  replace(base, initial_loss_mm=il, loss_rate_mm_h=cl)))
    for n in (0.03, 0.06, 0.08):
        c.append(("manning", f"n = {n:g} everywhere", replace(base, manning_n=n)))
    for n in (0.07, 0.10, 0.15):
        c.append(("manning", f"n = {n:g} on steep channels", replace(base, channel_n=n)))
    for d in (360, 1440):
        c.append(("duration", f"{d // 60} h", replace(base, duration_min=d)))
    for ari in (10, 25, 500):
        c.append(("return period", f"{ari}-year", replace(base, ari_years=ari)))
    for pk in (0.25, 0.75):
        c.append(("peak position", f"peak at {pk:.0%}", replace(base, peak_frac=pk)))
    return c


COLUMNS = ("group", "case", "tag", "rain_mm", "loss_frac", "outflow_frac",
           "parcel_p50_m", "parcel_p90_m", "parcel_max_m", "parcel_ge015", "parcel_ge03",
           "parcel_peak_min", "parcel_vmax_ms",
           "zoneA_p50_m", "zoneA_p90_m", "zoneA_ge03",
           "outside_p99_m", "outside_ge03", "steps", "wall_s")


def row(group: str, label: str, s: dict) -> dict:
    mb, p, out = s["mass_balance"], s["parcel"], s.get("outside_sfha", {})
    za = next((z for z in s.get("fema_zones", []) if z["zone"] == "A"), None)
    return {
        "group": group, "case": label, "tag": FloodParams(**s["params"]).tag,
        "rain_mm": s["storm"]["total_mm"],
        "loss_frac": round(mb["loss_m3"] / mb["rain_m3"], 3),
        "outflow_frac": round(mb["outflow_m3"] / mb["rain_m3"], 3),
        "parcel_p50_m": p["depth_m"]["p50"], "parcel_p90_m": p["depth_m"]["p90"],
        "parcel_max_m": p["depth_m"]["max"],
        "parcel_ge015": p["fraction_deeper_than"]["0.15m"],
        "parcel_ge03": p["fraction_deeper_than"]["0.3m"],
        "parcel_peak_min": p.get("time_of_max_depth_min_median"),
        "parcel_vmax_ms": p.get("speed_max_ms"),
        "zoneA_p50_m": za and za["depth_m"]["p50"], "zoneA_p90_m": za and za["depth_m"]["p90"],
        "zoneA_ge03": za and za["fraction_deeper_than"]["0.3m"],
        "outside_p99_m": out and out["depth_m"]["p99"],
        "outside_ge03": out and out["fraction_deeper_than"]["0.3m"],
        "steps": s["run"]["steps"], "wall_s": s["run"]["wall_seconds"],
    }


def _markdown(rows: list[dict], base: dict) -> str:
    def pct(v):
        return "" if v is None else f"{v:.1%}"

    def m(v):
        return "" if v is None else f"{v:.2f}"

    head = ("| group | case | rain mm | lost | parcel p50 | parcel p90 | parcel max "
            "| parcel ≥0.3 m | p90 vs base | peak min | Zone A p90 | Zone A ≥0.3 m "
            "| outside SFHA ≥0.3 m |")
    lines = [head, "|" + "---|" * (head.count("|") - 1)]
    for r in rows:
        ratio = r["parcel_p90_m"] / base["parcel_p90_m"] if base["parcel_p90_m"] else 0
        lines.append(
            f"| {r['group']} | {r['case']} | {r['rain_mm']:.1f} | {pct(r['loss_frac'])} "
            f"| {m(r['parcel_p50_m'])} | {m(r['parcel_p90_m'])} | {m(r['parcel_max_m'])} "
            f"| {pct(r['parcel_ge03'])} | ×{ratio:.2f} | {r['parcel_peak_min'] or ''} "
            f"| {m(r['zoneA_p90_m'])} | {pct(r['zoneA_ge03'])} | {pct(r['outside_ge03'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="floodflow sensitivity",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("--parcel", choices=list(PARCELS), default="deanza_villas")
    ap.add_argument("--res", type=float, default=FloodParams().resolution_m)
    ap.add_argument("--cpu", type=int, default=16, help="Cores per Modal machine")
    ap.add_argument("--local", action="store_true", help="Run here, one case at a time")
    ap.add_argument("--only", nargs="*", default=None, metavar="GROUP",
                    help="Run only these groups (e.g. losses manning)")
    a = ap.parse_args(argv)
    layout = Layout.for_parcel(a.parcel)
    if not layout.boundary.exists():
        layout.parcel.generate(layout.boundary)

    base = FloodParams(resolution_m=a.res)
    todo = [c for c in cases(base) if a.only is None or c[0] in a.only or c[0] == "baseline"]
    print(f"=== sensitivity: {layout.parcel.name}, {len(todo)} cases at {a.res:g} m ===")
    inp = inputs(layout, base)
    jobs = []
    for _, label, p in todo:
        print(f"  {label}: {p.tag}")
        jobs.append((grid_for(layout, p, inp), inp.blocks(p), 300.0,
                     p.after_storm_min * 60.0, p.solver()))

    t0 = time.time()
    summaries: dict[int, dict] = {}
    if a.local:
        for i, (g, rb, bs, ta, sp) in enumerate(jobs):
            t = time.time()
            st = simulate(g, rb, bs, ta, sp)
            summaries[i] = finish(layout, todo[i][2], inp, g, st, "local", time.time() - t)
    else:
        from floodflow import remote
        for i, st in remote.simulate_many(jobs, inp.z, cpu=a.cpu):
            print(f"  [{len(summaries) + 1}/{len(jobs)}] {todo[i][1]} done "
                  f"({time.time() - t0:.0f} s)")
            summaries[i] = finish(layout, todo[i][2], inp, jobs[i][0], st,
                                  f"modal, {a.cpu} cores", time.time() - t0)

    rows = [row(todo[i][0], todo[i][1], summaries[i]) for i in range(len(todo))]
    stem = layout.run_dir / "flood" / f"sensitivity_{a.res:g}m"
    with open(stem.with_suffix(".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    md = _markdown(rows, rows[0])
    stem.with_suffix(".md").write_text(md)
    print(md)
    print(f"  → {stem}.csv / .md ({time.time() - t0:.0f} s)")
    return 0
