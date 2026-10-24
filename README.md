# Motor insurance pricing platform

A small but complete pricing stack on French motor third-party liability data (freMTPL2,
677,991 policies, 26,444 claims): raw files land as parquet, dbt builds tested
staging → intermediate → mart layers in DuckDB, a frequency × severity GLM tariff and a
gradient-boosting challenger are fitted on the marts, model outputs go back into the
warehouse as a loss-ratio mart, and a FastAPI service quotes from the GLM tariff. A price
optimization layer, run on **simulated** demand, turns the technical premium into an offer
price, and a React app shows the quote. `docker compose up` starts the app and the API.
Airflow or a single `make pipeline` runs the data and modelling stack in about 5 minutes on a
laptop (about 40 seconds without the price optimization step).

## Results

All metrics are on a held-out 20% of policies (135,629 policies, seed 42). The source is
[`results/metrics.json`](results/metrics.json); `make pipeline` regenerates every number below.

### GLM tariff vs GBM challenger

| | Flat rate | GLM (Poisson × Gamma) | GBM (Poisson × Gamma, monotone in bonus-malus) |
|---|---|---|---|
| Frequency: mean Poisson deviance | 0.4718 | 0.4514 | **0.4455** |
| Frequency: deviance explained | – | 4.3% | **5.6%** |
| Frequency Gini | 0 | 0.285 | **0.312** |
| Pure premium Gini, capped claims (95% bootstrap CI) | 0 | 0.309 (0.270–0.349) | **0.338** (0.302–0.381) |
| Pure premium Gini, full incurred (95% CI) | 0 | 0.367 (0.199–0.548) | 0.378 (0.229–0.556) |
| Double lift: mean \|actual/predicted − 1\| over deciles | – | 0.26 | **0.105** |
| Predicted / actual losses on test | 0.935 | 0.935 | 0.933 |

- **The GBM ranks risks better, but not by much.** On capped claims its Gini lead is
  +0.029 with a bootstrap 95% CI of +0.004 to +0.054, so the gain is real but small. On full
  incurred losses the difference (CI −0.055 to +0.075) is lost in the noise of a few very
  large claims.
- **The double lift shows where the two models disagree.** For the 10% of policies the GBM
  prices highest relative to the GLM, actual losses come in at 1.78× the GLM premium and
  1.00× the GBM premium. Most of the GLM's shortfall comes from treating bonus-malus as
  linear on the log scale (see the loss ratios below), and splines or bands on bonus-malus
  would be the first fix to try in the GLM.
- **Severity is close to unpredictable** with these variables. Mean Gamma deviance is
  1.1402 for the null model, 1.1381 for the GLM and 1.1412 for the GBM. Backward selection
  on training-set BIC keeps only driver age, vehicle power and region in the severity GLM.
  Nearly all the segmentation comes from frequency.
- **Large losses matter.** Claims above the training-set 99.5th percentile (€34,986) make up
  24% of incurred cost. They are capped for severity modelling and spread back as a
  ×1.309 load, which keeps the tariff balanced.
- The test set happens to have about 7% more losses than the training-set average. All
  three tariffs show the same 0.93 ratio, so this is sampling noise from large claims, not
  miscalibration.

![Lorenz curve](results/figures/lorenz_curve.png) ![Double lift](results/figures/double_lift.png)

### Key GLM frequency relativities

Base profile: driver aged 51–70, vehicle 1–10 years old, power class 6, regular fuel,
brand B1, region Centre, bonus-malus 50, density e^5.97 ≈ 390 inhabitants/km².
The full table, including severity, regions and 95% CIs, is in
[`results/glm_relativities.csv`](results/glm_relativities.csv).

| Factor | Level | Relativity (95% CI) |
|---|---|---|
| Bonus-malus | per point above 50 | 1.028 (1.027–1.029), i.e. **×3.97 at 100 vs 50** |
| Fuel | Diesel vs regular | 1.18 (1.15–1.22) |
| Driver age | 18–20 | 1.12 (1.02–1.24) |
| | 26–30 | 0.68 (0.65–0.72) |
| | 41–50 | 1.08 (1.04–1.12) |
| Vehicle age | 11+ years | 0.83 (0.80–0.85) |
| Vehicle power | 9+ | 1.17 (1.12–1.23) |
| Population density | ×2 density | 1.05 |
| Region | Limousin (highest) | 1.44 (1.23–1.69) |

Most of the young-driver risk shows up in bonus-malus rather than age: French
drivers start at 100 (the legal CRM scale runs 0.50–3.50), so an 18-year-old already pays
roughly 4× the max-bonus rate before the age relativity. Severity adds its own young-driver
loading of ×1.50 (1.25–1.79) for 18–20.

The GBM agrees on what matters. By mean |SHAP| on the log-frequency scale over 5,000 test
policies, the ranking is bonus-malus 0.41, driver age 0.16, density 0.12, vehicle age 0.10
and fuel 0.09 ([`results/figures/shap_frequency.png`](results/figures/shap_frequency.png)).

### Portfolio and loss-ratio insights (dbt marts)

From `marts.mart_segment_kpis`, across all 358k policy-years: claim frequency is 0.074 per
year, average claim cost €2,266, and pure premium €167 per year.

- Drivers aged 18–20 have 3.2× the portfolio frequency (0.239) and a pure premium of
  €3,206. They account for 0.7% of exposure.
- Frequency rises steadily with density: 0.057 below 100 inhabitants/km² vs 0.096 above
  2,000.
- Bonus-malus is the strongest single split: 0.052 at max bonus (50) vs 0.352 in malus
  (> 100).

`marts.mart_loss_ratio_by_segment` compares each test segment's losses to the premium of
three tariffs. Claims are capped and the excess loaded back. The table shows the
exposure-weighted mean |loss ratio − 1| across each dimension's segments:

| Dimension | Flat | GLM | GBM |
|---|---|---|---|
| Bonus-malus band | 0.360 | 0.113 | **0.046** |
| Driver age band | 0.134 | 0.049 | 0.048 |
| Density band | 0.171 | 0.049 | 0.053 |
| Region (2016) | 0.141 | 0.072 | 0.076 |
| Vehicle brand | 0.137 | 0.099 | 0.099 |

The GLM's straight-line bonus-malus effect underprices the 51–79 band (loss ratio 1.14)
and overprices max bonus (0.90). The GBM's monotone fit gets those to 0.92 and 1.03. On
other dimensions the two tariffs are equally good.

## Quote app

![Quote app](docs/quote-app.png)

A Vite + React + TypeScript single page (`frontend/`). The form validates the same bounds as
the API, posts to `/api/quote`, and shows the technical premium, the optimized offer with its
simulated conversion, the factor-by-factor breakdown (bars on a log scale around the base
profile) and a sensitivity chart of conversion and expected profit against the price
multiplier under three assumed price sensitivities. Every simulated figure carries a visible
"Simulated" notice. There is no authentication and no gender field.

```bash
docker compose up --build          # app on http://localhost:8080, API reachable only through /api
scripts/smoke_test.sh              # health, one quote through nginx, one rejected payload
docker compose down
```

`WEB_PORT=8090 docker compose up` changes the host port. The `web` image is multi-stage
(Node 22 build, then unprivileged nginx serving the static files and proxying `/api/` to the
`api` service). The `api` image runs as a non-root user with pinned Python and package
versions, a read-only filesystem and a health check; it needs only FastAPI, Pydantic and
Uvicorn. For development: `uv run uvicorn pricing.api:app` and `cd frontend && npm ci && npm run dev`
(Vite proxies `/api` to port 8000). Frontend checks: `npm run lint`, `npm run typecheck`,
`npm test`, `npm run build`.

## Price optimization (simulated demand)

> **Everything in this section that involves conversion, volume or profit is simulated.**
> freMTPL2 holds one year of policies and claims. It has no quotes, conversions, renewals or
> competitor prices, so a demand curve cannot be estimated from it. The demand model below is a
> set of explicit assumptions. The results show what the optimizer does *if* those assumptions
> held, and how much that depends on them. They are not observed or forecast business results.

**Method** (`src/pricing/demand.py`, `src/pricing/optimize.py`, `make optimize`, about 4.5 minutes):

- **Technical premium** = (GLM expected claims + €20 fixed cost) / (1 − 25% variable expenses).
  This is the break-even gross price.
- **Demand:** conversion = sigmoid(logit(c0) − b · ln(price / market price)). c0 is the
  conversion when we match the market proxy and b the price sensitivity. The elasticity of
  conversion at the market price is −b(1 − c0).
- **Market-price proxy:** a less segmented tariff than ours (50% flat rate, 50% GLM) at break-even
  plus 5%. This is what makes some segments look expensive and others cheap to the customer.
- **Objective:** expected profit = conversion × (price × (1 − 25%) − €20 − expected claims),
  summed over all 677,991 policies weighted by exposure.
- **Decision:** one price multiplier on the technical premium for each of 84 segments (driver age
  band × bonus-malus band × density band), solved with SciPy SLSQP and analytic gradients.
- **Constraints:** multiplier between 0.80 and 1.30; expected volume at least 90% of the baseline;
  expected loss ratio at most 70%; multiplier at most 1.10 for drivers aged 71+ (an assumed
  vulnerable-customer guard).
- **Baselines:** (a) technical premium + a flat 10% loading, as requested; (b) the best single
  multiplier for the whole book under the same constraints, because beating a loading that was
  not tuned says little.

**Parameters.** No elasticity is taken from the literature, because I did not find a figure
I could cite and verify. The base case is c0 = 15% and b = 4 (elasticity −3.4 at the market
price). These are assumptions, with a sensitivity grid of b from 2 to 8 (elasticity about −1.5
to −7) and c0 from 10% to 25%. Guillén, Guelman and Pérez-Marín
([ASTIN Colloquium 2013](https://actuaries.org/app/uploads/2025/07/Guillen_Paper_Hague2013.pdf))
is the methodological reference for estimating price elasticity in motor insurance
with causal methods on real quote data, which is what replacing these assumptions would need.
The 25% expense ratio, €20 fixed cost, 10% loading and the constraint levels are also assumptions.

**Results** (simulated, per year over the whole book, base case; source
[`results/price_optimization.json`](results/price_optimization.json)):

| | Flat 10% loading | Best flat multiplier (×1.135) | Optimized per segment |
|---|---|---|---|
| Expected profit | €0.98M | €1.20M | **€1.22M** |
| Profit vs flat 10% loading | – | +22.2% | **+24.8%** |
| Expected volume (policy-years converted) | 68,778 | 62,533 | 61,901 |
| Mean simulated conversion | 19.2% | 17.5% | 17.3% |
| Expected loss ratio | 58.6% | 56.8% | 56.3% |
| Profit if costs follow the GBM instead of the GLM | €1.22M | €1.42M | €1.47M |

- **Most of the gain is the loading level, not the segmentation.** The best single multiplier
  already captures +22.2 of the +24.8 points. Segment-level optimization adds only 2.6 points on
  top, at the same 90% volume floor, which binds.
- **Price changes versus the flat-loading price** (exposure-weighted): median +3.4%, 25th–75th
  percentile +3.0% to +4.7%, 95th percentile +11.0%, 99th +15.6%. No policy gets cheaper and 92%
  pay more than 0.5% extra, because at this market proxy the optimum under the volume floor sits above 1.10.
- **Who pays more.** Mean multipliers rise from 1.10 for 71+ (capped) and 1.14 for 51–70 to 1.27 for
  18–20; from 1.13 at max bonus to 1.27 above bonus-malus 100. The optimizer pushes load onto the
  segments that are already the most expensive, which is where a regulator and a pricing committee
  should look first. Density barely matters (gap 0.03).
- **Volume floor frontier** ([`price_optimization_volume_frontier.csv`](results/price_optimization_volume_frontier.csv)):
  profit uplift vs flat loading is +44.2% at a floor of 80% of baseline volume, +24.8% at 90%,
  +1.2% at 100%. The result depends heavily on how much volume is allowed to go.
- **Sensitivity** ([`price_optimization_sensitivity.csv`](results/price_optimization_sensitivity.csv),
  17 scenarios, each re-optimized): the uplift vs flat loading ranges from +10.4% (b = 8, c0 = 10%)
  to +70.5% (b = 2, c0 = 25%). Applying the base-case multipliers when demand is really different
  still gives +12.5% to +39.8%, but violates the 90% volume floor in most scenarios (down to
  84.8% of baseline), so those profit numbers are not like for like with the re-optimized ones.
  Moving the market offset to 0% or 10% changes the uplift only from +23.7% to +26.1%.

![Price optimization](results/figures/price_optimization.png)

Files: `results/price_optimization.json`, `price_optimization_segments.csv` (multiplier,
exposure and conversion per segment), `price_optimization_sensitivity.csv`,
`price_optimization_volume_frontier.csv`. The segment multipliers served by the API live in
`models/price_optimization.json`, written by the same run.

**In the API.** `POST /quote` now also returns an `offer`: technical premium, segment, multiplier,
offer price, market-price proxy, simulated conversion and expected profit, the flat-loading
reference price, and three conversion/profit curves over multipliers 0.80–1.30 for different
price sensitivities. `offer.simulated` is always `true`.

**Fairness and regulation.**

- The optimizer sees only three legitimate tariff factors (age band, bonus-malus band, density band);
  the code has an explicit list of forbidden factors (gender and others) and a test checks that
  neither the request schema nor the segment factors contain them. Gender has been banned in EU
  insurance pricing since Test-Achats (see above).
- Price optimization on demand elasticity is a separate question from risk-based pricing. In the UK
  the FCA banned renewal "price walking" for home and motor from 1 January 2022
  ([PS21/5](https://www.fca.org.uk/publication/policy/ps21-5.pdf)). I did not research the French
  or ACPR position on price optimization, so I make no claim about it here. A production version needs
  that review, a customer-outcome (fair value) test, and a check that the multipliers do not
  concentrate increases on vulnerable or protected groups. Age is a legal rating factor in
  France, but here the largest increases go to the youngest drivers, so this check is not a formality.
- Guards implemented: bounded multiplier, a cap for 71+, a loss-ratio ceiling and a volume floor.
  The report lists mean multipliers by band so the spread is visible.

**Limits of this layer.**

- The demand curve is assumed, with one curve for everyone: no customer-level elasticity, no
  competitor reaction, no renewal or tenure effect, no cross-product effects.
- Higher prices attract worse risks, and none of that adverse selection is modelled. Expected claims
  are the GLM's, treated as exact; the GBM cost check above shows the profit level moves by 20–25%.
- It is optimized and evaluated on the same book, and the GLM in-sample part (80% of policies) is
  slightly optimistic. The book is treated as the quote population, so "volume" means expected
  converted policy-years, not real sales.
- Segment-level multipliers only; a per-policy optimizer would be easy to add (the demand model
  is per policy) but would raise the fairness question above.

## Governance

- [Model card](docs/MODEL_CARD.md): intended use, GLM and GBM details, measured performance, explainability, regulatory notes (gender ban, proxies, GDPR, EU AI Act), a segment proxy check, limits, monitoring ideas, and the price-optimization risks (the demand model is simulated).
- [Data card](docs/DATA_CARD.md): source and licence, size, fields, known gaps and biases, privacy.
- Segment proxy check (premium dispersion and actual vs expected by driver age, Area and Region on the test set): `scripts/segment_fairness.py` writes [`docs/results/segment_fairness.json`](docs/results/segment_fairness.json). It is a proxy check, not a fairness audit.

## Architecture

```mermaid
flowchart LR
    A[CASdatasets / OpenML<br/>freMTPL2 .rda] -->|scripts/download_data.py| B[(data/raw/*.parquet)]
    B --> C[dbt: staging<br/>stg_policies, stg_claims]
    S[seed: region_mapping<br/>INSEE codes] --> D
    C --> D[dbt: intermediate<br/>int_policy_claims, int_policies_enriched]
    D --> E[dbt: marts<br/>fct_policies, fct_claims, mart_segment_kpis]
    E -->|pricing.train| F[GLM tariff JSON<br/>+ GBM challenger]
    F --> G[(policy_predictions.parquet)]
    G --> H[dbt: mart_loss_ratio_by_segment]
    F -->|models/tariff.json| I[FastAPI POST /quote]
    subgraph Orchestration
      J[Airflow DAG / make pipeline]
    end
```

| Layer | What it does |
|---|---|
| `scripts/download_data.py` | Pulls the original CASdatasets `.rda` files (OpenML as fallback) and writes parquet. Raw data is not committed. |
| `dbt/models/staging` | Renames and types columns; one view per source. |
| `dbt/models/intermediate` | Claims rolled up per policy, region reference joined (INSEE codes and 2016 regions), rating bands. |
| `dbt/models/marts` | `fct_policies`, `fct_claims`, `mart_segment_kpis` (frequency, severity, pure premium by segment), and `mart_loss_ratio_by_segment` (tag `post_model`). |
| dbt tests (50) | `unique`, `not_null`, `relationships`, `accepted_values`, plus three custom generic tests (`accepted_range`, `row_count_between` volume checks on sources and marts, `unique_combination`) and a singular test that every policy's ClaimNb matches its claim records. |
| `src/pricing/train.py` | GLMs (statsmodels), GBMs (scikit-learn HistGradientBoosting), metrics, relativities, SHAP, figures. |
| `src/pricing/rating.py`, `api.py` | Pure-Python rating from the tariff JSON; FastAPI `/quote` (with the optimized offer) and `/health`. |
| `src/pricing/demand.py`, `optimize.py`, `offer.py` | Simulated demand model, segment price optimization (SciPy), and the pure-Python offer computation used by the API. |
| `frontend/` | Vite + React + TypeScript quote app, served by nginx in the `web` image. |
| `compose.yaml` | `api` (FastAPI) and `web` (nginx + static app) on localhost:8080. |
| `dags/motor_pricing_dag.py` | `data → dbt_build → train → optimize → dbt_post → [docs, test]`, each task calls the matching `make` target. |
| `.github/workflows/ci.yml` | Three jobs. `build`: lint, download, dbt build and tests on DuckDB, training, price optimization, post-model dbt, pytest, dbt docs. `frontend`: `npm ci`, ESLint, tsc, Vitest, build. `docker`: `docker compose config`, build both images, start the stack, smoke test `/health` and one `/quote`. |

### Modelling choices

- **Frequency:** Poisson GLM with log link and `log(exposure)` offset. Exposure is capped
  at 1 year and claim counts at 4 (standard freMTPL2 cleaning). The bands follow Noll,
  Salzmann & Wüthrich (2018). Area is dropped because it is a banding of density, and using
  both makes the two coefficients unstable.
- **Severity:** Gamma GLM with log link on the average capped claim, weighted by claim
  count. Factors are chosen by backward elimination on training BIC.
- **GBM challenger:** the same two targets with Poisson and Gamma losses. Early stopping
  uses an internal 10% validation split. Bonus-malus has a monotone-increasing constraint
  because a worse claims history must never lower the price. The categoricals are one-hot
  encoded. scikit-learn's native categorical splits are not reproduced correctly by SHAP's
  TreeExplainer (SHAP sums were off by up to 2 on the log scale), so training checks SHAP
  additivity against the model's own predictions and fails if it breaks.
- **Balance:** each component is rescaled so its training-set total matches observed. For
  the GLM the factor goes into the intercept.
- **Selection:** nothing is tuned on the test set.

### Regulation, fairness and explainability

- **No gender.** EU law has banned gender-based insurance pricing since the Test-Achats
  ruling (CJEU C-236/09, applicable from 21 December 2012). freMTPL2 has no gender
  variable, and the API schema has no such field; a test asserts this.
- **Proxies.** Region and density are legitimate rating factors, but they correlate with
  socio-economic characteristics. A production tariff would monitor premium outcomes
  across groups where that data is lawfully available. Here the dbt loss-ratio mart is the
  monitoring hook: it shows by segment whether a tariff over- or under-charges.
- **Explainability.** The GLM is the tariff of record. Each quote returns its base premium
  and one frequency, severity and combined relativity per factor, which multiply exactly
  to the price (tested). The GBM is a challenger used to find where the GLM misfits, for
  example the bonus-malus shape. Its SHAP values are exact decompositions of its
  log-frequency.
- **AI Act.** Annex III lists pricing in life and health insurance as high-risk; motor
  insurance is not on that list. The logging, documentation and tests here still follow
  the same spirit.

## Architecture & cost choices

**DuckDB is the default and Snowflake is the production target.** The whole dataset is
7 MB of parquet, and `dbt build` over it takes about 1 second in DuckDB on a laptop. At this
size a cloud warehouse adds cost and latency without solving any problem, and CI can run
the full build and tests for free.

Snowflake becomes the right call when the platform stops being one person's laptop:

- several years of policy and claims history from operational systems
- several teams (pricing, reserving, finance) reading the same marts
- role-based access and masking on personal data
- BI tools querying concurrently

The project is set up for that switch without a rewrite:

- One dbt project, two targets in `dbt/profiles.yml`. `DBT_TARGET=snowflake` points
  everything at `MOTOR_PRICING`. Sources resolve to parquet files on DuckDB and to
  `RAW.*` / `MODEL_OUTPUTS.*` tables on Snowflake, and `dbt parse --target snowflake`
  resolves every source and model correctly.
- No dbt packages and no adapter-specific SQL. The custom tests are plain SQL.
- [`warehouse/snowflake_setup.sql`](warehouse/snowflake_setup.sql) creates an X-Small
  warehouse with 60 s auto-suspend, a 10-credit monthly resource monitor that suspends at
  100%, a `TRANSFORMER` role, schemas and a parquet stage.
- [`scripts/load_snowflake.py`](scripts/load_snowflake.py) PUTs the parquet files and
  creates tables with `INFER_SCHEMA` + `COPY INTO … MATCH_BY_COLUMN_NAME`, keeping source
  column names so the staging SQL is unchanged.
- An X-Small warehouse costs 1 credit per running hour, billed per second with a 60 s
  minimum, so short monthly runs with auto-suspend stay small. The resource monitor caps
  the worst case.

The Snowflake path has not been run yet. It needs an account; the setup is written but
untested against a live warehouse.

**Other choices:**

- **Tariff as JSON.** The model ships as a few-KB file that an actuary can review and diff.
  The API image needs only FastAPI, Pydantic and Uvicorn, with no pandas, statsmodels or
  scikit-learn.
- **Airflow runs in its own environment.** The DAG only calls `make`, so Airflow's
  dependency tree never meets dbt's or the modelling stack's. The same steps run without
  Airflow.

## How to run

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv.

```bash
uv sync
make pipeline        # download -> dbt build + tests -> train -> loss-ratio mart -> dbt docs -> pytest
```

Individual steps: `make data`, `make dbt-build`, `make train`, `make optimize`, `make dbt-post`, `make docs`,
`make test`. Explore the marts with `uv run duckdb data/warehouse.duckdb`, or browse the
docs with `cd dbt && uv run dbt docs serve --profiles-dir .`.

Quote API:

```bash
make serve
curl -s localhost:8000/quote -H 'content-type: application/json' -d '{
  "driver_age": 22, "vehicle_age": 3, "vehicle_power": 7, "bonus_malus": 90,
  "population_density": 2500, "fuel_type": "Diesel", "vehicle_brand": "B12",
  "region_name": "Ile-de-France"}'
```

Docker: `make docker-build && make docker-run` for the API alone, or `docker compose up --build` for the app (see Quote app).

Airflow (3.x, in a separate environment):

```bash
uv venv .venv-airflow --python 3.12 && uv pip install --python .venv-airflow "apache-airflow>=3,<4"
export AIRFLOW_HOME=$PWD/.airflow AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
.venv-airflow/bin/airflow standalone            # UI on :8080, or:
.venv-airflow/bin/airflow dags test motor_pricing
```

Snowflake (once an account exists):

```bash
uv sync --extra snowflake
export SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=...
# run warehouse/snowflake_setup.sql once
uv run python scripts/load_snowflake.py
DBT_TARGET=snowflake make dbt-build
```

## What has been verified

| Check | Status |
|---|---|
| `make pipeline` from a clean state | Passes locally in about 40 s: 50 dbt tests, 21 pytest tests (before the price optimization layer) |
| Full pipeline in a clean `python:3.12` container from a `git archive` of the commit | Passes (download, dbt build with 50 tests, train, `make optimize`, post-model dbt, docs, ruff, 33 pytest tests). Outputs match the committed results to 1e-11 relative |
| `airflow dags test motor_pricing` | All 7 tasks succeed, including `optimize` (Airflow 3.3.2, separate venv, run time about 8 min, DagRun state=success) |
| API rating vs training predictions | Equal to 1e-9 on 500 real policies (`tests/test_pipeline_consistency.py`) |
| `dbt parse` against the Snowflake target | Passes |
| Frontend: `npm ci`, ESLint, `tsc`, Vitest (16 tests), `vite build` | Pass in a clean Node 22 container from a `git archive` of the commit |
| Docker images and compose | Built and run on OrbStack (Docker 29.8, Compose 5.5), also from the clean `git archive`. `scripts/smoke_test.sh` passes: `/api/health`, one `/api/quote` with an offer, and a 422 on an invalid payload. Containers run as non-root (api uid 10001, nginx uid 101) |
| GitHub Actions workflow | Written (jobs `build`, `frontend`, `docker`) and not run on GitHub yet; each step was run locally as above |
| Snowflake load and build | Not run (no account yet) |

## Limits

- **Simulated demand.** The price optimization results depend entirely on assumed demand parameters (see that section); they are not observed.
- **No written premium.** Loss ratios are actual losses over each model's technical
  (pure) premium, with no expenses, commissions or profit loading.
- **One year of data.** freMTPL2 is a single cross-section, so there is no out-of-time
  validation. The split is a random split by policy. 38% of rows share every rating
  feature with at least one other row, and some of these are probably the same
  policyholder under several policy ids. A grouped split would be stricter, and the test
  metrics may be slightly optimistic for both models.
- **Wide uncertainty on uncapped results.** Full-incurred Gini CIs are wide because a few
  claims (up to €4.1M) dominate the losses. The capped metrics are the more reliable
  comparison.
- **Simplified tariff.** The GLM uses fixed bands and no interactions, and bonus-malus is
  linear on the log scale. That is a deliberately simple baseline, and the double lift
  shows where it falls short.
- **Two snapshots of the data.** CASdatasets has 677,991 policies and 26,444 claims, with
  claim counts that reconcile exactly. OpenML's copy is slightly different (678,013 /
  26,639). The download uses OpenML only if GitHub is unreachable. That path has not been
  exercised here; if its claim counts don't reconcile, `assert_claim_counts_reconcile`
  will fail the build rather than pass silently.

## Data

freMTPL2freq / freMTPL2sev from the R package CASdatasets (Charpentier & Dutang), also on
OpenML (ids 41214 and 41215). Region codes are INSEE codes for the pre-2016 regions.
