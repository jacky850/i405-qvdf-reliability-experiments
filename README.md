# I-405 South QVDF Threshold Sensitivity and Reliability Experiments

This small, reproducible experiment tests how the congestion speed threshold
changes the fitted duration relationship

\[
P = f_d x^n,
\]

where `P` is the longest AM congestion episode in hours. Five thresholds are
tested: `0.90`, `0.95`, `1.00`, `1.05`, and `1.10` times the S3 speed at
capacity.

## Scope

- Dataset: Caltrans PeMS
- Corridor: I-405 South
- Adjacent links: `L405S-132`, `L405S-115`, and `L405S-114`
- Dates: 15 consecutive non-holiday weekdays, September 5-25, 2025
- AM analysis period for flow parameters: 06:00-10:00 Pacific local time
- Episode-search window: 05:30-10:30, including a 30-minute boundary buffer
- Resolution: 5 minutes
- Common sample: 45 link-days at every threshold

## Definitions and units

For link \(l\), day \(d\), and threshold multiplier \(a\), let
\(\mathcal{E}_{l,d,a}\) denote the detected congestion episode and let
\(\Delta t=5/60\) hour. The variables are defined as

\[
D_{l,d,a}
=
\sum_{t\in\mathcal{E}_{l,d,a}}q_{l,d,t}\,\Delta t,
\qquad
[D]=\mathrm{veh/link},
\]

\[
C_l
=
Q_{0.95}\!\left(
\left\{q_{l,d,t}:06{:}00\le t<10{:}00\right\}
\right),
\qquad
[C]=\mathrm{veh/(h\cdot link)},
\]

\[
\left[\frac{D}{C}\right]=\mathrm{h},
\qquad
N_{l,d,a}=\left|\mathcal{E}_{l,d,a}\right|,
\qquad
P_{l,d,a}=N_{l,d,a}\Delta t,
\qquad
[P]=\mathrm{h},
\]

\[
P=f_d\left(\frac{D}{C}\right)^n.
\]

Both \(q\) and \(C\) are whole-link quantities over all lanes. A single fixed
\(C_l\) is used for every day and every threshold tested on link \(l\).
Here, uppercase \(N_{l,d,a}\) is the number of 5-minute bins in the detected
episode. It is distinct from lowercase \(n\), the fitted exponent in the QVDF.

## Method, one step at a time

### Step 1 - Estimate fixed link parameters

Run:

```bash
python scripts/step1_estimate_link_parameters.py
```

For each link:

- free-flow speed `vf_mph` = 95th percentile of observed AM speed;
- whole-link capacity `capacity_vph_link` = 95th percentile of observed AM
  whole-link flow;
- S3 capacity speed `vc_mph = vf_mph / sqrt(2)`.

Output: `results/step1_link_parameters.csv`

### Step 2 - Prepare link-day flow statistics

Run:

```bash
python scripts/step2_compute_daily_demand.py
```

This script prepares the link-day intermediate table used by the automated
experiment pipeline.

Output: `results/step2_daily_demand.csv`

### Step 3 - Detect congestion under five thresholds

Run:

```bash
python scripts/step3_detect_threshold_episodes.py
```

Speed is smoothed by a centered 3-bin median. A candidate episode must contain
at least three consecutive 5-minute bins at or below the selected threshold.
The longest episode is retained; ties use the lower minimum speed and then the
earlier start. For each retained episode, the script computes \(P\), \(D\),
\(C\), and \(D/C\) using the definitions above.

Outputs:

- `results/step3_threshold_episodes.csv`
- `results/step3_common_support.csv`

### Step 4 - Fit QVDF and compare parameters

Run:

```bash
python scripts/step4_fit_qvdf.py
```

For each threshold, the pooled fit uses all 45 common link-days and estimates
both `f_d` and `n` by least squares, with `1 <= n <= 4`. Per-link fits are
reported separately. The script also produces 500 fixed-seed bootstrap
replicates for pooled-fit confidence intervals.

Outputs:

- `results/step4_qvdf_fit_summary.csv`
- `results/step4_qvdf_predictions.csv`
- `results/experiment_a_summary.json`

### Step 5 - Create figures

Run:

```bash
python scripts/step5_make_figures.py
```

Outputs:

- `figures/threshold_parameter_sensitivity.png`
- `figures/duration_vs_dc.png`

To reproduce everything after installing `requirements.txt`:

```bash
python scripts/run_all.py
```

## Primary results

| threshold / capacity speed | median P (h) | f_d | n | R-squared | RMSE (h) |
|---:|---:|---:|---:|---:|---:|
| 0.90 | 2.833 | 1.286 | 1.248 | 0.949 | 0.199 |
| 0.95 | 3.000 | 1.238 | 1.281 | 0.932 | 0.211 |
| 1.00 | 3.000 | 1.193 | 1.313 | 0.928 | 0.214 |
| 1.05 | 3.083 | 1.164 | 1.316 | 0.909 | 0.236 |
| 1.10 | 3.250 | 1.238 | 1.209 | 0.874 | 0.274 |

Relative to the `1.00 x vc` case, `f_d` changes by at most 7.9% and `n` by at
most 7.9%. The relationship is therefore reasonably stable from `0.90` through
`1.05 x vc`. At `1.10 x vc`, `n` drops by 7.9%, R-squared falls to 0.874, and
RMSE rises to 0.274 hours, showing that the highest threshold begins to weaken
the fit.

## Folder structure

```text
sensitive test/
├── config/experiment_a.json
├── data/
│   ├── i405s_pems_am_15_weekdays_raw.csv.gz
│   └── i405s_pems_am_15_weekdays_link_5min.csv
├── experiment_a/core.py
├── scripts/
│   ├── step1_estimate_link_parameters.py
│   ├── step2_compute_daily_demand.py
│   ├── step3_detect_threshold_episodes.py
│   ├── step4_fit_qvdf.py
│   ├── step5_make_figures.py
│   └── run_all.py
├── tests/test_core.py
├── results/
├── figures/
├── requirements.txt
└── README.md
```

## Input data dictionary

### `data/i405s_pems_am_15_weekdays_raw.csv.gz`

Station-level PeMS observations retained from the full source. It contains
5,400 rows. All retained rows have `is_observed = 1` and `is_missing = 0`.

### `data/i405s_pems_am_15_weekdays_link_5min.csv`

The 2,700-row experiment input. Multiple stations assigned to the same link
and timestamp are averaged, not summed.

| Column | Unit | Definition |
|---|---:|---|
| `corridor` | - | Corridor label, `I405_S`. |
| `road_order` | - | Link order by increasing median milepost. |
| `link_id` | - | PeMS-derived link identifier. |
| `timestamp_local` | ISO 8601 | Pacific local timestamp with UTC offset. |
| `date_local` | date | Pacific local calendar date. |
| `time_local` | HH:MM | Pacific local clock time. |
| `minute_of_day` | minutes | Minutes since local midnight. |
| `is_am_analysis_bin` | boolean | True for 06:00-10:00. |
| `direction` | - | Travel direction, `S`. |
| `milepost` | miles | Median source milepost for the link's stations. |
| `station_count` | stations | Source stations represented in the row. |
| `speed_mph` | mph | Mean observed speed across represented stations. |
| `flow_vph` | veh/h/link | Mean observed station-total whole-link flow, not per lane. |
| `occupancy_fraction` | fraction | Mean detector occupancy. |
| `density_veh_per_mi` | veh/mile/link | Mean source density converted to miles. |

The source file appends `Z` to PeMS local wall-clock timestamps without
converting the clock to UTC. `timestamp_local` therefore interprets the source
clock in `America/Los_Angeles`; the September sample has UTC offset `-07:00`.

---

# Experiment B - Day-to-day D/C reliability calibration

Experiment B treats daily demand-to-capacity as stochastic and prepares the
empirical distribution of

\[
X_{s,d}=\frac{D_{s,d}}{C_s},
\qquad
Y_{s,d}=\ln X_{s,d},
\]

for PeMS mainline detector (s) and weekday (d). This first step prepares the
quality-controlled detector-day sample. The next step estimates
\(\sigma_{\ln(D/C)}\) as a function of mean (D/C) and uses it in the QVDF
reliability envelope.

## Experiment B scope

- Dataset: Caltrans PeMS
- Corridor: I-405 South
- Period: AM, 06:00-10:00 Pacific local time
- Resolution: 5 minutes
- Dates: 100 non-holiday weekdays, June 2-October 23, 2025
- Excluded dates: June 19, July 4, September 1, and October 13, 2025
- Quality rule: all 48 AM bins in a detector-day must have PeMS
  `pct_observed = 100`
- Availability rule: a detector must have at least 80 complete days
- Retained sample: 12 mainline detectors on 9 mapped network links and 1,184
  detector-days. Each retained detector has 98-99 complete days. October 7,
  2025 has no retained strict detector-day, so the output spans 99 of the 100
  selected calendar dates.

The strict quality rule matters because the processed detector file marks
filled cells as observed. Experiment B uses the separately reconstructed raw
PeMS `% observed` field so filled or partially observed cells cannot
artificially reduce the estimated day-to-day variance.

## Experiment B definitions

Let (q_{s,d,t}) be the whole-detector flow rate at 5-minute bin (t), and let
\(\mathcal W_{d}\) be the set of all consecutive 12-bin windows in the AM
period. Daily demand is

\[
D_{s,d}
=
\max_{w\in\mathcal W_d}
\left(\frac{1}{12}\sum_{t\in w}q_{s,d,t}\right),
\qquad
[D]=\mathrm{veh/(h\cdot detector)}.
\]

Capacity is fixed for every day but estimated from PeMS. First calculate the
corridor-wide 95th-percentile per-lane flow from every fully observed I-405
South mainline AM cell in the selected 100 weekdays:

\[
c_{95}
=
Q_{0.95}\!\left(\left\{\frac{q_{s,d,t}}{L_s}:\text{PeMS percent observed}=100\right\}\right),
\qquad
C_s=c_{95}L_s,
\qquad
[C]=\mathrm{veh/(h\cdot detector)},
\]

where (L_s) is the PeMS metadata lane count. In this sample,
\(c_{95}=1{,}872\) veh/h/lane. A common empirical per-lane value is used rather
than a separate P95 for each station. A station-specific P95 would mechanically
normalize every station's (D/C) close to one and remove the loading range
needed to estimate whether variability changes with mean (D/C). Cube link
lane counts are not used because several detector-to-network matches cross
network segmentation boundaries. Both (D) and (C) are whole-detector,
all-lane rates.

The capacity pool contains 87,238 fully observed 5-minute cells from 33 PeMS
mainline detectors. It is saved separately so the 1,872 veh/h/lane percentile
can be checked without mixing the capacity-estimation sample with the 12
detectors that satisfy the stricter repeated-day availability rule.

## Step B1 - Prepare detector-day D/C

Run:

```bash
python scripts/b1_prepare_detector_days.py
```

Outputs:

- `data/i405s_pems_am_100_weekdays_detector_5min.csv.gz`: retained strict
  5-minute observations
- `data/i405s_pems_am_100_weekdays_capacity_pool.csv.gz`: fully observed cells
  used to estimate the common PeMS P95 per-lane capacity
- `results/b1_sample_dates.csv`: the frozen 100-date sample
- `results/b1_detector_day_dc.csv`: one row per detector-day with (D), (C),
  (D/C), \(\ln(D/C)\), and peak-hour speed/TTI diagnostics
- `results/b1_detector_inventory.csv`: detector metadata and preliminary
  across-day log statistics
- `results/b1_data_quality_summary.json`: machine-readable sample audit

The retained detectors have mean (D/C) from approximately 0.56 to 1.01. Any
later reliability envelope outside this range must be labeled as extrapolation
rather than presented as observed I-405 South AM evidence.

## Step B2 - Calibrate day-to-day log variability

Run:

```bash
python scripts/b2_calibrate_sigma.py
```

For each detector, Step B2 estimates the across-weekday parameters

\[
\mu_s=\operatorname{mean}_d\!\left[\ln(D_{s,d}/C_s)\right],
\qquad
\sigma_s=\operatorname{sd}_d\!\left[\ln(D_{s,d}/C_s)\right].
\]

It then compares the two simplest candidate models:

\[
\sigma(x)=a,
\qquad
\sigma(x)=a+bx,
\qquad x=\operatorname{mean}_d(D/C).
\]

The comparison uses AICc and leave-one-detector-out RMSE. When the constant
model is within 2 AICc units of the minimum, the constant is selected by
parsimony.

Outputs:

- `results/b2_detector_log_stats.csv`: one row per detector with
  \(\mu_{\ln(D/C)}\), \(\sigma_{\ln(D/C)}\), skewness, kurtosis, and normal Q-Q
  correlation
- `results/b2_dc_bins.csv`: 0.1-wide mean-(D/C) bin summary
- `results/b2_sigma_model_comparison.csv`: constant-versus-linear diagnostics
- `results/b2_sigma_curve.csv`: selected model from 0.4 to 1.3 with an
  empirical-support flag
- `results/b2_summary.json`: selected model and main diagnostics
- `figures/experiment_b_sigma_calibration.png`: clean calibration figure

The selected model for the current sample is the constant specification,

\[
\sigma_{\ln(D/C)}=0.0376.
\]

The linear alternative improves AICc by only 1.71 units, below the configured
two-unit threshold. The constant is therefore retained as the simpler model.
This does not establish that loading can never affect variability; it states
that the current 12-detector sample does not support the extra slope strongly
enough.

## Step B3 - Fit delay and create the reliability envelope

Run:

```bash
python scripts/b3_reliability_envelope.py
```

The daily PeMS peak-hour observations calibrate the travel-time branch

\[
\mathrm{TTI}=1+\alpha(D/C)^\beta
\]

by nonlinear least squares in observed TTI space. This calibration is separate
from Experiment A's duration parameters \(f_d\) and \(n\). It supplies the
travel-time parameters that were not present in the existing duration-only
code.

For the current 1,184 detector-days, the fitted values are

\[
\alpha=0.278,
\qquad
\beta=1.772.
\]

The pooled fit has \(R^2=0.129\), TTI RMSE = 0.166, and TTI MAE = 0.126.
This is a weak delay fit. It is sufficient to exercise the reliability
calculation end to end, but the resulting envelope is provisional rather than
a validated forecasting relationship. More days can stabilize each detector's
distribution; broader detectors, periods, and facility types are also needed
to test whether one pooled delay curve is defensible.

For an arithmetic mean loading \(x=E[D/C]\), the lognormal location parameter
is

\[
\mu_{\ln(D/C)}=\ln x-\frac{1}{2}\sigma_{\ln(D/C)}^2.
\]

The percentile travel-time index is then

\[
\mathrm{TTI}_p
=
1+\alpha\exp\!\left(
\beta\mu_{\ln(D/C)}+z_p\beta\sigma_{\ln(D/C)}
\right),
\]

and the expected TTI is

\[
E[\mathrm{TTI}]
=
1+\alpha\exp\!\left(
\beta\mu_{\ln(D/C)}+
\frac{1}{2}\beta^2\sigma_{\ln(D/C)}^2
\right).
\]

The output includes \(\mathrm{TTI}_{50}\), \(\mathrm{TTI}_{80}\),
\(\mathrm{TTI}_{90}\), \(\mathrm{TTI}_{95}\), the derived multiplier
\(\gamma_p=\mathrm{TTI}_p/E[\mathrm{TTI}]\), and the SHRP2 L03 benchmark

\[
\mathrm{TTI}_{95}^{\mathrm{SHRP2}}
=1+3.67\ln(E[\mathrm{TTI}]).
\]

When delay dominates free-flow time and \(\beta\) and \(\sigma\) are stable,
the multiplier approaches

\[
\gamma_p
\approx
\exp\!\left(
z_p\beta\sigma-\frac{1}{2}\beta^2\sigma^2
\right),
\]

which explains when an approximately fixed reliability multiplier can emerge.

Outputs:

- `results/b3_delay_fit_predictions.csv`: observed and fitted detector-day TTI
- `results/b3_reliability_envelope.csv`: percentile curves from mean D/C 0.4
  to 1.3, with observed-support flags
- `results/b3_summary.json`: calibrated parameters, fit diagnostics, and scope
- `figures/experiment_b_delay_calibration.png`: observed TTI and fitted delay
  curve
- `figures/experiment_b_reliability_envelope.png`: TTI percentile envelope and
  SHRP2 comparison

The calibration figure and `b3_summary.json` must be read with the envelope.
A completed pipeline is not by itself evidence that the delay curve has strong
predictive fit.

Run the full Experiment B pipeline with:

```bash
python scripts/run_experiment_b.py
```

The repository includes the quality-controlled detector-day table required by
Steps B2 and B3. They can be reproduced directly with:

```bash
python scripts/b2_calibrate_sigma.py
python scripts/b3_reliability_envelope.py
```

Rebuilding Step B1 requires the original PeMS source files, which are not
redistributed here. Place them under `raw_data/` using the filenames listed in
`config/experiment_b.json`, or replace those entries with absolute paths on
your machine. The `raw_data/` directory is excluded from version control.
