# NVTA Reliability Metric Definition Lock

## Scope

This note freezes the definitions for the first NVTA reliability implementation. The analysis unit is one TMC or matched network link on one weekday and one analysis period. General-purpose (GP) and managed-lane facilities remain separate throughout the analysis.

## Observed travel time and reliability metrics

For link \(i\), day \(d\), and time bin \(t\):

$$
TT_{i,d,t}=\frac{L_i}{v_{i,d,t}}\times 60 \quad [\mathrm{min}],
$$

where \(L_i\) is link length in miles and \(v_{i,d,t}\) is the observed INRIX/RITIS speed in mph. Corridor travel time is the sum of ordered link travel times.

Let \(T_0\) denote the free-flow corridor travel time. Across weekdays:

$$
TTI=\frac{\mathbb{E}[T]}{T_0},
\qquad
PTI_{95}=\frac{T_{95}}{T_0},
\qquad
BI=\frac{T_{95}-\mathbb{E}[T]}{\mathbb{E}[T]}=\frac{PTI_{95}-TTI}{TTI}.
$$

`TTI_50`, `TTI_80`, `TTI_90`, and `TTI_95` may also be reported as percentile envelopes, but `TTI` without a percentile means the weekday mean travel time divided by free-flow travel time.

## Congestion duration

For a tested speed threshold \(v_{\mathrm{cut}}\), an observed congestion episode is a contiguous interval in which the smoothed speed remains below the threshold after applying the declared persistence rule. Its duration is

$$
P_{i,d}=t_{3,i,d}-t_{0,i,d} \quad [\mathrm{h}].
$$

The threshold is an experimental setting. The baseline and sensitivity thresholds must be recorded in every result; they are not part of the definition of \(D/C\).

## S3-derived flow and D/C

When observed flow is unavailable, flow is reconstructed from observed speed with the existing inverse S3 fundamental diagram:

$$
v=\frac{v_f}{\left[1+(k/k_c)^m\right]^{2/m}},
$$

$$
k(v)=k_c\left[\left(\frac{v_f}{v}\right)^{m/2}-1\right]^{1/m},
\qquad
q_{\mathrm{lane}}(v)=k(v)v.
$$

The whole-link flow is

$$
q_{\mathrm{link}}(t)=q_{\mathrm{lane}}(t)N_i \quad [\mathrm{veh/h/link}],
$$

where \(N_i\) is the number of lanes. The episode demand volume and whole-link capacity are

$$
D_{i,d}=\sum_{t\in\mathcal{E}_{i,d}}q_{\mathrm{link}}(t)\Delta t \quad [\mathrm{veh/link}],
$$

$$
C_i=c_{\mathrm{lane},i}N_i \quad [\mathrm{veh/h/link}].
$$

Therefore,

$$
\left(\frac{D}{C}\right)_{i,d}=\frac{D_{i,d}}{C_i} \quad [\mathrm{h}].
$$

This is capacity-equivalent congestion duration in hours. It is not the dimensionless peak-hour \(V/C\) used in conventional assignment summaries. Multiplying both reconstructed demand and capacity by the same lane count leaves \(D/C\) unchanged, but the stored \(D\) and \(C\) values must still be whole-link quantities.

## Role of QVDF parameters

The QVDF duration branch is

$$
\widehat{P}=f_d\left(\frac{D}{C}\right)^n.
$$

The inverse-S3 calculation above produces \(q(t)\), \(D\), and \(D/C\) without using \(f_d\) or \(n\). Steps 1 and 2 do not fit \(f_d\) or \(n\).

The parameters have two distinct later uses:

1. **Threshold sensitivity (Experiment A):** for every tested threshold \(r\), recompute \(P_r\) and \((D/C)_r\), then estimate a separate pair \((f_{d,r},n_r)\) from

   $$
   P_r=f_{d,r}\left(\frac{D}{C}\right)_r^{n_r}.
   $$

   The change in \(f_{d,r}\) and \(n_r\) across thresholds is the sensitivity result.
2. **Reliability projection after calibration:** once a threshold and parameter source are selected, hold that chosen parameter set fixed when producing the downstream reliability envelope or comparing facilities. This prevents the evaluation data from silently recalibrating the model.

Thus, \(f_d,n\) are not inputs to the S3 flow inversion, but they are estimated separately at each threshold when the purpose is Experiment A.

## Facility classification

The primary observed-data classification is the corridor mapping field `facility` with values `GP` and `HOV`. Network fields such as `allowed_use`, `PMLIMIT`, toll, and link type are used as operational checks. The TMC `type` field alone is not a reliable managed-lane classifier for this selected sample.

For reversible facilities, a GP-versus-managed comparison must use the direction that is open during the selected period. Closed network links are excluded from a period comparison even when an observed TMC speed record exists.

## Provenance rule

S3-derived flow is reconstructed from speed and is not an independent traffic count. Results using it test internal consistency and support a D/C-based reliability pipeline; they do not constitute independent flow validation.
