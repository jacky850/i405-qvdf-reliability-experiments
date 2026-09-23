# NVTA Data Inventory for Reliability Analysis

## Finding

The local NVTA data contain managed-lane observations. The selected corridor mapping contains 213 TMCs: 186 GP and 27 HOV/managed-lane TMCs. The managed-lane records cover I-395 HOV and I-95 HOV in both directions. All 27 managed-lane TMCs have records for all 23 weekdays in October 2025 in the processed day-period table.

The data are sufficient to start a minimal GP-versus-managed reliability analysis. The first comparison should respect reversible-lane operations: use an operating managed-lane direction for the chosen period rather than pooling both directions.

## Primary sources

| Dataset | Grain | Coverage | Key fields | Planned use |
|---|---|---|---|---|
| `1_map_matching2026/data/raw/ritis/NOVA-Oct1-31-2025--Avg-at-5min-.csv` | TMC × 5-minute timestamp | October 1–31, 2025; approximately 1.03 GB | `tmc_code`, timestamp, speed, reference speed, travel time | Day-level travel time, TTI, PTI and Buffer Index; speed input to inverse S3. |
| `1_map_matching2026/data/raw/ritis/TMC_Identification.csv` | TMC | Regional metadata | road, direction, intersection, length, coordinates, order, type | Link length, corridor order and TMC metadata. |
| `1_map_matching2026/data/processed/cbi_metrics/ritis_tmc_day_period_speed_stats.csv` | TMC × date × AM/PM | 23 October 2025 weekdays for all 213 selected TMCs | daily mean speed, speed ratio, congestion duration, severe duration | Fast day-level screening and cross-checks. |
| `T2_Task_3/t2_vt2_analysis (2)/qvdf_projection/data/corridor_tmc_mapping.csv` | TMC | 12 selected corridor-direction groups | corridor, `facility`, orientation, model link, lanes, capacity context, free speed | Primary GP/HOV classification and TMC-to-network mapping. |
| `1_map_matching2026/data/raw/base_2025/pm/link.csv` | model link | 49,329 PM network links | lanes, per-lane capacity, whole-link capacity, allowed use, period closure code, toll, assigned volume and speed | Network capacity and period-operability audit. |
| `I405--FDQ-dashboard-github/scripts/run_nvta_corridor_dv_forward.py` | implementation | Existing local code | inverse S3 and forward summation of episode demand | Reference implementation for `speed → q(t) → D → D/C`; it uses existing QVDF parameters only as an optional duration-branch cross-check. |
| `I405--FDQ-dashboard-github/outputs/nvta_corridor_dv_forward_i395nb/corridor_dv_forward.csv` | link × period | Existing I-395 NB average-weekday run; 23 links | S3-reconstructed demand, episode demand, capacity and D/C | Existing numerical evidence that the forward D/C calculation already runs independently of the duration branch. |

## Managed-lane coverage

| Corridor | Managed TMCs | October weekdays | AM/PM day-period rows | PM network note |
|---|---:|---:|---:|---|
| I-395 HOV NB | 9 | 23 | 414 | Five mapped TMC rows are closed in the PM network; use AM or audit the open subsection. |
| I-395 HOV SB | 3 | 23 | 138 | All three mapped rows are open in the PM network. |
| I-95 HOV NB | 14 | 23 | 644 | All fourteen mapped rows are closed in the PM network, consistent with reversible operation. |
| I-95 HOV SB | 1 | 23 | 46 | The mapped row is open in the PM network. |

The day-period table has two records per TMC-day, one for AM and one for PM. Median interval counts are 42 per TMC-day-period, with observed counts ranging from 31 to 48 in the managed-lane sample.

## Network and capacity checks

For the 213 selected TMCs, the corridor mapping references 194 unique model links. The selected network links include the fields needed to distinguish per-lane and whole-link capacity:

$$
C_{\mathrm{link}}=C_{\mathrm{lane}}\times \mathrm{lanes}.
$$

In the inspected PM network, `capacity` and `IPMHRLNCAP` agree as per-lane capacity, while `IPMHRLKCAP` equals per-lane capacity multiplied by lanes. These fields will be retained separately and checked row by row before computing whole-link demand and capacity.

The managed-lane sample has two or three lanes per mapped TMC. Period closure and `allowed_use` must be applied before comparing managed lanes with GP lanes.

## Existing inverse-S3 evidence

The previous NVTA workflow already contains the forward reconstruction requested for this project:

1. read observed speed;
2. calculate per-lane flow with inverse S3;
3. multiply by lanes to obtain whole-link flow;
4. sum \(q(t)\Delta t\) over the detected congestion episode to obtain \(D\);
5. divide by whole-link hourly capacity to obtain \(D/C\) in hours.

The existing one-week package applies this method to 12 GP and managed-lane corridors. The full October raw file and the processed 23-weekday statistics are available locally, so the next implementation can operate day by day rather than on a five-day average profile.

## Parameter handling

The inverse-S3 step uses fundamental-diagram inputs such as free-flow speed, speed at capacity, S3 shape, and capacity. It does not require QVDF duration parameters \(f_d\) or \(n\).

No new \(f_d,n\) fitting belongs in Steps 1 or 2. In Experiment A, however, every tested speed threshold must produce its own recalculated \(P_r\) and \((D/C)_r\), followed by its own fitted \((f_{d,r},n_r)\). After a threshold is selected, that chosen parameter pair is frozen for downstream reliability projection.

## Readiness and limits

Ready now:

- full October 2025 five-minute speed and travel-time observations;
- 23 weekday day-period summaries;
- explicit GP/HOV corridor labels;
- TMC length and corridor order;
- TMC-to-network mapping;
- lane counts and separate per-lane/whole-link capacity fields;
- an existing inverse-S3 implementation and prior D/C outputs.

Still requiring an explicit rule before the first analytical run:

- select the first GP/managed paired corridor and period, respecting reversible direction;
- select the fundamental-diagram parameter source for each facility class;
- declare the baseline and sensitivity speed thresholds;
- decide whether corridor reliability uses a common set of complete TMC-days or link-specific available days.

The data inventory supports starting with I-95 in its operating direction: I-95 HOV NB for AM and I-95 HOV SB for PM. Because the local PM sample has only one I-95 HOV SB TMC, I-395 may provide a stronger first PM comparison; I-95 HOV NB is the stronger managed-lane sample for AM.
