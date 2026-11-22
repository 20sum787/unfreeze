# Mounting orientation for the v4 movement model

## Position and units

Two public raw recordings from Edge Impulse project 1170229 were multiplied by 1,000 and matched row by row to Daphnet. Both matches were in columns 8–10, counting time as column 1. Those channels represent forward, vertical and lateral trunk acceleration, in mg. The two Studio recordings express them in g. The study's trunk sensor was worn on the lower-back belt. This supports a lower-back Movement module and a separate thigh actuator.

| Studio sample | Daphnet file | Original rows (one-based) | Time range (ms) | Matching samples |
|---|---|---|---|---|
| freeze, 3233555685 | S05R01.txt | 64325–64752 | 1005078–1011750 | 428/428 |
| normal, 3233556955 | S08R01.txt | 113249–113440 | 1769515–1772500 | 192/192 |

Original activity codes were 2 (freezing) and 1 (nonfreezing during the experiment). Source matching covered these two recordings. The rest of the training set would require its own verification.

## What a calibration could establish

A stationary accelerometer gives a vertical reference. It leaves rotation around that axis ambiguous. A gyroscope tracks subsequent rotations but cannot reconstruct an unknown initial forward direction from a stationary start. One possible calibration uses gravity while upright and during a known forward lean. Average each stationary pose, project the second vector onto the horizontal plane of the first and derive an orthogonal basis. Apply that fixed rotation to subsequent samples. Preserve gravity and actual trunk pitch in the classifier input.

A secure lower-back mounting and repeated forward leans with consistent direction are prerequisites. A sideways lean, loose strap or disagreement across repeats warrants a new calibration. Moving the sensor to the thigh changes the underlying acceleration. Rotation alone cannot correct a change of body site. The submitted classifier uses explicit axis order and signs in motion.json; the two-pose method is an experiment.

## Calibration, noise and validation

An orthogonal rotation preserves vector length and noise energy. Averaging stationary samples reduces uncertainty in the calibration estimate. First check sequence gaps, saturation, strap movement and motor interference. Any filtering change needs independent labeled comparisons of false alarms and missed episodes. A shin study in 11 people reported 3–8 Hz activity during some freezes. Smoothing away everything above 3 Hz could discard useful information. An optimal cutoff for the lower-back model has not been established.

## Model replay

The v4 AArch64 EIM ran under Cortex-A53 emulation. The first 128 observations of each reference recording were replayed under all 24 proper axis-aligned rotations, including the identity and excluding mirrors.

| Window | Original freeze score | Orientations reaching 0.75 |
|---|---|---|
| Labeled freeze | 0.973963 | 5/24 |
| Labeled normal | 0.000111 | 0/24 |

Changing the freeze window from forward/vertical/lateral to forward/lateral/negative vertical gave 0.002490. The 0.75 threshold describes this historical experiment. Live risk cueing uses 0.70. Two windows cannot estimate event-level recall.

For the two-pose numerical test, 40 rotations each generated noiseless upright and 25-degree forward-lean gravity vectors. The estimated rotations recovered the reference freeze scores for 80 window replays under known sign conventions. In a bench study, fix two modules side by side, measure same-orientation error, and then rotate and recalibrate one. Compare time-aligned waveforms and scores during forward lean, left/right tilt and walking. Repeat on a belt to quantify slippage, placement and repeated fitting.

## References

- [UCI Daphnet data and columns](https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait)
- [Original mounting study, section 3.1](https://eudl.eu/pdf/10.4108/ICST.BODYNETS2009.5852)
- [Freeze raw recording](https://studio.edgeimpulse.com/v1/api/1170229/raw-data/3233555685/raw)
- [Normal raw recording](https://studio.edgeimpulse.com/v1/api/1170229/raw-data/3233556955/raw)
- [Modulino Movement specifications](https://docs.arduino.cc/tutorials/modulino-movement/how-movement/)
- [Trunk posture with randomly oriented sensors](https://pmc.ncbi.nlm.nih.gov/articles/PMC9573549/)
- [Studio input configuration](https://studio.edgeimpulse.com/public/1170229/live/impulse/1/create-impulse)
- [Functional calibration and sensor location](https://pmc.ncbi.nlm.nih.gov/articles/PMC13250779/)
- [Original freezing spectrum study](https://pubmed.ncbi.nlm.nih.gov/17928063/)
