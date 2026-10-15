# Legacy point tracking scripts

The original scripts, kept unchanged **for verification only** (comparing the new `ptrack` results with the old ones).
They are not maintained and not used by the new application.

| File | Role |
|---|---|
| `Tracking_Video_ZNCC.py` | Driver: FPS conversion, ROI selection, tracking, save |
| `function_Tracking_video.py` | Functions used by the driver |
| `convertfiles.py` | Resamples a tracking CSV onto the force-data time base |
| `output.mp4_tracking.csv` | Reference output (`time, x, y` per ROI, top-left corners) |

Note: the scripts use `cv2.imshow` / `cv2.selectROIs`, which are not available in the headless OpenCV
installed for the new application.
