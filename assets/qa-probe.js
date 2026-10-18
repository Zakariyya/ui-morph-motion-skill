/* Optional DOM telemetry. Canvas renderers return the same schema from motionQA(). */
window.MotionQA = {
  collect() {
    const rect=e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]};
    const opacity=e=>{let n=e,v=1;while(n){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden')return 0;v*=Number(s.opacity);n=n.parentElement;}return v;};
    const objects=[...document.querySelectorAll('[data-motion-id]')].map(e=>({id:e.dataset.motionId,box:rect(e),opacity:opacity(e)}));
    const texts=[...document.querySelectorAll('[data-qa-text]')].map(e=>{
      const s=getComputedStyle(e),r=document.createRange();r.selectNodeContents(e);
      const b=r.getBoundingClientRect();let clip=[0,0,innerWidth,innerHeight];
      for(let p=e.parentElement;p;p=p.parentElement){const style=getComputedStyle(p);
        if(/hidden|clip|scroll|auto/.test(style.overflow+style.overflowX+style.overflowY)){
          const a=rect(p),x=Math.max(clip[0],a[0]),y=Math.max(clip[1],a[1]);
          clip=[x,y,Math.max(0,Math.min(clip[0]+clip[2],a[0]+a[2])-x),Math.max(0,Math.min(clip[1]+clip[3],a[1]+a[3])-y)];
        }
      }
      const scale=e.offsetHeight?e.getBoundingClientRect().height/e.offsetHeight:1;
      return {id:e.dataset.qaText,box:[b.x,b.y,b.width,b.height],fontSize:parseFloat(s.fontSize)*scale,opacity:opacity(e),clip};
    });
    return {objects,texts};
  }
};
