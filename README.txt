ASTROAGENT — ADAPTIVE GAIA DR3 RESEARCH
======================================

WHAT IT DOES
- Queries the public ESA Gaia DR3 archive using asynchronous TAP queries.
- Starts with a broad distant-candidate sample and a hot-star sample.
- Evaluates parameter coverage and the share of candidates with parallax SNR >= 10.
- Chooses follow-up queries based on observed coverage and measurement quality.
- Deduplicates Gaia source IDs and preserves query provenance.
- Writes candidate CSV, a JSON decision log, and a Markdown research report.
- Provides a Streamlit dashboard with an explicit agent decision log and filters that are clear by default.

WINDOWS SETUP
1. Extract this ZIP into a normal folder (not inside the ZIP preview).
2. Open the AstroAgent folder.
3. Double-click run_astroagent.bat.
4. Wait for tests and the Gaia research queries to finish.
5. The dashboard starts in your browser. If it does not, keep the terminal open and visit http://localhost:8501.

MANUAL COMMANDS (run in this folder)
  py -m pip install -r requirements.txt
  py -m unittest discover -s tests -v
  py astro_agent.py --limit 100 --snr 5
  py -m streamlit run dashboard.py --server.headless=true --browser.gatherUsageStats=false

AGENT DECISIONS
The agent uses a transparent rules-based research loop, not an LLM. It logs why follow-up queries were selected. It is intentionally lightweight for laptops with limited RAM.

SCIENTIFIC LIMITATIONS
- The sample is query-limited and is not a census of all stars.
- Distance is estimated with inverse parallax: d(pc)=1000/parallax(mas). This can be biased, particularly for uncertain measurements.
- The displayed approximate bounds are simple parallax-error transformations, not Bayesian credible intervals.
- Priority scores are heuristics, not probabilities. Tags are exploratory screening labels, not confirmed stellar classifications.
- A high parallax SNR indicates a more precise parallax measurement, but does not by itself guarantee an unbiased distance.

CV DESCRIPTION
Built a lightweight, explainable astronomy research agent using Python, asynchronous ESA Gaia DR3 TAP queries, adaptive follow-up selection, data-quality metrics, reproducible research logs, CSV/Markdown reporting, automated tests, and a Streamlit dashboard.
