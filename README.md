# AstroAgent 🌌

**An educational astronomy research prototype built with Python, Gaia DR3, and Streamlit.** AstroAgent queries public Gaia archive data, ranks retrieved star candidates using transparent heuristics, and includes a theoretical relativity calculator for comparing hypothetical clock rates.

> **Scientific scope:** This is an educational prototype, not a validated astronomical discovery system. Rankings depend on query strategy and the retrieved sample. Inverse-parallax distances can be biased when parallax uncertainty is significant. The relativity calculator produces theoretical estimates; it does not measure time dilation.

## Features

- Query public Gaia DR3 data through TAP/ADQL.
- Filter candidates using parallax signal-to-noise and available stellar parameters.
- Estimate distance from positive parallax (`distance_pc ≈ 1000 / parallax_mas`) with documented caveats.
- Use Gaia DR3 astrophysical mass/radius estimates when available.
- Rank retrieved candidates transparently and export results.
- Explore candidates in a Streamlit dashboard.
- Compare hypothetical star-surface clock rates using a simplified general-relativity model.
- Run automated unit tests for core calculations.

## Quick start (Windows)

1. Install Python 3.10+ and enable **Add Python to PATH** during installation.
2. Download this repository or clone it:

   ```bash
   git clone https://github.com/contactsyedsamad-dotcom/astroagent.git
   cd astroagent
   ```

3. Install dependencies:

   ```bash
   py -m pip install -r requirements.txt
   ```

4. Launch the dashboard:

   ```bash
   py -m streamlit run dashboard.py
   ```

5. Open the local URL printed by Streamlit, usually `http://localhost:8501`.

Alternatively, on Windows, double-click `run_astroagent.bat`.

## Run tests

```bash
py -m unittest discover -s tests -v
```

## Relativity model and limitations

For a non-rotating spherical body, a stationary clock at radius `R` has the Schwarzschild clock-rate factor:

`dτ/dt = sqrt(1 - 2GM/(Rc²))`

The result depends on mass and the clock's position in the gravitational field—not simply on distance from Earth. A surface-clock estimate needs appropriate mass and radius inputs. Missing values should remain unavailable rather than being guessed. A rigorous comparison with a clock on Earth's surface also requires an explicit Earth reference model and assumptions. The calculator is educational and does not fully model rotation, oblateness, stellar atmospheres, orbital motion, or all relativistic effects.

A limited sample returned by a query cannot establish which star is farthest in the entire Galaxy. Catalogue estimates are not necessarily direct measurements; uncertainties and source provenance matter.

## Data sources

- [Gaia Archive](https://gea.esac.esa.int/archive/)
- [Gaia DR3 documentation](https://www.cosmos.esa.int/web/gaia/dr3)
- [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) (supplementary stellar parameters)

Public archive availability, query limits, and catalogue coverage may change.

## Project layout

- `astro_agent.py` — query and analysis logic
- `dashboard.py` — Streamlit interface
- `tests/` — automated tests
- `requirements.txt` — Python dependencies
- `run_astroagent.bat` — Windows launcher
- `*_NOTES.txt` — implementation notes and scientific caveats

## CV project description

Built a Python-based astronomy research prototype integrating public Gaia DR3 data, TAP/ADQL queries, data-quality filtering, explainable candidate ranking, a Streamlit dashboard, and an educational general-relativity calculator. Added automated tests and documented scientific uncertainty and model limitations.

## License

No license is included yet. Until a license is selected, others should not assume permission to reuse, modify, or redistribute the code.
