#!/usr/bin/env python3
"""Timeline screenshots, beat sheets, scan, preflight, gates and focused repair evidence."""
import argparse, hashlib, io, json, math, sys
from pathlib import Path
from qa_checks import finding, gate, trajectory, readability, frame_diffs, contract_checks, region_checks


def dump(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sheet(paths,times,out):
    from PIL import Image,ImageDraw
    width=240;height=270;cols=4
    canvas=Image.new('RGB',(width*cols,height*math.ceil(len(paths)/cols)),'#eee')
    for i,(path,t) in enumerate(zip(paths,times)):
        tile=Image.open(path).convert('RGB');tile.thumbnail((width,width))
        x=i%cols*width;y=i//cols*height
        canvas.paste(tile,(x+(width-tile.width)//2,y))
        ImageDraw.Draw(canvas).text((x+5,y+245),f'{t:.4f}s / Timeline Still',fill='black')
    canvas.save(out)


def scan(scene,out,config,start=0,end=None,fps=None):
    from PIL import Image
    out.mkdir(parents=True,exist_ok=True)
    meta=scene.meta;end=meta['duration'] if end is None else end;fps=fps or meta['fps']
    if not (0<=start<end<=meta['duration'] and 0<fps<=1000):raise ValueError('Invalid scan range/FPS')
    # Include both sides of declared transitions at subframe distances.
    times={start+i/fps for i in range(math.ceil((end-start)*fps)) if start+i/fps<end}
    times.add(end)
    boundaries=config.get('boundaries',meta.get('boundaries',[]))
    for t in boundaries:
        times.update(t+d for d in (-2/fps,-1/fps,-.001,0,.001,1/fps,2/fps) if start<=t+d<=end)
    scene.page.add_script_tag(path=str(Path(__file__).resolve().parents[1]/'assets/canvas-probe.js'))
    times=sorted({round(t,9) for t in times});samples=[];frames=[];paths=[];stills=[];hits=[]
    for i,t in enumerate(times):
        scene.page.evaluate('window.__qaCanvasTexts=[]')
        probe=scene.at(t)
        telemetry=scene.page.evaluate('''async () => typeof window.motionQA==='function' ? await window.motionQA() :
            window.MotionQA ? window.MotionQA.collect() : {texts:window.__qaCanvasTexts||[]}''')
        item={'t':t,'probe':probe,**telemetry};samples.append(item)
        path=out/f'frame-{i:05d}.png';path.write_bytes(scene.page.screenshot(type='png',caret='hide',scale='css'));paths.append(path)
        im=Image.open(path).convert('RGB')
        hits+=region_checks(im,t,config.get('regions',[]))
        im.thumbnail((160,160));frames.append(im.copy())
        stills.append({'kind':'Timeline Still','time':t,'file':path.name,'sha256':sha(path),'source_sha256':sha(scene.path)})
        for hit in readability(item.get('texts',[]),meta,config.get('readability',{})):
            hits.append(dict(hit,t=t))
    # Out-of-order re-render compares actual pixels, not only author-supplied probes.
    for i in sorted(set([0,len(times)//3,len(times)//2,len(times)-1]),reverse=True):
        if hashlib.sha256(scene.capture(times[i])).hexdigest()!=stills[i]['sha256']:
            hits.append(finding('non-deterministic','FAIL',t=times[i]))
    hits+=trajectory(samples,config.get('limits',{}),config.get('exemptions',[]))
    if not config.get('limits'):hits.append(finding('motion-limits-missing'))
    hits+=frame_diffs(frames,times,config.get('frameThreshold',.15))
    hits+=contract_checks(dict(config,viewport=[0,0,meta['width'],meta['height']]),samples,stills)
    for window in config.get('readingWindows',[]):
        if start>window['start'] or end<window['end']:
            hits.append(finding('reading-window-not-covered',id=window['id']));continue
        relevant=[s for s in samples if window['start']<=s['t']<=window['end']]
        valid=[]
        for s in relevant:
            text=next((x for x in s.get('texts',[]) if x['id']==window['id'] and x.get('opacity',1)>.9),None)
            valid.append(bool(text) and not readability([text],meta,config.get('readability',{})))
        longest=run=0
        for i,ok in enumerate(valid):
            run=run+(relevant[i]['t']-relevant[i-1]['t']) if ok and i and valid[i-1] else 0
            longest=max(longest,run)
        if longest<window['minSeconds']:hits.append(finding('reading-window-short','FAIL',id=window['id'],seconds=longest))
    # Do not infer camera implementation from a numeric zoom probe alone.
    hits.append(finding('visual-review',checks=['shape identity and masks','color seams','composition','real-time playback','audio audition if applicable']))
    boundary_indices=sorted({i for i,t in enumerate(times) if any(abs(t-b)<=2/fps+.00001 for b in boundaries)})
    if boundary_indices:sheet([paths[i] for i in boundary_indices],[times[i] for i in boundary_indices],out/'boundaries.png')
    candidates=sorted({i for h in hits if 't' in h for i,t in enumerate(times) if abs(t-h['t'])<=1/fps+.00001})
    # Keep all source frames; the overview is bounded, incident timestamps remain complete.
    if candidates:sheet([paths[i] for i in candidates[:80]],[times[i] for i in candidates[:80]],out/'candidates.png')
    report={'kind':'Timeline Scan','status':gate(hits),'source':str(scene.path),'source_sha256':sha(scene.path),'resources':scene.resources,
        'metadata':meta,'config':config,'range':[start,end],'sample_fps':fps,'sample_count':len(times),
        'evidence_type':'Timeline Still','stills':stills,'samples':samples,'findings':hits,
        'limits':'Sampled telemetry and pixels; Canvas boxes require author instrumentation. Pixel differences are candidates, not aesthetic verdicts.'}
    dump(out/'report.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('preflight');a.add_argument('manifest',type=Path);a.add_argument('--out',type=Path,required=True)
    g=sub.add_parser('gate');g.add_argument('manifest',type=Path);g.add_argument('--out',type=Path,required=True)
    for name in ('render','beats','scan','repair','replay'):
        a=sub.add_parser(name);a.add_argument('html',type=Path);a.add_argument('--out',type=Path,required=True)
        if name=='render':a.add_argument('--time',type=float,required=True)
        if name=='beats':a.add_argument('--bpm',type=float);a.add_argument('--beats',type=int)
        if name in ('scan','repair'):
            a.add_argument('--config',type=Path);a.add_argument('--start',type=float,default=0);a.add_argument('--end',type=float)
            a.add_argument('--fps',type=float)
        if name=='repair':a.add_argument('--before',type=Path,required=True)
    args=p.parse_args();report={}
    report_path=args.out.with_suffix('.json') if args.command=='render' else args.out/'report.json'
    try:
        if args.command=='doctor':
            from browser_env import diagnose
            report=diagnose(args.out)
        elif args.command=='preflight':
            from asset_preflight import preflight
            report=preflight(args.manifest)
        elif args.command=='gate':report=evaluate_gates(args.manifest)
        else:
            from render import Scene
            with Scene(args.html) as scene:
                if args.command=='render':
                    if not 0<=args.time<=scene.meta['duration']:raise ValueError('Time outside timeline')
                    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(scene.capture(args.time))
                    report={'status':'PASS','kind':'Timeline Still','time':args.time,'sha256':sha(args.out),
                        'source':str(scene.path),'source_sha256':sha(scene.path),'resources':scene.resources,'output':str(args.out.resolve()),'output_sha256':sha(args.out),
                        'meaning':'Screenshot capture passed; visual quality not adjudicated.'}
                elif args.command=='replay':
                    args.out.mkdir(parents=True,exist_ok=True)
                    timing=scene.page.evaluate("""async duration=>{
                        const started=performance.now(), samples=[];
                        while(true){await new Promise(requestAnimationFrame);const elapsed=(performance.now()-started)/1000;
                            const t=Math.min(duration,elapsed);await window.seek(t);samples.push({time:t,completed:(performance.now()-started)/1000});
                            if(elapsed>=duration)break;
                        }return samples;
                    }""",scene.meta['duration'])
                    (args.out/'last-frame.png').write_bytes(scene.capture(scene.meta['duration']))
                    report={'kind':'Browser Replay','status':'NEEDS_REVIEW','source':str(scene.path),
                        'source_sha256':sha(scene.path),'resources':scene.resources,'timing':timing,
                        'browser_errors':scene.errors,'note':'Actual requestAnimationFrame replay completed; timing/last frame do not replace human viewing or audio audition.'}
                    if scene.errors:report['status']='FAIL'
                elif args.command=='beats':
                    bpm=args.bpm or scene.meta.get('bpm');count=args.beats
                    if count is not None and (not bpm or bpm<=0 or count<=0):raise ValueError('Positive BPM/count required')
                    times=[i*60/bpm for i in range(count)] if count else scene.meta['beats']
                    if any(not 0<=t<scene.meta['duration'] for t in times):raise ValueError('Beat outside timeline')
                    args.out.mkdir(parents=True,exist_ok=True);paths=[]
                    for i,t in enumerate(times):
                        path=args.out/f'beat-{i:03d}.png';path.write_bytes(scene.capture(t));paths.append(path)
                    sheet(paths,times,args.out/'contact-sheet.png')
                    report={'status':'NEEDS_REVIEW','kind':'Beat Sheet','source':str(scene.path),'times':times,'source_sha256':sha(scene.path),
                        'resources':scene.resources,'frames':[{'file':x.name,'sha256':sha(x)} for x in paths]}
                else:
                    config=json.loads(args.config.read_text()) if args.config else scene.meta.get('qa',{})
                    report=scan(scene,args.out,config,args.start,args.end,args.fps)
                    if args.command=='repair':
                        before=json.loads(args.before.read_text())
                        if before.get('source')!=report['source']:raise ValueError('Repair must use the same source path')
                        report['repair']={'before_report':str(args.before.resolve()),'before_sha256':sha(args.before),
                            'before_source_sha256':before.get('source_sha256'),'after_source_sha256':report['source_sha256'],
                            'before_findings':len(before.get('findings',[])),'after_findings':len(report['findings']),
                            'status':'NEEDS_REVIEW','note':'Inspect local frames and affected boundaries; counts alone never prove repair.'}
    except Exception as exc:
        from browser_env import BrowserBlocked
        blocked=isinstance(exc,(BrowserBlocked,ImportError,FileNotFoundError))
        report={'status':'BLOCKED' if blocked else 'FAIL','error':str(exc),'attempts':getattr(exc,'attempts',[])}
        if blocked:report['recovery']='Run motion_qa.py doctor; install missing dependencies or use approved compatible runner. Keep sandbox enabled.'
    dump(report_path,report)
    print(json.dumps({'status':report['status'],'report':str(report_path)},ensure_ascii=False))
    return {'PASS':0,'NEEDS_REVIEW':0,'FAIL':1,'BLOCKED':2}[report['status']]


def validate_report(report,role,number,base=None):
    """Reject stale or mislabelled evidence before applying any human review."""
    status=report.get('status')
    if status not in ('PASS','FAIL','BLOCKED','NEEDS_REVIEW'):return 'FAIL'
    if status in ('BLOCKED','FAIL'):return status
    if base is not None:
        for artifact in report.get('stills',[])+report.get('frames',[]):
            file=Path(base)/artifact['file']
            if not file.is_file() or sha(file)!=artifact.get('sha256'):return 'FAIL'
    source=report.get('source')
    if source:
        if not Path(source).is_file() or sha(source)!=report.get('source_sha256'):return 'FAIL'
        for name,value in report.get('resources',{}).items():
            file=Path(source).parent/name
            if not file.is_file() or sha(file)!=value:return 'FAIL'
    audio=report.get('audio',{})
    if audio.get('mode')=='audio':
        file=Path(audio.get('source',''))
        if not file.is_file() or sha(file)!=audio.get('source_sha256'):return 'FAIL'
    output=report.get('output')
    if output and (not Path(output).is_file() or sha(output)!=report.get('output_sha256')):return 'FAIL'
    kind=report.get('kind')
    if role=='environment':
        file=Path(report.get('selftest_path',''))
        if kind!='Browser Doctor' or not file.is_file() or sha(file)!=report.get('selftest_sha256'):return 'FAIL'
    if role=='assets':
        manifest=Path(report.get('manifest',''))
        if kind!='Asset Preflight' or not manifest.is_file() or sha(manifest)!=report.get('manifest_sha256'):return 'FAIL'
        for asset in report.get('assets',[]):
            file=Path(report.get('asset_root',''))/asset['file']
            if not file.is_file() or sha(file)!=asset.get('sha256'):return 'FAIL'
    if role in ('qa','timeline'):
        if not source:return 'FAIL'
        if role=='qa':
            if kind!='Timeline Scan' or not report.get('sample_count') or not report.get('stills'):return 'FAIL'
            if number==5 and report.get('range')!=[0,report.get('metadata',{}).get('duration')]:return 'FAIL'
        elif kind not in ('Timeline Scan','Beat Sheet','Encoded Video'):return 'FAIL'
    if role=='encoded' and (kind!='Encoded Video' or not report.get('video',{}).get('decoded_frames')):return 'FAIL'
    # Narrative/creative approvals are review evidence, never executable PASS alone.
    if role in ('facts','blueprint','continuity','production','playback'):return 'NEEDS_REVIEW'
    return status


def evaluate_gates(path):
    spec=json.loads(path.read_text());result=[]
    for number in range(1,6):
        stage=next((g for g in spec.get('gates',[]) if g['number']==number),{})
        evidence=[]
        required={1:{'environment','assets','facts'},2:{'blueprint','continuity'},3:{'timeline','qa','playback'},4:{'production'},5:{'qa','encoded','playback'}}[number]
        missing=required-{e.get('role') for e in stage.get('evidence',[])}
        if missing:evidence.append(finding('required-evidence-missing','BLOCKED',roles=sorted(missing)))
        for entry in stage.get('evidence',[]):
            file=path.parent/entry['file']
            if not file.is_file():evidence.append(finding('evidence-missing','BLOCKED',file=str(file)));continue
            if sha(file)!=entry.get('sha256'):evidence.append(finding('evidence-stale','FAIL',file=str(file)));continue
            if entry.get('type')=='report':
                report=json.loads(file.read_text())
                evidence.append({'status':validate_report(report,entry.get('role'),number,file.parent),'file':str(file)})
            else:evidence.append({'status':'FAIL' if entry.get('role') in ('environment','assets','qa','encoded','timeline') else 'NEEDS_REVIEW','file':str(file)})
        # Human review is a separate evidence file with reviewer, decision, scope and source hashes.
        review=stage.get('review')
        if review:
            file=path.parent/review['file']
            if file.is_file() and sha(file)==review.get('sha256'):
                r=json.loads(file.read_text())
                bound={e['file']:e['sha256'] for e in stage.get('evidence',[])}
                if r.get('reviewer') and r.get('decision')=='PASS' and r.get('evidence')==bound:
                    evidence=[dict(e,status='PASS') if e['status']=='NEEDS_REVIEW' else e for e in evidence]
                else:evidence.append(finding('review-invalid'))
            else:evidence.append(finding('review-missing-or-stale'))
        if number in (1,2,3,4,5) and not review:evidence.append(finding('review-required'))
        state=gate(evidence)
        if number>1 and result[-1]['status']!='PASS':state='BLOCKED'
        result.append({'number':number,'name':stage.get('name'),'status':state,'evidence':evidence})
    return {'status':gate(result),'gates':result,'note':'Review records attest human decisions; tool cannot authenticate reviewer identity. Gate 2 requires creative approval in review.'}

def supervised():
    # Playwright driver startup can hang before its own launch timeout applies.
    import os, subprocess, signal
    if os.environ.get('UI_MORPH_QA_WORKER')=='1':return main()
    env=dict(os.environ,UI_MORPH_QA_WORKER='1')
    timeout=float(os.environ.get('UI_MORPH_QA_TIMEOUT','600' if any(x in sys.argv for x in ('scan','repair','beats')) else '60'))
    process=subprocess.Popen([sys.executable,__file__,*sys.argv[1:]],env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        stdout,stderr=process.communicate(timeout=timeout)
        print(stdout,end='');print(stderr,end='',file=sys.stderr);return process.returncode
    except subprocess.TimeoutExpired:
        if os.name=='posix':os.killpg(process.pid,signal.SIGTERM)
        else:process.terminate()
        try:stdout,stderr=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name=='posix':os.killpg(process.pid,signal.SIGKILL)
            else:process.kill()
            stdout,stderr=process.communicate()
        out=Path(sys.argv[sys.argv.index('--out')+1]) if '--out' in sys.argv else Path('qa-timeout')
        report_path=out.with_suffix('.json') if 'render' in sys.argv else out/'report.json'
        dump(report_path,{'status':'BLOCKED','error':'worker-timeout','timeout_seconds':timeout,
            'stdout':stdout,'stderr':stderr,'recovery':'Driver or browser stalled. Run doctor in an approved runner; preserve sandbox. UI_MORPH_QA_TIMEOUT can increase the explicit processing budget.'})
        print(json.dumps({'status':'BLOCKED','report':str(report_path)}));return 2

if __name__=='__main__':sys.exit(supervised())
