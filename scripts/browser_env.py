"""Safe Chromium launch, bounded compatibility retry and reproducible diagnostics."""
import os, platform, shutil, subprocess, sys
from pathlib import Path
from qa_checks import classify_error


class BrowserBlocked(RuntimeError):
    def __init__(self,attempts):
        self.attempts=attempts
        super().__init__('Chromium launch blocked; see attempts and recovery in report')


def launch(pw):
    explicit=os.environ.get('UI_MORPH_BROWSER')
    candidates=[explicit] if explicit else [None,shutil.which('google-chrome') or shutil.which('chromium')]
    attempts=[]
    for executable in dict.fromkeys(candidates):
        if executable is None and attempts:continue
        for args in ([],['--disable-dev-shm-usage','--disable-gpu']):
            try:
                browser=pw.chromium.launch(headless=True,executable_path=executable,
                    chromium_sandbox=True,timeout=12000,args=args)
                return browser,attempts
            except Exception as exc:
                attempts.append({'executable':executable or pw.chromium.executable_path,'args':args,
                    'category':classify_error(str(exc)),'log':str(exc)})
                if attempts[-1]['category'] in ('browser-missing','sandbox-permission','system-dependencies'):break
    raise BrowserBlocked(attempts)


def diagnose(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    info={'kind':'Browser Doctor','platform':platform.platform(),'python':sys.version,'uid':os.getuid() if hasattr(os,'getuid') else None,
          'display':os.environ.get('DISPLAY'),'wayland':os.environ.get('WAYLAND_DISPLAY'),
          'recovery':['Install browser with python -m playwright install chromium in the selected environment.',
            'Use playwright install-deps chromium with system administrator approval if libraries are missing.',
            'For sandbox permission errors use an approved host/CI runner with user namespaces; do not add --no-sandbox.',
            'Set UI_MORPH_BROWSER to a compatible Chromium executable, then rerun doctor.',
            'DBus warnings alone are harmless if screenshot self-test succeeds.']}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            binary=Path(os.environ.get('UI_MORPH_BROWSER',pw.chromium.executable_path))
            info.update(executable=str(binary),exists=binary.is_file(),executable_permission=os.access(binary,os.X_OK))
            if binary.is_file() and shutil.which('ldd'):
                info['ldd']=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,timeout=10).stdout
            if shutil.which('fc-list'):
                fonts=subprocess.run(['fc-list'],capture_output=True,text=True,timeout=10).stdout.splitlines()
                info['font_count']=len(fonts);info['font_sample']=fonts[:5]
            browser,attempts=launch(pw);info['attempts']=attempts
            try:
                page=browser.new_page(viewport={'width':320,'height':180})
                page.set_content('<body style="background:#eee;font:28px sans-serif">Motion QA 自检</body>')
                page.evaluate('document.fonts.ready')
                page.screenshot(path=str(out/'browser-selftest.png'))
                import hashlib
                info.update(status='PASS',chromium=browser.version,selftest='browser-selftest.png',selftest_path=str((out/'browser-selftest.png').resolve()),selftest_sha256=hashlib.sha256((out/'browser-selftest.png').read_bytes()).hexdigest())
            finally:browser.close()
    except Exception as exc:
        info.update(status='BLOCKED',error=str(exc),attempts=getattr(exc,'attempts',[]))
    return info
