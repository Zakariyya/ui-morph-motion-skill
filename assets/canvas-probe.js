/* QA-only instrumentation of actual Canvas text calls; does not change drawing.
   Clips/occlusion cannot be recovered reliably: supply motionQA() for those. */
(() => {
 const proto=CanvasRenderingContext2D.prototype, original=proto.fillText;
 if(window.__qaCanvasInstalled)return;window.__qaCanvasInstalled=true;
 proto.fillText=function(text,x,y,maxWidth){
   const m=this.getTransform(),metrics=this.measureText(text),canvas=this.canvas;
   if(canvas.isConnected){
     const r=canvas.getBoundingClientRect(),sx=r.width/canvas.width,sy=r.height/canvas.height;
     const left=metrics.actualBoundingBoxLeft,right=metrics.actualBoundingBoxRight;
     const top=metrics.actualBoundingBoxAscent,bottom=metrics.actualBoundingBoxDescent;
     const points=[[x-left,y-top],[x+right,y-top],[x+right,y+bottom],[x-left,y+bottom]].map(([a,b])=>({x:r.x+(m.a*a+m.c*b+m.e)*sx,y:r.y+(m.b*a+m.d*b+m.f)*sy}));
     const xs=points.map(p=>p.x),ys=points.map(p=>p.y);
     const size=parseFloat(this.font.match(/([\d.]+)px/)?.[1]||'0');
     (window.__qaCanvasTexts??=[]).push({id:String(text),box:[Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)],fontSize:size*Math.hypot(m.c*sx,m.d*sy),opacity:this.globalAlpha,clipUnknown:true});
   }
   return maxWidth===undefined?original.call(this,text,x,y):original.call(this,text,x,y,maxWidth);
 };
})();
