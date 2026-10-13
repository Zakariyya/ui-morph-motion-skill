/* Inline this file in scene.html. Pure analytic motion; no frame history. */
(function (root) {
  'use strict';
  const clamp = (x, a=0, b=1) => Math.max(a, Math.min(b, x));
  const smooth = x => { x=clamp(x); return x*x*x*(x*(x*6-15)+10); };
  const mix = (a,b,p) => a+(b-a)*p;
  function release(t, position, velocity, target, omega=26, damping=1) {
    if (t <= 0) return position;
    if (!(omega>0 && damping>0 && damping<=1)) throw Error('Use 0 < damping <= 1, omega > 0');
    const a=position-target;
    if (damping===1) return target+(a+(velocity+omega*a)*t)*Math.exp(-omega*t);
    const wd=omega*Math.sqrt(1-damping*damping);
    return target+Math.exp(-damping*omega*t)*(a*Math.cos(wd*t)+(velocity+damping*omega*a)/wd*Math.sin(wd*t));
  }
  function step(t, omega=26, damping=1) {
    return t<=0 ? 0 : release(t, 0, 0, 1, omega, damping);
  }
  function track(t, initial, changes, omega=26, damping=1) {
    let value=initial, previous=initial;
    for (const change of changes) {
      value+=(change.value-previous)*step(t-change.t, change.omega??omega, change.damping??damping);
      previous=change.value;
    }
    return value;
  }
  function drag(t, {start,end,from,to,target,omega=26,damping=1}) {
    if (!(end>start)) throw Error('Drag end must follow start');
    if (t<start) return from;
    const velocity=(to-from)/(end-start);
    if (t<=end) return from+velocity*(t-start);
    return release(t-end,to,velocity,target,omega,damping);
  }
  const api={clamp,smooth,mix,release,step,track,drag};
  if (typeof module!=='undefined' && module.exports) module.exports=api;
  else root.Motion=api;
})(typeof window==='undefined' ? globalThis : window);
