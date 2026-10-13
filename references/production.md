# Production reference

## Setup and commands

Python 3.10+, NumPy, Pillow, Playwright with Chromium, FFmpeg with libx264. Node is only needed for the motion unit test. Resolve `SKILL` to this skill's directory. Generated videos belong in the user's output directory, not the installed skill.

Use a suitable existing environment or create one:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install numpy pillow playwright imageio-ffmpeg
.venv/bin/python -m playwright install chromium
```

If `ensurepip` is missing, the encoder alone can be installed privately without replacing system packages:

```sh
python3 -m pip install --target "$HOME/.local/share/ui-morph-motion/deps" imageio-ffmpeg
```

This fallback directory is used only for the encoder package. Other missing packages need a suitable environment or explicit `PYTHONPATH`. Encoder resolution: `UI_MORPH_FFMPEG` path → system `ffmpeg` → `imageio_ffmpeg` → the private directory above. No downloads during rendering. Chromium installation is a separate explicit setup step.

```sh
SKILL="$HOME/.codex/skills/ui-morph-motion"
python3 "$SKILL/scripts/render.py" doctor
python3 "$SKILL/scripts/media.py" analyze music.wav --bpm-hint 120 --out beat-analysis.json
python3 "$SKILL/scripts/media.py" mix audio-manifest.json --out mixed.wav
python3 "$SKILL/scripts/render.py" preview scene.html --out preview
# Inspect the contact sheet and full-size frames before this command.
python3 "$SKILL/scripts/render.py" render scene.html --out video.mp4 \
  --reviewed-preview preview/receipt.json --audio mixed.wav
# For deliberately silent work, replace --audio mixed.wav with --silent.
```

Preview receipt binds HTML bytes, scene metadata and contact-sheet hash. It is not proof of visual inspection or a user-approval token. The caller inspects images before passing `--reviewed-preview`. Edit → regenerate/inspect preview. Existing MP4/WAV files are not overwritten; choose versioned names.

## HTML contract

One self-contained HTML: embed styles, scripts, SVG and fonts. No network-loaded fonts, random values, live video, external images or unresolved local dependencies. The renderer rejects non-inline asset requests and awaits font loading.

```js
window.scene = {
  width: 1440, height: 1440, fps: 60, duration: 14,
  bpm: 120, beats: Array.from({length: 28}, (_, i) => i * 0.5),
  reviewTimes: [0.18, 2.2, 7.2, 13.9]
};
window.ready = document.fonts.ready;
window.seek = function(t) {
  // Set ALL changing styles/SVG/text from t, irrespective of call order.
  return {width: 300, height: 90, radius: 30, cursorX: 780, cursorY: 760, zoom: 1};
};
```

Beats/review times are seconds in `[0,T)`. Canvas dimensions are positive even integers; FPS is integral; `duration*fps` must be integral. At an arbitrary BPM, choose a compatible duration explicitly rather than silently retiming music.

`seek(t)` may be async but must complete DOM updates before returning a nonempty flat numeric probe covering all seam-critical geometry. A preview shell may use `requestAnimationFrame` ONLY to call `seek(elapsed % duration)`; it must be disabled by default during export. Viewer controls must stay outside the recorded canvas. The example uses a manual time slider; its mouse cursor is authored animation, not a functioning product.

Inline `assets/motion.js` in scene HTML:

- `track(t, initial, [{t,value,omega?,damping?},...])`: sorted changes; sums `(newTarget - previousTarget) * step(t-changeTime)`. Never restart from rounded rendered values.
- `release(dt,x0,v0,target,omega=26,damping=1)`: preserves release position AND velocity. The API default is critical damping; for the expressive visual default explicitly choose underdamping (see [expressive-motion.md](expressive-motion.md)). Preserve readability and settle before reading windows.
- `drag(t,{start,end,from,to,target})`: linear direct manipulation plus analytic release. Custom trajectories require their own position and derivative at release.
- `smooth`: zero-velocity endpoint blending for authored cursor paths and deliberate loop closure.

Keep the persistent shell separate from content layers with independent exit/enter windows. For liquid indicators, edges have different spring speeds/delays and positive width. During a drag the handle and cursor share a coordinate function; overscroll can stretch the track but must not arbitrarily lag the handle.

Return early enough to settle or use periodic trajectories. Modulo alone hides endpoint discontinuities. Check `T-ε,0,+ε` and velocities for shell, camera, cursor, text and dragging state. `check` tolerances are 0.5 position units and 5 velocity units/s on probes (CSS px, radians, RGB 0..255 or unitless zoom). Numeric probes cover only returned values; inspect seam images too.

## Audio and sources

For final-audio decisions, silent-player diagnosis, audible playback controls and 2× variants, also read [audio-and-speed.md](audio-and-speed.md). A temporary silent preview is not the final sound choice. Verify the final MP4 has nonzero decoded audio when sound is requested.

The analyzer uses 5 ms RMS changes and BPM/phase search near the hint. Suitable for approximately constant tempo; it does not robustly infer meter, downbeats, tempo changes or half/double-time interpretation. Inspect onset times and audition the phrase. An onset at 0.73 seconds is not necessarily bar one.

Maintain project `sources.md`: asset name, actual URL or user-provided path, author, checked license/date and attribution. A platform label is not a specific music license. Use user-provided music within stated permissions; describe unresolved publication limitations. Original test pulses may validate the pipeline but must not silently replace the chosen song.

Manifest paths are relative to the manifest; event times are output seconds:

```json
{
  "duration": 14,
  "music": {"file": "assets/song.wav", "start": 12.73, "gain": 0.65},
  "effects": [
    {"file": "assets/click.wav", "time": 0.5, "anchor": "peak", "gain": 0.4},
    {"file": "assets/swish.wav", "time": 4.0, "anchor": "onset", "gain": 0.25}
  ],
  "edge_fade_ms": 0
}
```

Music is optional. The mixer decodes 48 kHz stereo, crops the source segment, places each effect at `eventTime - measuredAnchorTime`, wraps negative pre-roll and tails around the loop, applies a reported uniform gain to prevent clipping, and writes exact-duration WAV + alignment report. Peak is maximum absolute sample; onset is first sample above 10% of peak, a listening-dependent heuristic. Too-short music is refused instead of silently padded.

An explicit 0–100 ms edge fade can remove a click but not guarantee musical continuity. Choose phrase boundaries and deliberately edit a crossfade when needed while preserving duration/beat mapping. Audition two cycles AFTER encoding; AAC padding/player behavior is separate from WAV continuity. Deliver WAV for re-encoding when useful.

## Exact sampling and verification

Frame n at FPS F has four samples `t(n,j) = (n + (j+0.5)/4)/F`, j=0..3: midpoint samples of a full-frame box exposure. Feed PNGs at `4F` FPS. Filter (replace 60 with configured FPS):

```text
tmix=frames=4:weights='1 1 1 1',select='eq(mod(n,4),3)',setpts=N/(60*TB)
```

Selecting each group's fourth frame avoids partial startup windows and gives disjoint averages. Do not simply add `fps=60` to a sliding average. Never capture `t=T`. 14 seconds at 60 FPS = 3,360 images → 840 decoded frames. References: [FFmpeg tmix](https://ffmpeg.org/ffmpeg-filters.html#tmix), [Playwright screenshots](https://playwright.dev/python/docs/screenshots).

Encoding uses `-fps_mode cfr -r 60 -enc_time_base:v 1:60` after assigning exact 60 fps presentation timestamps. Scope the encoder time base to video: unqualified `-enc_time_base 1:60` also quantizes AAC timestamps and can extend a 7 s container to 7.021 s. Keep audio at its own sample-based time base; do not hide this mismatch by relaxing the duration check. The declared video rate also sets each packet's duration: passthrough alone can retain the 240 fps input metadata and leave the last packet zero-length. Passthrough with output `-r` is rejected by FFmpeg. Validate decoded frames/PTS AND actual browser container duration; neither a flag nor a frame count proves the complete duration.

Screenshots stream directly to FFmpeg (no thousands of stored full-size frames). H.264, yuv420p, CRF18, fast-start MP4; optional 192 kbps AAC. The finished temporary MP4 is decoded to verify frame count, dimensions and contiguous timestamps before becoming the final file. Browser/decoder errors stop delivery. Four samples increase render cost; do not silently lower final quality.

| Evidence | Proves | Does not prove |
|---|---|---|
| Skill validator | Frontmatter/discovery | Workflow effectiveness |
| Unit tests | Sampling groups, anchors, spring continuity | Aesthetics |
| Random seek screenshots | Checked timestamps reproduce | Every instant correct |
| Loop probes/images | Reported geometry/visible boundary | Audio/player loop |
| Decoded MP4 report | Frames, size, FPS, timestamps | Readability or rhythm |
| Visual review/playback | Inspected framing and transitions | Music licensing |

## Default 28-beat proposal

Example only; not already approved. Beat zero is time zero, 0.5 seconds per beat.

| Bar | Beats | Events |
|---|---|---|
| 1 | 0–3 | Button/approach → click → loader → check draws |
| 2 | 4–7 | Island → metadata → player expands → play/pause |
| 3 | 8–11 | Grab progress → scrub → release → volume slider |
| 4 | 12–15 | Volume drag → stretch past max → release → toggle |
| 5 | 16–19 | Toggle click → tab indicator → liquid tab move → chart opens |
| 6 | 20–23 | Chart draws → tooltip hover → collapse to ⌘K → click/type |
| 7 | 24–27 | Filter result → enter → toast → return/loop closure |

Confirm exact words, sizes, cursor targets and audio events for the actual storyboard. Give the final return time to settle. If text requires more reading time, reduce events or agree a longer duration. Every beat having an event does not mean every beat needs a new component.
