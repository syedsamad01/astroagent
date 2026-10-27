"""AstroAgent dashboard: transparent filters, run log, and candidate inspection."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="AstroAgent | Star Research", page_icon="🔭", layout="wide")
st.title("🔭 AstroAgent")
st.caption("Adaptive, explainable astronomy research · Public ESA Gaia DR3 data")
results_dir = Path(__file__).resolve().parent / "results"
csv_files = sorted(results_dir.glob("candidates_*.csv"), reverse=True) if results_dir.exists() else []
if not csv_files:
    st.warning("No research results found yet. Run the research agent first, then refresh this page.")
    st.code("py astro_agent.py --limit 100 --snr 5\npy -m streamlit run dashboard.py", language="powershell")
    st.stop()

selected = st.selectbox("Research run", csv_files, format_func=lambda p: p.name)
df = pd.read_csv(selected)
if df.empty or "distance_ly" not in df.columns:
    st.error("The selected results file contains no usable candidate rows.")
    st.stop()
for col in ["distance_ly", "distance_pc", "parallax_mas", "parallax_error_mas", "parallax_snr", "temperature_k", "metallicity_mh", "gaia_g_magnitude", "ra_deg", "dec_deg", "research_priority_score", "relative_distance_uncertainty_pct_approx", "mass_solar", "radius_solar"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

log_path = results_dir / selected.name.replace("candidates_", "run_log_").replace(".csv", ".json")
logdata = {}
if log_path.exists():
    try:
        logdata = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        pass

with st.expander("How the agent researched this sample", expanded=True):
    if logdata:
        st.write(f"**Minimum parallax SNR:** {logdata.get('minimum_parallax_snr', 'unknown')} · **Rows per query:** {logdata.get('limit_per_query', 'unknown')}")
        for entry in logdata.get("query_log", []):
            status = entry.get("status", "unknown").upper()
            st.markdown(f"**{entry.get('label', entry.get('plan', 'Query'))} — {status}**")
            st.caption(entry.get("reason", "No decision reason recorded."))
            if entry.get("trigger_metrics"):
                st.json(entry["trigger_metrics"])
            if entry.get("error"):
                st.error(entry["error"])
    else:
        st.info("No matching run log was found for this result file.")

st.subheader("Research overview")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Unique candidates", f"{len(df):,}")
c2.metric("Farthest in sample", f"{df['distance_ly'].max():,.0f} ly")
c3.metric("Parallax SNR ≥ 10", f"{int((df['parallax_snr'] >= 10).sum()) if 'parallax_snr' in df else 0:,}")
c4.metric("With temperature", f"{int(df['temperature_k'].notna().sum()) if 'temperature_k' in df else 0:,}")
c5.metric("Mean priority score", f"{df['research_priority_score'].mean():.1f}" if "research_priority_score" in df else "N/A")
st.caption("These metrics describe only this query sample, not the complete Milky Way catalogue.")
st.divider()
st.subheader("Explore candidates")
if st.button("Clear all filters", type="secondary"):
    for key in ["min_dist", "min_snr", "selected_tags", "goal_filter"]:
        st.session_state.pop(key, None)
    st.rerun()
col1, col2, col3 = st.columns(3)
maxdist = float(df["distance_ly"].max()) if df["distance_ly"].notna().any() else 1.0
min_dist, max_dist = col1.slider("Approximate distance (light-years)", 0.0, max(1.0, maxdist), (0.0, max(1.0, maxdist)), key="min_dist")
max_snr = float(df["parallax_snr"].max(skipna=True)) if "parallax_snr" in df and df["parallax_snr"].notna().any() else 10.0
min_snr = col2.slider("Minimum parallax SNR", 0.0, max(10.0, max_snr), min(5.0, max(10.0, max_snr)), key="min_snr")
tag_options = sorted({tag for value in df.get("agent_tags", pd.Series(dtype=str)).fillna("") for tag in str(value).split(";") if tag})
selected_tags = col3.multiselect("Candidate tags (none = all tags)", tag_options, default=[], key="selected_tags")
filtered = df[df["distance_ly"].between(min_dist, max_dist) & (df["parallax_snr"].fillna(0) >= min_snr)].copy()
if selected_tags and "agent_tags" in filtered.columns:
    filtered = filtered[filtered["agent_tags"].fillna("").apply(lambda value: all(tag in value.split(";") for tag in selected_tags))]
st.write(f"Showing **{len(filtered):,} of {len(df):,}** candidates. No tag filter is active unless selected above.")
if filtered.empty:
    st.warning("No candidates match these filters. Click 'Clear all filters' or lower the thresholds.")

# Per-candidate one-hour clock comparison. Only calculate when stellar mass and
# radius are explicitly present in the data; Gaia DR3's basic query does not
# provide reliable mass/radius for every row, so missing values stay unavailable.
G_CLOCK = 6.67430e-11
C_CLOCK = 299792458.0
M_SUN_CLOCK = 1.98847e30
R_SUN_CLOCK = 6.957e8
M_EARTH_CLOCK = 5.9722e24
R_EARTH_CLOCK = 6.371e6

def one_hour_clock_comparison(row):
    mass_col = next((c for c in ("mass_solar", "stellar_mass_solar", "mass_msun") if c in row.index), None)
    radius_col = next((c for c in ("radius_solar", "stellar_radius_solar", "radius_rsun") if c in row.index), None)
    if mass_col is None or radius_col is None:
        return "Unavailable (mass/radius missing)"
    try:
        mass = float(row[mass_col]) * M_SUN_CLOCK
        radius = float(row[radius_col]) * R_SUN_CLOCK
        if not (mass > 0 and radius > 0):
            return "Unavailable (invalid inputs)"
        compactness = 2 * G_CLOCK * mass / (radius * C_CLOCK**2)
        earth_compactness = 2 * G_CLOCK * M_EARTH_CLOCK / (R_EARTH_CLOCK * C_CLOCK**2)
        if compactness >= 1:
            return "Invalid surface model"
        star_rate = (1 - compactness) ** 0.5
        earth_rate = (1 - earth_compactness) ** 0.5
        # Compare gravitational clock rates only; no star-specific 3D velocity
        # is assumed. Output is Earth-clock elapsed time corresponding to 1h
        # at the stellar surface under this simplified static model.
        earth_seconds_for_star_hour = 3600 * earth_rate / star_rate
        delta = earth_seconds_for_star_hour - 3600
        return f"1 h star ≈ {earth_seconds_for_star_hour/3600:.9f} h Earth ({delta:+.6f} s)"
    except (TypeError, ValueError, OverflowError):
        return "Unavailable (invalid inputs)"

filtered["one_hour_star_vs_earth"] = filtered.apply(one_hour_clock_comparison, axis=1)
display_cols = [c for c in ["source_id", "one_hour_star_vs_earth", "mass_solar", "radius_solar", "mass_radius_status", "research_priority_score", "distance_ly", "relative_distance_uncertainty_pct_approx", "parallax_mas", "parallax_snr", "temperature_k", "metallicity_mh", "gaia_g_magnitude", "ra_deg", "dec_deg", "agent_tags", "found_by_queries"] if c in filtered.columns]
if "research_priority_score" in filtered.columns:
    filtered = filtered.sort_values("research_priority_score", ascending=False)
st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
st.caption("The per-star clock column uses Gaia DR3 FLAME mass/radius estimates where available. These are model-derived catalogue estimates; unavailable values are not fabricated. This simplified comparison includes gravitational time dilation only; it excludes motion and other gravitational potentials.")
if "mass_solar" in filtered.columns:
    mass_count = int(filtered["mass_solar"].notna().sum())
    st.info(f"Gaia FLAME mass/radius estimates available for {mass_count:,} of {len(filtered):,} currently filtered candidates. These are model-derived catalogue estimates; check source/status fields before scientific interpretation.")

st.subheader("Research priority")
if "research_priority_score" in filtered.columns and not filtered.empty:
    st.bar_chart(filtered.nlargest(20, "research_priority_score").set_index("source_id")["research_priority_score"], height=260)
    st.caption("Transparent heuristic: 70% parallax SNR and 30% inverse-parallax distance signal. This is not a probability or official stellar classification.")
st.subheader("Distance distribution")
if not filtered.empty:
    st.bar_chart(filtered[["distance_ly"]].dropna().reset_index(drop=True), height=240)
else:
    st.info("No candidates match the current filters.")
st.subheader("Sky positions")
if {"ra_deg", "dec_deg"}.issubset(filtered.columns):
    sky = filtered[["ra_deg", "dec_deg"]].dropna().rename(columns={"ra_deg": "ra", "dec_deg": "dec"})
    if not sky.empty:
        st.scatter_chart(sky, x="ra", y="dec", height=300)
        st.caption("Catalogue coordinates in degrees; this is not a projection-corrected sky map.")
st.subheader("Candidate details")
if not filtered.empty:
    ids = filtered["source_id"].astype(str).tolist()
    choice = st.selectbox("Select a Gaia source", ids)
    item = filtered[filtered["source_id"].astype(str) == choice].iloc[0]
    st.json({k: (None if pd.isna(v) else v) for k, v in item.to_dict().items()})
st.download_button("Download filtered candidates as CSV", filtered.to_csv(index=False).encode("utf-8-sig"), file_name="astroagent_filtered_candidates.csv", mime="text/csv")
st.divider()
st.subheader("Relativity lab: star clock vs Earth")
st.write("Estimate the theoretical clock-rate difference for a hypothetical clock at a star's surface compared with a clock on Earth's surface. Gaia DR3 does not directly provide stellar mass and radius for every candidate, so these are explicit model inputs—not measured time dilation.")
with st.expander("Set the physical assumptions", expanded=True):
    r1, r2, r3 = st.columns(3)
    star_mass_solar = r1.number_input("Star mass (solar masses)", min_value=0.08, max_value=150.0, value=1.0, step=0.1)
    star_radius_solar = r2.number_input("Star radius (solar radii)", min_value=0.01, max_value=2000.0, value=1.0, step=0.1)
    relative_speed_kms = r3.number_input("Relative speed (km/s)", min_value=0.0, max_value=299000.0, value=30.0, step=1.0, help="Illustrative total relative speed. Gaia radial velocity alone is not the full 3D speed.")
    elapsed_earth_years = st.number_input("Elapsed time on Earth clock (years)", min_value=1.0, max_value=1000000000.0, value=1.0, step=1.0)

G = 6.67430e-11
C = 299792458.0
M_SUN = 1.98847e30
R_SUN = 6.957e8
M_EARTH = 5.9722e24
R_EARTH = 6.371e6

def _gravitational_clock_factor(mass_kg, radius_m):
    compactness = 2.0 * G * mass_kg / (radius_m * C * C)
    if compactness >= 1.0:
        return None
    return (1.0 - compactness) ** 0.5

star_grav_factor = _gravitational_clock_factor(star_mass_solar * M_SUN, star_radius_solar * R_SUN)
earth_grav_factor = _gravitational_clock_factor(M_EARTH, R_EARTH)
beta = relative_speed_kms * 1000.0 / C
gamma = 1.0 / (1.0 - beta * beta) ** 0.5
if star_grav_factor is None:
    st.error("These mass/radius inputs imply a Schwarzschild radius at or beyond the stellar radius. This simple surface-clock model is not valid for these inputs.")
else:
    star_rate_vs_far = star_grav_factor / gamma
    rate_ratio = star_rate_vs_far / earth_grav_factor
    delta_fraction = rate_ratio - 1.0
    earth_seconds = elapsed_earth_years * 365.25 * 24 * 3600
    difference_seconds = earth_seconds * delta_fraction
    m1, m2, m3 = st.columns(3)
    m1.metric("Star clock rate vs Earth", f"{rate_ratio:.12f}")
    m2.metric("Clock difference over selected Earth time", f"{difference_seconds:+.6f} s")
    m3.metric("Rate difference", f"{delta_fraction * 1e6:+.6f} ppm")
    st.caption("Positive difference means the modeled star-surface clock accumulates more time than the Earth-surface clock; negative means less. The entered speed is applied as a special-relativistic factor.")

with st.expander("Model assumptions and limitations"):
    st.markdown("""- Gravitational factor: Schwarzschild exterior solution, `sqrt(1 - 2GM/(Rc²))`, evaluated at the stellar surface and Earth's surface.
- Motion factor: special-relativistic `1/gamma = sqrt(1 - v²/c²)` using the speed entered above.
- The model ignores stellar rotation, oblateness, magnetic effects, companions, galactic gravitational potential, Earth rotation, and details of how clocks are transported or compared.
- Gaia distance does not determine a star's mass or radius. Values here are user-supplied assumptions unless reliable external measurements are added later.
- This is a theoretical estimate, not a direct measurement from Gaia. Radial velocity alone is not the star's full relative speed.
""")

st.caption("Scientific caveat: inverse-parallax distances can be biased, especially when uncertainty is substantial. Scores and tags are exploratory heuristics; candidates are not confirmed classifications.")
