# QVDF Reliability Evidence for NVTA: I-95

This branch tests the QVDF reliability chain on Northern Virginia data. The
PeMS prototype is on
[`main`](https://github.com/jacky850/i405-qvdf-reliability-experiments).

In the chain under test, one stochastic loading ratio $`X`$ with
$`\ln X\sim N(\mu_X,\sigma_X^2)`$ drives both QVDF branches:

```math
P=f_dX^n\ \ [\mathrm{h}],\qquad T=T_0\left(1+\alpha X^\beta\right)\ \ [\mathrm{min/trip}].
```

Congestion duration $`P`$, mean travel time $`E[T]`$ and planning time $`T_{95}`$
are therefore different quantities driven by one mechanism. With
$`\mathrm{TTI}=E[T]/T_0`$ and $`\mathrm{PTI}_{95}=T_{95}/T_0`$,

```math
\mathrm{PTI}_{95}=1+\alpha e^{\beta\mu_X+1.645\,\beta\sigma_X},\qquad
\gamma_{95}=\frac{\mathrm{PTI}_{95}}{\mathrm{TTI}}.
```

## Data

- **RITIS/INRIX TMC export**: 5-minute speed, reference speed and travel
  time for 23 weekdays in October 2025.
- **NVTA CBI calibration package**: per-TMC QVDF parameters
  $`(f_d,n,\alpha,\beta)`$, and the accepted daily congestion episodes with
  $`P`$ and loading. All QVDF parameters used here are read from this package;
  none are re-estimated.
- **Cube 2025 AM network**: lanes, capacity, and period closure codes
  (`AMLIMIT`, `PMLIMIT`).

The RITIS data are licensed and are not redistributed.

**Loading measures.** Neither source has vehicle counts, so flow $`q(t)`$ is
reconstructed from RITIS speed with the inverse S3 speed–flow model. Two
loading measures are used:

- **A1 and A2** use the capacity-equivalent congested-flow duration
  $`X_E=\int_Eq(t)\,dt\,/\,C`$, where $`E`$ is the congestion episode and $`C`$ is
  hourly capacity (veh/h). $`X_E`$ is in hours, so $`f_d`$ has units
  $`\mathrm{h}^{1-n}`$.
- **B and C1–C5** use the CBI package's episode loading
  $`x=X_E/4\,\mathrm{h}`$: vehicles per lane over the episode divided by
  2,000 veh/h/lane × 4 h of PM capacity. For example, 4,193 veh/lane in a
  2.5-hour episode gives $`X_E=2.10`$ h and $`x=0.52`$.

Both measures accumulate flow over the same episode that defines $`P`$, and
both exist only on days with an accepted congestion episode. Neither is the
peak-hour $`D/C`$ of a planning model.

## Experiments

| ID | Question | Corridor, period | Sample |
|---|---|---|---|
| A1 | Does the threshold near $`v_c`$ change $`f_d`$, $`n`$? | I-95 NB GP, AM | 20 TMCs, 275 TMC-days |
| A2 | How much does the cutoff $`0.50v_f\to0.25v_f`$ change B1? | I-95 NB GP, AM | 20 TMCs, 460 TMC-days |
| B | What is the day-to-day distribution of $`x`$? | 6 GP corridor-periods on I-95 and I-395 | 67 TMC-periods with ≥ 8 episode-days, 936 TMC-days |
| C1–C2 | Do $`x`$, $`P`$, TTI and $`\mathrm{PTI}_{95}`$ move together? | I-95 SB GP, PM | 10 TMCs, 133 TMC-days |
| C3 | Does stochastic $`x`$ reproduce observed TTI and $`\mathrm{PTI}_{95}`$? | same | same |
| C4 | How much travel-time variability does $`x`$ explain? | same | same |
| C5 | Does the SHRP2 PTI–TTI relation hold? | same | same |
| C6 | Can managed-lane reliability credit be derived from its own loading and QVDF? | I-95 and I-395 express lanes, open direction | 4 corridor-periods, 23 weekdays |
| D | What does congestion duration measure at nested cutoffs of 0.75, 0.50 and 0.25 $`v_f`$? | I-95 NB GP, AM; I-95 SB GP, PM | 552 and 529 TMC-days |
| E | Where and when are mean and 95th-percentile travel times high? | same | 24 and 23 TMCs, 23 weekdays |

A TMC-day is one TMC on one weekday. I-95 SB has 24 GP TMCs (23.0 mi).
C1–C5 use the 10 TMCs (10.2 mi) whose own QVDF parameters pass the CBI
quality screen and that have at least 3 accepted PM congestion episodes. Of
the 230 possible TMC-days (10 TMCs × 23 weekdays), 133 have an accepted PM
congestion episode; these form the C1–C5 sample. All C1–C5 results are
conditional on these congestion days.

## A1. Threshold sensitivity near the speed at capacity

RITIS speed on I-95 NB, weekdays 05:00–10:00, 15-minute bins. For each TMC,
$`v_f`$ is the weekday off-peak (21:00–05:00) speed P85, $`v_c=v_f/\sqrt2`$, and
$`C`$ is the Cube AM link capacity. Episodes are detected at thresholds
$`a\,v_c`$ with $`a`$ from 0.90 to 1.10. At each threshold, $`P`$ and $`X_E`$ are
recomputed and $`P=f_dX_E^{\,n}`$ is refitted on the same 275 TMC-days.

![A1](figures/nvta_a_v2_threshold_parameter_sensitivity.png)

| Threshold / $`v_c`$ | Median $`P`$ (h) | Median $`X_E`$ (h) | $`f_d`$ ($`\mathrm{h}^{1-n}`$) | $`n`$ | $`R^2`$ |
|---:|---:|---:|---:|---:|---:|
| 0.90 | 2.08 | 1.76 | 1.223 | 0.943 | 0.948 |
| 0.95 | 2.30 | 1.96 | 1.228 | 0.928 | 0.948 |
| 1.00 | 2.50 | 2.13 | 1.165 | 0.972 | 0.959 |
| 1.05 | 2.72 | 2.35 | 1.163 | 0.972 | 0.955 |
| 1.10 | 2.97 | 2.61 | 1.151 | 0.979 | 0.966 |

$`P`$ and $`X_E`$ both grow with the threshold. Relative to $`1.00v_c`$, $`f_d`$
changes by at most 5.4% and $`n`$ by at most 4.5%. The duration structure is
stable near $`v_c`$. $`P`$ and $`X_E`$ share the episode, so this is an
internal-consistency check, not independent validation. A fit on the
dimensionless peak-hour basis $`D^{60}/C`$ (A3) was run on PeMS data and is
reported on `main`.

## A2. Policy cutoff: $`0.50v_f`$ vs $`0.25v_f`$

Same data and episode rule as A1. A qualifying TMC-day is one on which the
TMC's AM speed stays below the cutoff $`r\,v_f`$, $`r\in\{0.50,0.25\}`$, for at
least 0.5 hours. The daily B1 measure sums congestion duration × TMC length
over TMCs, $`\sum_sP_{s,d}L_s`$, in link-mile-hours. For example, a 1.2-mile
TMC congested for 2 hours contributes 2.4 link-mile-hours.

| Facility | Cutoff | Qualifying TMC-days | Mean daily link-mile-hours |
|---|---:|---:|---:|
| GP | $`0.50v_f`$ | 201 of 460 | 13.63 |
| GP | $`0.25v_f`$ | 43 of 460 | 1.54 |

Moving to $`0.25v_f`$ removes 88.7% of congested link-mile-hours and 79% of
qualifying TMC-days. The duration fit is stable near $`v_c`$ (A1), while the
B1 total changes substantially with the policy cutoff. D examines the
cutoffs as nested layers of the same speed profile.

## B. Day-to-day distribution of the loading

Every GP TMC with at least 8 accepted episode-days in six corridor-periods
is used. For each TMC, the across-day mean $`\mu`$ and standard deviation
$`\sigma`$ of $`\ln x`$ are computed. Normality is checked with Q-Q plots, and
AICc compares a constant $`\sigma`$ with $`\sigma`$ linear in mean $`x`$.

![B distribution](nvta/b-dc-variability/figures/nvta_b_dc_distribution.png)

*(a) Each of the 936 TMC-days, with $`\ln x`$ standardized within its TMC,
against the standard normal curve. (b) Each small panel is one of the 10
C1–C5 TMCs; the step line is the cumulative share of its congestion days
(one step per day), with the fitted lognormal and normal curves.*

![B Q-Q and sigma](nvta/b-dc-variability/figures/nvta_b_dc_lognormal_sigma.png)

*(a) Each point is one TMC-day, standardized within its TMC; orange tests
whether $`x`$ is normal, blue tests whether $`\ln x`$ is normal ($`x`$
lognormal). (b) Each point is one TMC: its mean loading across congestion
days versus the day-to-day $`\sigma`$ of $`\ln x`$.*

| Corridor-period | TMCs | TMC-days | Median $`\sigma_{\ln x}`$ |
|---|---:|---:|---:|
| I-95 SB PM | 16 | 213 | 0.24 |
| I-95 NB AM | 10 | 155 | 0.26 |
| I-95 NB PM | 9 | 97 | 0.55 |
| I-395 NB AM | 12 | 173 | 0.20 |
| I-395 NB PM | 9 | 122 | 0.21 |
| I-395 SB PM | 11 | 176 | 0.19 |

The daily loading has a smooth, single-peaked distribution. A lognormal $`x`$
is not rejected, but a normal $`x`$ fits equally well: the pooled Q-Q $`R^2`$ is
0.984 for $`\ln x`$ and 0.997 for $`x`$, $`\ln x`$ is left-skewed on 75% of TMCs,
and on each of the 10 C1–C5 TMCs the two fitted curves nearly coincide. With
$`\sigma\approx0.25`$ the two shapes differ little. $`\sigma`$ shows no trend
with mean loading (the constant model is selected), but it varies between
TMCs from 0.09 to 0.66 (interquartile range 0.20–0.31). These statistics
cover congestion days only.

## C1–C2. Do the quantities move together?

C1 correlates $`x`$, $`P`$, and the day's 15:00–19:00 TTI from RITIS travel time
across the 133 TMC-days; each point in the figure is one TMC-day. C2
aggregates each of the 10 TMCs over its congestion days. Intervals come from
2,000 bootstrap resamples.

![C1](key_results/fig_c1_dc_p_tti.png)

| Level | Pair | n | Pearson | Spearman (95% CI) |
|---|---|---:|---:|---:|
| C1 | $`x`$ vs $`P`$ | 133 TMC-days | 0.98 | 0.98 (0.97–0.99) |
| C1 | $`x`$ vs TTI | 133 TMC-days | 0.76 | 0.81 (0.72–0.88) |
| C1 | $`P`$ vs TTI | 133 TMC-days | 0.82 | 0.89 (0.81–0.94) |
| C2 | $`E[P]`$ vs TTI | 10 TMCs | 0.92 | 0.87 (0.41–1.00) |
| C2 | $`P_{95}`$ vs $`\mathrm{PTI}_{95}`$ | 10 TMCs | 0.81 | 0.90 (0.59–1.00) |
| C2 | TTI vs $`\mathrm{PTI}_{95}`$ | 10 TMCs | 0.94 | 0.93 (0.65–1.00) |

All pairs are positive and strong, and rankings agree at both levels. The
0.98 for $`x`$ vs $`P`$ is largely mechanical, because both come from the same
episode and the same RITIS speeds. The pairs involving TTI and
$`\mathrm{PTI}_{95}`$ use RITIS travel time. The C2 intervals are wide
because there are only 10 TMCs.

## C3. Observed vs QVDF-implied reliability

For each of the 10 TMCs, two values of each metric are computed:

- **Model**: $`\mu_x`$ and $`\sigma_x`$ come from the TMC's accepted
  episode-days, and the TMC's $`(\alpha,\beta)`$ are read from the CBI package
  (not re-estimated here). The lognormal formulas give model TTI,
  $`\mathrm{PTI}_{95}`$ and $`\gamma_{95}`$.
- **Observed**: from the TMC's daily PM TTI (RITIS travel time), TTI is the
  mean over days, $`\mathrm{PTI}_{95}`$ the 95th percentile, and $`\gamma_{95}`$
  their ratio.

Each metric therefore has 10 (observed, model) pairs, one per TMC. The table
compares these pairs. Pearson $`r`$ measures linear agreement between the
observed and model values. Spearman $`\rho`$ measures whether the model ranks
the 10 TMCs in the same order as the observations. MAE is the mean of
$`|\text{model}-\text{observed}|`$, and bias is the mean of
$`\text{model}-\text{observed}`$.

| Metric (observed vs model, 10 TMCs) | Pearson $`r`$ | Spearman $`\rho`$ | MAE | Bias |
|---|---:|---:|---:|---:|
| TTI | 0.96 | 0.94 | 0.86 | −0.86 |
| $`\mathrm{PTI}_{95}`$ | 0.86 | 0.78 | 1.23 | −1.23 |
| $`\gamma_{95}`$ | 0.47 | 0.44 | 0.14 | −0.10 |

TMCs that are less reliable in the observations are also less reliable in the
model: the rank agreement is 0.94 for TTI and 0.78 for $`\mathrm{PTI}_{95}`$.
However, the model value is lower than the observed value on all 10 TMCs, by
0.86 for TTI and 1.23 for $`\mathrm{PTI}_{95}`$ on average. For $`\gamma_{95}`$
the rank agreement is weak (0.44). The variation in $`x`$ alone does not produce
enough travel-time spread.

## C4. How much variability does the loading explain?

The daily log delay is split as
$`\ln(\mathrm{TTI}-1)=\ln\alpha+\beta\ln x+\varepsilon`$. For each TMC,
$`\beta^2\sigma_x^2`$ is the loading-driven variance and $`\tau^2`$ is the
variance of the residual $`\varepsilon`$. $`\tau`$ is estimated leave-one-TMC-out:
each TMC's $`\tau`$ comes only from the other nine TMCs, so no TMC corrects
itself. Adding $`\tau`$ while keeping the mean delay unchanged gives

```math
\mathrm{PTI}_{95}=1+\alpha\exp\left(\beta\mu_x-\tfrac12\tau^2+1.645\sqrt{\beta^2\sigma_x^2+\tau^2}\right).
```

![C4](nvta/c4-variability-decomposition/figures/nvta_c4_variability_decomposition.png)

| Model $`\mathrm{PTI}_{95}`$ | Pearson | Spearman | MAE | Bias |
|---|---:|---:|---:|---:|
| Loading variability only (C3) | 0.86 | 0.78 | 1.23 | −1.23 |
| Loading variability + $`\tau`$ | 0.95 | 0.84 | 0.82 | −0.82 |

On the median TMC, day-to-day loading accounts for 29.1% of log-delay
variance and 70.9% is residual. The residual may include incidents, weather,
work zones and measurement error; the data do not identify the individual
causes. The loading share ranges from 0.4% to 80.5% across TMCs. Adding
$`\tau`$ cuts the $`\mathrm{PTI}_{95}`$ error by a third and improves the
ranking, but the model value remains below the observed value.

## C5. PTI–TTI relationship vs SHRP2

$`\mathrm{PTI}_{95}=1+k\ln\mathrm{TTI}`$ is fitted to the 10 TMCs and compared
with the SHRP2 L03 value $`k=3.67`$. The local $`k`$ is scored
leave-one-TMC-out: each TMC is predicted with the $`k`$ fitted to the other
nine.

![C5](nvta/c5-pti-tti-comparison/figures/nvta_c5_pti_tti_shrp2_comparison.png)

TTI and $`\mathrm{PTI}_{95}`$ are strongly related (Spearman 0.93), so the
functional form works. The local fit gives $`k=2.69`$ (95% CI 2.49–2.92),
which excludes 3.67. SHRP2 overpredicts all 10 TMCs (MAE 0.94, bias +0.94),
while the local $`k`$ gives MAE 0.28, 71% lower. Over 81 GP TMCs in four
corridor-periods (C6 sample, all weekdays), $`k=2.97`$ (2.83–3.10), also below
3.67.

## C6. Managed-lane reliability credit — not feasible with current data

**Intended.** Derive managed-lane TTI and PTI95 from the lane's own loading
distribution and QVDF, as in C3, then compute a project's planning-time saving
$`\Delta T_{95}=T_{95}^{\mathrm{NoBuild}}-T_{95}^{\mathrm{Build}}`$.

**Why it cannot be done.**

1. *No loading distribution.* The I-95 and I-395 express lanes are reversible
   (northbound AM, southbound PM). In the open direction they almost never
   congest: accepted episode TMC-days are 0 of 460 on I-95 SB PM, 1 of 460 on
   I-95 NB AM, 0 of 506 on I-395 SB PM and 9 of 506 on I-395 NB AM. Without
   episodes, $`x`$ and $`\sigma_x`$ are undefined.
2. *No QVDF parameters.* For the same reason, no managed-lane
   $`(f_d,n,\alpha,\beta)`$ can be calibrated in the open direction. The
   existing CBI managed-lane fits come from closed-direction records (RITIS
   still reports about 0.70 of reference speed while a lane is closed) and are
   rejected.
3. *No Build scenario.* A project saving needs Build and No-Build loadings
   from a model run, which is not available.

**Substitute.** Observed travel times on matched GP and managed-lane sections,
open direction, 23 weekdays:

| Corridor-period | Section (mi) | TTI GP / ML | PTI95 GP / ML | GP − ML planning time (min/trip) |
|---|---:|---:|---:|---:|
| I-95 SB PM | 23.6 | 2.12 / 1.01 | 2.55 / 1.01 | 36.2 |
| I-95 NB AM | 23.6 | 1.53 / 1.01 | 2.02 / 1.09 | 23.2 |
| I-395 SB PM | 9.6 | 1.85 / 0.98 | 2.38 / 0.99 | 14.2 |
| I-395 NB AM | 9.5 | 1.79 / 1.02 | 2.21 / 1.10 | 12.0 |

The open managed lane runs at free flow. This is the observed GP–managed-lane
difference for current users. It is not a QVDF-derived managed-lane
reliability, not a Build-versus-No-Build benefit, and not a causal credit.

## D. Congestion duration at nested cutoffs

The NVTA cutoffs are treated as layers of one speed profile. For each GP
TMC-day, $`P_r`$ is the total time with speed (centered 3-bin median of the
5-minute RITIS speed) below $`r\,v_f`$, $`r\in\{0.75,0.50,0.25\}`$, where $`v_f`$
is the TMC's weekday off-peak speed P85. Windows are 05:00–10:00 on I-95 NB
and 12:00–21:00 on I-95 SB. Because $`P_r`$ is total time rather than the
longest episode used in A2, the layers are nested on every TMC-day:
$`P_{0.25}\le P_{0.50}\le P_{0.75}`$. D uses all 24 (NB) and 23 (SB) mainline
GP TMCs of the CBI corridors, so its counts differ from A2.

![D I-95 NB AM](nvta/d-duration-layers/figures/nvta_d_layers_i95_nb_am.png)

![D I-95 SB PM](nvta/d-duration-layers/figures/nvta_d_layers_i95_sb_pm.png)

*(a) Cumulative share of TMC-days at or below each duration; the height at
$`P=0`$ is the share of TMC-days with no congestion at that cutoff.
(b), (c) Each point is one TMC-day; points lie on or below the diagonal
because the narrower layer is contained in the broader one.*

| Corridor-period | TMC-days | TMC-days with $`P>0`$ at 0.75 / 0.50 / 0.25 $`v_f`$ | Spearman $`P_{0.25}`$ vs $`P_{0.50}`$ | Spearman $`P_{0.50}`$ vs $`P_{0.75}`$ |
|---|---:|---:|---:|---:|
| I-95 NB AM | 552 | 66% / 51% / 18% | 0.55 | 0.86 |
| I-95 SB PM | 529 | 84% / 70% / 34% | 0.81 | 0.83 |

$`P_{0.50}`$ and $`P_{0.75}`$ are closely related on both corridors. $`P_{0.25}`$
is zero on 82% (NB) and 66% (SB) of TMC-days, so it varies on a minority of
days. It is not a scaled copy of $`P_{0.50}`$: among TMC-days with
$`P_{0.50}>0`$, only 35% (NB) and 48% (SB) also have $`P_{0.25}>0`$, and on
I-95 NB the two layers are only moderately correlated. On both corridors,
$`P_{0.50}`$ is the layer most closely associated with the day's TTI
(Spearman 0.91 NB, 0.95 SB). About 4% of I-95 SB TMC-days are congested for
the whole 9-hour window.

## E. Time-space view of mean and 95th-percentile travel time

For every GP TMC and 5-minute time of day, the 23 weekday travel times give
mean TTI, $`\mathrm{PTI}_{95}`$ and $`\gamma_{95}=\mathrm{PTI}_{95}/\mathrm{TTI}`$,
with $`T_0`$ from the TMC's off-peak free-flow speed. Distance runs in the
direction of travel; each cell's width is the TMC length.

![E I-95 NB AM](nvta/e-time-space/figures/nvta_e_time_space_i95_nb_am.png)

![E I-95 SB PM](nvta/e-time-space/figures/nvta_e_time_space_i95_sb_pm.png)

Mean TTI and $`\mathrm{PTI}_{95}`$ give different pictures. On I-95 NB AM, the
two bottlenecks near miles 9–11 and 15–19 have a mean TTI of about 2–3.5 but a
$`\mathrm{PTI}_{95}`$ of 4–5 or more, and near mile 21 around 08:30–09:30 the
mean shows little congestion while the 95th-percentile day is heavily
congested. On I-95 SB PM, miles 7.3–9 are congested through the whole
afternoon (mean TTI at least 1.7 from noon), with a lower $`\gamma_{95}`$ than
the upstream section at miles 3–7, where $`\gamma_{95}`$ is high between 12:00
and 14:30. With 23 days, each cell's 95th percentile is close to the second
slowest day, so individual cells can reflect a single day.

## Answers

The answers state what the current evidence shows and what it does not cover.

**1. Is one PTI–TTI relationship transferable across facility types and
geographies?**

- Within I-95 SB PM GP, $`\mathrm{PTI}_{95}=1+k\ln\mathrm{TTI}`$ fits the
  observations closely (Spearman 0.93). The estimated $`k`$ is 2.69 (10 TMCs)
  and 2.97 (81 GP TMCs in four Northern Virginia corridor-periods); SHRP2's
  3.67 lies outside both intervals (C5).
- Open managed lanes have $`\gamma_{95}\approx1.0`$, compared with 1.2–1.3 on
  the parallel GP lanes, so GP and managed lanes do not share the same
  relationship in these data (C6).
- Not covered: other geographies (all data are from Northern Virginia) and
  facility classes other than freeway GP and managed lanes.

**2. Should B1 count planning-time savings instead of congested duration?**

- Congested duration and planning time rank TMCs similarly ($`P_{95}`$ vs
  $`\mathrm{PTI}_{95}`$, Spearman 0.90) (C2).
- The duration-based B1 total changes by 88.7% between the $`0.50v_f`$ and
  $`0.25v_f`$ cutoffs (A2). $`P_{0.50}`$ and $`P_{0.75}`$ carry similar
  information; $`P_{0.25}`$ is zero on 66–82% of TMC-days and is not a scaled
  copy of $`P_{0.50}`$ (D).
- Locations with similar mean TTI can have very different
  $`\mathrm{PTI}_{95}`$ (E). Day-to-day loading accounts for a median 29% of
  travel-time variability, and QVDF-implied $`\mathrm{PTI}_{95}`$ is below
  observed by 1.23 on average, and by 0.82 after a residual term is added
  (C3, C4).
- Not covered: no NVTA project scenario was scored under either measure.
  Summed link planning time is an exposure proxy, not route planning time.

**3. How should managed lanes receive reliability credit?**

- With current data, managed-lane credit cannot be derived through the QVDF
  chain: in the open direction there is no loading distribution and no
  usable managed-lane QVDF parameters (C6).
- Observed data show the open managed lanes near free flow, with 12–36
  min/trip less planning time than the parallel GP lanes for current users
  (C6).
- Not covered: a Build-versus-No-Build test of an express-lane project, and
  toll, lane-choice and user effects.

**4. Test all four options, or narrow first?**

- Covered by current evidence: threshold sensitivity near $`v_c`$ (A1); the
  effect of the NVTA speed cutoff on the duration measure (A2, D); the
  association of duration, TTI and $`\mathrm{PTI}_{95}`$ on I-95 GP (C1–C5);
  the time-space pattern of mean and 95th-percentile travel time (E); the
  observed GP–managed-lane difference (C6).
- Not covered: scoring of any project scenario, managed-lane reliability
  through the QVDF chain, and transfer across facility classes and
  geographies.

## Reproduce

The RITIS export, CBI package and Cube network are not included. Set their
locations in `config/nvta_*.json` (A1, A2) and with `NVTA_EXTERNAL_ROOT`
(B–E), then run:

```bash
python scripts/audit_nvta_i95_parameters.py
python scripts/run_nvta_experiment_a.py --config config/nvta_experiment_a_i95_nb_am_empirical.json
python scripts/run_nvta_b1_speed_cutoff.py
python nvta/c3-qvdf-reliability/run_nvta_c3.py
python nvta/b-dc-variability/run_nvta_b.py
python nvta/b-dc-variability/plot_nvta_b_distribution.py
python nvta/c4-variability-decomposition/run_nvta_c4.py
python nvta/c5-pti-tti-comparison/run_nvta_c5.py
python nvta/c6-managed-lane-comparison/run_nvta_c6.py
python nvta/d-duration-layers/run_nvta_layers.py
python nvta/e-time-space/run_nvta_time_space.py
python nvta/core_evidence.py
```
