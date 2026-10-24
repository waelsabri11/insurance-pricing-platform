# Model card: motor pricing models (GLM tariff, monotone GBM, simulated price optimisation)

Companion document: [DATA_CARD.md](DATA_CARD.md). Every number below comes from a file in this
repository (`results/metrics.json`, `results/glm_relativities.csv`, `results/price_optimization.json`,
`docs/results/segment_fairness.json`) or is marked otherwise. Nothing here is a legal opinion.

## 1. Intended use

- **Illustrative** motor third-party-liability pricing on a public French dataset (freMTPL2), to
  show a pricing workflow: data pipeline, frequency x severity GLM tariff, a machine-learning
  challenger, explainability, monitoring hooks and governance documentation.
- **Not a production tariff.** There is no written premium, no expense or commission data, no
  quote or renewal data, a single year of cross-sectional data and no out-of-time validation.
  Do not use the outputs to price real policies or to make decisions about real individuals.
- **Users:** reviewers of this portfolio project, and people who want a worked example. No
  deployment, no customers.

## 2. Models

| | GLM tariff (model of record) | GBM challenger |
|---|---|---|
| Frequency | Poisson, log link, offset log(exposure); 48 parameters | scikit-learn `HistGradientBoostingRegressor`, Poisson loss, 187 iterations (early stopping) |
| Severity | Gamma, log link, on average capped claim weighted by claim count; 33 parameters after backward selection on training BIC (driver age, vehicle power, region kept) | Gamma loss, 58 iterations |
| Pure premium | frequency x severity x large-loss load (x1.3086) | same construction |
| Constraints | none beyond the factor bands | **monotone increasing in bonus-malus** |
| Calibration | each component rescaled so the training total matches observed | same |

- **Training:** 542,362 policies (80% random split by policy, seed 42); test: 135,629 policies.
  Nothing is tuned on the test set. GBM hyperparameters are fixed in `src/pricing/train.py`
  (learning rate 0.05, 31 leaves, L2 1.0, early stopping on an internal 10% split); I did not run a hyperparameter search.
- **Large losses:** claims are capped at the training 99.5th percentile (34,986 EUR) for severity
  modelling, and the excess is spread back as a flat factor (x1.3086) so the tariff stays balanced.
- **Artifacts:** `models/tariff.json` (GLM, a few KB, reviewable and diffable) is served by the
  FastAPI `/quote`. The GBM is not served; it is used to find GLM misfit.
- **Software:** statsmodels (GLM), scikit-learn (GBM), SHAP (explanations); versions pinned in `uv.lock`.

## 3. Variables

Rating factors used: driver age (bands 18-20, 21-25, 26-30, 31-40, 41-50, 51-70, 71+), vehicle age
(0, 1-10, 11+), vehicle power (capped at 9), bonus-malus (capped at 150, linear on log scale in the GLM),
log population density, fuel type, vehicle brand, region (pre-2016 regions). **Area is excluded** from
the models because it is a banding of density. **No gender or other protected attribute exists in the
data or the API** (see section 6). The GBM uses raw driver age, vehicle age, power, bonus-malus,
log density and diesel flag, plus one-hot brand and region.

## 4. Performance (held-out 20%, as measured in `results/metrics.json`)

| | Flat rate | GLM | GBM (monotone) |
|---|---|---|---|
| Frequency mean Poisson deviance | 0.4718 | 0.4514 | 0.4455 |
| Frequency deviance explained | n/a | 4.3% | 5.6% |
| Frequency Gini | 0 | 0.285 | 0.312 |
| Pure-premium Gini, capped claims (95% bootstrap CI) | 0 | **0.309** (0.270-0.349) | **0.338** (0.302-0.381) |
| Pure-premium Gini, full incurred (95% CI) | 0 | 0.367 (0.199-0.548) | 0.378 (0.229-0.556) |
| Severity mean Gamma deviance (null 1.1402) | n/a | 1.1381 | 1.1412 |
| Predicted / actual losses on test | 0.935 | 0.935 | 0.933 |

- The GBM's Gini lead on capped claims is +0.029 (95% CI +0.004 to +0.054): real but small. On full
  incurred losses the difference (CI -0.055 to +0.075) is not distinguishable from zero.
- Severity is barely predictable with these variables; the GBM severity model is slightly worse than
  the null on the test set (1.1412 vs 1.1402).
- Test losses are about 7% higher than the training average for all three tariffs (ratio about 0.93);
  README attributes this to large-claim sampling noise. I did not test that explanation separately.
- Caveat: a random split by policy can leak near-duplicate policyholders, so test metrics may be slightly optimistic.

## 5. Explainability

- **GLM relativities** (full table with 95% CIs: `results/glm_relativities.csv`). Base profile: driver 51-70,
  vehicle 1-10 years, power 6, regular fuel, brand B1, region Centre, bonus-malus 50.

  | Factor (frequency) | Relativity (95% CI) |
  |---|---|
  | Bonus-malus, per point above 50 | 1.028 (1.027-1.029), i.e. about x3.97 at 100 vs 50 |
  | Diesel vs regular | 1.18 (1.15-1.22) |
  | Driver age 18-20 / 21-25 / 26-30 / 31-40 / 41-50 / 71+ | 1.12 / 0.77 / 0.68 / 0.80 / 1.08 / 1.00 |
  | Vehicle power 9+ (vs 6) | 1.17 (1.12-1.23) |
  | Vehicle age 11+ | 0.83 (0.80-0.85) |

  The young-driver risk shows mostly through bonus-malus (new drivers start at 100); severity adds x1.50
  (1.25-1.79) for 18-20.
- **Quote-level:** each `/quote` response returns base premium and one frequency, severity and combined
  relativity per factor, which multiply exactly to the price (tested in `tests/`).
- **GBM:** monotone constraint on bonus-malus (a worse claims history can never lower the price); SHAP values
  (additivity checked against the model, max gap 8e-15). Mean |SHAP| on log-frequency: bonus-malus 0.41,
  driver age 0.16, density 0.12, vehicle age 0.10, fuel 0.09.

## 6. Regulatory and fairness notes

This section is a proxy check and a list of questions, **not a fairness audit and not legal advice**.

- **Gender (EU).** The Court of Justice ruled in *Test-Achats* (C-236/09) that using gender as a rating
  factor in insurance is incompatible with EU equal-treatment law, applicable from 21 December 2012.
  **Finding in this repo:** the raw freMTPL2 files contain no gender column (list of raw columns in
  `DATA_CARD.md`), the API schema has no such field, and a test asserts that. Because gender is absent,
  nothing here can measure or remove gender proxies; whether any rating factor correlates with gender
  cannot be checked with this data.
- **Age.** Driver age is a legal rating factor in France, as far as I know; I did not verify national
  rules beyond the README's statement. It is a strong factor here (relativities above), and it raises a
  fair-treatment question: young drivers pay the most, and in the simulated optimisation they receive the largest increases (section 8).
- **Geography (Area, Region, Density).** Allowed rating factors in this project, but they can correlate with
  socio-economic or ethnic composition (proxy discrimination). I have no data on those characteristics, so this
  repo cannot test that correlation.
- **GDPR** (general points, not a compliance assessment): data minimisation and purpose limitation for the
  rating factors used; transparency about profiling; Article 22 on solely automated decisions with legal or
  similarly significant effects; special-category data (for example health) is not used. The demo uses no
  personal data beyond the public pseudonymous dataset.
- **EU AI Act.** Annex III lists AI systems for risk assessment and pricing in life and health insurance as
  high-risk. Motor insurance pricing is not on that list as far as I know. This project is therefore not
  claimed to be high-risk, but the documentation, logging and testing here follow the same spirit. Other rules
  (GDPR, insurance-sector supervision, national law) may still apply; I have not analysed them.

### Segment proxy check (test set, `docs/results/segment_fairness.json`, `scripts/segment_fairness.py`)

135,629 test policies, 71,676 exposure-years. A/E = actual losses / predicted pure premium by segment, using
capped claims times the large-loss load (full-incurred A/E is also in the JSON but is noisy). 95% bootstrap CIs
(300 resamples). Segments below 500 exposure-years are listed in the JSON but excluded from the summaries below.
Figure: [segment_fairness.png](results/segment_fairness.png).

**Premium dispersion (individual policies, exposure-weighted):** mean pure premium 165 EUR/year for both models.

| | GLM | GBM |
|---|---|---|
| Coefficient of variation | 0.73 | 0.87 |
| 5th / 50th / 95th percentile (EUR) | 78 / 133 / 360 | 53 / 124 / 410 |
| p95 / p05 | 4.6 | 7.7 |

| Dimension (reliable segments) | Premium index vs portfolio, min to max (GLM / GBM) | A/E range (GLM / GBM) | Mean abs(A/E - 1), exposure-weighted (GLM / GBM) |
|---|---|---|---|
| Driver age band (7 of 7) | 0.87-4.33 / 0.88-3.77 | 0.78-1.18 / 0.77-1.36 | 0.049 / 0.048 |
| Area (6 of 6) | 0.73-1.31 / 0.74-1.36 | 0.88-1.04 / 0.85-1.03 | 0.049 / 0.052 |
| Region (16 of 22) | 0.59-1.34 / 0.71-1.28 | 0.67-1.34 / 0.59-1.31 | 0.077 / 0.077 |

Reading it carefully:
- **Premiums differ a lot by age**: 18-20-year-olds pay 4.3x (GLM) or 3.8x (GBM) the portfolio mean; Area E pays
  1.31x and Area A 0.73x (GLM). That is the intended effect of risk-based pricing, and it is what a proxy review
  would examine.
- **Where A/E is significantly below 1** (CI excludes 1, i.e. the segment is over-charged relative to its losses):
  driver age 21-25 (GLM 0.78 [0.63, 0.96], GBM 0.77 [0.62, 0.94]); Area E (GLM 0.88 [0.79, 0.99], GBM 0.85
  [0.77, 0.96]); regions Bourgogne, Haute-Normandie and Nord-Pas-de-Calais under the GLM, Haute-Normandie and
  Nord-Pas-de-Calais under the GBM. No reliable segment has A/E significantly above 1. The 18-20 band has a point
  A/E above 1 (1.18 GLM, 1.36 GBM) but a CI that includes 1 (0.83-1.62, 0.94-1.88): too few policies (523
  exposure-years) to say.
- **Caveat on multiple comparisons:** about 29 reliable segments x 2 models were tested at 95%, so a few flags are
  expected by chance. The GLM and GBM flag nearly the same segments, which they would also do from shared noise, as
  they are trained on the same data. Treat these as leads, not findings.
- **Limits of this check:** it uses only the segments that the rating factors define; it cannot test gender or any
  protected group (not in the data); A/E equality by segment does not establish fairness; premium here is the
  technical pure premium, not a commercial price.

## 7. Limitations

- Single year, random split by policy, no out-of-time validation; possible near-duplicate policyholders.
- Simple GLM: fixed bands, no interactions, bonus-malus linear on the log scale. The double lift shows the
  consequence: for the 10% of policies the GBM prices highest relative to the GLM, actual losses are 1.78x the GLM
  premium and 1.00x the GBM premium (README). Splines or bands on bonus-malus are the first fix to try.
- Large losses (up to 4.08M EUR; capped excess is 24% of incurred cost) make uncapped metrics very noisy.
- No expenses, commissions, taxes or competitor data in the data; loss ratios are against pure premium.
- Credibility: small segments (for example 18-20, several regions) have wide intervals.
- Data representativeness is undocumented (see the data card).

## 8. Price optimisation layer: the demand model is SIMULATED

> **All conversion, volume and profit figures from the price-optimisation layer are simulated.** freMTPL2 contains
> no quotes, conversions, renewals or competitor prices, so a demand curve cannot be estimated from it. The demand
> model is an explicit assumption (conversion = sigmoid(logit(c0) - b ln(price / market price)), base case c0 = 15%,
> b = 4). The results show what the optimiser does *if* those assumptions held; they are not observed or forecast
> business results.

- **Headline (simulated, base case, whole book per year):** expected profit EUR 1.22M with per-segment optimised
  multipliers vs EUR 0.98M with a flat 10% loading, an **uplift of +24.8%**. **+22.2 points of that comes from the
  loading level itself** (the best single flat multiplier, x1.135); segmentation adds only 2.6 points.
- **Sensitivity** (17 re-optimised scenarios): uplift from +10.4% to +70.5%; it depends mostly on the assumed
  elasticity and on the allowed volume loss (+44.2% at an 80% volume floor, +24.8% at 90%, +1.2% at 100%).
- **Who pays more (simulated multipliers):** mean multiplier 1.27 for ages 18-20, 1.20 for 21-25, 1.10 for 71+
  (capped by an assumed vulnerable-customer guard); 1.13 at max bonus vs 1.27 above bonus-malus 100. Load is pushed
  onto segments that are already the most expensive.

**Price-optimisation risks and mitigations**

| Risk | Why it matters | Mitigation in the repo / what a production system would need |
|---|---|---|
| **Price walking / loyalty penalty** | Pricing on willingness to pay rather than risk can raise prices for customers least likely to switch. In the UK the FCA's rules (PS21/5) have applied since 1 January 2022 to home and motor: a renewal price cannot exceed the equivalent new-business price. Checked against FCA sources on 2026-10-24. | This layer has no tenure or renewal effect, so it does not model price walking, but a production version would need an equivalent new-business-price test where applicable. I did not research the French / ACPR or EU position, so I make no claim about it. |
| Concentrating increases on groups | The optimiser puts the largest increases on the youngest and highest-malus drivers. | Bounded multiplier (0.80-1.30), 71+ cap, loss-ratio ceiling 70%, volume floor; multipliers are reported by band. A production system needs a fair-value / customer-outcome test and a protected-group impact check. |
| Assumed demand | One curve for everyone; elasticity not estimated from data. | Sensitivity grid; visible "Simulated" notice in the API (`offer.simulated` is always true) and the app. Replace with causal elasticity estimates from real quote data. |
| Adverse selection | Higher prices attract worse risks; not modelled. | None in the repo. |
| Cost model error | Profit is computed from GLM expected claims treated as exact; using GBM costs moves profit by 20-25%. | Reported in the README as a cost check. |
| Proxy discrimination | Segments are built from age, bonus-malus and density only. | Forbidden-factor list (gender, nationality, ethnicity, religion, disability) enforced in code and by test; see section 6 for the limits. |

## 9. Monitoring and retraining ideas (not implemented unless stated)

- **Implemented:** dbt loss-ratio mart by segment (`mart_loss_ratio_by_segment`) on test predictions; the
  segment proxy check in this card; pipeline tests (API rating equals training predictions to 1e-9 on 500 policies).
- **Ideas:** track A/E and premium index by segment on new data each period; population-stability checks on
  rating factors; trigger retraining on a calibration or Gini drift threshold; out-of-time validation once multiple
  years are available; challenger comparison with a grouped (by customer) split; review of bonus-malus treatment;
  periodic human review of the optimiser's multipliers before any use.

## 10. Risks and mitigations (summary)

| Risk | Mitigation / status |
|---|---|
| Misuse as a real tariff | Stated as illustrative; no production controls (approval, audit trail, access control) |
| Protected characteristic leakage | None in data; forbidden-factor tests; proxies only checkable on rating segments |
| Over-reading small differences | Bootstrap CIs, capped vs uncapped metrics, flagged small segments |
| Model drift | Not applicable to a static demo; monitoring ideas above |
| Simulated results mistaken for real | Explicit labels in README, API, app and this card |
| Data licence uncertainty | See the data card; data is downloaded, not redistributed |
