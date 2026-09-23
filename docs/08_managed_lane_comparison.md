# C6: GP versus Managed-Lane Reliability (memo Section 8)

[Back to the summary README](../README.md)

Script: [`nvta/c6-managed-lane-comparison/run_nvta_c6.py`](../nvta/c6-managed-lane-comparison/run_nvta_c6.py)

## Reversible operation decides which data are valid

The I-95 and I-395 express lanes are reversible. A managed-lane TMC keeps
reporting a RITIS speed while its direction is closed. The Cube network codes
the closure (`AMLIMIT`/`PMLIMIT` = 9), and the observed speeds agree:

| Managed-lane corridor | AM network status | AM median speed / reference | PM network status | PM median speed / reference |
|---|---|---:|---|---:|
| I-95 HOV NB | open (20 of 20) | 1.00 | closed (20 of 20) | 0.70 |
| I-95 HOV SB | closed (20 of 20) | 0.88 | open (20 of 20) | 1.00 |
| I-395 HOV NB | open (22 of 22) | 1.01 | closed (19 of 22) | 0.76 |
| I-395 HOV SB | closed (19 of 22) | 0.91 | open (22 of 22) | 1.02 |

The CBI QVDF parameters that exist for managed lanes are fitted on those
closed-direction records:

| Corridor-period | Link-specific high/medium fits | On open links |
|---|---:|---:|
| I-95 HOV NB PM | 12 | 0 |
| I-395 HOV NB PM | 13 | 1 |
| I-95 HOV NB MD | 8 | 8 by network code, but MD straddles the reversal (speed ratio 0.91) |
| every open-direction AM/PM corridor-period | 0 or 1 | 0 or 1 |

No other CBI corridor (I-66, I-495, US and state routes) has a managed-lane
folder. **There are no usable QVDF parameters for an open managed lane.** This
is expected: in its open direction the managed lane rarely forms a congestion
episode, so episode-based calibration has nothing to fit. Managed-lane
reliability is therefore measured directly from observed travel times.

Full audit: `nvta/c6-managed-lane-comparison/output/c6_managed_lane_parameter_audit.csv`.

## Method

For each open corridor-period, the section is the open managed-lane TMCs plus
the unrestricted GP TMCs whose midpoints fall on the same stretch (principal-axis
projection of TMC coordinates). For facility $f$ and weekday $d$,

$$
T_{f,d}=\frac{1}{|W|}\sum_{t\in W}\sum_{s\in f}\mathrm{TT}_{s,d,t},
\qquad
T_{0,f}=\sum_{s\in f}\frac{L_s}{v^{\mathrm{ref}}_s},
$$

with $W$ = AM 06:00–09:00 or PM 15:00–19:00 (CBI model periods), $L_s$ the
length implied by RITIS travel time and speed, and $v^{\mathrm{ref}}_s$ the RITIS
reference speed. Then

$$
\mathrm{TTI}=\frac{E_d[T]}{T_0},\quad
\mathrm{PTI}_{95}=\frac{Q_{0.95,d}[T]}{T_0},\quad
\gamma_{95}=\frac{\mathrm{PTI}_{95}}{\mathrm{TTI}}.
$$

Savings compare per-mile times scaled to the managed-lane section length, so
a small difference in covered GP length does not appear as a saving.
Intervals are day-bootstrap 95% intervals (2,000 replicates). With 23 weekdays
the 95th percentile sits near the sample maximum, so its upper interval is
tight by construction.

## Results (23 weekdays, October 2025)

| Pair | Section (mi) | GP TTI | ML TTI | GP PTI95 | ML PTI95 | GP $\gamma_{95}$ | ML $\gamma_{95}$ | Mean-time saving (min/trip) | Planning-time saving (min/trip) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **I-95 SB PM** | 23.6 | 2.12 | 1.01 | 2.55 | 1.01 | 1.20 | 1.01 | 27.0 (24.7–29.1) | **36.2** (31.5–36.7) |
| I-95 NB AM | 23.6 | 1.53 | 1.01 | 2.02 | 1.09 | 1.32 | 1.08 | 14.0 (11.6–16.5) | 23.2 (17.5–26.9) |
| I-395 SB PM | 9.6 | 1.85 | 0.98 | 2.38 | 0.99 | 1.28 | 1.01 | 9.2 (7.9–10.5) | 14.2 (12.5–14.3) |
| I-395 NB AM | 9.5 | 1.79 | 1.02 | 2.21 | 1.10 | 1.24 | 1.07 | 8.5 (7.3–9.8) | 12.0 (10.3–15.7) |

At TMC level (85 GP, 84 managed-lane TMCs), 80 of 84 managed-lane TMCs sit at
TTI < 1.1 and PTI95 < 1.2, and the median managed-lane $\gamma_{95}$ is 1.02
against 1.39 for GP. The GP TMCs give $k=2.97$ (95% CI 2.83–3.10) in
$\mathrm{PTI}_{95}=1+k\ln\mathrm{TTI}$, again below SHRP2's 3.67. A managed-lane
$k$ is not identified: only 5 managed-lane TMCs have TTI ≥ 1.05.

![GP versus managed lane](../nvta/c6-managed-lane-comparison/figures/nvta_c6_gp_vs_managed_lane.png)

## What this does and does not show

- **Sign and size are sensible.** In every open corridor-period the managed
  lane has lower mean time, lower planning time, and a buffer near zero.
- **A single PTI–TTI curve does not transfer across lane types.** The managed
  lane sits at the free-flow limit, where the memo's derivation gives
  $\gamma_p\to1$; GP sits on a curve with $k\approx3$.
- **Not a project benefit.** The savings are what a traveler already in the
  managed lane avoids today. The memo's build-versus-no-build test of an
  express-lane extension needs a model run, and user-level valuation (toll,
  eligibility, lane choice, option value) is out of scope.
- GP and managed-lane daily times are positively correlated
  (Pearson 0.26–0.64), so bad GP days are partly bad managed-lane days;
  route-level reliability must carry that covariance.
