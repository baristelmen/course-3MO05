# How point tracking works — guide for students

This guide explains what the application does with your video, which assumptions it makes,
which settings it uses, and how to get reliable results. Read it before your first analysis.

**Contents**
1. [The workflow in one page](#1-the-workflow-in-one-page)
2. [The project folder and the results file](#2-the-project-folder-and-the-results-file)
3. [Step 2 — converting the video to a target FPS](#3-step-2--converting-the-video-to-a-target-fps)
4. [Step 5 — how a box is tracked](#4-step-5--how-a-box-is-tracked)
5. [From positions to strain](#5-from-positions-to-strain)
6. [How precise are the results?](#6-how-precise-are-the-results)
7. [Assumptions](#7-assumptions)
8. [Default settings](#8-default-settings)
9. [Practical guide: getting good results](#9-practical-guide-getting-good-results)
10. [Known limitations](#10-known-limitations)
11. [Glossary](#11-glossary)

---

## 1. The workflow in one page

The application is a simplified **DIC** (Digital Image Correlation): it follows small areas of the
specimen surface (the *boxes*) through the video and computes how the distances between them change.

| Step | What you do | What the application does |
|---|---|---|
| 0. Project | Create a project (name, location, description) — **one project per tested specimen** | Creates the project folder |
| 1. Import video | Choose the video file (any phone or camera) | Copies it into the project, reads its frame rate, size, duration, frame timing |
| 2. Process | Choose a target frame rate (whole number, default 5 FPS) | Writes a new video at exactly that frame rate, same resolution |
| 3. Define boxes | Add at least 2 boxes on marks of the specimen, adjust x, y, width, height | Checks the boxes are inside the frame and large enough |
| 4. Verify | Check the boxes and their numbers, accept or go back | — |
| 5. Track | Nothing: tracking starts automatically and runs to the last frame | Finds every box in every frame |
| 6. Results | Read the three tabs, open `results.csv` and `tracking.mp4` | **Summary**: analysis info, warnings, quality of each box, final strains · **Plots**: strain vs time, score vs frame (also saved in `images/`) · **Frames**: browse every tracked frame |

**Synchronisation with the force data is not done by the application**: you do it yourself with the
time column of `results.csv` (see §2).

---

## 2. The project folder and the results file

```
<ProjectName>/
  project.json             all parameters (paths are relative: the folder can be moved or zipped)
  raw/input.<ext>          copy of your original video
  processed/processed.mp4  video at the target frame rate (you may use it for your own processing)
  results/results.csv      the numbers
  results/tracking.mp4     processed video with the tracked boxes drawn (open it with any video player)
  images/strain_vs_time.png   strain of every pair vs time (for your report)
  images/score_vs_frame.png   score of every box vs frame, with the refresh (0.8) and lost (0.5) lines
```

### `results.csv` — one row per processed frame

| Column | Unit | Meaning |
|---|---|---|
| `processed_frame` | — | Frame number in `processed.mp4` (0 = reference frame) |
| `source_frame` | — | Number of the same image in your original video |
| `time_s` | s | Time of the frame **in the original video**, with frame 0 at 0 s — use it to synchronise with the force data |
| `roiN_cx`, `roiN_cy` | px | Centre of box N |
| `roiN_ux`, `roiN_uy` | px | Displacement of the centre of box N since frame 0 (x to the right, **y downwards**, as in all images) |
| `roiN_score` | — | Match quality of box N in this frame (1 = perfect; see §4.2) |
| `strain_i_j` | — | Engineering strain between boxes i and j (see §5) |

Positions are written with 3 decimals; this is only rounding for the file — the real precision is
about 0.04 px (§6).

### Opening `results.csv` in a spreadsheet

The file uses the international CSV format: **comma** between columns, **point** as decimal separator.
Python (`pandas.read_csv`), MATLAB and LibreOffice in English read it directly. A spreadsheet set to
French (or another language that uses decimal commas) shows everything in one column if you simply
double-click the file. Import it instead:

| Program | Steps |
|---|---|
| Excel (Windows, Microsoft 365) | *Data → From Text/CSV* → choose `results.csv` → Delimiter: **Comma** → *Transform Data* → select all columns → *Transform → Data Type → Using Locale…* → Data type *Decimal Number*, Locale **English (United States)** → *Close & Load* |
| Excel (older versions, Windows or Mac) | *Data → From Text* (Text Import Wizard) → *Delimited* → **Comma** → *Advanced…* → Decimal separator **.** and Thousands separator **,** → *Finish* |
| LibreOffice Calc | Open the file → in the import window: Separated by **Comma**, Language **English (USA)** → *OK* |

Close the file in the spreadsheet before running the tracking again (see §10).

---

## 3. Step 2 — converting the video to a target FPS

**Why convert?** Phones record at 30 or 60 FPS. A tensile test rarely needs that many images, and fewer
frames make a smaller file and a faster tracking. The resolution is never changed.

**How frames are chosen.** The application wants one frame every `1 / FPS` seconds:
target times `0, 0.2, 0.4, 0.6 s, …` for 5 FPS. For each target time it takes the original frame
whose **real timestamp** is the closest.

Real timestamps matter: phones do not record perfectly regularly. The example video `essai_2.mp4` is
announced as 29.88 FPS but some frames are 0.066 s apart instead of 0.033 s (dropped frames).
Computing the time as `frame number / FPS` would give wrong times; the application reads the time of
each frame from the file.

**Rules**
- The target FPS must be a whole number, at least 1, and not higher than the video's frame rate
  (rounded: a "30 FPS" phone video stored as 29.97 accepts 30).
- If the original video has a gap longer than one target interval (camera hiccup), the same original
  frame is used twice so that the processed video keeps a constant frame rate. You see it in
  `results.csv`: two rows with the same `source_frame` and the same `time_s`.

**Compression.** The processed video is H.264 with quality setting **CRF 18** ("visually lossless").
Compression slightly blurs fine texture; tracking precision measured on test videos:
0.030 px without compression, **0.039 px at CRF 18**, 0.048 px at CRF 23.

---

## 4. Step 5 — how a box is tracked

### 4.1 The search, frame by frame

For every box:
1. The image inside the box on frame 0 is the **template**.
2. In the next frame, the application looks for the template inside a **search window**: the box at
   its previous position, enlarged by `search_margin × box size` on each side.
   With the default `search_margin = 1.0` the window is **3 × the box** in each direction:

   | Box | Search window | Positions tried |
   |---|---|---|
   | 40 × 40 px | 120 × 120 px | 81 × 81 = 6 561 |
   | 50 × 50 px (default) | 150 × 150 px | 101 × 101 = 10 201 |

   The window depends on the **box size**, not on the video (it is only cut at the image border).
3. The template is placed at **every whole-pixel position** of the window and a similarity **score** is
   computed for each position (OpenCV `matchTemplate`).
4. The position with the **highest score** is the new position of the box.
5. The position is refined to a fraction of a pixel (§4.3).

The whole box is compared as one block: the result is the displacement of the box as a whole
(its centre), not of individual pixels.

### 4.2 The score (ZNCC)

The score is the *zero-normalised cross-correlation*:

```
score = Σ (T − mean T) × (W − mean W)  /  √( Σ (T − mean T)² × Σ (W − mean W)² )
```
`T` = template pixels, `W` = pixels of the frame under the template.

- Subtracting the means removes the overall brightness; dividing removes the contrast.
  → **Changes of lighting do not matter**, only the pattern does.
- `+1` = same pattern, `0` = unrelated, `−1` = inverted pattern.

**Small example** (one row of 3 pixels instead of a 40 × 40 box).
Template `[10, 50, 30]` → minus its mean (30) → `[−20, +20, 0]`. Search window `[20, 10, 50, 30, 40]`:

| Position | Pixels | Minus their mean | Score |
|---|---|---|---|
| 0 | 20, 10, 50 | −6.7, −16.7, +23.3 | −0.24 |
| **1** | **10, 50, 30** | **−20, +20, 0** | **+1.00** ← best |
| 2 | 50, 30, 40 | +10, −10, 0 | −1.00 |

If the whole window becomes brighter and more contrasted (`×2 + 40` → `[80, 60, 140, 100, 120]`),
the scores are exactly the same.

**Reading the score in your results**
- Close to 1 (typically 0.95–1.0): the box is found reliably.
- Decreasing slowly: the surface inside the box changes (large strain, necking, reflections).
- Below **0.5**: the box is considered **lost** in that frame (red in `tracking.mp4`, counted on the
  results page). Its position in that frame is not reliable.

### 4.3 Sub-pixel refinement

Step 4 only gives whole pixels, so the error could be up to 0.5 px. The scores of the two neighbours
of the best pixel tell on which side the true position is. A **parabola** is drawn through the three
scores (left `L`, best `C`, right `R`) and its top is taken:

```
offset = (L − R) / (2 × (L − 2C + R))        (between −0.5 and +0.5 px)
```
This is done once in x and once in y. There is **no sub-pixel grid**: the formula gives any value
directly (0.329, 0.767, …).

**Example** (real scores, image moved by exactly 0.3 px): best pixel 0, `L = 0.8928`, `C = 0.9928`,
`R = 0.9723` → `L − R = −0.0795`, `L − 2C + R = −0.1205` → offset = −0.0795 / (2 × −0.1205) = **+0.33 px**.

| True shift | Whole pixel only | With sub-pixel |
|---|---|---|
| 0.3 px | 0 | 0.329 |
| 0.5 px | 0 | 0.499 |
| 0.8 px | 1 | 0.767 |

### 4.4 Template refresh

Normally every frame is compared with the template from **frame 0**. If the surface inside a box changes
a lot (large strain, necking), the score drops. When a box's score falls **below 0.8** (but stays above
the lost limit 0.5), its template is replaced by the box image in the current frame, cut at its
sub-pixel position.

Refreshing has a cost: each refresh starts from the current position *with its small error*, and these
errors add up (drift). That is why the template is **not** refreshed at regular intervals (the original
program refreshed every 50 frames): on `essai_2.mp4` refreshing every 5 frames moved the final result
by 13–19 px. With the score rule, a test with small strain is never refreshed (no drift); a test with
large strain is refreshed only when needed. Below 0.5 the template is not refreshed, so a lost box does
not "learn" a wrong image.

---

## 5. From positions to strain

For every **pair** of boxes (i, j), in every frame:

```
L  = √((cx_j − cx_i)² + (cy_j − cy_i)²)      distance between the two centres (px)
L0 = L in frame 0
strain_i_j = (L − L0) / L0                    engineering strain (no unit)
```

- **All pairs** are computed: n boxes give n(n−1)/2 strains (3 boxes → 3, 5 → 10, 10 → 45).
- The distance is measured **along the line joining the two centres**, so the result does not depend on
  the camera being tilted or on the specimen being vertical or horizontal in the image.
- Because it is a ratio of two lengths in pixels, strain needs **no pixel → mm calibration**.
- Displacements (`roiN_ux`, `roiN_uy`) stay in **pixels**.
- Choose your pairs when you analyse: e.g. two boxes on the gauge length along the loading direction
  give the axial strain; two boxes across the width give the transverse strain.

---

## 6. How precise are the results?

| | Error of one box position | Smallest strain step visible (two boxes 160 px apart) |
|---|---|---|
| Whole pixels only | up to 0.5 px (0.30 px RMS) | ≈ 1 / 160 ≈ **0.6 %** (staircase curve) |
| **Sub-pixel (this application)** | **≈ 0.04 px RMS** (largest ≈ 0.12 px) | ≈ 0.04 × √2 / 160 ≈ **0.035 %** |

For comparison, steel yields at about 400 MPa / 200 GPa ≈ **0.2 %** strain: with whole pixels the whole
elastic region would be invisible; with sub-pixel tracking it is resolved.

Rules of thumb:
- **Boxes further apart → better strain precision** (the error is divided by `L0`).
- Strain values smaller than about 0.05 % are within the noise.
- A pair on the same rigid piece should give 0; what you read there is the noise of your measurement.

---

## 7. Assumptions

The results are correct only if these assumptions are (nearly) true. Keep them in mind when you set up
the camera and when you interpret the results.

| # | Assumption | What happens if it is not true |
|---|---|---|
| A1 | The specimen surface is **flat and parallel to the camera sensor** | Out-of-plane movement (specimen moving towards/away from the camera) changes the scale of the image and appears as a false strain |
| A2 | The **camera does not move** during the test | Camera movement is added to all boxes; strains between boxes are less affected than displacements |
| A3 | The **scale is the same everywhere in the image** (no lens distortion) | Wide-angle phone lenses distort near the image edges; keep the specimen in the centre of the image |
| A4 | Each box **only moves** (translation); the pattern inside does not change shape much | Large strain or rotation inside a box lowers the score and the accuracy; the template refresh helps; use smaller boxes |
| A5 | The **marks stay visible** in every frame | Hidden or reflecting marks give low scores (lost boxes) |
| A6 | **Frame 0 is the reference**: the specimen is unloaded (or at the state you call "zero") at the first frame | All displacements and strains are measured from frame 0 |
| A7 | A box moves **less than its own size between two processed frames** (with `search_margin = 1`) | The mark leaves the search window → lost box. Use a higher target FPS |
| A8 | The timestamps stored in the video file are correct | `time_s` would be wrong; this is the camera's responsibility |

---

## 8. Default settings

The settings are in `point_tracking/settings.toml`. **They are chosen by the teacher; students do not
change them.** A value with the wrong type or outside its allowed range (e.g. a threshold above 1, a
negative margin) is ignored and the default is used. The values used for a run are copied into the project's `project.json`, so a project
always records how it was analysed.

| Setting | Default | Meaning | Effect of changing it |
|---|---|---|---|
| `processing.crf` | 18 | Compression quality of the processed video (0 = lossless, 23 = ffmpeg default) | Lower: bigger file, slightly better precision. Higher: smaller file, worse precision |
| `processing.default_target_fps` | 5 | Frame rate proposed in step 2 (students can choose another value) | — |
| `roi.default_width`, `roi.default_height` | 50, 50 px | Size of a new box (placed in the centre of the frame) | — |
| `roi.min_size` | 8 px | Smallest allowed box width/height | Very small boxes contain too little texture to be tracked |
| `roi.min_texture` | 8.0 | Grey-level standard deviation below which a box gets a "plain area" warning in step 3 | Higher: more warnings. A completely plain box (0) is always reported lost during tracking |
| `tracker.search_margin` | 1.0 | Search window = box ± margin × box size on each side | Larger: tolerates faster movement but slower and more risk of matching a similar-looking wrong spot |
| `tracker.subpixel` | true | Sub-pixel refinement (§4.3) | false: whole pixels only (0.3 px RMS error) |
| `tracker.refresh_threshold` | 0.8 | Template refreshed when the score drops below this value | Higher: more refreshes, more drift. Lower: fewer refreshes, risk of losing changing marks |
| `tracker.lost_threshold` | 0.5 | Below this score a box counts as lost in that frame | Changes what is reported as lost; does not change the positions |
| `preview.update_every_n_frames` | 5 | Live preview refresh during tracking | Display only |

Other fixed choices (not settings):
- At least **2 boxes** are required (strain needs a pair).
- The **reference frame** is always frame 0 of the processed video.
- Tracking **always runs to the last frame** (there is no Stop button).

---

## 9. Practical guide: getting good results

### Before the test (camera)
- Camera on a tripod, **perpendicular** to the specimen, specimen in the **centre** of the image (A1–A3).
- Fill the image with the specimen: more pixels per mm = better precision.
- Even lighting, no reflections on the marks.
- Marks or speckle with **good contrast** (black dots or spray paint on a white background).
- Start recording **before** loading, so frame 0 is the unloaded state (A6).

### Step 2 — choosing the target FPS
- Start with the default (5 FPS).
- After tracking, if boxes are lost during fast events (e.g. the fracture), process again with a
  **higher FPS**. Each box must move less than its own size between two frames (A7).
- Higher FPS = more frames = longer tracking and bigger files.

### Step 3 — choosing and placing boxes
- Put each box on a **mark with texture inside** (a dot, a speckle area). A box on a plain surface
  cannot be tracked: step 3 shows an orange warning "Box N is on a plain area" (saving is still allowed).
- Box size: about 2–4 × the mark size is usually good (e.g. 40–50 px for a 15 px dot).
  - Larger boxes: more stable, tolerate faster movement, but average over more material.
  - Smaller boxes: more local, but noisier.
- Place boxes **far enough apart** along the direction you want to measure (§6).
- Keep boxes away from the image border and from the grips.
- Remember the numbering: strains are labelled `strain_i_j` with the box numbers.

### After tracking — checking the results
1. **Summary** tab: read the **Warnings** (lost boxes, repeated frames), then the quality table: lowest score
   (and when), mean score, frames lost, template refreshes. Lost frames = positions not reliable.
2. **Plots** tab, score plot: a box whose curve approaches the red line (0.5) is in trouble at that moment.
   Hide pairs in the strain plot with the check boxes to compare them.
3. **Frames** tab: move the slider to the frames where the score drops and check that every box is still on
   its mark (red = lost). The same images are in `results/tracking.mp4`.
4. A pair of boxes on the same rigid part should give a strain close to 0 — that is your noise level.

### Common problems
| Symptom | Likely cause | What to do |
|---|---|---|
| Box lost at the fracture | Movement too large between frames | Higher target FPS |
| Score slowly decreasing | Surface inside the box deforms or reflects | Smaller box, better lighting |
| Strain not zero on a rigid part | Out-of-plane movement, camera movement, noise | Check camera setup; compare with §6 |
| Box jumps to another mark | Similar marks close together, window too large | Use more distinct marks, keep marks apart |

---

## 10. Known limitations

- **Files open in another program**: on Windows, a file open elsewhere (e.g. `results.csv` in Excel,
  `tracking.mp4` in a video player) cannot be replaced. The step stops with the message
  "… cannot be modified: it is probably open in another program": close the file and run the step again.
  The project is never left with a mix of old and new results.
- **Missing files**: if files of the project are deleted or moved by hand, the application tells you
  when the project is opened and undoes the steps concerned (e.g. "process the video again").
- **Cancel during import** cannot interrupt the copy of the file itself; it acts once the copy is
  finished (a few seconds for very large files). The project is never left half-imported.
- Boxes are edited **with the keyboard only** (x, y, width, height); drawing with the mouse is planned.
- **Unsaved box changes** are lost if another step is run: press *Save boxes*.
- Each box measures a **translation** only (A4); full DIC (deforming boxes, strain maps) is not
  implemented.
- The sub-pixel method has a small systematic error (a few hundredths of a pixel), visible as the
  ≈ 0.03 px error even on uncompressed videos.
- Displacements are in **pixels**; there is no pixel → mm calibration yet.
- **Force data** are not handled: synchronise them yourself using `time_s`.
- `tracking.mp4` is not played inside the application (the Frames tab shows it frame by frame): open it with
  your own video player to watch it.

---

## 11. Glossary

| Term | Meaning |
|---|---|
| Box / ROI | Region of interest: the rectangle you place on a mark; it is tracked as a whole |
| Template | The image inside a box that is searched for in the next frames |
| Search window | Area around the previous position where the template is searched |
| ZNCC score | Similarity between the template and the image (1 = identical); insensitive to brightness and contrast |
| Sub-pixel | Position given to a fraction of a pixel by fitting a parabola through neighbouring scores |
| Template refresh | Replacing the template by the current image of the box when its score drops |
| Drift | Slow accumulation of small position errors (caused by template refreshes) |
| FPS | Frames per second |
| VFR | Variable frame rate: the time between frames is not constant (common on phones) |
| CRF | Quality setting of the H.264 compression (lower = better quality, bigger file) |
| Engineering strain | (L − L0) / L0, with L the current and L0 the initial distance |
| RMS | Root mean square: a typical size of the error |
