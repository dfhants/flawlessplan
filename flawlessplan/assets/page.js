
(function(){
  var NS="http://www.w3.org/2000/svg", U=100;
  var KEYS=__KEYS__, LABEL=__LABELS__;
  function $(id){ return document.getElementById(id); }
  function all(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  var stagesEl=$("stages"), statusEl=$("status"), dotEl=$("dot"), posEl=$("pos"), countEl=$("count");
  var undoBtn=$("undo"), redoBtn=$("redo"), clearBtn=$("clear"), menuEl=$("clearmenu");
  var clearSheetBtn=$("clear-sheet"), clearAllBtn=$("clear-all");
  var zoomEl=$("zoom"), zinBtn=$("zin"), zoutBtn=$("zout"), MINZ=0.25, MAXZ=16;
  var tool="pen", db=null, local=false, marks=[], drag=null, pan=null, press=null, active=KEYS[0];
  var editor=null;                      // the text being typed onto the plan, if any
  var undoStack=[], redoStack=[];       // this visit's changes, each {added, removed}
  var held=null;                        // the tool to go back to when space is let go
  var SAVED="Saved — Claude can read these", UNSAVED="Not saved — marks stay in this browser";
  var CURSOR={note:"text",pan:"grab"}, TOOLKEY={d:"pen",t:"note",h:"pan"};
  function settle(){ closeEditor(true); }   // what is being typed lands before the sheet moves under it

  var pane={};
  KEYS.forEach(function(k){
    pane[k]={ wrap:$("cv-"+k), svg:$("sv-"+k), marks:$("mk-"+k), ghost:$("gh-"+k),
              info:$("in-"+k), tab:$("tab-"+k), list:document.createElement("section") };
    pane[k].list.className="marklist"; pane[k].info.appendChild(pane[k].list);
  });

__VIEW__
  // the notes panel takes room from the sheet, so the view is fitted again
  $("notes").addEventListener("click",function(){
    var off=document.body.classList.toggle("noinfo");
    this.setAttribute("aria-expanded",off?"false":"true");
    closeEditor(true); setView(active,pane[active].view);
  });

  // the drawing each sheet was traced from, over it, while asked for
  if($("source")) $("source").addEventListener("click",function(){
    var on_=document.body.classList.toggle("under"); this.setAttribute("aria-pressed",on_?"true":"false"); });

  function el(tag,a){var e=document.createElementNS(NS,tag);for(var k in a)e.setAttribute(k,a[k]);return e;}
  function status(t,s){ statusEl.textContent=t; dotEl.className="dot"+(s?" "+s:""); }
  function sheetOf(m){ return m.sheet||KEYS[0]; }
  // a mark is open until whoever built it in says so; then it is resolved:
  // kept, out of the way, and shown in grey when asked for, on the sheet it
  // was drawn on and on every sheet it was applied to
  function isDone(m){ return m.status==="resolved"; }
  // blocked (it needs the engine changed, or something only the owner knows)
  // and question (Claude asked something) stay in sight until the owner replies
  function waiting(m){ return m.status==="blocked"||m.status==="question"; }
  var STATE={blocked:"Blocked",question:"Claude asks"};
  function applied(m){ return Array.isArray(m.applied)?m.applied.filter(function(a){return typeof a==="string";}):[]; }
  function on(k){ return marks.filter(function(m){return !isDone(m)&&sheetOf(m)===k;}); }
  function done(k){ return marks.filter(function(m){
    return isDone(m)&&(sheetOf(m)===k||applied(m).indexOf(k)>=0); }); }
  function openMarks(){ return marks.filter(function(m){return !isDone(m)&&pane[sheetOf(m)];}); }   // of the sheets that show
  var showDone=false, asking=null;      // whether resolved marks are drawn; the mark being asked about, by its time
  function plural(n){ return n+(n===1?" mark":" marks"); }
  function r2(v){ return Math.round(v*100)/100; }
  function fmt(n){ return (Math.round(n*100)/100).toFixed(2); }

  // a comment is a numbered pin, or a box with its pin at a corner; what it
  // says is in the list beside the sheet, where it neither hides the drawing
  // nor runs off its edge. Every mark on a sheet has a number, in the order
  // drawn, and keeps it: the brief Claude reads numbers them the same way.
  var numbers={};
  function isComment(m){ return m.type==="note"||m.type==="box"; }
  function numberAll(){
    numbers={}; var n={};
    marks.slice().sort(function(a,b){ return (a.ts||0)-(b.ts||0); }).forEach(function(m){
      var k=sheetOf(m); n[k]=(n[k]||0)+1; numbers[m.ts]=n[k]; });
  }
  function pin(g,x,y,num){
    g.appendChild(el("circle",{cx:x*U,cy:y*U,r:17,"class":"mk-pin"}));
    var t=el("text",{x:x*U,y:y*U+7,"class":"mk-pinno"}); t.textContent=String(num); g.appendChild(t);
  }
  function node(m){
    var g=el("g",{"class":isDone(m)?"done":waiting(m)?"waiting":"","data-ts":String(m.ts)});
    if(m.type==="pen"){
      g.appendChild(el("polyline",{points:(m.pts||[]).map(function(p){return (p[0]*U)+","+(p[1]*U);}).join(" "),"class":"mk-pen"}));
    } else if(m.type==="note"){
      pin(g,m.x,m.y,numbers[m.ts]||"?");
    } else if(m.type==="box"&&m.box){
      var b=m.box, x0=Math.min(b[0],b[2]), y0=Math.min(b[1],b[3]);
      g.appendChild(el("rect",{x:x0*U,y:y0*U,width:Math.abs(b[2]-b[0])*U,height:Math.abs(b[3]-b[1])*U,"class":"mk-box"}));
      pin(g,x0,y0,numbers[m.ts]||"?");
    }
    return g;
  }
  function render(){
    numberAll();
    KEYS.forEach(function(k){
      var g=pane[k].marks; while(g.firstChild)g.removeChild(g.firstChild);
      (showDone?done(k):[]).concat(on(k)).forEach(function(m){g.appendChild(node(m));});
      list(k);
    });
    refresh();
  }
  // ---- the marks of a sheet, listed under its notes: what each is, how it
  // was dealt with, and the one way a mark leaves for good
  function words(tag,cls,text){ var e=document.createElement(tag); if(cls) e.className=cls; e.textContent=text; return e; }
  function clock(ts){ var d=new Date(ts); return isFinite(d)?d.toLocaleString([], {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):""; }
  function hot(m,is){
    all('#mk-'+active+' g').forEach(function(g){ if(g.getAttribute("data-ts")===String(m.ts)) g.classList.toggle("hot",is); });
  }
  // a mark deleted is not one undo or redo can bring back
  function forget(m){
    function without(stack){ return stack.filter(function(op){
      return !op.added.concat(op.removed).some(function(o){ return o.ts===m.ts; }); }); }
    undoStack=without(undoStack); redoStack=without(redoStack);
  }
  function list(k){
    var box=pane[k].list, was=box.contains(document.activeElement)?document.activeElement.getAttribute("data-do"):null;
    while(box.firstChild) box.removeChild(box.firstChild);
    var open=on(k), dealt=done(k);
    if(!open.length&&!dealt.length) return;
    box.appendChild(words("h3","","Marks"));
    if(dealt.length){
      var lab=words("label","showdone",""), cb=document.createElement("input");
      cb.type="checkbox"; cb.checked=showDone; cb.setAttribute("data-do","show");
      cb.addEventListener("change",function(){ showDone=cb.checked; asking=null; render(); });
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" Show resolved ("+dealt.length+")"));
      box.appendChild(lab);
    }
    var ul=document.createElement("ul");
    open.concat(showDone?dealt:[]).forEach(function(m){
      var li=document.createElement("li"); if(isDone(m)) li.className="done"; else if(waiting(m)) li.className="waiting";
      li.appendChild(words("span","num",String(numbers[m.ts]||"")));
      li.appendChild(words("span","what",isComment(m)?(m.text||"?"):"Stroke"));
      if(waiting(m)) li.appendChild(words("span","state",STATE[m.status]));
      li.appendChild(words("small","",clock(m.ts)+(Array.isArray(m.room)&&m.room.length?" · on "+m.room.join(", "):"")
        +(sheetOf(m)!==k?" · drawn on "+(LABEL[sheetOf(m)]||sheetOf(m)):"")));
      var said=replies(m);
      said.forEach(function(r){
        li.appendChild(words("small","reply "+r.by,(r.by==="agent"?"Claude":"You")+" · "+clock(r.ts)+": "+r.text));
      });
      if(isDone(m)){
        var to=applied(m).map(function(a){ return LABEL[a]||a; });
        li.appendChild(words("small","how","Resolved"+(m.resolved?" "+clock(m.resolved):"")
          +(m.how&&!said.some(function(r){return r.by==="agent"&&r.text===m.how;})?": "+m.how:"")
          +(to.length?" · applied to "+to.join(", "):"")));
      }
      if(local||db){
        var form=document.createElement("form"); form.className="replyto";
        var box=document.createElement("input"); box.type="text"; box.maxLength=300;
        box.placeholder=isDone(m)||waiting(m)?"Reply — this opens it again":"Reply";
        box.setAttribute("aria-label","Reply to mark "+(numbers[m.ts]||""));
        form.appendChild(box);
        form.addEventListener("submit",function(ev){ ev.preventDefault(); answer(m,box.value); });
        li.appendChild(form);
      }
      var row=words("span","acts","");
      if(asking===m.ts){
        row.appendChild(words("span","sure","Delete for good?"));
        var yes=words("button","del","Delete"), no=words("button","","Keep");
        yes.setAttribute("data-do","yes"); no.setAttribute("data-do","no");
        yes.addEventListener("click",function(){ asking=null; forget(m); commit([],[m],"Deleted for good."); });
        no.addEventListener("click",function(){ asking=null; render(); });
        row.appendChild(yes); row.appendChild(no);
      } else {
        var del=words("button","","Delete…"); del.setAttribute("data-do","ask");
        del.setAttribute("aria-label","Delete this mark for good");
        del.addEventListener("click",function(){ asking=m.ts; render(); });
        row.appendChild(del);
      }
      li.appendChild(row);
      li.addEventListener("mouseenter",function(){ hot(m,true); });
      li.addEventListener("mouseleave",function(){ hot(m,false); });
      ul.appendChild(li);
    });
    box.appendChild(ul);
    // the keyboard stays where it was: on Keep, never on Delete, once the question is put
    if(was==="ask"||was==="show"){ var b=box.querySelector('[data-do="'+(was==="ask"?"no":"show")+'"]'); if(b) b.focus(); }
  }
  // a reply from the owner: kept under the mark, and if the mark was resolved
  // it opens again, which is how the owner says it was not done
  function replies(m){ return (Array.isArray(m.replies)?m.replies:[]).filter(function(r){
    return r&&(r.by==="agent"||r.by==="owner")&&typeof r.text==="string"; }); }
  function answer(m,text){
    text=(text||"").trim().slice(0,300); if(!text) return;
    var c={}; for(var key in m) if(key!=="_id") c[key]=m[key];
    c.replies=replies(m).concat([{by:"owner",text:text,ts:Math.max(Date.now(),(m.resolved||0)+1)}]);
    var was=isDone(m)||waiting(m);
    if(was){ delete c.status; delete c.resolved; delete c.how; delete c.applied; }
    act([c],[m],was?"Replied: mark "+(numbers[m.ts]||"")+" is open again.":"Replied.");
  }
  // what each control can do just now: nothing is offered that would do nothing
  function refresh(){
    var here=on(active).length, n=openMarks().length;
    countEl.textContent=plural(here)+" on "+LABEL[active];
    undoBtn.disabled=!(undoStack.length||here); redoBtn.disabled=!redoStack.length;
    clearBtn.disabled=!n; if(!n) menu(false);
    clearSheetBtn.disabled=!here; clearSheetBtn.lastElementChild.textContent=here;
    clearAllBtn.disabled=!n; clearAllBtn.lastElementChild.textContent=n;
    KEYS.forEach(function(k){
      var c=on(k).length, b=pane[k].tab.lastElementChild;
      b.hidden=!c; b.textContent=c; b.title=plural(c)+" drawn on this sheet";
    });
  }
  function clearGhost(){ KEYS.forEach(function(k){ var g=pane[k].ghost;
    while(g.firstChild)g.removeChild(g.firstChild); });
    if(editor) editor.at.appendChild(editor.dot); }      // but for the dot of a note being typed

  // Served by `flawlessplan serve`, the whole list is kept in houses/<house>/marks.json.
  // Saves go one after another, so the last list sent is the one that lands.
  var saving=Promise.resolve();
  function put(said){
    var body=JSON.stringify(marks);
    saving=saving.then(function(){
      return fetch("marks.json",{method:"PUT",headers:{"Content-Type":"application/json"},body:body})
        .then(function(r){ if(!r.ok) throw 0; status(said?said+" Saved.":SAVED,"on"); })
        ["catch"](function(){ status("Save failed — is the server still running?","off"); });
    });
  }

  // ---- every change to the marks goes through here: drawing, undo, redo
  // and clearing are all some marks put in and some taken out. A mark is
  // known by its time, which survives a reload and a round trip to the store.
  function where(m){ for(var i=0;i<marks.length;i++) if(marks[i].ts===m.ts) return i; return -1; }
  function commit(adds,removes,said){
    removes.forEach(function(m){
      var i=where(m); if(i<0) return;
      var gone=marks.splice(i,1)[0];
      if(db&&gone._id) db.doc("marks/"+gone._id)["delete"]()["catch"](function(){});
    });
    adds.forEach(function(m){
      if(where(m)>=0) return;
      var c={}; for(var key in m) if(key!=="_id") c[key]=m[key];
      marks.push(c);
      if(db) db.collection("marks").add(c).then(function(ref){ c._id=ref.id; })
        ["catch"](function(e){ status("Save failed ("+((e&&e.code)||"error")+")","off"); });
    });
    marks.sort(function(a,b){ return (a.ts||0)-(b.ts||0); });
    render();
    if(local) put(said);
    else if(db) status(said||SAVED,"on");
    else status((said?said+" ":"")+UNSAVED,"off");
  }
  function act(adds,removes,said){
    undoStack.push({added:adds,removed:removes}); redoStack=[];
    commit(adds,removes,said);
  }
  var lastTs=0;
  function add(m){
    m.ts=lastTs=Math.max(Date.now(),lastTs+1); m.id="m"+m.ts.toString(36); m.sheet=active;
    if(isComment(m)&&VERSION) m.version=VERSION;           // the house file it was made on
    act([m],[],"");
  }
  // a change made on one sheet is undone where it can be seen
  function goTo(op){
    var ms=op.added.concat(op.removed), s=ms.length&&sheetOf(ms[0]);
    if(s&&s!==active&&pane[s]&&ms.every(function(m){return sheetOf(m)===s;})) show(s);
  }
  // With nothing from this visit left to undo, undo takes the sheet's last
  // mark, as it always did, so marks from an earlier visit can still go.
  function undo(){
    closeEditor(false);
    var op=undoStack.pop();
    if(!op){ var mine=on(active), m=mine[mine.length-1]; if(!m) return; op={added:[m],removed:[]}; }
    goTo(op); redoStack.push(op); commit(op.removed,op.added,"Undone.");
  }
  function redo(){
    var op=redoStack.pop(); if(!op) return;
    closeEditor(false);
    goTo(op); undoStack.push(op); commit(op.added,op.removed,"Redone.");
  }
  function clear(list,place){
    menu(false);
    if(list.length) act([],list.slice(),"Cleared "+plural(list.length)+" on "+place+"; Undo brings them back.");
  }

  // ---- text is typed where it goes: click the plan, type, Enter. The click
  // leaves the note's dot there at once, and the field opens beside it, as
  // the words will stand beside the dot.
  function openEditor(k,p,ev,box){
    closeEditor(true);
    var r=stagesEl.getBoundingClientRect(), W=220, H=34, inp=document.createElement("input");
    inp.type="text"; inp.maxLength=300; inp.className="note-edit";
    inp.placeholder="Type, then Enter"; inp.setAttribute("aria-label","Text to put on the plan here");
    var x=ev.clientX-r.left, G=14;
    if(x+G+W>r.width-4) x-=G+W; else x+=G;       // on the other side of the dot where there is no room
    inp.style.left=Math.max(4,x)+"px";
    inp.style.top=Math.max(4,Math.min(r.height-H-4,ev.clientY-r.top-H/2))+"px";
    inp.addEventListener("keydown",function(e){
      if(e.key==="Enter"){ e.preventDefault(); closeEditor(true); }
      else if(e.key==="Escape"){ e.preventDefault(); closeEditor(false); }
    });
    inp.addEventListener("blur",function(){ closeEditor(true); });
    editor={el:inp,x:p.x,y:p.y,box:box||null,at:pane[k].ghost,dot:el("g",{})};
    if(box) editor.dot.appendChild(el("rect",{x:Math.min(box[0],box[2])*U,y:Math.min(box[1],box[3])*U,
      width:Math.abs(box[2]-box[0])*U,height:Math.abs(box[3]-box[1])*U,"class":"mk-box"}));
    pin(editor.dot,box?Math.min(box[0],box[2]):p.x,box?Math.min(box[1],box[3]):p.y,(on(k).length+done(k).length)+1);
    editor.at.appendChild(editor.dot);
    stagesEl.appendChild(inp); inp.focus();
  }
  function closeEditor(keep){
    var ed=editor; if(!ed) return;
    editor=null;                         // first: taking the field out blurs it, which comes back here
    var txt=ed.el.value.trim();
    clearGhost();
    if(ed.el.parentNode) ed.el.parentNode.removeChild(ed.el);
    if(keep&&txt&&ed.box) add({type:"box",box:ed.box.map(r2),text:txt.slice(0,300)});
    else if(keep&&txt) add({type:"note",x:r2(ed.x),y:r2(ed.y),text:txt.slice(0,300)});
  }

  KEYS.forEach(function(k){
    var svg=pane[k].svg;
    svg.addEventListener("pointerdown",function(ev){
      var p=toSvg(k,ev); if(!p) return;
      menu(false);
      if(tool==="note"){ press={x:ev.clientX,y:ev.clientY,p:p}; try{ svg.setPointerCapture(ev.pointerId); }catch(e){} return; }   // placed on the way up, once the last text has landed
      try{ svg.setPointerCapture(ev.pointerId); }catch(e){}
      if(tool==="pan"){
        pan={px:ev.clientX,py:ev.clientY,cx:pane[k].view.cx,cy:pane[k].view.cy};
        svg.style.cursor="grabbing"; return;
      }
      drag={type:"pen",pts:[[r2(p.x),r2(p.y)]]};
    });
    svg.addEventListener("pointermove",function(ev){
      var p=toSvg(k,ev); if(!p) return;
      posEl.textContent=fmt(p.x)+", "+fmt(p.y)+" m";
      if(pan){
        var v=pane[k].view, s=fit(k)/v.z;
        setView(k,{cx:pan.cx-(ev.clientX-pan.px)*s,cy:pan.cy-(ev.clientY-pan.py)*s,z:v.z});
        return;
      }
      if(press&&tool==="note"&&(Math.abs(ev.clientX-press.x)>=6||Math.abs(ev.clientY-press.y)>=6)){
        clearGhost();                     // a drag with the comment tool is a box
        pane[k].ghost.appendChild(el("rect",{x:Math.min(press.p.x,p.x)*U,y:Math.min(press.p.y,p.y)*U,
          width:Math.abs(p.x-press.p.x)*U,height:Math.abs(p.y-press.p.y)*U,"class":"mk-box"}));
        return;
      }
      if(!drag) return;
      clearGhost();
      var last=drag.pts[drag.pts.length-1];
      if(Math.abs(p.x-last[0])>0.04||Math.abs(p.y-last[1])>0.04) drag.pts.push([r2(p.x),r2(p.y)]);
      pane[k].ghost.appendChild(el("polyline",{points:drag.pts.map(function(q){return (q[0]*U)+","+(q[1]*U);}).join(" "),"class":"mk-pen"}));
    });
    svg.addEventListener("pointerup",function(ev){
      if(pan){ pan=null; svg.style.cursor=CURSOR[tool]||""; return; }
      if(press){
        var still=Math.abs(ev.clientX-press.x)<6&&Math.abs(ev.clientY-press.y)<6, p=toSvg(k,ev), from=press.p;
        press=null; clearGhost();
        if(p&&tool==="note") openEditor(k,p,ev,still?null:[from.x,from.y,p.x,p.y]);
        return;
      }
      if(!drag) return;
      clearGhost();
      if(drag.pts.length>1) add({type:"pen",pts:drag.pts});
      drag=null;
    });
    svg.addEventListener("pointercancel",function(){drag=null;pan=null;press=null;clearGhost();});
  });

  function show(k){
    closeEditor(true);
    active=k; drag=null; pan=null; press=null; clearGhost();
    KEYS.forEach(function(o){
      var is=(o===k);
      pane[o].wrap.hidden=!is; pane[o].info.hidden=!is;
      pane[o].tab.setAttribute("aria-selected",is?"true":"false"); pane[o].tab.tabIndex=is?0:-1;
    });
    setView(k,pane[k].view);              // once it is on screen and has a size
    if(pane[k].tab.scrollIntoView) pane[k].tab.scrollIntoView({block:"nearest",inline:"nearest"});
    refresh();
  }
  function setTool(t){
    closeEditor(true);
    tool=t;
    all("[data-tool]").forEach(function(b){
      var is=b.getAttribute("data-tool")===t;
      b.setAttribute("aria-checked",is?"true":"false"); b.tabIndex=is?0:-1;
    });
    KEYS.forEach(function(k){ pane[k].svg.style.cursor=CURSOR[t]||""; });
  }
  function menu(open){
    if(menuEl.hidden===!open) return;
    menuEl.hidden=!open; clearBtn.setAttribute("aria-expanded",open?"true":"false");
    if(open) (clearSheetBtn.disabled?clearAllBtn:clearSheetBtn).focus();
  }

  // one stop in the tab order for each group; the arrows move inside it
  function rove(items,back,on_,pick){
    items.forEach(function(b,i){
      b.addEventListener("keydown",function(ev){
        if(ev.altKey) return;                 // alt and an arrow moves a tab itself
        var n=items.length, j=ev.key===on_?(i+1)%n : ev.key===back?(i+n-1)%n :
                              ev.key==="Home"?0 : ev.key==="End"?n-1 : -1;
        if(j<0||items[j].disabled) return;
        ev.preventDefault(); items[j].focus(); if(pick) pick(items[j]);
      });
    });
  }
  var tabs=KEYS.map(function(k){ return pane[k].tab; }), tools=all("[data-tool]");
  tabs.forEach(function(b){ b.addEventListener("click",function(){ show(b.getAttribute("data-sheet")); }); });
  tools.forEach(function(b){ b.addEventListener("click",function(){ held=null; setTool(b.getAttribute("data-tool")); }); });
  rove(tabs,"ArrowLeft","ArrowRight",function(b){ show(b.getAttribute("data-sheet")); });
  rove(tools,"ArrowUp","ArrowDown",function(b){ setTool(b.getAttribute("data-tool")); });
  rove([clearSheetBtn,clearAllBtn],"ArrowUp","ArrowDown");

  // ---- the sheets themselves: their order, which are hidden, one binned.
  // Each is a change to the house file, made by the server the way an
  // agent's tools make one: refused if the file is no longer the one this
  // page was drawn from, kept only if the house still solves. The page is
  // then drawn again and follows.
  var HIDDEN=__HIDDEN__, MOVABLE=__MOVABLE__, VERSION=__VERSION__;
  var sheetWrap=$("sheetwrap"), sheetBtn=$("sheets"), sheetMenu=$("sheetmenu"), binning=null, busy=false, dragging=null;
  function change(what,said){
    if(busy||!local) return;
    busy=true; what.version=VERSION; settle();
    status("Changing the house file\u2026","");
    fetch("sheets",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(what)})
      .then(function(r){ return r.json().then(function(j){ return {ok:r.ok,j:j}; },function(){ return {ok:false,j:null}; }); })
      .then(function(a){
        busy=false;
        if(!a.ok){ status((a.j&&a.j.error)||"The house file was not changed.","off"); follow(); return; }
        VERSION=a.j.version; status(said,"on"); follow();
      })["catch"](function(){ busy=false; status("Not changed \u2014 is the server still running?","off"); });
  }
  function sheetsMenu(open){
    sheetMenu.hidden=!open; sheetBtn.setAttribute("aria-expanded",open?"true":"false");
    if(!open){ binning=null; return; }
    while(sheetMenu.firstChild) sheetMenu.removeChild(sheetMenu.firstChild);
    var can=MOVABLE.indexOf(active)>=0&&MOVABLE.length>1;
    var hide=words("button","","Hide \u201c"+LABEL[active]+"\u201d");
    hide.setAttribute("role","menuitem"); hide.disabled=!can;
    hide.title=can?"It stays in the house file, drawn and checked, and comes back from this menu":"A house shows at least one sheet";
    hide.addEventListener("click",function(){ var k=active; sheetsMenu(false); change({hide:k},LABEL[k]+" is hidden."); });
    sheetMenu.appendChild(hide);
    if(HIDDEN.length) sheetMenu.appendChild(words("div","head","Hidden sheets"));
    HIDDEN.forEach(function(h){
      var row=words("div","row","");
      row.appendChild(words("span","name",h.label));
      if(binning===h.id){
        row.appendChild(words("span","sure","Bin for good?"));
        var yes=words("button","del","Bin"), no=words("button","","Keep");
        yes.addEventListener("click",function(){ sheetsMenu(false); change({bin:h.id},h.label+" is binned: it is out of the house file."); });
        no.addEventListener("click",function(){ binning=null; sheetsMenu(true); });
        row.appendChild(yes); row.appendChild(no);
      } else {
        var back=words("button","","Show"), bin=words("button","","Bin\u2026");
        back.setAttribute("aria-label","Show "+h.label+" again");
        bin.setAttribute("aria-label","Bin "+h.label+": take it out of the house file for good");
        back.addEventListener("click",function(){ sheetsMenu(false); change({show:h.id},h.label+" is back."); });
        bin.addEventListener("click",function(){ binning=h.id; sheetsMenu(true); var k=sheetMenu.querySelector(".row .sure+button+button"); if(k) k.focus(); });
        row.appendChild(back); row.appendChild(bin);
      }
      sheetMenu.appendChild(row);
    });
  }
  sheetBtn.addEventListener("click",function(){ closeEditor(true); sheetsMenu(sheetMenu.hidden); });
  $("nhidden").hidden=!HIDDEN.length; $("nhidden").textContent=HIDDEN.length;
  function clearDrop(){ all(".tab").forEach(function(b){ b.classList.remove("drop-before","drop-after"); }); }
  function reorder(k,to,after){
    var order=MOVABLE.filter(function(x){ return x!==k; });
    order.splice(order.indexOf(to)+(after?1:0),0,k);
    if(order.join("\n")!==MOVABLE.join("\n")) change({order:order},"The sheets are in their new order.");
  }
  // a tab is dragged along the row to where it should be; alt and an arrow does the same from the keys
  MOVABLE.forEach(function(k){
    var b=pane[k].tab;
    b.addEventListener("dragstart",function(ev){
      if(!local||busy){ ev.preventDefault(); return; }
      dragging=k; b.classList.add("dragging");
      try{ ev.dataTransfer.effectAllowed="move"; ev.dataTransfer.setData("text/plain",k); }catch(e){}
    });
    b.addEventListener("dragend",function(){ dragging=null; b.classList.remove("dragging"); clearDrop(); });
    b.addEventListener("dragover",function(ev){
      if(!dragging||dragging===k) return;
      ev.preventDefault(); clearDrop();
      var r=b.getBoundingClientRect();
      b.classList.add(ev.clientX<r.left+r.width/2?"drop-before":"drop-after");
    });
    b.addEventListener("drop",function(ev){
      if(!dragging||dragging===k) return;
      ev.preventDefault();
      var r=b.getBoundingClientRect(), from=dragging;
      dragging=null; clearDrop();
      reorder(from,k,ev.clientX>=r.left+r.width/2);
    });
    b.addEventListener("keydown",function(ev){
      var d=ev.key==="ArrowLeft"?-1:ev.key==="ArrowRight"?1:0, i=MOVABLE.indexOf(k);
      if(!ev.altKey||!d||!local) return;
      ev.preventDefault();
      if(MOVABLE[i+d]) reorder(k,MOVABLE[i+d],d>0);
    });
  });
  // only a served page can change the house file: until it is known to be one, nothing offers to
  function sheetsReady(){
    sheetWrap.hidden=false;
    MOVABLE.forEach(function(k){ pane[k].tab.draggable=MOVABLE.length>1;
      pane[k].tab.setAttribute("aria-keyshortcuts","Alt+ArrowLeft Alt+ArrowRight"); });
  }

  undoBtn.addEventListener("click",undo);
  redoBtn.addEventListener("click",redo);
  clearBtn.addEventListener("click",function(){ closeEditor(true); menu(menuEl.hidden); });
  clearSheetBtn.addEventListener("click",function(){ clear(on(active),LABEL[active]); });
  clearAllBtn.addEventListener("click",function(){ clear(openMarks(),"every sheet"); });
  document.addEventListener("pointerdown",function(ev){
    if(!menuEl.hidden&&!menuEl.contains(ev.target)&&!clearBtn.contains(ev.target)) menu(false);
    if(!sheetMenu.hidden&&!sheetMenu.contains(ev.target)&&!sheetBtn.contains(ev.target)) sheetsMenu(false);
  });

  // ---- keys. Not while typing; space pans for as long as it is held.
  document.addEventListener("keydown",function(ev){
    var t=ev.target, key=(ev.key||"").toLowerCase();
    if(t&&(t.tagName==="INPUT"||t.tagName==="TEXTAREA"||t.isContentEditable)) return;
    if(ev.altKey) return;
    if(ev.metaKey||ev.ctrlKey){
      if(key==="z"){ ev.preventDefault(); if(ev.shiftKey) redo(); else undo(); }
      else if(key==="y"){ ev.preventDefault(); redo(); }
      return;
    }
    if(key==="escape"){
      if(!menuEl.hidden){ menu(false); clearBtn.focus(); }
      else if(!sheetMenu.hidden){ sheetsMenu(false); sheetBtn.focus(); }
      else if(drag){ drag=null; clearGhost(); }
      return;
    }
    if(key===" "){
      if(t&&t.closest&&t.closest("button,a")) return;     // space presses the button it is on
      ev.preventDefault();
      if(!ev.repeat&&held===null&&!drag&&tool!=="pan"){ held=tool; setTool("pan"); }
      return;
    }
    if(TOOLKEY[key]){ held=null; setTool(TOOLKEY[key]); }
    else if(key==="+"||key==="=") step(1);
    else if(key==="-"||key==="_") step(-1);
    else if(key==="0") fitSheet(active);
    else if(key>="1"&&key<="9"&&key.length===1&&KEYS[+key-1]) show(KEYS[+key-1]);
  });
  document.addEventListener("keyup",function(ev){
    if(ev.key===" "&&held!==null){ var back=held; held=null; setTool(back);
      if(pan) pane[active].svg.style.cursor="grabbing"; }
  });

  // ---- a page that is served follows its house: when the drawing in build/
  // is no longer the one this page was made from, it loads itself again, on
  // the sheet and at the view it had. Never under a stroke or a word half made.
  var KEPT="flawlessplan:"+location.pathname, drawn=null;
  function follow(){
    fetch("stamp",{cache:"no-store"}).then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(now){
        if(!now) return;
        if(drawn===null){ drawn=now; return; }
        if(now===drawn||drag||pan||press||editor) return;
        // after the dot is which marks are resolved: those are read again, where they lie
        if(now.split(".")[0]===drawn.split(".")[0]){
          drawn=now;
          saving=saving.then(function(){ return fetch("marks.json",{cache:"no-store"}); })
            .then(function(r){ if(!r.ok) throw 0; return r.json(); })
            .then(function(list){ if(!drag&&!editor){ marks=list; render(); } })["catch"](function(){});
          return;
        }
        try{ sessionStorage.setItem(KEPT,JSON.stringify({sheet:active,view:pane[active].view,done:showDone})); }catch(e){}
        saving.then(function(){ location.reload(); });
      })["catch"](function(){});
  }
  var kept=null;
  try{ kept=JSON.parse(sessionStorage.getItem(KEPT)); sessionStorage.removeItem(KEPT); }catch(e){}
  if(kept) showDone=!!kept.done;
  // an address may name a sheet to open on: index.html#option-e
  function named(){ var k=null; try{ k=decodeURIComponent((location.hash||"").slice(1)); }catch(e){} return k&&pane[k]?k:null; }
  if(kept&&pane[kept.sheet]){
    show(kept.sheet);
    if(kept.view&&isFinite(kept.view.cx)&&isFinite(kept.view.cy)&&isFinite(kept.view.z)) setView(kept.sheet,kept.view);
  } else show(named()||KEYS[0]);
  window.addEventListener("hashchange",function(){ var k=named(); if(k&&k!==active) show(k); });
  if(window.claude&&window.claude.use){
    window.claude.use("db").then(function(d){
      if(!d){ status(UNSAVED.replace("Not saved","Not connected"),"off"); return; }
      db=d; status("Connected — marks are saved for Claude","on");
      db.collection("marks").orderBy("ts").onSnapshot(function(snap){
        marks=snap.docs.map(function(s){var o=s.data()||{};o._id=s.id;return o;}); render();
      },function(e){ status("Sync error ("+((e&&e.code)||"?")+")","off"); });
    })["catch"](function(){ status(UNSAVED.replace("Not saved","Not connected"),"off"); });
  } else {
    fetch("marks.json",{cache:"no-store"}).then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(list){ local=true; marks=list; render(); status("Connected — marks are saved for Claude","on");
        sheetsReady(); follow(); setInterval(follow,1500); })
      ["catch"](function(){
        status(UNSAVED.replace("Not saved","Not connected"),"off");
        // opened as a file: nothing can be saved from here, so point at the served page
        if(location.protocol==="file:"){
          var dir=location.pathname.split("/").slice(-2,-1)[0];
          var a=document.createElement("a"); a.href="http://localhost:8765/"+dir+"/index.html";
          a.textContent="NOT SAVING — open "+a.href; a.className="warn";
          statusEl.textContent=""; statusEl.appendChild(a);
        }
      });
  }
})();
