# QVDF Reliability Evidence for NVTA: I-95 and I-395

This repository tests whether congestion duration, travel-time reliability,
and managed-lane reliability credit can be represented consistently through
QVDF using Northern Virginia RITIS/INRIX and NVTA CBI data.

The PeMS proof-of-concept remains available on
[`main`](https://github.com/jacky850/i405-qvdf-reliability-experiments).

## Main findings

1. **The QVDF duration relationship is stable near the speed at capacity.**
   Across thresholds from $0.90v_c$ to $1.10v_c$, the fitted $f_d$ and $n$
   change only modestly.
2. **The B1 result is highly sensitive to the policy cutoff.** Changing the
   severe-congestion cutoff from $0.50v_f$ to $0.25v_f$ removes 88.7% of the
   measured congested link-mile-hours.
3. **Day-to-day loading explains only part of travel-time variability.** On
   the median I-95 SB PM TMC, loading explains 29.1% of log-delay variance;
   70.9% remains as an unmodeled residual.
4. **The PTI–TTI relationship is strong, but one fixed coefficient is not
   supported.** The local coefficient is $k=2.69$ for the primary I-95 sample
   and $k=2.97$ for the broader Northern Virginia GP sample, both below the
   SHRP2 value of 3.67.
5. **The managed-lane QVDF experiment is incomplete.** Open-direction express
   lanes provide too few accepted congestion episodes to estimate reliable
   link-specific QVDF parameters. C6 therefore provides an observed
   GP-versus-managed-lane benchmark, not a QVDF-derived or build-versus-no-build
   project benefit.

## Direct answers to the four NVTA/ICF questions

### 1. Is one PTI–TTI relationship transferable across facility types and geographies?

Not as a universal coefficient. Within the Northern Virginia GP samples,

$$
\mathrm{PTI}_{95}=1+k\ln(\mathrm{TTI})
$$

describes the observed relationship well, but the locally estimated $k$ is
2.7–3.0 rather than 3.67. Geographic transfer remains untested because the
NVTA analysis uses one region. A managed-lane coefficient cannot be estimated
reliably because nearly all open-direction managed-lane TMCs remain close to
free flow and provide too little variation in TTI.

### 2. Should B1 count planning-time savings instead of congested duration?

Planning time is the more direct reliability measure. Congested duration
depends strongly on the chosen speed cutoff, whereas planning time uses the
observed day-to-day travel-time distribution. A project-level measure could be
defined as the Build-minus-No-Build change in $T_{95}$, aggregated with the
appropriate trip or vehicle exposure. The current work demonstrates the
measurement chain but does not yet contain NVTA project scenarios.

### 3. How should managed lanes receive reliability credit?

Managed lanes should be treated as a separate facility group and evaluated in
their open direction. The intended credit is the Build-minus-No-Build reduction
in planning time for the managed-lane project and its affected GP traffic.
Current data show a large observed difference between existing GP and express
lanes, but that difference is not a causal project benefit because it does not
control for tolls, lane choice, users, or a no-build counterfactual.

### 4. Test all four options, or narrow first?

Narrow first. The near-$v_c$ threshold sensitivity is already characterized.
The immediate policy decisions are the severe-congestion cutoff and whether B1
should remain duration-based or move to planning time. Broader geographic and
facility-class transfer tests should follow after suitable data are available.

## Data and scope

- **RITIS/INRIX TMC export:** 5-minute speed, reference speed, and travel time
  for 23 weekdays in October 2025.
- **NVTA CBI calibration package:** per-TMC QVDF parameters
  $(f_d,n,\alpha,\beta)$ and accepted daily congestion episodes.
- **Cube 2025 network:** lanes, capacity, network matching, and period closure
  codes.

The licensed RITIS data and external CBI/Cube inputs are not redistributed.

Neither RITIS nor the CBI package contains observed vehicle counts. Flow is
reconstructed from RITIS speed with the inverse S3 speed–flow model. Because
RITIS travel time is also based on speed and segment length, relationships
between reconstructed loading and travel time are **same-source consistency
evidence**, not independent validation against measured volume.

Two loading measures appear in the experiments:

$$
X_E=\frac{\int_E q(t)\,dt}{C},
$$

where $E$ is the congestion episode and $C$ is hourly capacity. $X_E$ has
units of hours. B and C1–C5 use the CBI package's dimensionless four-hour
loading:

$$
x=\frac{X_E}{4\ \mathrm{h}}.
$$

Both measures exist only for days with an accepted congestion episode. Neither
is the planning model's peak-hour volume-to-capacity ratio.

## QVDF reliability chain

The model treats loading $x$ as stochastic:

$$
\ln x\sim N(\mu_x,\sigma_x^2),
$$

$$
P=f_dx^n,
\qquad
T=T_0(1+\alpha x^\beta).
$$

The corresponding mean and 95th-percentile travel-time indices are

$$
\mathrm{TTI}
=1+\alpha\exp\left(\beta\mu_x+\frac{1}{2}\beta^2\sigma_x^2\right),
$$

$$
\mathrm{PTI}_{95}
=1+\alpha\exp\left(\beta\mu_x+1.645\,\beta\sigma_x\right).
$$

## Experiment map

| ID | Question | Corridor and period | Sample | Status |
|---|---|---|---:|---|
| A1 | Does the threshold near $v_c$ change $f_d,n$? | I-95 NB GP, AM | 20 TMCs, 275 TMC-days | Complete |
| A2 | How does $0.50v_f\rightarrow0.25v_f$ change B1? | I-95 NB GP, AM | 20 TMCs, 460 TMC-days | Complete |
| B | What is the day-to-day distribution of loading? | Six I-95/I-395 GP corridor-periods | 67 TMCs, 936 episode-days | Complete |
| C1–C2 | Do loading, duration, TTI, and PTI95 move together? | I-95 SB GP, PM | 10 TMCs, 133 episode-days | Complete |
| C3 | Does stochastic loading reproduce observed reliability? | I-95 SB GP, PM | Same sample | Complete |
| C4 | How much variability does loading explain? | I-95 SB GP, PM | Same sample | Complete |
| C5 | Does the SHRP2 PTI–TTI relationship hold? | I-95 SB GP, PM and wider GP check | 10 primary TMCs | Complete within Northern Virginia |
| C6 | How should managed lanes receive reliability credit? | Four open I-95/I-395 corridor-periods | 23 weekdays | Partial: observed benchmark only |

All C1–C5 results are conditional on accepted congestion episodes.

## A1. Threshold sensitivity near the speed at capacity

Episodes are detected using thresholds $a v_c$, with $a$ from 0.90 to 1.10.
At every threshold, $P$, $X_E$, $f_d$, and $n$ are recalculated on the same
275 TMC-days.

![A1 threshold sensitivity](figures/nvta_a_v2_threshold_parameter_sensitivity.png)

| Threshold / $v_c$ | Median $P$ (h) | Median $X_E$ (h) | $f_d$ | $n$ | $R^2$ |
|---:|---:|---:|---:|---:|---:|
| 0.90 | 2.08 | 1.76 | 1.223 | 0.943 | 0.948 |
| 0.95 | 2.30 | 1.96 | 1.228 | 0.928 | 0.948 |
| 1.00 | 2.50 | 2.13 | 1.165 | 0.972 | 0.959 |
| 1.05 | 2.72 | 2.35 | 1.163 | 0.972 | 0.955 |
| 1.10 | 2.97 | 2.61 | 1.151 | 0.979 | 0.966 |

Relative to $1.00v_c$, $f_d$ changes by at most 5.4% and $n$ by at most
4.5%. Because duration and loading are calculated from the same detected
episode, this is an internal sensitivity test rather than independent
validation.

## A2. Severe-congestion policy cutoff

| Cutoff | Qualifying GP TMC-days | Mean daily congested link-mile-hours |
|---:|---:|---:|
| $0.50v_f$ | 201 of 460 | 13.63 |
| $0.25v_f$ | 43 of 460 | 1.54 |

Moving to $0.25v_f$ removes 88.7% of congested link-mile-hours and 79% of
qualifying TMC-days. The B1 score is therefore strongly controlled by the
policy cutoff even though the near-$v_c$ duration fit is stable.

## B. Day-to-day loading distribution

![Loading distribution](nvta/b-dc-variability/figures/nvta_b_dc_lognormal_sigma.png)

| Corridor-period | TMCs | Episode-days | Median $\sigma_{\ln x}$ |
|---|---:|---:|---:|
| I-95 SB PM | 16 | 213 | 0.24 |
| I-95 NB AM | 10 | 155 | 0.26 |
| I-95 NB PM | 9 | 97 | 0.55 |
| I-395 NB AM | 12 | 173 | 0.20 |
| I-395 NB PM | 9 | 122 | 0.21 |
| I-395 SB PM | 11 | 176 | 0.19 |

The lognormal approximation is empirically reasonable, but it is not clearly
superior to a normal approximation. The pooled Q-Q $R^2$ is 0.984 for
$\ln x$ and 0.997 for $x$. The fitted $\sigma$ shows no clear trend with mean
loading, but it varies substantially among TMCs. These results cover accepted
congested days only.

## C1–C2. Association among loading, duration, and reliability

![C1 associations](key_results/fig_c1_dc_p_tti.png)

| Level | Pair | Sample | Pearson | Spearman (95% interval) |
|---|---|---:|---:|---:|
| C1 | $x$ vs $P$ | 133 days | 0.98 | 0.98 (0.97–0.99) |
| C1 | $x$ vs TTI | 133 days | 0.76 | 0.81 (0.72–0.88) |
| C1 | $P$ vs TTI | 133 days | 0.82 | 0.89 (0.81–0.94) |
| C2 | $E[P]$ vs TTI | 10 TMCs | 0.92 | 0.87 (0.41–1.00) |
| C2 | $P_{95}$ vs $\mathrm{PTI}_{95}$ | 10 TMCs | 0.81 | 0.90 (0.59–1.00) |
| C2 | TTI vs $\mathrm{PTI}_{95}$ | 10 TMCs | 0.94 | 0.93 (0.65–1.00) |

The directions and rankings are consistent with the QVDF chain. These are not
independent flow-versus-travel-time validations because reconstructed flow and
RITIS travel time both originate from the same speed observations. The wide C2
intervals also reflect the 10-TMC sample.

## C3–C4. Reliability prediction and unexplained variability

| PTI95 model | Pearson | Spearman | MAE | Bias |
|---|---:|---:|---:|---:|
| Loading variability only | 0.86 | 0.78 | 1.23 | −1.23 |
| Loading variability plus residual $\tau$ | 0.95 | 0.84 | 0.82 | −0.82 |

The loading-only model ranks TMCs reasonably well but underpredicts PTI95 on
all 10 TMCs. For the median TMC, loading explains 29.1% of log-delay variance;
70.9% remains as an unmodeled residual. That residual may contain incidents,
weather, work zones, measurement error, and other effects, but the present data
cannot attribute it to specific causes.

![C4 variability decomposition](nvta/c4-variability-decomposition/figures/nvta_c4_variability_decomposition.png)

## C5. PTI–TTI relationship

![C5 PTI-TTI comparison](nvta/c5-pti-tti-comparison/figures/nvta_c5_pti_tti_shrp2_comparison.png)

TTI and PTI95 are strongly associated in the primary sample (Spearman 0.93).
The local fit gives $k=2.69$ with a bootstrap 95% interval of 2.49–2.92.
SHRP2's $k=3.67$ overpredicts all 10 TMCs, with MAE 0.94. A leave-one-TMC-out
local fit gives MAE 0.28. Across the broader Northern Virginia GP sample,
$k=2.97$ with a 95% interval of 2.83–3.10.

These results support local calibration within Northern Virginia GP facilities.
They do not establish geographic transferability.

## C6. Managed-lane feasibility check and observed benchmark — partial

### Intended experiment

The intended experiment was to estimate the managed lane's own loading
distribution and QVDF parameters, derive its TTI and PTI95, and then calculate
reliability credit from a Build-versus-No-Build planning-time difference:

$$
\Delta T_{95}=T_{95}^{\mathrm{NoBuild}}-T_{95}^{\mathrm{Build}}.
$$

### Why the intended experiment could not be completed

The express lanes are reversible. The open directions generally remain near
free flow and rarely produce accepted congestion episodes. The CBI audit found:

| Open managed-lane corridor-period | Link-specific high/medium QVDF fits |
|---|---:|
| I-95 HOV NB AM | 0 |
| I-95 HOV SB PM | 0 |
| I-395 HOV NB AM | 1 |
| I-395 HOV SB PM | 0 |

This is insufficient to estimate open-direction managed-lane
$(f_d,n,\alpha,\beta)$ or a stochastic QVDF reliability envelope. The 12
high/medium I-95 HOV NB PM fits and most I-395 HOV NB PM fits come from links
that are closed in PM, so those parameters were rejected for this purpose.

### What C6 provides instead

C6 compares observed GP and express-lane travel times for four open
corridor-periods. Each value is based on 23 weekdays and a matched corridor
section. The GP time is converted to a per-mile rate and scaled to the managed
lane's section length.

| Corridor-period | Managed-lane section | Observed TTI GP / ML | Observed PTI95 GP / ML | Observed mean-time difference | Observed planning-time difference |
|---|---:|---:|---:|---:|---:|
| I-95 SB PM | 23.6 mi | 2.12 / 1.01 | 2.55 / 1.01 | 27.0 min/trip | 36.2 min/trip |
| I-95 NB AM | 23.6 mi | 1.53 / 1.01 | 2.02 / 1.09 | 14.0 min/trip | 23.2 min/trip |
| I-395 SB PM | 9.6 mi | 1.85 / 0.98 | 2.38 / 0.99 | 9.2 min/trip | 14.2 min/trip |
| I-395 NB AM | 9.5 mi | 1.79 / 1.02 | 2.21 / 1.10 | 8.5 min/trip | 12.0 min/trip |

![C6 observed GP and managed-lane benchmark](nvta/c6-managed-lane-comparison/figures/nvta_c6_gp_vs_managed_lane.png)

The existing express lanes operate close to free flow in their open direction.
This confirms that a separate managed-lane treatment is necessary, but it does
not complete the intended QVDF experiment.

The C6 differences must not be interpreted as project benefits because:

- no Build-versus-No-Build scenario is available;
- managed-lane QVDF parameters were not estimated;
- tolling, lane choice, and user selection are not controlled;
- GP and managed-lane sections are geographically matched but not identical;
- TTI values slightly below 1 reflect differences between observed speed and
  the RITIS reference-speed baseline.

Completing C6 requires either observed open-lane flow sufficient to estimate a
managed-lane loading distribution, or an NVTA scenario model that supplies
Build and No-Build managed-lane travel-time distributions.

## Reproduce

The RITIS export, CBI package, and Cube network are external inputs. Configure
their locations with `NVTA_EXTERNAL_ROOT` and the files under `config/`, then
run:

```bash
python scripts/audit_nvta_i95_parameters.py
python scripts/run_nvta_experiment_a.py --config config/nvta_experiment_a_i95_nb_am_empirical.json
python scripts/run_nvta_b1_speed_cutoff.py
python nvta/b-dc-variability/run_nvta_b.py
python nvta/c3-qvdf-reliability/run_nvta_c3.py
python nvta/c4-variability-decomposition/run_nvta_c4.py
python nvta/c5-pti-tti-comparison/run_nvta_c5.py
python nvta/c6-managed-lane-comparison/run_nvta_c6.py
python nvta/core_evidence.py
```
