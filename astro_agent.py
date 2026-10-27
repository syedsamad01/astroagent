"""
AstroAgent — explainable multi-step astronomy research agent with dashboard.
Public data: ESA Gaia DR3 archive via TAP asynchronous queries.
"""
from __future__ import annotations
import argparse, csv, io, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Dependency missing. Run: py -m pip install -r requirements.txt")
    sys.exit(1)

TAP_BASE = "https://gea.esac.esa.int/tap-server/tap"
FIELDS = ("source_id, ra, dec, parallax, parallax_error, parallax_over_error, "
          "phot_g_mean_mag, bp_rp, teff_gspphot, logg_gspphot, mh_gspphot")
PLANS = {
    "distant": {
        "label": "Distant candidates",
        "where": "parallax IS NOT NULL AND parallax > 0 AND parallax_over_error >= {snr}",
        "purpose": "Find positive-parallax sources with the selected measurement-quality threshold.",
    },
    "high_quality": {
        "label": "High-quality parallax candidates",
        "where": "parallax IS NOT NULL AND parallax > 0 AND parallax_over_error >= {snr}",
        "purpose": "Prioritize sources with stronger parallax signal-to-noise to compare data quality against the broader sample.",
    },
    "hot": {
        "label": "Hot-star candidates",
        "where": "parallax IS NOT NULL AND parallax > 0 AND parallax_over_error >= {snr} AND teff_gspphot >= 10000",
        "purpose": "Explore hot sources with usable parallax measurements.",
    },
    "metalpoor": {
        "label": "Low-metallicity candidates",
        "where": "parallax IS NOT NULL AND parallax > 0 AND parallax_over_error >= {snr} AND mh_gspphot <= -1.0",
        "purpose": "Explore sources with low reported metallicity and usable parallaxes.",
    },
    "cool": {
        "label": "Cool-star candidates",
        "where": "parallax IS NOT NULL AND parallax > 0 AND parallax_over_error >= {snr} AND teff_gspphot > 0 AND teff_gspphot <= 3500",
        "purpose": "Explore cool sources with usable parallax measurements.",
    },
}

def build_adql(plan: str, limit: int, snr: float) -> str:
    """Build conservative ADQL for Gaia TAP; use unqualified column names.

    Gaia TAP supports ADQL TOP rather than SQL LIMIT. Keep identifiers plain and
    avoid relying on computed/aliased columns in WHERE clauses.
    """
    if plan not in PLANS:
        raise ValueError(f"Unknown research plan: {plan}")
    limit = max(1, min(int(limit), 1000))
    # The SNR is checked in the WHERE clause using Gaia's published column.
    where = PLANS[plan]["where"].format(snr=float(snr))
    return (f"SELECT TOP {limit} {FIELDS} FROM gaiadr3.gaia_source "
            f"WHERE {where}")


def build_fallback_adql(limit: int) -> str:
    """Minimal valid fallback query when an optional plan fails."""
    limit = max(1, min(int(limit), 1000))
    return (f"SELECT TOP {limit} source_id, ra, dec, parallax, parallax_error, "
            "phot_g_mean_mag, bp_rp FROM gaiadr3.gaia_source "
            "WHERE parallax IS NOT NULL AND parallax > 0 "
            "AND parallax_error IS NOT NULL AND parallax_error > 0 ")

def query_gaia(adql: str, max_wait: int = 240) -> str:
    session = requests.Session()
    response = session.post(
        f"{TAP_BASE}/async",
        data={"REQUEST":"doQuery","LANG":"ADQL","FORMAT":"csv","QUERY":adql},
        timeout=30, allow_redirects=False)
    if response.status_code not in (200, 201, 303):
        response.raise_for_status()
    job_url = response.headers.get("Location")
    if not job_url:
        body = response.text.strip()
        if body.startswith("http"):
            job_url = body
        else:
            raise RuntimeError(f"Gaia did not return an async job URL (HTTP {response.status_code}).")
    job_url = job_url.rstrip("/")
    if not job_url.startswith("http"):
        job_url = "https://gea.esac.esa.int" + job_url
    phase_url = job_url + "/phase"
    run = session.post(phase_url, data={"PHASE":"RUN"}, timeout=30)
    if run.status_code >= 400:
        session.get(phase_url, timeout=30).raise_for_status()
    started, previous = time.time(), None
    while time.time() - started < max_wait:
        phase_response = session.get(phase_url, timeout=30)
        phase_response.raise_for_status()
        phase = phase_response.text.strip().upper()
        if phase != previous:
            print(f"    Gaia status: {phase}")
            previous = phase
        if phase == "COMPLETED":
            result = session.get(job_url + "/results/result", timeout=30)
            result.raise_for_status()
            if not result.text.strip() or result.text.lstrip().startswith("<"):
                raise RuntimeError("Gaia returned no valid CSV.")
            return result.text
        if phase in ("ERROR", "ABORTED"):
            try: detail = session.get(job_url + "/error", timeout=30).text[:1000]
            except requests.RequestException: detail = "No error details available."
            raise RuntimeError(f"Gaia query {phase}: {detail}")
        time.sleep(3)
    raise TimeoutError(f"Gaia query exceeded {max_wait} seconds.")

def num(v: Any):
    try:
        if v is None or str(v).strip() in ("", "nan", "NaN", "NULL"): return None
        return float(v)
    except (ValueError, TypeError): return None

def enrich_stellar_mass_radius(rows: list[dict], max_wait: int = 90) -> dict:
    """Enrich a bounded candidate sample from Gaia DR3 astrophysical_parameters.

    mass_flame and radius_flame are catalogue estimates, not direct measurements
    for every source. Query in small batches to avoid expensive catalogue joins.
    """
    eligible = [r for r in rows if r.get("source_id")]
    enriched = 0
    failed_batches = 0
    batch_size = 40
    for start in range(0, min(len(eligible), 200), batch_size):
        batch = eligible[start:start + batch_size]
        ids = ",".join(str(int(r["source_id"])) for r in batch)
        adql = ("SELECT source_id, mass_flame, radius_flame "
                "FROM gaiadr3.astrophysical_parameters "
                f"WHERE source_id IN ({ids})")
        try:
            text = query_gaia(adql, max_wait=max_wait)
            by_id = {}
            for raw in csv.DictReader(io.StringIO(text)):
                sid = str(raw.get("source_id", ""))
                mass, radius = num(raw.get("mass_flame")), num(raw.get("radius_flame"))
                if mass is not None and mass > 0 and radius is not None and radius > 0:
                    by_id[sid] = (mass, radius)
            for row in batch:
                if row["source_id"] in by_id:
                    row["mass_solar"], row["radius_solar"] = by_id[row["source_id"]]
                    row["mass_radius_source"] = "Gaia DR3 astrophysical_parameters (FLAME estimates)"
                    row["mass_radius_status"] = "catalogue_estimate"
                    enriched += 1
        except Exception as exc:
            failed_batches += 1
            print(f"    Mass/radius enrichment batch skipped: {exc}")
    for row in rows:
        row.setdefault("mass_solar", None)
        row.setdefault("radius_solar", None)
        row.setdefault("mass_radius_source", "")
        row.setdefault("mass_radius_status", "unavailable")
    return {"attempted_sources": min(len(eligible), 200), "enriched_sources": enriched, "failed_batches": failed_batches,
            "source": "Gaia DR3 astrophysical_parameters mass_flame/radius_flame; model-derived estimates"}


def normalize(text: str, plan: str) -> list[dict]:
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        p, pe, snr = num(raw.get("parallax")), num(raw.get("parallax_error")), num(raw.get("parallax_over_error"))
        if p is None or p <= 0: continue
        temp, metal, mag = num(raw.get("teff_gspphot")), num(raw.get("mh_gspphot")), num(raw.get("phot_g_mean_mag"))
        tags = []
        if snr is not None and snr >= 10: tags.append("high-parallax-SNR")
        elif snr is not None: tags.append("distance-needs-extra-caution")
        if temp is not None and temp >= 10000: tags.append("hot-star-candidate")
        if temp is not None and 0 < temp <= 3500: tags.append("cool-star-candidate")
        if metal is not None and metal <= -1.0: tags.append("low-metallicity-candidate")
        if mag is not None and mag <= 8: tags.append("bright-in-Gaia-band")
        dpc = 1000 / p
        # Approximate 1-sigma distance bounds from parallax +/- uncertainty.
        # These are only meaningful when the lower parallax bound remains positive.
        low_pc = 1000 / (p + pe) if pe is not None and pe > 0 else None
        high_pc = 1000 / (p - pe) if pe is not None and pe > 0 and p > pe else None
        rel_unc = (pe / p * 100) if pe is not None and p > 0 else (100 / snr if snr and snr > 0 else None)
        # Explainable screening score (0-100), not a scientific probability.
        quality = max(0.0, min(1.0, (snr or 0.0) / 20.0))
        distance_signal = max(0.0, min(1.0, dpc / 10000.0))
        score = round(100 * (0.70 * quality + 0.30 * distance_signal), 2)
        rows.append({
            "source_id": str(raw.get("source_id","")), "ra_deg": num(raw.get("ra")), "dec_deg": num(raw.get("dec")),
            "parallax_mas": p, "parallax_error_mas": pe, "parallax_snr": snr,
            "distance_pc": round(dpc,3), "distance_ly": round(dpc*3.26156,2),
            "relative_distance_uncertainty_pct_approx": round(rel_unc, 2) if rel_unc is not None else None,
            "distance_low_pc_approx": round(low_pc, 3) if low_pc is not None else None,
            "distance_high_pc_approx": round(high_pc, 3) if high_pc is not None else None,
            "distance_low_ly_approx": round(low_pc * 3.26156, 2) if low_pc is not None else None,
            "distance_high_ly_approx": round(high_pc * 3.26156, 2) if high_pc is not None else None,
            "research_priority_score": score,
            "research_priority_note": "Heuristic score combining parallax SNR (70%) and estimated distance (30%); not a probability or scientific classification.",
            "measurement_quality": "Higher parallax SNR generally indicates a more precise parallax measurement; it does not guarantee an unbiased distance.",
            "gaia_g_magnitude": mag, "bp_rp_colour": num(raw.get("bp_rp")),
            "temperature_k": temp, "surface_gravity_logg": num(raw.get("logg_gspphot")),
            "metallicity_mh": metal, "found_by_queries": [plan], "agent_tags": tags,
        })
    return rows

def dedupe(rows: list[dict]) -> list[dict]:
    by_id = {}
    for r in rows:
        sid = r["source_id"]
        if not sid: continue
        if sid not in by_id: by_id[sid] = r
        else:
            by_id[sid]["found_by_queries"] = sorted(set(by_id[sid]["found_by_queries"] + r["found_by_queries"]))
            by_id[sid]["agent_tags"] = sorted(set(by_id[sid]["agent_tags"] + r["agent_tags"]))
    return sorted(by_id.values(), key=lambda x: (x.get("research_priority_score", 0), x.get("distance_pc", 0)), reverse=True)

def write_outputs(rows, log, outdir: Path, limit: int, snr: float):
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csvpath, jsonpath, mdpath = (outdir/f"candidates_{stamp}.csv",
                                 outdir/f"run_log_{stamp}.json",
                                 outdir/f"research_report_{stamp}.md")
    fields = list(rows[0].keys()) if rows else ["source_id"]
    with csvpath.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for row in rows:
            item = dict(row); item["found_by_queries"] = ";".join(row["found_by_queries"]); item["agent_tags"] = ";".join(row["agent_tags"])
            writer.writerow(item)
    metadata = {"agent":"AstroAgent","generated_utc":datetime.now(timezone.utc).isoformat(),
                "unique_candidates":len(rows),"limit_per_query":limit,"minimum_parallax_snr":snr,"query_log":log}
    jsonpath.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    hot=[r for r in rows if "hot-star-candidate" in r["agent_tags"]]
    cool=[r for r in rows if "cool-star-candidate" in r["agent_tags"]]
    metalpoor=[r for r in rows if "low-metallicity-candidate" in r["agent_tags"]]
    lines=["# AstroAgent Research Report","",f"- Generated: {metadata['generated_utc']}",
           "- Source: ESA Gaia DR3 public archive",f"- Unique candidates: {len(rows)}",
           f"- Candidates with Gaia FLAME mass/radius estimates: {sum(r.get('mass_solar') is not None and r.get('radius_solar') is not None for r in rows)}",
           f"- Queries completed: {sum(q['status']=='completed' for q in log)}",
           f"- Hot-star candidates: {len(hot)}",f"- Cool-star candidates: {len(cool)}",
           f"- Low-metallicity candidates: {len(metalpoor)}","","## Agent decision log",""]
    for q in log: lines.append(f"- **{q['label']}**: {q['status']}; rows={q.get('rows',0)}; reason: {q['reason']}")
    lines += ["","## Distance-ranked sample","","| Rank | Gaia source ID | Distance (ly, approximate) | Parallax (mas) | SNR | Temperature (K) | Metallicity | Tags |",
              "|---:|---|---:|---:|---:|---:|---:|---|"]
    for i,r in enumerate(rows[:30],1):
        lines.append(f"| {i} | {r['source_id']} | {r['distance_ly']} | {r['parallax_mas']} | {r['parallax_snr']} | {r['temperature_k']} | {r['metallicity_mh']} | {', '.join(r['agent_tags'])} |")
    lines += ["","## Scientific caveats","",
              "This ranks only the returned sample, not all stars or the most distant star in the universe.",
              "Distances use inverse parallax: d(pc)=1000/parallax(mas). This can be biased when parallax uncertainty is substantial; Bayesian distance inference is preferable for low-SNR sources.",
              "Approximate distance bounds are derived from parallax +/- its reported error only when the lower parallax bound stays positive. They are not Bayesian credible intervals.",
              "Research-priority score is an explainable heuristic (70% parallax SNR, 30% estimated distance), not a probability, physical property, or confirmed classification.",
              "Tags are exploratory screening heuristics, not confirmed classifications. Missing astrophysical parameters are common.",
              "Stellar mass/radius, when available, come from Gaia DR3 FLAME catalogue estimates and are model-derived, not direct measurements. Their uncertainties and applicability vary; clock calculations are simplified surface-clock comparisons, not observed time dilation.",
              "Documentation: https://gea.esac.esa.int/archive/documentation/GDR3/"]
    mdpath.write_text("\n".join(lines), encoding="utf-8")
    return csvpath,jsonpath,mdpath

def run_agent(limit: int, snr: float, max_wait: int=240):
    """Run a small, explainable plan-query-evaluate-follow-up research loop."""
    all_rows, log = [], []
    initial_plans = ["distant", "hot"]
    for plan in initial_plans:
        cfg = PLANS[plan]
        print(f"\nAgent decision: {cfg['label']} — {cfg['purpose']}")
        item = {"plan": plan, "label": cfg["label"], "reason": cfg["purpose"], "status": "running", "rows": 0}
        log.append(item)
        try:
            found = normalize(query_gaia(build_adql(plan, limit, snr), max_wait=max_wait), plan)
            all_rows.extend(found)
            item["status"] = "completed"
            item["rows"] = len(found)
            print(f"    Usable rows: {len(found)}")
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            print(f"    Query failed: {e}")

    # If every targeted query failed, try one conservative fallback query once.
    if not all_rows:
        print("\nAll targeted queries failed; trying one minimal Gaia fallback query.")
        fallback_item = {"plan": "fallback", "label": "Minimal Gaia fallback", 
                         "reason": "Recover a basic sample after targeted-query failures.",
                         "status": "running", "rows": 0}
        log.append(fallback_item)
        try:
            fallback_rows = normalize(query_gaia(build_fallback_adql(limit), max_wait=max_wait), "distant")
            all_rows.extend(fallback_rows)
            fallback_item["status"] = "completed"
            fallback_item["rows"] = len(fallback_rows)
            print(f"    Fallback usable rows: {len(fallback_rows)}")
        except Exception as e:
            fallback_item["status"] = "failed"
            fallback_item["error"] = str(e)
            print(f"    Fallback query failed: {e}")

    current = dedupe(all_rows)
    print("\nEnriching candidate sample with available Gaia stellar mass/radius estimates...")
    enrichment = enrich_stellar_mass_radius(current, max_wait=min(max_wait, 90))
    log.append({"plan":"mass_radius_enrichment", "label":"Gaia stellar mass/radius cross-match",
                "reason":"Look up FLAME mass and radius estimates for returned Gaia source IDs; missing values remain unavailable.",
                "status":"completed" if enrichment["failed_batches"] == 0 else "partial", "rows":enrichment["enriched_sources"],
                "trigger_metrics":enrichment})
    total = len(current)
    temp_cov = sum(r.get("temperature_k") is not None for r in current) / total if total else 0.0
    metal_cov = sum(r.get("metallicity_mh") is not None for r in current) / total if total else 0.0
    high_quality_count = sum((r.get("parallax_snr") or 0) >= 10 for r in current)
    high_quality_share = high_quality_count / total if total else 0.0

    # The next query is selected from observed coverage/quality, not a fixed list alone.
    follow = []
    if high_quality_share < 0.20:
        follow.append(("high_quality", f"Only {high_quality_share:.0%} of the current sample has parallax SNR >= 10; test a stricter quality-focused sample."))
    if temp_cov < 0.50:
        follow.append(("cool", f"Temperature coverage is {temp_cov:.0%}; broaden stellar-property coverage with a cool-star query."))
    if metal_cov < 0.50:
        follow.append(("metalpoor", f"Metallicity coverage is {metal_cov:.0%}; explore a distinct low-metallicity population."))
    if not follow:
        follow.append(("cool", "Core property coverage is adequate; sample a different stellar population to improve diversity."))

    already = set(initial_plans)
    for plan, reason in follow:
        if plan in already:
            continue
        already.add(plan)
        cfg = PLANS[plan]
        print(f"\nAgent adaptive follow-up: {cfg['label']} — {reason}")
        item = {"plan": plan, "label": cfg["label"], "reason": reason, "status": "running", "rows": 0,
                "trigger_metrics": {"temperature_coverage": round(temp_cov, 3), "metallicity_coverage": round(metal_cov, 3),
                                    "parallax_snr_ge_10_share": round(high_quality_share, 3)}}
        log.append(item)
        try:
            found = normalize(query_gaia(build_adql(plan, limit, snr), max_wait=max_wait), plan)
            all_rows.extend(found)
            item["status"] = "completed"
            item["rows"] = len(found)
            print(f"    Usable rows: {len(found)}")
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            print(f"    Query failed: {e}")
    return dedupe(all_rows), log

def main():
    parser=argparse.ArgumentParser(description="AstroAgent: multi-step public-data astronomy research plus dashboard.")
    parser.add_argument("--limit",type=int,default=50,help="Maximum rows per query, 1-1000 (small samples reduce Gaia timeouts)")
    parser.add_argument("--snr",type=float,default=5.0,help="Minimum parallax SNR")
    parser.add_argument("--max-wait",type=int,default=120,help="Maximum seconds to wait for each Gaia query")
    args=parser.parse_args()
    if not 1<=args.limit<=1000: parser.error("--limit must be between 1 and 1000")
    if args.snr<=0: parser.error("--snr must be positive")
    print("AstroAgent — running live Gaia DR3 research queries")
    print("Performance mode: small samples; ranking is performed locally, not across the full Gaia catalogue.")
    rows,log=run_agent(args.limit,args.snr,args.max_wait)
    if not any(x["status"]=="completed" for x in log):
        print("No query completed. Check internet access or Gaia availability."); sys.exit(2)
    paths=write_outputs(rows,log,Path("results"),args.limit,args.snr)
    print(f"\nResearch complete. Unique candidates: {len(rows)}")
    for label,path in zip(("CSV","JSON run log","Markdown report"),paths): print(f"{label}: {path.resolve()}")
    print("\nStart the dashboard with: py -m streamlit run dashboard.py")

if __name__=="__main__": main()
