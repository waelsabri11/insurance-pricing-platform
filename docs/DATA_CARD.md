# Data card: freMTPL2 (French motor third-party liability)

Scope: the data used by this repository for an **illustrative** motor pricing pipeline. Not a
production dataset. Companion document: [MODEL_CARD.md](MODEL_CARD.md).

## Source and licence

- **Datasets:** `freMTPL2freq` (one row per policy) and `freMTPL2sev` (one row per claim) from
  the R package **CASdatasets** (Dutang & Charpentier), also mirrored on OpenML (ids 41214 and
  41215).
- **What the code downloads:** `scripts/download_data.py` fetches the `.rda` files from the
  CASdatasets GitHub repository (`dutangc/CASdatasets`) and writes parquet to `data/raw/`
  (not committed). OpenML is only a fallback if GitHub is unreachable; that path has not been
  exercised in this repo, and the OpenML snapshot differs slightly (678,013 policies and
  26,639 claims, per the script's docstring). The results in this repo come from the
  CASdatasets snapshot.
- **Licence:** the CASdatasets package `DESCRIPTION` file states `GPL (>= 2)` (checked on
  GitHub on 2026-10-24, version 1.2-1). I did **not** find a separate licence statement for the
  individual datasets, so I cannot say whether that package licence fully covers redistribution
  of the data. This repo does not redistribute the raw data; it downloads it at run time.
- **Insurer and period:** not documented in the repo. The data are commonly described as a
  French motor third-party liability portfolio, but I have not verified the insurer, the
  calendar year(s) or whether the sample is representative of any market.

## Size

From `results/metrics.json` and the dbt marts:

| | |
|---|---|
| Policies | 677,991 |
| Claims (records in `freMTPL2sev`) | 26,444 (claim counts reconcile exactly with the policy table; a dbt test asserts it) |
| Exposure | 358,483 policy-years raw; 358,344 after capping exposure at 1 year |
| Share of policies with no claim | 96.3% |
| Train / test split | 542,362 / 135,629 policies (random split by policy, seed 42) |

## Fields used

| Source column | Repo name | Type / range observed | Use |
|---|---|---|---|
| `IDpol` | `policy_id` | integer id | key |
| `ClaimNb` | `claim_count` | 0 to 16 | frequency target (capped at 4 for modelling) |
| `Exposure` | `exposure_years` | 0.003 to 2.01 | offset (capped at 1) |
| `VehPower` | `vehicle_power` | 4 to 15 | rating factor (capped at 9) |
| `VehAge` | `vehicle_age` | 0 to 100 | rating factor (bands 0, 1-10, 11+) |
| `DrivAge` | `driver_age` | 18 to 100 | rating factor (bands 18-20 ... 71+) |
| `BonusMalus` | `bonus_malus` | 50 to 230 | rating factor (capped at 150, linear on log scale) |
| `VehBrand` | `vehicle_brand` | 11 anonymised brands (B1...B14) | rating factor |
| `VehGas` | `fuel_type` | Diesel 332,128 / Regular 345,863 | rating factor |
| `Area` | `area_code` | A to F (6 levels) | reporting and segment checks only; **not in the models** (it bands density) |
| `Density` | `population_density` | inhabitants/km², up to 27,000 | rating factor (log) |
| `Region` | `region_name` | 22 pre-2016 French regions | rating factor |
| (`freMTPL2sev`) `ClaimAmount` | `claim_amount` | 1 to 4,075,401 EUR, median 1,172 | severity target (capped at 34,986 EUR, the training 99.5th percentile) |

A seed table (`dbt/seeds/region_mapping.csv`) maps regions to INSEE codes and to the 2016
regions; it is repo-authored reference data.

## What is in the data and what is not

- **No gender, nationality, ethnicity, religion or health field.** The raw columns are listed
  above and contain none of them. Gender-based pricing is also banned in the EU since the
  Test-Achats ruling (see the model card).
- **No personal identifiers.** Policies carry an id, no name, address, postcode or date of
  birth. Quasi-identifiers exist (driver age, region, density, vehicle brand, power, age), and
  38% of rows share every rating feature with at least one other row (README, Limits).
  I have not run a re-identification analysis, so I do not claim the data are anonymous in the
  GDPR sense.
- **No premium, quote, conversion, renewal, competitor or expense data.** Loss ratios here
  are actual losses over a model's technical premium, and the price-optimisation demand model
  is simulated for this reason.
- **No claim cause, date or coverage detail.** Third-party liability only; the amounts are not
  split into bodily injury and property damage in the files used.

## Known gaps, quirks and biases

- **Single cross-section.** There is no calendar dimension, so no out-of-time validation and no
  trend or inflation handling.
- **Possible repeated policyholders.** The README notes that some identical rows are probably
  the same customer under several policy ids; a random split by policy can therefore leak
  between train and test and make test metrics slightly optimistic.
- **Cleaning applied:** exposure capped at 1 year (1,224 policies exceed it, up to 2.01); claim
  counts capped at 4 (8 policies have more, up to 16); bonus-malus capped at 150 (209 policies
  above, up to 230); vehicle power capped at 9 (66,424 policies above). These are standard
  freMTPL2 case-study choices (Noll, Salzmann & Wuthrich, 2018), not ground truth.
- **Implausible values left in.** Vehicle age up to 100 (8,321 policies above 20 years) and
  driver age up to 100 (401 above 90) are kept as they are in the source; I did not investigate them.
- **Heavy-tailed losses.** A few claims dominate: the largest is 4.08M EUR, and claims above the
  cap make up 24% of incurred cost (README). Uncapped metrics have wide confidence intervals.
- **Few young drivers.** 18-20-year-olds are about 1,338 test policies (523 test policy-years),
  so any estimate for them is noisy (see the confidence intervals in
  `docs/results/segment_fairness.json`).
- **Sampling bias is unknown.** The source does not document how policies were selected, so
  conclusions about "French drivers" are not supported. Region and density distributions
  reflect this one portfolio (for example Centre has the most policies), not the population.
- **Two snapshots exist** (CASdatasets vs OpenML) with different counts; results are tied to
  the CASdatasets one.
- **Missing values:** the dbt tests require key fields to be non-null and in range; I did not
  separately tabulate missingness in the raw files for this card.

## Privacy and use

- The raw data contain no direct identifiers; this repository does not commit them and
  downloads them from the public source.
- For a real tariff, personal data processing would need a GDPR lawful basis, data
  minimisation and purpose limitation, and access control (the Snowflake notes in the README
  mention masking). None of that is implemented or claimed for this public demo.
- Do not use this data to infer anything about individuals.
