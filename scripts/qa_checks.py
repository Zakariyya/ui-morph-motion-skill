"""Pure QA rules. Heuristics produce review candidates, never aesthetic PASS."""
import math


def finding(code,status='NEEDS_REVIEW',**details):
    return dict(code=code,status=status,**details)


def gate(evidence):
    states={e['status'] for e in evidence}
    for state in ('FAIL','BLOCKED','NEEDS_REVIEW'):
        if state in states:return state
    return 'PASS' if states=={'PASS'} else 'NEEDS_REVIEW'


def classify_error(message):
    s=message.lower()
    for words,category in [(['executable doesn','executable doesn’t','enoent'],'browser-missing'),
        (['shared libraries','missing dependencies'],'system-dependencies'),
        (['operation not permitted','sandbox','permission denied'],'sandbox-permission'),
        (['display','x server'],'display'), (['timeout'],'timeout')]:
        if any(w in s for w in words):return category
    return 'browser-launch' # DBus text alone never establishes failure.


def trajectory(samples,limits,exemptions=()):
    hits=[]
    for key,limit in limits.items():
        previous=None
        for a,b in zip(samples,samples[1:]):
            if key not in a['probe'] or key not in b['probe']:
                hits.append(finding('probe-missing',key=key,t=b['t']));continue
            dt=b['t']-a['t']
            if dt<=0:raise ValueError('Sample timestamps must increase')
            v=(b['probe'][key]-a['probe'][key])/dt
            acc=0 if previous is None else (v-previous[0])/((dt+previous[1])/2)
            for code,value,threshold in [('motion-speed',abs(v),limit.get('speed',math.inf)),
                                         ('motion-acceleration',abs(acc),limit.get('acceleration',math.inf))]:
                if value>threshold:
                    exemption=next((e for e in exemptions if e.get('approved') and e.get('reason') and
                        e.get('key')==key and e['start']<=a['t'] and b['t']<=e['end']),None)
                    hits.append(finding(code,'PASS' if exemption else 'NEEDS_REVIEW',key=key,
                        start=a['t'],t=b['t'],value=value,threshold=threshold,exemption=exemption))
            previous=(v,dt)
    return hits


def intersection_box(a,b):
    x=max(a[0],b[0]);y=max(a[1],b[1]);r=min(a[0]+a[2],b[0]+b[2]);d=min(a[1]+a[3],b[1]+b[3])
    return [x,y,max(0,r-x),max(0,d-y)]


def intersection(a,b):
    box=intersection_box(a,b)
    return box[2]*box[3]


def readability(texts,meta,policy):
    hits=[]; margin=policy.get('safeMargin',0);scale=policy.get('deviceWidth',meta['width'])/meta['width']
    safe=[margin,margin,meta['width']-2*margin,meta['height']-2*margin]
    visible=[x for x in texts if x.get('opacity',1)>.5]
    for x in visible:
        box=x['box'];area=box[2]*box[3]
        if x['fontSize']*scale<policy.get('minFont',12):hits.append(finding('text-small','NEEDS_REVIEW' if x.get('clipUnknown') else 'FAIL',id=x['id'],effectiveFont=x['fontSize']*scale))
        if intersection(box,safe)<area-.1:hits.append(finding('text-unsafe','NEEDS_REVIEW' if x.get('clipUnknown') else 'FAIL',id=x['id']))
        if x.get('clip') and intersection(box,x['clip'])<area-.1:hits.append(finding('text-clipped',id=x['id']))
    for i,a in enumerate(visible):
        for b in visible[i+1:]:
            if intersection(a['box'],b['box'])>1:hits.append(finding('text-overlap',ids=[a['id'],b['id']]))
    return hits


def frame_diffs(frames,times,threshold=.15):
    import numpy as np
    hits=[]
    diff=lambda a,b:float(np.mean(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)))/255)
    for i in range(1,len(frames)):
        d=diff(frames[i-1],frames[i])
        if d>threshold:hits.append(finding('frame-change',start=times[i-1],t=times[i],difference=d))
        if i<len(frames)-1:
            after=diff(frames[i],frames[i+1]);neighbor=diff(frames[i-1],frames[i+1])
            if min(d,after)>threshold and neighbor<min(d,after)*.3:
                hits.append(finding('flash-candidate',t=times[i],difference=d,neighborDifference=neighbor))
    return hits


def contract_checks(config,samples,stills):
    hits=[]
    if not samples or not any(s.get('objects') for s in samples):hits.append(finding('telemetry-missing'))
    if config.get('cameraRequired') and (not samples or not all(s.get('camera') for s in samples)):
        hits.append(finding('camera-missing','FAIL'))
    for still in stills:
        if still.get('kind')!='Timeline Still' or not still.get('sha256') or not still.get('source_sha256'):
            hits.append(finding('still-provenance','FAIL',still=still))
    for s in samples:
        for c in config.get('continuity',[]):
            if c['start']<=s['t']<=c['end']:
                visible=[o for o in s.get('objects',[]) if o['id'] in c['ids'] and o.get('opacity',1)>.05 and o['box'][2]*o['box'][3]>0]
                visible=[o for o in visible if intersection(intersection_box(o['box'],o.get('clip',o['box'])),config.get('viewport',o['box']))>0]
                if not visible:hits.append(finding('handoff-gap','FAIL',t=s['t'],ids=c['ids']))
        cursor=s.get('cursor')
        if cursor and config.get('pointerEvents'):
            events=sorted([e for e in config['pointerEvents'] if e['time']<=s['t']],key=lambda e:e['time'])
            expected=bool(events and events[-1]['type']=='press')
            if bool(cursor.get('pressed'))!=expected:hits.append(finding('pointer-event-mismatch','FAIL',t=s['t']))
        if cursor and cursor.get('dragging'):
            target=cursor.get('target')
            if not cursor.get('pressed'):hits.append(finding('drag-without-press','FAIL',t=s['t']))
            if target and math.hypot(cursor['x']-target[0],cursor['y']-target[1])>config.get('dragTolerance',2):
                hits.append(finding('drag-detached','FAIL',t=s['t']))
    return hits


def region_checks(image,t,regions):
    import numpy as np
    hits=[]
    for region in regions:
        if region['start']<=t<=region['end']:
            x,y,w,h=region['box'];crop=np.asarray(image.crop((x,y,x+w,y+h)).convert('L'),dtype=float)
            variation=float(crop.std())
            if variation<region['minStd']:
                hits.append(finding('low-detail-region',t=t,id=region['id'],std=variation,threshold=region['minStd']))
    return hits
