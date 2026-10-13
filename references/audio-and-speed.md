# Audio delivery and speed variants

Read for soundtrack work, a “no sound” report, a playback page, or a 2× version. Keep the user's chosen soundtrack and prior approvals; these checks do not require another storyboard approval.

## Preview versus final audio

Agree the final sound plan with the storyboard: selected/provided music, original composition plus effects, or explicitly silent output. A user accepting a **temporary silent preview** has not selected a silent final. No supplied song does not imply “no audio.” If the user delegates musical choices, compose original audio and disclose that choice; do not stop to ask for a specific song. If the choice is still missing, ask early while continuing visual work.

Do not use test pulses as an undisclosed final soundtrack. A composed original track may use synthesized instruments; it needs an intentional phrase, rhythm and instrument balance. Keep its generation source and event schedule, identify it as original, and list any third-party samples separately.

For original music, authored BPM and sample event times define the downbeat. Run the analyzer as a cross-check, not as the authority. For external music, its BPM/phase candidates need listening and phrase-boundary decisions.

## Diagnose “no sound” in this order

1. Inspect the **exact file the user opened**: no audio stream, an all-zero stream, and a quiet but valid stream are different failures. Decode the final MP4, not only the source WAV. Check duration, sample rate, channels, finite PCM, peak and RMS; report clipping or silence. A successful `--audio` encode alone is insufficient.
2. Check the playback page: actual `src`, `muted`, `volume`, autoplay policy, and AudioContext state. Do not immediately blame user speakers. A `<video autoplay muted>` wrapper intentionally suppresses sound even when the file contains it.
3. For a sound-first preview, show a visible **Play with sound** button. On its user gesture, set `muted=false`, a nonzero volume, call `play()`, and resume an AudioContext if one is used. Test that gesture in the real page. Avoid unhandled autoplay rejection.
4. Verify audio decoding and nonzero output with a browser analyser when available. Serve local generated files on loopback for the test so cross-origin restrictions do not manufacture zero analyser output. Close the test server afterward.
5. Play two consecutive loops of the encoded file and inspect errors and the seam. Separate objective PCM/player checks from subjective listening. State if listening was not possible. Nonzero Web Audio output cannot prove the user's physical speaker configuration or musical taste.

Minimal player pattern, with filenames selected for the actual deliverable:

```html
<video id="video" src="video-2x.mp4" controls loop playsinline preload="auto"></video>
<button id="play">播放 · 开启声音</button>
<span id="status"></span>
<script>
const video = document.getElementById('video');
const playButton = document.getElementById('play');
const statusLabel = document.getElementById('status');
playButton.onclick = async () => {
  video.muted = false;
  video.volume = 1;
  try { await video.play(); statusLabel.textContent = '声音已开启'; }
  catch (error) { statusLabel.textContent = '播放未启动，请使用视频控件重试'; }
};
</script>
```

A scene-only HTML animation has no soundtrack unless one is deliberately connected; identify it as a visual editor/preview rather than claiming it is the audible MP4 player.

When only adding audio to a verified video, stream-copy the video and encode the audio into a **new file**. This avoids a needless second video compression. Verify the resulting video stream identity, duration and audio. Preserve the prior artifact, update the delivery link/player, and distinguish the new audio report from the old silent report.

AAC may decode extra padding samples. Report source-WAV length, decoded-AAC length and actual player duration separately. An exact WAV duration or zero endpoint sample jump does not certify a gapless musical seam in every player.

If the player duration is longer than the correctly decoded video, inspect stream timing before attributing it to harmless AAC padding. The renderer must use video-scoped `-enc_time_base:v`, not a global video time base applied to audio. Keep strict container-duration verification; a small mismatch can still shift every loop.

## Offer speed options

At the first storyboard confirmation offer **1× / 2× / both** unless already selected. For the default scene explain 14 s versus 7 s, both at 60 fps, and shorter reading time in the fast version. Do not force a second approval after the user selects a variant. Do not always generate both by default.

For a selected factor `s`:

| Item | Transformation |
|---|---|
| Duration | `T / s` |
| Scene motion | `seek_fast(t) = seek_original(s * t)` |
| Beat, click, drag, release, text and review times | `time / s` |
| Visual event-grid BPM for the same action sequence | `BPM * s`; this is not a soundtrack tempo instruction |
| Output FPS | Keep chosen FPS; default 60 |
| Frame count | `(T / s) * FPS`, must be integral |
| Four-sample captures | `frames * 4`, no duplicate terminal frame |

Prefer mapping the single master clock: it scales analytic motion, text windows and release velocities together. Do not double spring frequencies again when already mapping `seek(s*t)`. With a full explicit timeline rewrite instead, spring frequency and velocities must also scale, damping unchanged. Update viewer controls, time labels, loop modulus and audio-event manifests along with scene metadata.

For 14 s / 60 fps → 2×, deliver 7 s / 60 fps / 420 frames, with 1680 subframe samples. Merely changing `playbackRate=2` leaves the file at 14 s; changing FPS metadata does not fulfill a 7 s / 60 fps deliverable. Prefer re-rendering the deterministic HTML to preserve four-sample motion blur at the faster motion. If only an MP4 exists, retime with explicit output FPS and disclose source-frame limits rather than claiming a native resampled scene.

## Video speed, musical tempo and stronger rhythm

“2× video” defines visual timing, not music playback speed or composition BPM. Unless the user explicitly requests faster music, keep a natural musical tempo and compose/select a fitting shorter phrase. Treat stronger rhythm as drum weight, groove, contrast and arrangement, not automatically higher note density or doubled BPM. Do not treat a louder copy as a rhythmic redesign.

- If retaining a selected song, choose a normal-speed excerpt or edit its phrase to fit the new duration. Only use time-stretching such as `atempo=2` when the user explicitly wants faster music. Pitch preservation does not preserve perceived pace: both pitch-preserving time-stretch and newly synthesized double-BPM notes can sound unnaturally rushed.
- If original composition or rearrangement is authorized, choose music BPM independently from the visual grid. For example, 2× visuals may retain 120 BPM music while visual events use a 240 BPM grid. Use deliberate kick/snare accents, natural note decays, bass weight and breathing room around UI events. Avoid a rapid arpeggio or tick on every UI subdivision when the user wants normal-speed music. A half-time groove is another option; label its actual feel and tempo accurately.
- Re-place clean click/confirmation effects at `time / s` using their **new measured onset/peak anchors**. Do not automatically stretch every effect with the music. Shorten long transition tails when they obscure adjacent fast actions; preserve effect pitch unless a changed timbre is intentional.
- Rebuild an exact-duration audio manifest, mix and recheck alignment. Generate and inspect a new preview receipt for the speed-specific HTML before rendering. Never reuse a 1× receipt for edited 2× bytes.

Verify fast-version clicks, dragging, legibility, frame count, container duration, non-silent audio and two loops. State any unperformed listening review. Keep standard and fast artifacts separate and make the requested variant the primary link.
