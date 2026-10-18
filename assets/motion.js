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
  // Cubic Hermite keys share explicit endpoint velocities (units/second).
  function path(t, keys) {
    if (!keys.length || keys.some((k,i)=>i && k.t<=keys[i-1].t)) throw Error('Ordered path keys required');
    if(t<=keys[0].t) return {x:keys[0].x,y:keys[0].y};
    const last=keys[keys.length-1];
    if(t>=last.t) return {x:last.x,y:last.y};
    const i=keys.findIndex(k=>k.t>=t), a=keys[i-1], b=keys[i];
    const d=b.t-a.t,u=(t-a.t)/d;
    const h00=2*u**3-3*u**2+1,h10=u**3-2*u**2+u,h01=-2*u**3+3*u**2,h11=u**3-u**2;
    const value=k=>h00*a[k]+h10*d*(a['v'+k]??0)+h01*b[k]+h11*d*(b['v'+k]??0);
    return {x:value('x'),y:value('y')};
  }
  const evaluate=(value,t,fallback)=>typeof value==='function'?value(t):(value??fallback);
  function camera(t, {x=0,y=0,zoom=1,anchor={x:0,y:0},follow,lag=0}={}) {
    const target=follow?follow(t-lag):{x:0,y:0};
    const c={x:evaluate(x,t,0)+target.x,y:evaluate(y,t,0)+target.y,
      zoom:evaluate(zoom,t,1),anchor};
    if(!(c.zoom>0) || ![c.x,c.y,c.zoom,anchor.x,anchor.y].every(Number.isFinite)) throw Error('Invalid camera');
    return c;
  }
  const toScreen=(p,c)=>({x:c.anchor.x+(p.x-c.x)*c.zoom,y:c.anchor.y+(p.y-c.y)*c.zoom});
  const toWorld=(p,c)=>({x:c.x+(p.x-c.anchor.x)/c.zoom,y:c.y+(p.y-c.anchor.y)/c.zoom});
  const cameraMatrix=c=>[c.zoom,0,0,c.zoom,c.anchor.x-c.x*c.zoom,c.anchor.y-c.y*c.zoom];
  const api={clamp,smooth,mix,release,step,track,drag,path,camera,toScreen,toWorld,cameraMatrix};
  if (typeof module!=='undefined' && module.exports) module.exports=api;
  else root.Motion=api;
})(typeof window==='undefined' ? globalThis : window);
