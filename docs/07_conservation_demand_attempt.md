# A3: Peak-Hour D/C Basis and Flow Conservation (PeMS)

[Back to the summary README](../README.md)

## Question

Experiment A's regressor integrates the link's own throughput over the
congestion episode, so $P$ and $X_E$ share their endpoints (memo Section 5).
This attempt asked whether an *arrival* demand built from flow conservation
(upstream mainline, plus on-ramps, minus off-ramps, plus storage change)
gives an independent loading measure that still predicts duration.

## Runs

| Run | Sample | Demand bases tested | Result at $1.00v_c$ |
|---|---|---|---|
| A3 | PeMS I-405 S AM, 15 weekdays, 45 link-days; complete ramp closure on 2 of 3 links | throughput; upstream; upstream + on; upstream + on − off | $R^2$ from −0.33 to −0.21; Spearman from −0.53 to −0.24 |
| A4 | PeMS I-5 N PM, 15 weekdays, 45 segment-days | throughput; upstream; upstream + on − off; throughput + storage | $R^2$ from −1.55 to −0.45; Spearman from −0.74 to −0.36; $n$ at the lower bound in every fit |
| A5 | PeMS I-5 N PM, remote upstream control volumes, 38 observations | downstream throughput; remote upstream + on − off | $R^2$ −0.10 and −0.07; Spearman −0.41 and −0.11 |

## Why it failed

- During a queue the bottleneck discharges at capacity, so higher arrival
  demand lengthens the queue without raising measured throughput. Measured
  daily loading is therefore nearly flat or *negatively* related to duration.
- Upstream detectors sit inside the queue on long-duration days, so they
  measure the same capped discharge, not arrivals. Moving the control volume
  further upstream (A5) weakened the negative sign but did not reverse it.
- Ramp detector gaps left one of three I-405 links without closure.

## Conclusion

Conservation-based arrivals are a diagnostic, not a validated demand
measure, on these samples. The dimensionless loading ratio used in the
reliability chain should come from the planning model (memo A3: maximum
rolling 60-minute demand over fixed capacity), not from detector throughput.

Outputs: `results/a3_conservation_*`, `results/a4_i5n_pm_*`,
`results/a5_i5n_pm_remote_*`; figures `figures/a3_*`, `figures/a4_*`,
`figures/a5_*`.
