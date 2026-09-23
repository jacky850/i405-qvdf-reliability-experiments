# I-95 Northbound Free-Flow Speed and Capacity Audit

## Scope

This audit checks the inputs used by the NVTA I-95 northbound AM experiment before the severe-congestion threshold test. It covers 20 GP TMCs and 14 northbound HOV/managed-lane TMCs over 23 weekdays in October 2025.

The audit does not change the completed legacy-prior run. It identifies the inputs recommended for the next run.

## Free-flow speed evidence

Three link-level sources were compared with the inherited facility-level prior:

1. the constant RITIS `reference_speed` for each TMC;
2. the 85th percentile of observed weekday speed from 00:00-05:00 and 21:00-24:00;
3. the AM Cube network free-flow speed matched to each TMC.

| Facility | TMCs | Legacy prior | Median RITIS reference | Median observed off-peak P85 | Median network free speed | Network range |
|---|---:|---:|---:|---:|---:|---:|
| I-95 NB GP | 20 | 70 mph | 63 mph | 70.195 mph | 69 mph | 63-75 mph |
| I-95 HOV NB | 14 | 65 mph | 71 mph | 71.000 mph | 75 mph | 75-75 mph |

The old GP/HOV ordering is not supported. The HOV prior of 65 mph is approximately 6 mph below the median observed off-peak P85 and 10 mph below the network free-flow speed. Only 4 of 14 HOV TMCs have a legacy prior within 5 mph of their observed off-peak P85.

The GP prior of 70 mph agrees with the facility median observed off-peak P85, but one facility-wide value hides link-level differences. All 20 GP TMCs are within 5 mph of the legacy value, while only 15 of 20 are within 5 mph of the matched network free speed.

The RITIS reference speed is constant within each TMC, but for GP links its facility median is about 7 mph below the observed off-peak P85. It is retained as a reference field rather than adopted automatically as the S3 free-flow speed.

## Recommended free-flow rule

For calibration on observed RITIS speed, use the TMC-specific observed off-peak P85:

$$
v_{f,i}=Q_{0.85}\left(v_{i,t}:t\in[00{:}00,05{:}00)\cup[21{:}00,24{:}00)\right).
$$

This rule is applied identically to GP and HOV TMCs. It removes the unsupported facility-wide 70/65 split.

For transfer to the NVTA planning model, rerun the result with the matched AM Cube network free speed. The two runs have different purposes:

- observed off-peak P85: empirical calibration and GP/HOV comparison;
- network free speed: sensitivity and future-year model application.

## Capacity checks

The corridor mapping was joined to the AM Cube network. All 34 TMC rows pass the following checks exactly:

$$
C_{\mathrm{link}}=C_{\mathrm{lane}}\times N,
$$

$$
\texttt{IAMHRLKCAP}=\texttt{IAMHRLNCAP}\times\texttt{lanes}.
$$

The mapping fields `net_lanes` and `net_capacity_raw` match the AM network `lanes` and `IAMHRLNCAP` fields for all 34 TMCs.

| Facility | Legacy capacity | AM network capacity | Lane range | Median whole-link capacity |
|---|---:|---:|---:|---:|
| I-95 NB GP | 2,200 veh/h/lane | 1,900-2,000 veh/h/lane | 2-4 | 7,600 veh/h/link |
| I-95 HOV NB | 1,800 veh/h/lane | 2,000 veh/h/lane | 2-3 | 6,000 veh/h/link |

The legacy capacity constants should be replaced with the matched network fields:

- per-lane capacity: `IAMHRLNCAP`;
- whole-link capacity: `IAMHRLKCAP`;
- number of lanes: `lanes`.

In the current speed-only S3 calculation, replacing capacity changes reconstructed flow and vehicle volume proportionally but does not change $D/C$ when the same capacity is used in the inversion and denominator:

$$
q_{\mathrm{link}}(t)=NC_{\mathrm{lane}}g(v/v_f,m),
$$

$$
\frac{D}{C}
=
\frac{\sum_tNC_{\mathrm{lane}}g(v/v_f,m)\Delta t}
{NC_{\mathrm{lane}}}
=
\sum_tg(v/v_f,m)\Delta t.
$$

Capacity remains necessary for reporting $q$, $D$, and whole-link constraints and for later use with independent counts or assigned volumes.

## Mapping item requiring review

TMC `110+04150` is labeled GP in the corridor mapping but maps to network link `39107`, which has the same AM-open/PM-closed reversible operation codes as the HOV facility (`AMLIMIT=4`, `PMLIMIT=9`). Its allowed-use field includes SOV and HOV classes. This row should be reviewed before a final GP-versus-managed comparison. It is not silently reclassified in this audit.

## Decision for the next experiment

The next I-95 AM threshold run should use:

- TMC-specific observed off-peak P85 as the primary $v_f$;
- matched `IAMHRLNCAP`, `IAMHRLKCAP`, and lane count from the AM network;
- a second run using network free-flow speed to measure model-transfer sensitivity;
- separate GP and HOV reporting;
- an explicit review or exclusion decision for TMC `110+04150`.
