
(function(){
  var U=100, KEYS=__KEYS__;
  function $(id){ return document.getElementById(id); }
  var zoomEl=$("zoom"), zinBtn=$("zin"), zoutBtn=$("zout"), MINZ=0.25, MAXZ=16;
  var active=KEYS[0], pane={};
  KEYS.forEach(function(k){
    pane[k]={ wrap:$("cv-"+k), svg:$("sv-"+k), tab:$("tab-"+k) };
  });
  function settle(){}                   // nothing is typed here for a moving sheet to leave behind
__VIEW__
  $("notes").addEventListener("click",function(){
    var off=document.body.classList.toggle("noinfo");
    this.setAttribute("aria-expanded",off?"false":"true");
    setView(active,pane[active].view);
  });

  // ---- one finger or the mouse drags the sheet; two fingers pinch it
  KEYS.forEach(function(k){
    var svg=pane[k].svg, down={}, from=null;
    function ids(){ return Object.keys(down); }
    function gap(){ var i=ids(), a=down[i[0]], b=down[i[1]]; return Math.hypot(a.x-b.x,a.y-b.y)||1; }
    function hold(){                     // again whenever a finger lands or lifts
      var i=ids(), v=pane[k].view;
      from = i.length===1 ? {x:down[i[0]].x,y:down[i[0]].y,cx:v.cx,cy:v.cy}
           : i.length===2 ? {gap:gap(),z:v.z} : null;
      svg.classList.toggle("held",i.length>0);
    }
    svg.addEventListener("pointerdown",function(ev){
      try{ svg.setPointerCapture(ev.pointerId); }catch(e){}
      down[ev.pointerId]={x:ev.clientX,y:ev.clientY}; hold();
    });
    svg.addEventListener("pointermove",function(ev){
      if(!down[ev.pointerId]||!from) return;
      down[ev.pointerId]={x:ev.clientX,y:ev.clientY};
      var i=ids(), v=pane[k].view, s=fit(k)/v.z;
      if(i.length===1) setView(k,{cx:from.cx-(ev.clientX-from.x)*s,cy:from.cy-(ev.clientY-from.y)*s,z:v.z});
      else {
        var a=down[i[0]], b=down[i[1]], p=toSvg(k,{clientX:(a.x+b.x)/2,clientY:(a.y+b.y)/2});
        if(p) zoomAt(k,from.z*gap()/from.gap,p.x*U,p.y*U);
      }
    });
    function up(ev){ delete down[ev.pointerId]; hold(); }
    svg.addEventListener("pointerup",up);
    svg.addEventListener("pointercancel",up);
  });

  function show(k){
    active=k;
    KEYS.forEach(function(o){
      var is=(o===k);
      pane[o].wrap.hidden=!is;
      pane[o].tab.setAttribute("aria-selected",is?"true":"false"); pane[o].tab.tabIndex=is?0:-1;
    });
    setView(k,pane[k].view);              // once it is on screen and has a size
    if(pane[k].tab.scrollIntoView) pane[k].tab.scrollIntoView({block:"nearest",inline:"nearest"});
  }
  // the sheets are the slides: the arrows go from one to the next
  function turn(d){
    var j=KEYS.indexOf(active)+d, on=document.activeElement===pane[active].tab;
    if(j<0||j>=KEYS.length) return;
    show(KEYS[j]); if(on) pane[KEYS[j]].tab.focus();
  }
  KEYS.forEach(function(k){ pane[k].tab.addEventListener("click",function(){ show(k); }); });
  document.addEventListener("keydown",function(ev){
    var key=ev.key||"";
    if(ev.altKey||ev.metaKey||ev.ctrlKey) return;
    if(key==="ArrowRight"||key==="ArrowLeft"){ ev.preventDefault(); turn(key==="ArrowRight"?1:-1); }
    else if(key==="+"||key==="=") step(1);
    else if(key==="-"||key==="_") step(-1);
    else if(key==="0") fitSheet(active);
    else if(key>="1"&&key<="9"&&key.length===1&&KEYS[+key-1]) show(KEYS[+key-1]);
  });

  show(KEYS[0]);
})();
