#!/usr/bin/env python3
"""Analyze a candidate beat grid and mix sample-aligned loop audio. See --help."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import numpy as np


def ffmpeg_exe():
    explicit = os.environ.get('UI_MORPH_FFMPEG')
    if explicit:
        if not Path(explicit).is_file():
            raise ValueError('UI_MORPH_FFMPEG must point to an existing executable')
        return explicit
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError:
        local = Path.home() / '.local/share/ui-morph-motion/deps'
        if local.exists():
            sys.path.insert(0, str(local))
        try:
            import imageio_ffmpeg
        except ImportError as exc:
            raise RuntimeError('Install ffmpeg or imageio-ffmpeg, or set UI_MORPH_FFMPEG. See references/production.md.') from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode(path, sr=48000):
    cmd = [ffmpeg_exe(), '-v', 'error', '-i', str(Path(path).resolve()), '-vn',
           '-f', 'f32le', '-ac', '2', '-ar', str(sr), 'pipe:1']
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    audio = np.frombuffer(data, dtype='<f4').reshape(-1, 2).copy()
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError('Empty or non-finite audio')
    return audio


def anchor_sample(audio, kind='peak'):
    envelope = np.max(np.abs(audio), axis=1) if audio.ndim==2 else np.abs(audio)
    peak = float(envelope.max(initial=0))
    if peak < 1e-8:
        raise ValueError('Silent audio has no onset or peak anchor')
    if kind == 'peak':
        return int(envelope.argmax())
    if kind == 'onset':
        return int(np.flatnonzero(envelope >= peak*0.1)[0])
    raise ValueError('Anchor must be peak or onset')


def analyze_samples(audio, sr, bpm_hint=120):
    if not np.isfinite(audio).all():
        raise ValueError('Audio contains non-finite samples')
    # Aggregate energy, not signed samples: opposite-phase stereo must not cancel.
    power = np.mean(audio.astype(np.float64)**2, axis=1) if audio.ndim==2 else audio.astype(np.float64)**2
    # Short-window RMS is an onset cue, not a music-theory downbeat detector.
    hop = max(1, round(sr*0.005))
    count = len(power)//hop
    if count < 4 or np.max(power, initial=0)<1e-12:
        raise ValueError('Audio is silent or too short to analyze')
    rms = np.sqrt(np.mean(power[:count*hop].reshape(-1,hop), axis=1))
    flux = np.maximum(0, np.diff(rms, prepend=0))
    peaks = np.flatnonzero((flux>=np.roll(flux,1)) & (flux>np.roll(flux,-1)) & (flux>flux.max()*0.15))
    selected = []
    for i in peaks:
        if not selected or (i-selected[-1])*hop/sr>0.09:
            selected.append(int(i))
        elif flux[i] > flux[selected[-1]]:
            selected[-1]=int(i)
    if len(selected)<3:
        raise ValueError('Too few onsets: provide a manually verified BPM/downbeat')
    onset = np.asarray(selected)*hop/sr
    best = None
    for bpm in np.linspace(bpm_hint*0.9, bpm_hint*1.1, 241):
        period=60/bpm
        phases=onset[:min(16,len(onset))] % period
        for phase in phases:
            distance=np.abs((onset-phase+period/2)%period-period/2)
            score=float(np.mean(np.exp(-(distance/0.025)**2)))
            if best is None or score>best[0]:
                best=(score,float(bpm),float(phase))
    score,bpm,phase=best
    first=anchor_sample(audio, 'onset')/sr
    return {'bpm_candidate':round(bpm,5), 'phase_candidate_seconds':phase,
            'first_onset_seconds':first, 'onsets_seconds':onset.tolist(),
            'grid_fit_score':score, 'downbeat_confirmed':False,
            'duration_seconds':len(power)/sr,
            'note':'Heuristic near BPM hint; listen to resolve syncopation, half/double tempo and bar phase.'}


def place_effect(track, effect, event_sample, anchor, gain=1):
    if not math.isfinite(gain):
        raise ValueError('Effect gain must be finite')
    # Wrap both negative pre-roll and positive tails into the periodic buffer.
    indices=(np.arange(len(effect))+int(event_sample)-int(anchor)) % len(track)
    np.add.at(track, indices, effect*gain)


def write_wav(path, audio, sr=48000):
    if audio.ndim!=2 or audio.shape[1]!=2 or not len(audio) or not np.isfinite(audio).all():
        raise ValueError('WAV requires nonempty, finite stereo samples')
    path=Path(path)
    if path.exists():
        raise FileExistsError(f'Refusing to overwrite {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm=np.rint(np.clip(audio,-1,1)*32767).astype('<i2')
    with wave.open(str(path),'wb') as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(sr); out.writeframes(pcm.tobytes())


def mix_manifest(path, out):
    path=Path(path).resolve()
    spec=json.loads(path.read_text())
    sr=48000
    duration=float(spec['duration'])
    if not math.isfinite(duration) or duration<=0:
        raise ValueError('Duration must be finite and positive')
    count=round(duration*sr)
    if count<1:
        raise ValueError('Duration must cover at least one audio sample')
    track=np.zeros((count,2),dtype=np.float64)
    anchors=[]
    music=spec.get('music')
    if music:
        source=decode(path.parent/music['file'],sr)
        start=round(float(music.get('start',0))*sr)
        if start<0 or start+count>len(source):
            raise ValueError('Music does not cover the selected duration; choose another segment')
        gain=float(music.get('gain',0.65))
        if not math.isfinite(gain): raise ValueError('Music gain must be finite')
        track += source[start:start+count]*gain
    for event in spec.get('effects',[]):
        effect=decode(path.parent/event['file'],sr)
        kind=event.get('anchor','peak')
        anchor=anchor_sample(effect,kind)
        at=round(float(event['time'])*sr)
        place_effect(track,effect,at,anchor,float(event.get('gain',1)))
        anchors.append({'file':event['file'],'kind':kind,'anchor_seconds':anchor/sr,
                        'event_seconds':at/sr,'placement_seconds':(at-anchor)/sr})
    # Optional tiny edge fade removes a click; does not certify musical continuity.
    edge_ms=float(spec.get('edge_fade_ms',0))
    if not math.isfinite(edge_ms) or not 0<=edge_ms<=100:
        raise ValueError('edge_fade_ms must be 0..100; longer fades need deliberate arrangement')
    edge=round(sr*edge_ms/1000)
    if edge and edge*2<count:
        ramp=np.linspace(0,1,edge)
        track[:edge]*=ramp[:,None]; track[-edge:]*=ramp[::-1,None]
    peak=float(np.abs(track).max(initial=0))
    gain=min(1,0.95/peak) if peak else 1
    track*=gain
    write_wav(out,track,sr)
    report={'samples':count,'sample_rate':sr,'duration':count/sr,'gain_to_avoid_clipping':gain,
            'seam_sample_jump':np.abs(track[0]-track[-1]).tolist(),
            'anchors':anchors,'audition_required':True,'source_manifest':str(path)}
    Path(str(out)+'.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('analyze',help='Heuristic grid near hint; never confirms musical downbeat')
    a.add_argument('audio',type=Path); a.add_argument('--bpm-hint',type=float,default=120)
    a.add_argument('--out',type=Path,required=True)
    m=sub.add_parser('mix',help='Read JSON with duration, optional music, effects; produce 48 kHz WAV')
    m.add_argument('manifest',type=Path); m.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='analyze':
        if not 20<=args.bpm_hint<=300: parser.error('BPM hint must be 20..300')
        result=analyze_samples(decode(args.audio,8000),8000,args.bpm_hint)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2)+'\n')
    else:
        result=mix_manifest(args.manifest,args.out)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
