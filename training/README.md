# Training assets and experiments

Model training and export took place in Edge Impulse Studio. The repository contains deployable model binaries, fixed replay inputs, the original camera preparation scripts and the movement orientation experiments. The original video recordings and Studio accounts are external inputs.

## Camera

`camera/` contains the frame sampling, contact sheets, manual selections and per-recording dataset packagers. The original workflow used Windows, FFmpeg on PATH, Python, Pillow and NumPy. Set `UNFREEZE_VIDEO` to the local recording before sampling. Example from the repository root:

```powershell
$env:UNFREEZE_VIDEO = 'D:\recordings\doorway.mp4'
python training/camera/sample_video.py --help
python training/camera/sample_video.py coarse --step 2 --end 20
```

The selection lists and timestamps belong to the team recordings. Review and annotate new recordings separately before training. The packaging scripts expect the associated frame directories and write beneath `outputs/`. To replace a deployed model, follow the [board manual](../board/unfreeze-uno-q/README.md).

## Movement

The [orientation study](../docs/IMU-orientation-feasibility.md) reports how the same two labeled windows scored after rotation. On AArch64 Linux with Python and NumPy, run the following from the repository root:

```sh
python training/movement/orientation_test.py board/unfreeze-uno-q/models/movement.eim
python training/movement/two_pose_validation.py board/unfreeze-uno-q/models/movement.eim
```

The two-pose calculation is a numerical experiment. Production-path axis mappings are defined in [motion.json](../board/unfreeze-uno-q/python/motion.json).
