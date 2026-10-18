#!/usr/bin/env python3
"""Deterministic HTML -> beat previews, checks and motion-blurred MP4. See --help."""
import argparse
import hashlib
import html
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import functools
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, unquote

from browser_env import launch

import numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from media import decode, ffmpeg_exe


def sample_times(duration, fps=60, subframes=4):
    if not (math.isfinite(duration) and duration>0 and fps>0 and subframes>0):
        raise ValueError('Duration, FPS and subframes must be positive')
    frames=round(duration*fps)
    if not math.isclose(frames,duration*fps,abs_tol=1e-7,rel_tol=0):
        raise ValueError('Duration must contain an integer number of output frames; adjust the plan explicitly')
    for n in range(frames):
        for j in range(subframes):
            yield (n+(j+0.5)/subframes)/fps


def blur_filter(fps=60, subframes=4):
    return (f"tmix=frames={subframes}:weights='"+' '.join(['1']*subframes)+"',"
            f"select='eq(mod(n,{subframes}),{subframes-1})',setpts=N/({fps}*TB)")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


class Scene:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.errors=[]
        self.resources={}
        self.server=None

    def __enter__(self):
        self.pw=sync_playwright().start()
        self.browser=None
        try:
            self.browser,self.launch_attempts=launch(self.pw)
            class Handler(SimpleHTTPRequestHandler):
                def log_message(self,*args): pass
            self.server=ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Handler,directory=str(self.path.parent)))
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
            self.thread.start()
            self.origin=f"http://127.0.0.1:{self.server.server_port}"
            self.page=self.browser.new_page(viewport={'width':1440,'height':1440},device_scale_factor=1)
            self.page.on('pageerror',lambda error:self.errors.append(str(error)))
            self.page.on('console',lambda msg:self.errors.append(msg.text) if msg.type=='error' else None)
            def route(request):
                url=request.request.url
                if url.startswith(('data:','blob:')):
                    request.continue_()
                elif url.startswith(self.origin+'/'):
                    local=(self.path.parent/unquote(urlparse(url).path).lstrip('/')).resolve()
                    if local.is_relative_to(self.path.parent) and local.is_file():
                        self.resources[str(local.relative_to(self.path.parent))]=digest(local)
                        request.continue_()
                    else:
                        self.errors.append('Missing or escaping local asset: '+url);request.abort()
                else:
                    self.errors.append('Offline render blocked remote asset: '+url);request.abort()
            self.page.route('**/*',route)
            self.page.goto(self.origin+'/'+self.path.name,wait_until='load',timeout=15000)
            self.page.evaluate('async () => { await document.fonts.ready; await window.ready; }')
            self.meta=self.page.evaluate('window.scene')
            if not isinstance(self.meta,dict): raise ValueError('Define window.scene metadata')
            for key in ('width','height','duration','fps','beats'):
                if key not in self.meta: raise ValueError('Missing window.scene.'+key)
            for key in ('width','height'):
                v=self.meta[key]
                if not isinstance(v,int) or v<=0 or v%2: raise ValueError(key+' must be a positive even integer')
            if not isinstance(self.meta['fps'],int) or self.meta['fps']<=0: raise ValueError('fps must be a positive integer')
            next(sample_times(self.meta['duration'],self.meta['fps'],4))
            if not self.meta['beats'] or any(not isinstance(t,(int,float)) or not 0<=t<self.meta['duration'] for t in self.meta['beats']):
                raise ValueError('beats must contain in-range timestamps (seconds)')
            self.page.set_viewport_size({key:self.meta[key] for key in ('width','height')})
            self.at(0)
            if self.page.evaluate('document.getAnimations().length'): raise ValueError('Use seek(t), not CSS/Web Animations')
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise

    def __exit__(self,*args):
        if self.browser: self.browser.close()
        self.pw.stop()
        if self.server:
            self.server.shutdown();self.server.server_close()

    def at(self,t):
        state=self.page.evaluate('(t) => window.seek(t)',t)
        if self.page.evaluate('document.getAnimations().length'):
            raise ValueError('Use seek(t), not CSS/Web Animations')
        if self.errors: raise ValueError('; '.join(self.errors))
        if not isinstance(state,dict) or not state:
            raise ValueError('seek(t) must return a non-empty flat numeric probe for geometry/cursor/camera')
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in state.values()):
            raise ValueError('seek(t) probe values must all be finite numbers')
        return state

    def capture(self,t):
        self.at(t)
        return self.page.screenshot(type='png',caret='hide',scale='css')


def check_scene(scene,out):
    out.mkdir(parents=True,exist_ok=True)
    duration=scene.meta['duration']
    times=[0,duration*0.17,duration*0.41,duration*0.73,duration-1/scene.meta['fps']]
    original=[scene.capture(t) for t in times]
    for i in [3,0,4,1,2]:
        if scene.capture(times[i])!=original[i]: raise ValueError(f'Non-deterministic seek at {times[i]}')
    first=scene.capture(0)
    terminal=scene.capture(duration)
    if scene.meta.get('loop',True) and first!=terminal: raise ValueError('seek(0) and seek(duration) must match exactly')
    epsilon=0.001
    s0=scene.at(0); sp=scene.at(epsilon); sm=scene.at(duration-epsilon)
    s2p=scene.at(2*epsilon); s2m=scene.at(duration-2*epsilon)
    errors={}
    for key in (s0 if scene.meta.get('loop',True) else {}):
        # Compare extrapolated boundary positions, not real travel across 2 ms.
        before=2*sm[key]-s2m[key]
        after=2*sp[key]-s2p[key]
        incoming=(3*s0[key]-4*sm[key]+s2m[key])/(2*epsilon)
        outgoing=(-3*s0[key]+4*sp[key]-s2p[key])/(2*epsilon)
        # Probe units are CSS px, radians, RGB 0..255, or unitless zoom/opacity.
        errors[key]={'position_gap':max(abs(before-after),abs(before-s0[key]),abs(after-s0[key])),
                     'velocity_gap':abs(outgoing-incoming)}
        if errors[key]['position_gap']>0.5 or errors[key]['velocity_gap']>5:
            raise ValueError(f'Loop seam discontinuity in {key}: {errors[key]}')
    for name,t in [('first',0),('before-seam',duration-1/scene.meta['fps']),('after-seam',1/scene.meta['fps'])]:
        (out/(name+'.png')).write_bytes(scene.capture(t))
    report={'html_sha256':digest(scene.path),'metadata':scene.meta,'random_seek_equal':True,
            'endpoint_equal':first==terminal,'loop_checked':scene.meta.get('loop',True),'seam_probes':errors,'browser_errors':scene.errors,
            'visual_review_required':['text legibility','in-between morphs','cursor hit targets','camera framing','two consecutive loops'],
            'limits':'Numeric probes test supplied geometry only. No audio audition or aesthetic certification.'}
    dump(out/'check.json',report)
    return report


def preview(scene,out):
    out.mkdir(parents=True,exist_ok=True)
    check_scene(scene,out/'checks')
    times=sorted(set(scene.meta['beats']+scene.meta.get('reviewTimes',[])))
    if any(not 0<=t<scene.meta['duration'] for t in times): raise ValueError('Review time out of range')
    tiles=[]
    for i,t in enumerate(times):
        data=scene.capture(t)
        name=f'frame-{i:03d}.png'
        (out/name).write_bytes(data)
        tile=Image.new('RGB',(280,310),'#f4f2ee')
        frame=Image.open(io.BytesIO(data)).convert('RGB')
        frame.thumbnail((280,280))
        tile.paste(frame,((280-frame.width)//2,(280-frame.height)//2))
        ImageDraw.Draw(tile).text((10,289),f'{i+1:02d}   t={t:.3f}s',fill='#222222')
        tiles.append(tile)
    sheet=Image.new('RGB',(280*4,310*math.ceil(len(tiles)/4)),'#f4f2ee')
    for i,tile in enumerate(tiles): sheet.paste(tile,(i%4*280,i//4*310))
    sheet.save(out/'contact-sheet.png')
    receipt={'resources':scene.resources,'html_sha256':digest(scene.path),'metadata':scene.meta,'times':times,
             'contact_sheet_sha256':digest(out/'contact-sheet.png'),
             'meaning':'Generated preview for this version, NOT proof of human approval or visual review.'}
    dump(out/'receipt.json',receipt)
    return receipt


def verify_video(path,expected_frames,width,height,fps):
    run=subprocess.run([ffmpeg_exe(),'-v','error','-i',str(path),'-map','0:v:0',
                        '-fps_mode','passthrough','-f','framemd5','-'],capture_output=True,text=True,check=True)
    lines=run.stdout.splitlines()
    frames=[line for line in lines if line and not line.startswith('#')]
    if len(frames)!=expected_frames: raise ValueError(f'Decoded {len(frames)} frames; expected {expected_frames}')
    if f'#dimensions 0: {width}x{height}' not in lines: raise ValueError('Unexpected decoded video dimensions')
    if f'#tb 0: 1/{fps}' not in lines: raise ValueError('Unexpected decoded frame timebase')
    pts=[int(row.split(',')[2]) for row in frames]
    if pts!=list(range(expected_frames)): raise ValueError('Duplicate/missing/nonuniform presentation timestamps')
    return {'decoded_frames':len(frames),'width':width,'height':height,'fps':fps,'timestamps_contiguous':True}


def verify_container(browser,path,duration):
    """PTS spacing alone misses a zero-duration final packet; ask a real player."""
    page=browser.new_page()
    wrapper=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',suffix='.html',dir=path.parent,delete=False) as f:
            wrapper=Path(f.name)
            f.write('<video preload="auto" src="'+html.escape(path.name,quote=True)+'"></video>')
        page.goto(wrapper.as_uri(),wait_until='load')
        page.wait_for_function('document.querySelector("video").readyState>=1',timeout=15000)
        actual=page.evaluate('document.querySelector("video").duration')
        if not math.isclose(actual,duration,abs_tol=1e-5,rel_tol=0):
            raise ValueError(f'Browser container duration {actual}, expected {duration}; inspect last packet duration')
        return actual
    finally:
        page.close()
        if wrapper: wrapper.unlink(missing_ok=True)


def render(scene,out,receipt,audio,silent):
    out=out.resolve()
    if out.exists(): raise FileExistsError(f'Refusing to overwrite {out}')
    proof=json.loads(receipt.read_text())
    if any(not (scene.path.parent/name).is_file() or digest(scene.path.parent/name)!=sha for name,sha in proof.get('resources',{}).items()):
        raise ValueError('Preview assets are stale; regenerate preview')
    if proof.get('html_sha256')!=digest(scene.path) or proof.get('metadata')!=scene.meta:
        raise ValueError('Preview is stale; regenerate and inspect it after editing the scene')
    if digest(receipt.parent/'contact-sheet.png')!=proof['contact_sheet_sha256']:
        raise ValueError('Preview contact sheet has changed')
    if bool(audio)==bool(silent): raise ValueError('Choose --audio mixed.wav OR --silent explicitly')
    duration=scene.meta['duration']; fps=scene.meta['fps']; subframes=4
    audio_report={'mode':'silent'}
    if audio:
        pcm=decode(audio)
        if abs(len(pcm)-round(duration*48000))>1: raise ValueError('Audio must match video duration exactly; use media.py mix')
        audio_report={'mode':'audio','source':str(audio.resolve()),'source_sha256':digest(audio),'samples':len(pcm),
                      'seam_sample_jump':np.abs(pcm[0]-pcm[-1]).tolist(),'audition_required':True}
    out.parent.mkdir(parents=True,exist_ok=True)
    check_scene(scene,out.parent/(out.stem+'-checks'))
    frames=round(duration*fps)
    with tempfile.TemporaryDirectory(prefix='.ui-morph-',dir=out.parent) as tmp:
        temp=Path(tmp)/'video.mp4'
        command=[ffmpeg_exe(),'-v','error','-f','image2pipe','-framerate',str(fps*subframes),'-i','pipe:0']
        if audio: command+=['-i',str(audio.resolve())]
        command+=['-map','0:v:0','-vf',blur_filter(fps,subframes),'-fps_mode','cfr','-r',str(fps),
                  '-enc_time_base:v',f'1:{fps}','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p']
        if audio: command+=['-map','1:a:0','-c:a','aac','-b:a','192k']
        else: command+=['-an']
        command+=['-movflags','+faststart','-n',str(temp)]
        with (Path(tmp)/'ffmpeg.log').open('w+b') as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            try:
                for i,t in enumerate(sample_times(duration,fps,subframes)):
                    process.stdin.write(scene.capture(t))
                    if (i+1)%(fps*subframes)==0: print(f'Rendered {(i+1)//subframes}/{frames} frames',flush=True)
                process.stdin.close()
                code=process.wait(timeout=120)
                if code:
                    log.seek(0); raise RuntimeError(log.read().decode(errors='replace'))
            except Exception:
                process.kill(); process.wait(); log.seek(0)
                details=log.read().decode(errors='replace')
                if details: print(details,flush=True)
                raise
        if proof.get('resources') is not None and scene.resources!=proof['resources']:
            raise ValueError('Render discovered changed or unpreviewed assets; include their times in preview')
        verification=verify_video(temp,frames,scene.meta['width'],scene.meta['height'],fps)
        verification['container_duration']=verify_container(scene.browser,temp,duration)
        if audio:
            decoded=decode(temp)
            audio_report.update(decoded_samples=len(decoded),
                                decoded_duration=len(decoded)/48000,
                                note='AAC decoder padding is reported; gapless player behavior needs audition.')
        if out.exists(): raise FileExistsError(out)
        temp.rename(out)
    report={'kind':'Encoded Video','status':'NEEDS_REVIEW','source':str(scene.path),'source_sha256':digest(scene.path),'resources':scene.resources,'output':str(out),'output_sha256':digest(out),'html_sha256':digest(scene.path),'input_samples':frames*subframes,
            'subframes':subframes,'sampling':'midpoints of four equal subintervals per frame, no terminal duplicate',
            'video':verification,'audio':audio_report,'browser_errors':scene.errors,
            'preview_receipt':str(receipt.resolve()),'visual_review':'caller must inspect previews and final playback'}
    dump(out.with_suffix('.render.json'),report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='Verify encoder and a real browser launch')
    for name in ('preview','check','render'):
        p=sub.add_parser(name)
        p.add_argument('html',type=Path); p.add_argument('--out',type=Path,required=True)
        if name=='render':
            p.add_argument('--reviewed-preview',type=Path,required=True,help='receipt.json of preview the caller has inspected')
            p.add_argument('--audio',type=Path); p.add_argument('--silent',action='store_true')
    args=parser.parse_args()
    if args.command=='doctor':
        encoder=ffmpeg_exe()
        version=subprocess.run([encoder,'-version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
        with sync_playwright() as pw:
            browser,_=launch(pw)
            result={'ffmpeg':encoder,'version':version,'chromium':browser.version}
            browser.close()
    else:
        with Scene(args.html) as scene:
            if args.command=='preview': result=preview(scene,args.out)
            elif args.command=='check': result=check_scene(scene,args.out)
            else: result=render(scene,args.out,args.reviewed_preview,args.audio,args.silent)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
