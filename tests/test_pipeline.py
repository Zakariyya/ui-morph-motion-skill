"""Behavior tests for the reusable media/render helpers (no network)."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class PipelineTests(unittest.TestCase):
    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec(name), f'{name} helper is missing')
        return __import__(name)

    def test_exact_sampling_excludes_terminal_frame(self):
        r = self.module('render')
        samples = list(r.sample_times(14, 60, 4))
        self.assertEqual(len(samples), 3360)
        self.assertAlmostEqual(samples[0], 1 / 480)
        self.assertAlmostEqual(samples[-1], 14 - 1 / 480)
        with self.assertRaises(ValueError):
            list(r.sample_times(1.01, 60, 4))

    def test_tmix_averages_disjoint_groups(self):
        r, m = self.module('render'), self.module('media')
        values = [0, 20, 40, 60, 100, 120, 140, 160]
        pngs = []
        for value in values:
            b = io.BytesIO()
            Image.new('RGB', (16, 16), (value,) * 3).save(b, format='PNG')
            pngs.append(b.getvalue())
        command = [m.ffmpeg_exe(), '-v', 'error', '-f', 'image2pipe', '-framerate', '240',
                   '-i', 'pipe:0', '-vf', r.blur_filter(60, 4), '-fps_mode', 'passthrough',
                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
        raw = subprocess.run(command, input=b''.join(pngs), capture_output=True, check=True).stdout
        result = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 16, 16, 3)
        self.assertEqual(len(result), 2)
        np.testing.assert_allclose(result.mean(axis=(1, 2, 3)), [30, 130], atol=1)

    def test_peak_alignment_handles_leading_silence_and_wrap(self):
        m = self.module('media')
        effect = np.zeros((1000, 2), dtype=np.float32)
        effect[730] = 0.7
        self.assertEqual(m.anchor_sample(effect, 'peak'), 730)
        track = np.zeros((4000, 2), dtype=np.float32)
        m.place_effect(track, effect, event_sample=100, anchor=730, gain=1)
        self.assertEqual(int(np.argmax(track[:, 0])), 100)
        self.assertAlmostEqual(float(track[100, 0]), 0.7, places=5)

    def test_beat_candidate_does_not_claim_downbeat(self):
        m = self.module('media')
        sr = 8000
        signal = np.zeros(sr * 8, dtype=np.float32)
        for t in np.arange(0.73, 7.9, 0.5):
            i = round(t * sr)
            signal[i:i + 40] = np.hanning(40)
        info = m.analyze_samples(signal, sr, bpm_hint=120)
        self.assertFalse(info['downbeat_confirmed'])
        self.assertAlmostEqual(info['bpm_candidate'], 120, delta=2)
        self.assertAlmostEqual(info['first_onset_seconds'], 0.73, delta=0.025)
        self.assertGreater(len(info['onsets_seconds']), 10)

    def test_silent_audio_has_no_fabricated_grid(self):
        m = self.module('media')
        with self.assertRaises(ValueError):
            m.analyze_samples(np.zeros(8000), 8000, bpm_hint=120)

    def test_antiphase_stereo_keeps_beat_energy(self):
        m = self.module('media')
        sr = 8000
        signal = np.zeros(sr * 4, dtype=np.float32)
        for t in np.arange(.23, 3.9, .5):
            i = round(t*sr)
            signal[i:i+40] = np.hanning(40)
        try:
            info = m.analyze_samples(np.column_stack([signal, -signal]), sr, 120)
        except ValueError as exc:
            self.fail(f'Non-silent stereo was rejected: {exc}')
        self.assertAlmostEqual(info['bpm_candidate'], 120, delta=2)

    def test_nonfinite_wav_is_rejected(self):
        m = self.module('media')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                m.write_wav(Path(tmp)/'invalid.wav', np.full((20, 2), np.nan))

    def test_nonfinite_effect_gain_is_rejected(self):
        m = self.module('media')
        with self.assertRaises(ValueError):
            m.place_effect(np.zeros((100, 2)), np.ones((10, 2)), 0, 0, float('inf'))

    def test_subsample_duration_is_rejected(self):
        m = self.module('media')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'manifest.json'
            path.write_text(json.dumps({'duration': 1e-10}))
            with self.assertRaisesRegex(ValueError, 'at least one audio sample'):
                m.mix_manifest(path, Path(tmp)/'audio.wav')

    def test_continuous_fast_loop_is_not_a_jump(self):
        r = self.module('render')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'scene.html'
            path.write_text('''<style>body{margin:0}#s{width:10px;height:10px;background:black}</style>
            <div id="s"></div><script>
            window.scene={width:64,height:64,fps:60,duration:1,beats:[0,.5]};
            window.seek=t=>{t=((t%1)+1)%1; const x=100*Math.sin(2*Math.PI*t);
            document.getElementById('s').style.transform=`translateX(${x}px)`; return {x};};
            seek(0);</script>''')
            with r.Scene(path) as scene:
                try:
                    report = r.check_scene(scene, Path(tmp)/'checks')
                except ValueError as exc:
                    self.fail(f'Continuous periodic trajectory was rejected: {exc}')
            self.assertTrue(report['endpoint_equal'])

    def test_full_mp4_pipeline_encodes_exact_frames_and_audio(self):
        r, m = self.module('render'), self.module('media')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'scene.html'
            path.write_text('''<style>body{margin:0;background:#eee}</style><script>
            window.scene={width:64,height:64,fps:60,duration:0.1,beats:[0,.05]};
            window.seek=t=>({x:0});</script>''')
            m.write_wav(root/'audio.wav',np.zeros((4800,2)))
            with r.Scene(path) as scene:
                r.preview(scene,root/'preview')
                report=r.render(scene,root/'video.mp4',root/'preview/receipt.json',root/'audio.wav',False)
            self.assertEqual(report['video']['decoded_frames'],6)
            self.assertEqual(report['video']['fps'],60)
            self.assertEqual(report['audio']['samples'],4800)
            self.assertGreater(report['audio']['decoded_samples'],0)
            viewer = root/'viewer.html'
            viewer.write_text('<video src="video.mp4" preload="auto"></video>')
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                page.goto(viewer.as_uri())
                page.wait_for_function('document.querySelector("video").readyState>=1')
                duration=page.evaluate('document.querySelector("video").duration')
                browser.close()
            self.assertAlmostEqual(duration,.1,places=6)

    def test_video_timebase_does_not_quantize_aac_timestamps(self):
        r, m = self.module('render'), self.module('media')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'scene.html'
            path.write_text('''<style>body{margin:0;background:#eee}</style><script>
            window.scene={width:64,height:64,fps:60,duration:7,beats:[0,.25]};
            window.seek=t=>({x:0});</script>''')
            t = np.arange(7*48000)/48000
            signal = .2*np.sin(2*np.pi*440*t)
            m.write_wav(root/'audio.wav', np.column_stack([signal,signal]))
            with r.Scene(path) as scene:
                # This scene is constant. Reuse its real browser screenshot to
                # exercise all 1680 mux samples without 1680 identical captures.
                frame = scene.capture(0)
                scene.capture = lambda t: frame
                r.preview(scene,root/'preview')
                report = r.render(scene,root/'video.mp4',root/'preview/receipt.json',root/'audio.wav',False)
            self.assertEqual(report['video']['decoded_frames'],420)
            self.assertAlmostEqual(report['video']['container_duration'],7,places=6)
            self.assertGreater(float(np.sqrt(np.mean(m.decode(root/'video.mp4')**2))),.05)


if __name__ == '__main__':
    unittest.main()
