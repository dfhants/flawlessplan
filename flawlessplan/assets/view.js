  // ---- zoom: each sheet is a window of fixed size on the page, looking at
  // its drawing. A view is the point at its middle and a zoom, where 100%
  // is the whole sheet fitted in the window.
  KEYS.forEach(function(k){
    var b=pane[k].svg.viewBox.baseVal;
    pane[k].base={x:b.x,y:b.y,w:b.width,h:b.height};
    pane[k].view={cx:b.x+b.width/2,cy:b.y+b.height/2,z:1};
  });
  // sheet units per screen pixel at 100%
  function fit(k){
    var b=pane[k].base, r=pane[k].svg.getBoundingClientRect();
    return r.width&&r.height ? Math.max(b.w/r.width,b.h/r.height) : 0;
  }
  function setView(k,v){
    var b=pane[k].base, r=pane[k].svg.getBoundingClientRect(), s=fit(k);
    v.z=Math.min(MAXZ,Math.max(MINZ,v.z));
    v.cx=Math.min(b.x+b.w,Math.max(b.x,v.cx)); v.cy=Math.min(b.y+b.h,Math.max(b.y,v.cy));
    pane[k].view=v;
    if(k===active){
      zoomEl.textContent=Math.round(100*v.z)+"%";
      zinBtn.disabled=v.z>=MAXZ; zoutBtn.disabled=v.z<=MINZ;
    }
    if(!s) return;                       // hidden: applied when its tab is shown
    var w=r.width*s/v.z, h=r.height*s/v.z;
    pane[k].svg.setAttribute("viewBox",(v.cx-w/2)+" "+(v.cy-h/2)+" "+w+" "+h);
  }
  // to zoom `z` keeping the sheet point (px, py) under the same screen point
  function zoomAt(k,z,px,py){
    var v=pane[k].view; z=Math.min(MAXZ,Math.max(MINZ,z));
    var r=v.z/z;
    setView(k,{cx:px+(v.cx-px)*r,cy:py+(v.cy-py)*r,z:z});
  }
  // the buttons step through round figures, about the middle of the window
  var STEPS=[0.25,0.33,0.5,0.67,0.75,0.9,1,1.1,1.25,1.5,1.75,2,2.5,3,4,5,6,8,10,12,16];
  function step(d){
    var v=pane[active].view, z=v.z, i;
    settle();
    if(d>0){ for(i=0;i<STEPS.length;i++) if(STEPS[i]>z*1.001){ z=STEPS[i]; break; } }
    else { for(i=STEPS.length-1;i>=0;i--) if(STEPS[i]<z*0.999){ z=STEPS[i]; break; } }
    setView(active,{cx:v.cx,cy:v.cy,z:z});
  }
  function fitSheet(k){ var b=pane[k].base; settle(); setView(k,{cx:b.x+b.w/2,cy:b.y+b.h/2,z:1}); }
  zinBtn.addEventListener("click",function(){ step(1); });
  zoutBtn.addEventListener("click",function(){ step(-1); });
  $("zfit").addEventListener("click",function(){ fitSheet(active); });
  window.addEventListener("resize",function(){ settle(); setView(active,pane[active].view); });
  function toSvg(k,ev){
    var svg=pane[k].svg, ctm=svg.getScreenCTM(); if(!ctm) return null;
    var p=svg.createSVGPoint(); p.x=ev.clientX; p.y=ev.clientY;
    var q=p.matrixTransform(ctm.inverse());
    return {x:q.x/U,y:q.y/U};
  }
  KEYS.forEach(function(k){
    // pinch or ctrl/cmd + wheel zooms on the pointer; the wheel alone moves the sheet
    pane[k].svg.addEventListener("wheel",function(ev){
      var v=pane[k].view;
      ev.preventDefault(); settle();
      if(ev.ctrlKey||ev.metaKey){
        var p=toSvg(k,ev); if(!p) return;
        zoomAt(k,v.z*Math.exp(-ev.deltaY*(ev.deltaMode?0.05:0.01)),p.x*U,p.y*U);
      } else {
        var s=fit(k)/v.z*(ev.deltaMode?16:1);
        setView(k,{cx:v.cx+ev.deltaX*s,cy:v.cy+ev.deltaY*s,z:v.z});
      }
    },{passive:false});
  });
