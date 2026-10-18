"""Local asset manifest validation. License evidence is recorded, never inferred."""
import json, subprocess
from pathlib import Path
from qa_checks import finding,gate


def preflight(manifest):
    from PIL import Image
    from media import ffmpeg_exe
    spec=json.loads(Path(manifest).read_text());root=Path(manifest).resolve().parent;hits=[];assets=[]
    for entry in spec.get('assets',[]):
        path=(root/entry['file']).resolve();item=dict(entry)
        if not path.is_relative_to(root):hits.append(finding('asset-outside-package','FAIL',file=entry['file']));continue
        if not path.is_file():hits.append(finding('asset-missing','BLOCKED',file=entry['file']));continue
        import hashlib
        item.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if not entry.get('license') or not entry.get('source'):hits.append(finding('license-unresolved',file=entry['file']))
        kind=entry.get('type')
        try:
            if kind=='image':
                if path.suffix.lower()=='.svg':
                    from playwright.sync_api import sync_playwright
                    from browser_env import launch
                    import base64
                    with sync_playwright() as pw:
                        browser,_=launch(pw)
                        try:
                            page=browser.new_page()
                            item['dimensions']=page.evaluate("async data=>{const im=new Image();im.src='data:image/svg+xml;base64,'+data;await im.decode();return [im.naturalWidth,im.naturalHeight]}",base64.b64encode(path.read_bytes()).decode())
                        finally:browser.close()
                else:
                    with Image.open(path) as im:im.load();item['dimensions']=list(im.size)
                expected=entry.get('minDimensions')
                if expected and any(a<b for a,b in zip(item['dimensions'],expected)):hits.append(finding('asset-resolution','FAIL',file=entry['file']))
            elif kind in ('video','audio'):
                result=subprocess.run([ffmpeg_exe(),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True,timeout=120)
                if result.returncode:raise ValueError(result.stderr)
                if kind=='video':
                    import io
                    frame=subprocess.run([ffmpeg_exe(),'-v','error','-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True,timeout=30).stdout
                    with Image.open(io.BytesIO(frame)) as im:item['dimensions']=list(im.size)
                    if entry.get('minDimensions') and any(a<b for a,b in zip(item['dimensions'],entry['minDimensions'])):hits.append(finding('asset-resolution','FAIL',file=entry['file']))
            elif kind=='font':
                if item['bytes']>spec.get('largeFontBytes',2000000):hits.append(finding('font-subset-recommended',file=entry['file'],bytes=item['bytes']))
                # Actual browser FontFace decoding is required, not file-extension acceptance.
                from playwright.sync_api import sync_playwright
                from browser_env import launch
                with sync_playwright() as pw:
                    browser,_=launch(pw)
                    try:
                        page=browser.new_page()
                        import base64
                        page.evaluate('''async data=>{const f=new FontFace('Preflight',`url(data:font/woff2;base64,${data})`); await f.load();document.fonts.add(f);if(!document.fonts.check('20px Preflight'))throw Error('Font failed');}''',base64.b64encode(path.read_bytes()).decode())
                        item['browser_font_loaded']=True
                    finally:browser.close()
            elif kind not in ('script','style','document'):hits.append(finding('asset-type-unverified',file=entry['file']))
            item['decode']='PASS'
        except Exception as exc:
            from browser_env import BrowserBlocked
            hits.append(finding('asset-decode','BLOCKED' if isinstance(exc,(BrowserBlocked,ImportError)) else 'FAIL',file=entry['file'],error=str(exc)))
        assets.append(item)
    if not spec.get('assets'):hits.append(finding('asset-manifest-empty'))
    hits.append(finding('license-review',detail='A declared license is evidence for review, not a legal determination.'))
    from hashlib import sha256
    return {'kind':'Asset Preflight','manifest':str(Path(manifest).resolve()),'manifest_sha256':sha256(Path(manifest).read_bytes()).hexdigest(),'asset_root':str(root),'status':gate(hits),'assets':assets,'findings':hits}
