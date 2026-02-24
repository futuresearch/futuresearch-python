"""MCP App UI HTML templates for results and session widgets."""

_APP_SCRIPT_SRC = "https://unpkg.com/@modelcontextprotocol/ext-apps@1.0.1/app-with-deps"

RESULTS_HTML = """<!DOCTYPE html>
<html><head><meta name="color-scheme" content="light dark">
<style>
:root{
  --bg:#fff;--bg-alt:#f8f9fa;--bg-hover:rgba(25,118,210,0.06);
  --bg-selected:rgba(25,118,210,0.10);--bg-toolbar:#fafafa;
  --text:#333;--text-sec:#666;--text-dim:#999;
  --border:#e0e0e0;--border-light:#eee;
  --accent:#1976d2;
  --research-dot:#42a5f5;
  --pop-bg:#fff;--pop-shadow:0 4px 20px rgba(0,0,0,0.15);
  --toast-bg:#333;--toast-text:#fff;
  --btn-bg:#f0f0f0;--btn-hover:#e0e0e0;--btn-text:#333;
  --btn-accent-bg:#1976d2;--btn-accent-text:#fff;--btn-accent-hover:#1565c0;
  --input-bg:#fff;--input-border:#ddd;--input-focus:#1976d2;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#1a1a1a;--bg-alt:#222;--bg-hover:rgba(100,181,246,0.08);
  --bg-selected:rgba(100,181,246,0.12);--bg-toolbar:#242424;
  --text:#e0e0e0;--text-sec:#aaa;--text-dim:#777;
  --border:#444;--border-light:#333;
  --accent:#64b5f6;
  --research-dot:#64b5f6;
  --pop-bg:#2d2d2d;--pop-shadow:0 4px 20px rgba(0,0,0,0.4);
  --toast-bg:#e0e0e0;--toast-text:#1a1a1a;
  --btn-bg:#333;--btn-hover:#444;--btn-text:#e0e0e0;
  --btn-accent-bg:#1565c0;--btn-accent-text:#fff;--btn-accent-hover:#1976d2;
  --input-bg:#2d2d2d;--input-border:#555;--input-focus:#64b5f6;
}}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:12px;color:var(--text);background:var(--bg);font-size:13px}
#toolbar{display:flex;align-items:center;gap:8px;padding:8px 4px;margin-bottom:8px;flex-wrap:wrap}
#toolbar #sum{font-weight:600;font-size:13px;flex:1;min-width:150px;color:var(--text-sec)}
#toolbar button{padding:5px 12px;border:1px solid var(--border);border-radius:5px;font-size:12px;cursor:pointer;background:var(--btn-bg);color:var(--btn-text);transition:background .15s}
#toolbar button:hover:not(:disabled){background:var(--btn-hover)}
#toolbar button:disabled{opacity:.4;cursor:default}
#toolbar #copyBtn:not(:disabled){background:var(--btn-accent-bg);color:var(--btn-accent-text);border-color:transparent}
#toolbar #copyBtn:not(:disabled):hover{background:var(--btn-accent-hover)}
.wrap{max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:6px 6px 0 0}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}
th,td{padding:6px 10px;text-align:left}
.hdr-row th{background:var(--bg-toolbar);position:sticky;top:0;z-index:3;border-bottom:2px solid var(--border);font-size:12px;font-weight:600;white-space:nowrap;cursor:pointer;user-select:none;transition:background .15s}
.hdr-row th:hover{background:var(--bg-hover)}
.sort-arrow{font-size:10px;margin-left:3px;opacity:.5}
.sort-arrow.active{opacity:1;color:var(--accent)}
.flt-row th{position:sticky;top:30px;z-index:3;background:var(--bg-toolbar);padding:4px;border-bottom:1px solid var(--border);cursor:default}
.flt-row input{width:100%;padding:3px 6px;border:1px solid var(--input-border);border-radius:3px;font-size:11px;background:var(--input-bg);color:var(--text);outline:none;transition:border-color .15s}
.flt-row input:focus{border-color:var(--input-focus)}
.flt-row input::placeholder{color:var(--text-dim)}
td{border-bottom:1px solid var(--border-light);max-width:400px;vertical-align:top;word-wrap:break-word;white-space:pre-wrap;position:relative;transition:background .1s}
td:hover{background:var(--bg-hover)}
td.has-research::after{content:"";position:absolute;top:6px;right:4px;width:6px;height:6px;border-radius:50%;background:var(--research-dot);opacity:.7}
tr.selected td{background:var(--bg-selected)!important}
tr:nth-child(even) td{background:var(--bg-alt)}
tr:nth-child(even).selected td{background:var(--bg-selected)!important}
a{color:var(--accent);text-decoration:none;word-break:break-all}
a:hover{text-decoration:underline}
td:first-child{position:sticky;left:0;background:inherit;z-index:1;font-weight:500}
.hdr-row th:first-child{position:sticky;left:0;z-index:4}
.flt-row th:first-child{position:sticky;left:0;z-index:4}
.popover{position:fixed;background:var(--pop-bg);border:1px solid var(--border);border-radius:8px;box-shadow:var(--pop-shadow);max-width:420px;min-width:200px;z-index:100;overflow:hidden;opacity:0;transform:translateY(-4px);transition:opacity .15s,transform .15s;pointer-events:none}
.popover.visible{opacity:1;transform:translateY(0);pointer-events:auto}
.pop-hdr{padding:8px 12px;font-size:11px;font-weight:600;color:var(--text-sec);border-bottom:1px solid var(--border-light);background:var(--bg-alt)}
.pop-body{padding:10px 12px;font-size:12px;line-height:1.5;white-space:pre-wrap;max-height:300px;overflow-y:auto;color:var(--text)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(60px);background:var(--toast-bg);color:var(--toast-text);padding:8px 20px;border-radius:20px;font-size:13px;font-weight:500;opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;z-index:200}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.resize-handle{height:6px;background:var(--border-light);cursor:ns-resize;border-radius:0 0 6px 6px;transition:background .15s;margin-top:-1px;border:1px solid var(--border);border-top:none}
.resize-handle:hover,.resize-handle.active{background:var(--accent);opacity:.5}
#expandBtn{font-size:14px;padding:5px 8px}
body.fullscreen .wrap{max-height:calc(100vh - 80px)!important}
body.fullscreen .resize-handle{display:none}
.copy-modal{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:300;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .2s}
.copy-modal.show{opacity:1;pointer-events:auto}
.copy-modal-box{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;max-width:600px;width:90%;max-height:80vh;display:flex;flex-direction:column;gap:8px}
.copy-modal-box textarea{width:100%;height:300px;font-family:monospace;font-size:12px;border:1px solid var(--border);border-radius:4px;padding:8px;background:var(--input-bg);color:var(--text);resize:vertical}
.copy-modal-box .modal-btns{display:flex;gap:8px;justify-content:flex-end}
.copy-modal-box button{padding:6px 16px;border:1px solid var(--border);border-radius:5px;background:var(--btn-bg);color:var(--btn-text);cursor:pointer;font-size:12px}
.session-link{margin-bottom:6px;font-size:12px}
.session-link a{font-weight:500}
.col-resize-handle{position:absolute;top:0;right:-2px;width:4px;height:100%;cursor:col-resize;z-index:5;user-select:none}
.col-resize-handle:hover{background:var(--accent);opacity:.3}
body.col-resizing,body.col-resizing *{cursor:col-resize!important;user-select:none!important}
body.row-resizing,body.row-resizing *{cursor:row-resize!important;user-select:none!important}
.cell-text{display:inline}
.cell-more,.cell-less{cursor:pointer;color:var(--accent);font-size:11px;margin-left:2px;white-space:nowrap;font-weight:500}
.cell-more:hover,.cell-less:hover{text-decoration:underline}
.export-btns{display:inline-flex;gap:2px}
.export-btns button{padding:3px 8px;font-size:11px}
.col-ghost{position:fixed;background:var(--bg-toolbar);border:1px solid var(--accent);border-radius:4px;padding:4px 8px;font-size:12px;font-weight:600;opacity:.85;pointer-events:none;z-index:200;white-space:nowrap}
body.col-dragging,body.col-dragging *{cursor:grabbing!important;user-select:none!important}
.hdr-row th.drag-over-left{box-shadow:inset 3px 0 0 var(--accent)}
.hdr-row th.drag-over-right{box-shadow:inset -3px 0 0 var(--accent)}
.settings-wrap{position:relative;display:inline-block}
#settingsBtn{font-size:14px;padding:5px 8px}
.settings-drop{position:absolute;top:100%;right:0;margin-top:4px;background:var(--pop-bg);border:1px solid var(--border);border-radius:6px;box-shadow:var(--pop-shadow);padding:8px 0;z-index:100;min-width:130px;display:none}
.settings-drop.show{display:block}
.settings-drop .drop-hdr{padding:2px 12px;font-size:11px;font-weight:600;color:var(--text-sec)}
.settings-drop label{display:flex;align-items:center;gap:6px;padding:4px 12px;font-size:12px;cursor:pointer;white-space:nowrap}
.settings-drop label:hover{background:var(--bg-hover)}
.settings-drop input[type="radio"]{margin:0}
.settings-drop .drop-sep{border-top:1px solid var(--border-light);margin:4px 0}
</style></head><body>
<div id="sessionLink" class="session-link"></div>
<div id="toolbar">
  <span id="sum">Loading...</span>
  <button id="selAllBtn">Select all</button>
  <button id="copyBtn" disabled>Copy (0)</button>
  <span class="settings-wrap"><button id="settingsBtn" title="Settings">Settings</button><div id="settingsDrop" class="settings-drop"><div class="drop-hdr">Copy format</div><label><input type="radio" name="cfmt" value="tsv" checked> TSV (tabs)</label><label><input type="radio" name="cfmt" value="csv"> CSV</label><label><input type="radio" name="cfmt" value="json"> JSON</label><div class="drop-sep"></div><div class="drop-hdr">Table height</div><label><input type="radio" name="tsize" value="250"> Small</label><label><input type="radio" name="tsize" value="420" checked> Medium</label><label><input type="radio" name="tsize" value="700"> Large</label></div></span>
  <button id="expandBtn" title="Toggle fullscreen">&#x2922;</button>
</div>
<div class="wrap" id="wrap"><table id="tbl"></table></div>
<div class="resize-handle" id="resizeHandle"></div>
<div id="pop" class="popover"><div class="pop-hdr"></div><div class="pop-body"></div></div>
<div id="toast" class="toast">Copied!</div>
<div id="copyModal" class="copy-modal"><div class="copy-modal-box"><div style="font-weight:600;font-size:13px">Select all and copy (Cmd+C / Ctrl+C)</div><textarea id="copyArea" readonly></textarea><div class="modal-btns"><button id="closeCopyModal">Close</button></div></div></div>
<script type="module">
import*as _SDK from"SCRIPT_SRC";
const App=_SDK.App;
function applyTheme(){try{_SDK.applyDocumentTheme?.()}catch{}try{_SDK.applyHostStyleVariables?.()}catch{}try{_SDK.applyHostFonts?.()}catch{}}

const app=new App({name:"EveryRow Results",version:"2.0.0"});
const tbl=document.getElementById("tbl");
const sum=document.getElementById("sum");
const selAllBtn=document.getElementById("selAllBtn");
const copyBtn=document.getElementById("copyBtn");
const pop=document.getElementById("pop");
const popHdr=pop.querySelector(".pop-hdr");
const popBody=pop.querySelector(".pop-body");
const toast=document.getElementById("toast");
const wrap=document.getElementById("wrap");
const resizeHandle=document.getElementById("resizeHandle");
const expandBtn=document.getElementById("expandBtn");
const copyModal=document.getElementById("copyModal");
const copyArea=document.getElementById("copyArea");
const closeCopyModal=document.getElementById("closeCopyModal");
const sessionLinkEl=document.getElementById("sessionLink");

let sessionUrl="",csvUrl="";
const TRUNC=200;
let didDrag=false;
let copyFmt="tsv";
const settingsBtn=document.getElementById("settingsBtn");
const settingsDrop=document.getElementById("settingsDrop");
const S={rows:[],allCols:[],filteredIdx:[],sortCol:null,sortDir:0,filters:{},selected:new Set(),lastClick:null,isFullscreen:false};

/* --- theming & display mode --- */
app.onhostcontextchanged=(ctx)=>{
  applyTheme();
  const mode=ctx?.displayMode||"contained";
  const isFull=mode==="fullscreen";
  S.isFullscreen=isFull;
  document.body.classList.toggle("fullscreen",isFull);
  expandBtn.textContent=isFull?"\\u2921":"\\u2922";
  expandBtn.title=isFull?"Exit fullscreen":"Toggle fullscreen";
};

/* --- helpers --- */
function esc(s){const d=document.createElement("div");d.textContent=String(s);return d.innerHTML;}
function escAttr(s){return esc(s).replace(/"/g,"&quot;");}
function linkify(s){return esc(s).replace(/https?:\\/\\/[^\\s<)\\]]+/g,m=>'<a href="'+escAttr(m)+'" target="_blank">'+m+'</a>');}

/* --- data processing --- */
function flat(obj,pre){
  const o={};
  for(const[k,v]of Object.entries(obj)){
    const key=pre?pre+"."+k:k;
    if(v&&typeof v==="object"&&!Array.isArray(v))Object.assign(o,flat(v,key));
    else o[key]=v;
  }
  return o;
}

function flatWithResearch(obj){
  const research={};
  if(obj.research&&typeof obj.research==="object"&&!Array.isArray(obj.research)){
    for(const[k,v]of Object.entries(obj.research)){
      if(v!=null)research[k]=typeof v==="string"?v:String(v);
    }
  }
  return{display:flat(obj),research};
}

function processData(data){
  if(!Array.isArray(data))data=[data];
  if(!data.length){sum.textContent="No results";tbl.innerHTML="";return;}
  S.rows=data.map(r=>flatWithResearch(r));
  const colSet=new Set();
  S.rows.forEach(r=>{for(const k of Object.keys(r.display))colSet.add(k)});
  const all=[...colSet];
  const visible=all.filter(k=>!k.startsWith("research."));
  S.allCols=[...visible.filter(k=>!k.includes(".")),...visible.filter(k=>k.includes("."))];
  S.sortCol=null;S.sortDir=0;S.filters={};S.selected.clear();S.lastClick=null;
  S.filteredIdx=S.rows.map((_,i)=>i);
  renderTable();
}

/* --- filter & sort --- */
function applyFilterAndSort(){
  let idx=S.rows.map((_,i)=>i);
  for(const[col,q]of Object.entries(S.filters)){
    if(!q)continue;
    const lq=q.toLowerCase();
    idx=idx.filter(i=>{const v=S.rows[i].display[col];return v!=null&&String(v).toLowerCase().includes(lq);});
  }
  if(S.sortCol&&S.sortDir!==0){
    const col=S.sortCol,dir=S.sortDir;
    idx.sort((a,b)=>{
      const va=S.rows[a].display[col],vb=S.rows[b].display[col];
      if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return-1;
      return String(va).localeCompare(String(vb),undefined,{numeric:true,sensitivity:"base"})*dir;
    });
  }
  S.filteredIdx=idx;
  const filtSet=new Set(idx);
  for(const s of S.selected){if(!filtSet.has(s))S.selected.delete(s);}
  renderTable();
}

let filterTimer=null;
function onFilterInput(col,val){S.filters[col]=val;clearTimeout(filterTimer);filterTimer=setTimeout(()=>applyFilterAndSort(),150);}

/* --- research lookup --- */
function getResearch(row,col){
  const r=row.research;
  if(!r||!Object.keys(r).length)return null;
  if(r[col]!=null)return r[col];
  if(col.startsWith("research.")){const base=col.slice(9);if(r[base]!=null)return r[base];}
  return null;
}

/* --- render --- */
function renderTable(){
  const cols=S.allCols;
  if(!cols.length){tbl.innerHTML="";return;}
  const activeEl=document.activeElement;
  const activeFilterCol=activeEl&&activeEl.matches&&activeEl.matches('.flt-row input')?activeEl.dataset.col:null;
  const cursorPos=activeFilterCol?activeEl.selectionStart:0;

  let h='<thead><tr class="hdr-row">';
  for(const c of cols){
    let arrow='<span class="sort-arrow">&#9650;</span>';
    if(S.sortCol===c)arrow=S.sortDir===1?'<span class="sort-arrow active">&#9650;</span>':'<span class="sort-arrow active">&#9660;</span>';
    h+='<th data-col="'+escAttr(c)+'" style="position:relative">'+esc(c)+arrow+'<div class="col-resize-handle"></div></th>';
  }
  h+='</tr><tr class="flt-row">';
  for(const c of cols){
    h+='<th><input data-col="'+escAttr(c)+'" placeholder="Filter..." value="'+escAttr(S.filters[c]||"")+'"></th>';
  }
  h+='</tr></thead><tbody>';
  for(const i of S.filteredIdx){
    const row=S.rows[i],sel=S.selected.has(i)?' class="selected"':"";
    h+='<tr data-idx="'+i+'"'+sel+'>';
    for(const c of cols){
      const hasR=getResearch(row,c)!=null;
      const v=row.display[c],cls=hasR?' class="has-research"':"",dc=' data-col="'+escAttr(c)+'"';
      if(v==null){h+="<td"+cls+dc+"></td>";}
      else{const s=String(v);
        if(s.length>TRUNC)h+='<td'+cls+dc+'><span class="cell-text">'+linkify(s.slice(0,TRUNC))+'</span><span class="cell-more">&hellip; more</span></td>';
        else h+='<td'+cls+dc+'>'+linkify(s)+'</td>';
      }
    }
    h+='</tr>';
  }
  tbl.innerHTML=h+'</tbody>';

  const total=S.rows.length,shown=S.filteredIdx.length;
  sum.textContent=(shown<total?shown+" of "+total:String(total))+" rows, "+cols.length+" columns";
  updateCopyBtn();

  tbl.querySelectorAll('.flt-row input').forEach(inp=>{
    inp.addEventListener('input',()=>onFilterInput(inp.dataset.col,inp.value));
  });
  if(activeFilterCol){
    tbl.querySelectorAll('.flt-row input').forEach(inp=>{
      if(inp.dataset.col===activeFilterCol){inp.focus();try{inp.setSelectionRange(cursorPos,cursorPos)}catch{}}
    });
  }

  requestAnimationFrame(()=>{
    const hdrRow=tbl.querySelector('.hdr-row');
    if(hdrRow){const h=hdrRow.getBoundingClientRect().height;tbl.querySelectorAll('.flt-row th').forEach(th=>th.style.top=h+'px');}
  });
}

/* --- sort --- */
tbl.addEventListener("click",e=>{
  if(didDrag){didDrag=false;return;}
  if(e.target.closest(".col-resize-handle"))return;
  const th=e.target.closest(".hdr-row th");
  if(!th)return;
  const col=th.dataset.col;
  if(S.sortCol===col){S.sortDir=S.sortDir===1?-1:S.sortDir===-1?0:1;if(S.sortDir===0)S.sortCol=null;}
  else{S.sortCol=col;S.sortDir=1;}
  applyFilterAndSort();
});

/* --- cell expand/collapse --- */
tbl.addEventListener("click",e=>{
  const more=e.target.closest(".cell-more");
  if(more){
    e.stopPropagation();
    const td=more.closest("td"),tr=td.closest("tr");
    const idx=parseInt(tr.dataset.idx,10),col=td.dataset.col;
    const full=String(S.rows[idx].display[col]);
    td.querySelector(".cell-text").innerHTML=linkify(full);
    more.textContent="less";more.className="cell-less";
    return;
  }
  const less=e.target.closest(".cell-less");
  if(less){
    e.stopPropagation();
    const td=less.closest("td"),tr=td.closest("tr");
    const idx=parseInt(tr.dataset.idx,10),col=td.dataset.col;
    const full=String(S.rows[idx].display[col]);
    td.querySelector(".cell-text").innerHTML=linkify(full.slice(0,TRUNC));
    less.textContent="\\u2026 more";less.className="cell-more";
    return;
  }
});

/* --- selection (click toggles, shift extends range) --- */
tbl.addEventListener("click",e=>{
  if(e.target.closest(".hdr-row")||e.target.closest(".flt-row")||e.target.closest("a")||e.target.closest(".cell-more")||e.target.closest(".cell-less"))return;
  const tr=e.target.closest("tbody tr");if(!tr)return;
  const idx=parseInt(tr.dataset.idx,10);if(isNaN(idx))return;
  if(e.shiftKey&&S.lastClick!=null){
    const posA=S.filteredIdx.indexOf(S.lastClick),posB=S.filteredIdx.indexOf(idx);
    if(posA>=0&&posB>=0){const lo=Math.min(posA,posB),hi=Math.max(posA,posB);for(let p=lo;p<=hi;p++)S.selected.add(S.filteredIdx[p]);}
  }else{
    if(S.selected.has(idx))S.selected.delete(idx);else S.selected.add(idx);
  }
  S.lastClick=idx;updateSelection();updateCopyBtn();
});

function updateSelection(){
  tbl.querySelectorAll("tbody tr").forEach(tr=>{
    const idx=parseInt(tr.dataset.idx,10);tr.classList.toggle("selected",S.selected.has(idx));
  });
}
function updateCopyBtn(){const n=S.selected.size;const fl=copyFmt.toUpperCase();copyBtn.textContent=n>0?"Copy ("+n+")":"Copy";copyBtn.title="Copy selected rows as "+fl;copyBtn.disabled=n===0;}

/* --- select all --- */
selAllBtn.addEventListener("click",()=>{
  if(S.selected.size===S.filteredIdx.length)S.selected.clear();
  else{S.selected.clear();S.filteredIdx.forEach(i=>S.selected.add(i));}
  updateSelection();updateCopyBtn();
});

/* --- copy --- */
function buildCopyText(){
  const cols=S.allCols;
  const sel=S.filteredIdx.filter(i=>S.selected.has(i));
  if(copyFmt==="json"){
    const data=sel.map(i=>{const o={};for(const c of cols)o[c]=S.rows[i].display[c]??null;return o;});
    return JSON.stringify(data,null,2);
  }
  const isCSV=copyFmt==="csv";
  const sep=isCSV?",":"\\t";
  const q=v=>isCSV?'"'+v.replace(/"/g,'""')+'"':v.replace(/\\t/g," ");
  const lines=[cols.map(c=>q(c)).join(sep)];
  for(const i of sel){
    lines.push(cols.map(c=>{const v=S.rows[i].display[c];return v==null?(isCSV?'""':""):q(String(v));}).join(sep));
  }
  return lines.join("\\n");
}
function execCopy(text){
  const ta=document.createElement("textarea");
  ta.value=text;ta.style.cssText="position:fixed;left:-9999px";
  document.body.appendChild(ta);ta.select();
  let ok=false;try{ok=document.execCommand("copy")}catch{}
  document.body.removeChild(ta);return ok;
}
function showCopyModal(text){
  copyArea.value=text;copyModal.classList.add("show");
  copyArea.focus();copyArea.select();
}
copyBtn.addEventListener("click",async()=>{
  if(!S.selected.size)return;
  const text=buildCopyText();
  const msg="Copied "+S.selected.size+" row"+(S.selected.size>1?"s":"")+" as "+copyFmt.toUpperCase();
  try{await navigator.clipboard.writeText(text);showToast(msg);return;}catch{}
  if(execCopy(text)){showToast(msg);return;}
  showCopyModal(text);
});
closeCopyModal.addEventListener("click",()=>copyModal.classList.remove("show"));
copyModal.addEventListener("click",e=>{if(e.target===copyModal)copyModal.classList.remove("show");});
function showToast(msg){toast.textContent=msg;toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),2000);}

/* --- settings dropdown --- */
settingsBtn.addEventListener("click",e=>{e.stopPropagation();settingsDrop.classList.toggle("show");});
document.addEventListener("click",()=>settingsDrop.classList.remove("show"));
settingsDrop.addEventListener("click",e=>e.stopPropagation());
settingsDrop.querySelectorAll('input[name="cfmt"]').forEach(r=>{
  r.addEventListener("change",()=>{copyFmt=r.value;updateCopyBtn();});
});
settingsDrop.querySelectorAll('input[name="tsize"]').forEach(r=>{
  r.addEventListener("change",()=>{wrap.style.maxHeight=r.value+"px";});
});

/* --- popover --- */
let popTimer=null,popTarget=null,popVisible=false;

function showPopover(td){
  const tr=td.closest("tr");const idx=parseInt(tr.dataset.idx,10);const col=td.dataset.col;
  const row=S.rows[idx];if(!row)return;
  const text=getResearch(row,col);if(text==null)return;
  popHdr.textContent="research."+col.replace(/^research\\./,"");
  popBody.innerHTML=linkify(text);
  const rect=td.getBoundingClientRect();
  let left=rect.left,top=rect.bottom+4;
  pop.classList.add("visible");popVisible=true;
  const pw=pop.offsetWidth,ph=pop.offsetHeight;
  if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;
  if(left<8)left=8;
  if(top+ph>window.innerHeight-8)top=rect.top-ph-4;
  pop.style.left=left+"px";pop.style.top=top+"px";
}
function hidePopover(){pop.classList.remove("visible");popVisible=false;popTarget=null;}

document.addEventListener("mouseover",e=>{
  if(pop.contains(e.target)){clearTimeout(popTimer);return;}
  const td=e.target.closest?e.target.closest("td"):null;
  if(td&&tbl.contains(td)&&td.classList.contains("has-research")){
    if(td===popTarget&&popVisible){clearTimeout(popTimer);return;}
    clearTimeout(popTimer);if(popVisible)hidePopover();
    popTarget=td;popTimer=setTimeout(()=>showPopover(td),300);
  }else{
    clearTimeout(popTimer);popTarget=null;
    if(popVisible)popTimer=setTimeout(()=>{if(!pop.matches(":hover"))hidePopover();},150);
  }
});
pop.addEventListener("mouseleave",()=>{clearTimeout(popTimer);hidePopover();});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){if(copyModal.classList.contains("show"))copyModal.classList.remove("show");else if(popVisible)hidePopover();}});

/* --- resize handle --- */
let resizing=false,startY=0,startH=0;
resizeHandle.addEventListener("mousedown",e=>{
  e.preventDefault();resizing=true;startY=e.clientY;startH=wrap.offsetHeight;
  resizeHandle.classList.add("active");
  document.addEventListener("mousemove",onResizeMove);
  document.addEventListener("mouseup",onResizeUp);
});
function onResizeMove(e){
  if(!resizing)return;
  const newH=Math.max(100,startH+(e.clientY-startY));
  wrap.style.maxHeight=newH+"px";
  settingsDrop.querySelectorAll('input[name="tsize"]').forEach(r=>{r.checked=false;});
}
function onResizeUp(){
  resizing=false;resizeHandle.classList.remove("active");
  document.removeEventListener("mousemove",onResizeMove);
  document.removeEventListener("mouseup",onResizeUp);
}

/* --- fullscreen toggle --- */
expandBtn.addEventListener("click",async()=>{
  try{
    const next=S.isFullscreen?"contained":"fullscreen";
    await app.requestDisplayMode({mode:next});
  }catch(e){showToast("Fullscreen not supported");}
});

/* --- column resize --- */
let colResizing=false,colResizeTh=null,colStartX=0,colStartW=0;
tbl.addEventListener("mousedown",e=>{
  const handle=e.target.closest(".col-resize-handle");
  if(!handle)return;
  e.preventDefault();e.stopPropagation();
  colResizeTh=handle.parentElement;
  colStartX=e.clientX;colStartW=colResizeTh.offsetWidth;
  colResizing=true;
  tbl.style.tableLayout="fixed";
  document.body.classList.add("col-resizing");
  /* snapshot all column widths so they stay stable while we drag */
  tbl.querySelectorAll(".hdr-row th").forEach(th=>{if(!th.style.width)th.style.width=th.offsetWidth+"px";});
  document.addEventListener("mousemove",onColResizeMove);
  document.addEventListener("mouseup",onColResizeUp);
});
function onColResizeMove(e){
  if(!colResizing)return;
  const delta=e.clientX-colStartX;
  colResizeTh.style.width=Math.max(30,colStartW+delta)+"px";
}
function onColResizeUp(){
  colResizing=false;colResizeTh=null;
  document.body.classList.remove("col-resizing");
  document.removeEventListener("mousemove",onColResizeMove);
  document.removeEventListener("mouseup",onColResizeUp);
}

/* --- column auto-fit (double-click resize handle) --- */
function measureColWidth(colIdx){
  const sp=document.createElement("span");
  sp.style.cssText="position:absolute;visibility:hidden;white-space:nowrap;padding:0 10px;font:13px system-ui";
  document.body.appendChild(sp);
  let maxW=0;
  const th=tbl.querySelectorAll(".hdr-row th")[colIdx];
  sp.style.fontWeight="600";sp.style.fontSize="12px";
  sp.textContent=th.dataset.col;
  maxW=Math.max(maxW,sp.offsetWidth+30);
  sp.style.fontWeight="normal";sp.style.fontSize="13px";
  tbl.querySelectorAll("tbody tr").forEach(tr=>{
    const td=tr.children[colIdx];
    if(td){sp.textContent=(td.textContent||"").slice(0,300);maxW=Math.max(maxW,sp.offsetWidth);}
  });
  document.body.removeChild(sp);
  return Math.min(Math.max(maxW+4,50),600);
}
tbl.addEventListener("dblclick",e=>{
  const handle=e.target.closest(".col-resize-handle");
  if(!handle)return;
  e.preventDefault();e.stopPropagation();
  const th=handle.parentElement;
  const colIdx=[...th.parentElement.children].indexOf(th);
  tbl.style.tableLayout="fixed";
  tbl.querySelectorAll(".hdr-row th").forEach(t=>{if(!t.style.width)t.style.width=t.offsetWidth+"px";});
  th.style.width=measureColWidth(colIdx)+"px";
});

/* --- column drag reorder --- */
let colDragging=false,dragCol=null,dragGhost=null,dragStartX=0,dragStartY=0;
const DRAG_THRESHOLD=5;
tbl.addEventListener("mousedown",e=>{
  if(e.target.closest(".col-resize-handle"))return;
  const th=e.target.closest(".hdr-row th");
  if(!th)return;
  dragCol=th.dataset.col;dragStartX=e.clientX;dragStartY=e.clientY;colDragging=false;
  document.addEventListener("mousemove",onColDragMove);
  document.addEventListener("mouseup",onColDragUp);
});
function onColDragMove(e){
  if(!dragCol)return;
  const dx=Math.abs(e.clientX-dragStartX),dy=Math.abs(e.clientY-dragStartY);
  if(!colDragging&&(dx>DRAG_THRESHOLD||dy>DRAG_THRESHOLD)){
    colDragging=true;didDrag=true;
    document.body.classList.add("col-dragging");
    dragGhost=document.createElement("div");
    dragGhost.className="col-ghost";dragGhost.textContent=dragCol;
    document.body.appendChild(dragGhost);
  }
  if(colDragging){
    dragGhost.style.left=(e.clientX+12)+"px";dragGhost.style.top=(e.clientY-12)+"px";
    const hdrs=[...tbl.querySelectorAll(".hdr-row th")];
    hdrs.forEach(h=>h.classList.remove("drag-over-left","drag-over-right"));
    const target=hdrs.find(h=>{const r=h.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right;});
    if(target&&target.dataset.col!==dragCol){
      const r=target.getBoundingClientRect();
      target.classList.add(e.clientX<r.left+r.width/2?"drag-over-left":"drag-over-right");
    }
  }
}
function onColDragUp(e){
  document.removeEventListener("mousemove",onColDragMove);
  document.removeEventListener("mouseup",onColDragUp);
  if(colDragging){
    const hdrs=[...tbl.querySelectorAll(".hdr-row th")];
    hdrs.forEach(h=>h.classList.remove("drag-over-left","drag-over-right"));
    const target=hdrs.find(h=>{const r=h.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right;});
    if(target&&target.dataset.col!==dragCol){
      const fromIdx=S.allCols.indexOf(dragCol);
      const toCol=target.dataset.col;
      let toIdx=S.allCols.indexOf(toCol);
      const r=target.getBoundingClientRect();
      if(e.clientX>=r.left+r.width/2)toIdx++;
      S.allCols.splice(fromIdx,1);
      if(fromIdx<toIdx)toIdx--;
      S.allCols.splice(toIdx,0,dragCol);
      renderTable();
    }
    if(dragGhost){dragGhost.remove();dragGhost=null;}
    document.body.classList.remove("col-dragging");
  }
  colDragging=false;dragCol=null;
}

/* --- export CSV / JSON --- */
async function copyToClipboard(text){
  try{await navigator.clipboard.writeText(text);return true;}catch{}
  if(execCopy(text))return true;
  return false;
}

function updateDownloadLink(){updateSessionLink();}

/* --- row resize (drag bottom border) --- */
let rowResizing=false,rowResizeTr=null,rowStartY=0,rowStartH=0;
const ROW_EDGE=4;
function nearRowBottom(e,td){
  const r=td.getBoundingClientRect();
  return e.clientY>=r.bottom-ROW_EDGE&&e.clientY<=r.bottom+1;
}
tbl.addEventListener("mousemove",e=>{
  if(rowResizing||colResizing)return;
  const td=e.target.closest("tbody td");
  if(td&&nearRowBottom(e,td)){td.style.cursor="row-resize";}
  else if(td){td.style.cursor="";}
});
tbl.addEventListener("mousedown",e=>{
  const td=e.target.closest("tbody td");
  if(!td||!nearRowBottom(e,td))return;
  e.preventDefault();
  rowResizeTr=td.closest("tr");
  rowStartY=e.clientY;rowStartH=rowResizeTr.offsetHeight;
  rowResizing=true;
  document.body.classList.add("row-resizing");
  document.addEventListener("mousemove",onRowResizeMove);
  document.addEventListener("mouseup",onRowResizeUp);
});
function onRowResizeMove(e){
  if(!rowResizing)return;
  const delta=e.clientY-rowStartY;
  const newH=Math.max(16,rowStartH+delta)+"px";
  rowResizeTr.querySelectorAll("td").forEach(td=>td.style.height=newH);
}
function onRowResizeUp(){
  rowResizing=false;rowResizeTr=null;
  document.body.classList.remove("row-resizing");
  document.removeEventListener("mousemove",onRowResizeMove);
  document.removeEventListener("mouseup",onRowResizeUp);
}

/* --- session URL display --- */
function updateSessionLink(){
  let h="";
  if(sessionUrl)h+='<a href="#" id="sessionOpenLink">Open everyrow session &#x2197;</a>';
  if(csvUrl){if(h)h+=" &nbsp;|&nbsp; ";h+='<a href="#" id="csvOpenLink">Download CSV &#x2913;</a>';}
  sessionLinkEl.innerHTML=h;
  document.getElementById("sessionOpenLink")?.addEventListener("click",e=>{
    e.preventDefault();
    app.openLink({url:sessionUrl}).catch(()=>window.open(sessionUrl,"_blank"));
  });
  document.getElementById("csvOpenLink")?.addEventListener("click",e=>{
    e.preventDefault();
    app.openLink({url:csvUrl}).catch(()=>window.open(csvUrl,"_blank"));
  });
}

/* --- data loading --- */
function fetchFullResults(url,opts,hasPreview,total){
  if(!hasPreview)sum.textContent="Loading"+(total?" "+total+" rows":"")+"...";
  fetch(url,opts).then(r=>{
    if(!r.ok)throw new Error(r.status+" "+r.statusText);
    return r.json();
  }).then(data=>processData(data)).catch(err=>{
    if(hasPreview){showToast("Full load failed, showing preview");}
    else{
      sum.innerHTML=esc("Failed to load: "+err.message)+' <button id="retryBtn" style="margin-left:8px;padding:2px 10px;border:1px solid var(--border);border-radius:4px;background:var(--btn-bg);color:var(--btn-text);cursor:pointer;font-size:12px">Retry</button>';
      document.getElementById("retryBtn")?.addEventListener("click",()=>fetchFullResults(url,opts,hasPreview,total));
    }
  });
}
app.ontoolresult=({content})=>{
  const t=content?.find(c=>c.type==="text");if(!t)return;
  let meta;try{meta=JSON.parse(t.text);}catch{sum.textContent=t.text;return;}
  if(meta.session_url&&!sessionUrl){sessionUrl=meta.session_url;updateSessionLink();}
  if(meta.csv_url){csvUrl=meta.csv_url;updateDownloadLink();}
  if(meta.results_url){
    if(meta.preview)processData(meta.preview);
    const opts=meta.download_token?{headers:{"Authorization":"Bearer "+meta.download_token}}:{};
    fetchFullResults(meta.results_url,opts,!!meta.preview,meta.total);
  }else if(meta.preview){processData(meta.preview);}
  else if(Array.isArray(meta)){processData(meta);}
  else{sum.textContent=JSON.stringify(meta);}
};

await app.connect();
applyTheme();
</script></body></html>""".replace("SCRIPT_SRC", _APP_SCRIPT_SRC)

SESSION_HTML = """<!DOCTYPE html>
<html><head><meta name="color-scheme" content="light dark">
<style>
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:12px;color:#333;font-size:13px}
@media(prefers-color-scheme:dark){body{color:#ddd;background:#1a1a1a}
  .bar-bg{background:#333}.info{color:#aaa}.seg-legend{color:#aaa}}
a{color:#1976d2;text-decoration:none;font-weight:500}
a:hover{text-decoration:underline}
.bar-bg{width:100%;background:#e8e8e8;border-radius:6px;overflow:hidden;height:22px;margin:8px 0;
  display:flex}
.seg{height:100%;transition:width .5s;display:flex;align-items:center;justify-content:center;
  font-size:11px;color:#fff;overflow:hidden;white-space:nowrap}
.seg-done{background:#4caf50}
.seg-run{background:#2196f3}
.seg-fail{background:#e53935}
.seg-pend{background:transparent}
.info{font-size:12px;color:#666;margin:4px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.seg-legend{display:flex;gap:10px;font-size:11px;color:#888}
.seg-legend span::before{content:"";display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:3px}
.l-done::before{background:#4caf50!important}.l-run::before{background:#2196f3!important}
.l-fail::before{background:#e53935!important}
.status-done{color:#4caf50;font-weight:600}
.status-fail{color:#e53935;font-weight:600}
.eta{color:#888;font-size:11px}
@keyframes flash{0%,100%{background:transparent}50%{background:rgba(76,175,80,.15)}}
.flash{animation:flash 1s ease 3}
</style></head><body>
<div id="c">Waiting...</div>
<script type="module">
import{App}from"SCRIPT_SRC";
const app=new App({name:"EveryRow Session",version:"1.0.0"});
const el=document.getElementById("c");
let pollUrl=null,pollTimer=null,sessionUrl="",wasDone=false;

app.ontoolresult=({content})=>{
  const t=content?.find(c=>c.type==="text");if(!t)return;
  try{
    const d=JSON.parse(t.text);sessionUrl=d.session_url||"";render(d);
    if(d.progress_url&&!pollTimer){pollUrl=d.progress_url;startPoll()}
  }catch{el.textContent=t.text}
};

function render(d){
  const comp=d.completed||0,tot=d.total||0,fail=d.failed||0,run=d.running||0;
  const pend=Math.max(0,tot-comp-fail-run);
  const done=["completed","failed","revoked"].includes(d.status);
  const url=d.session_url||sessionUrl;
  const elapsed=d.elapsed_s||0;

  let h=url?`<a href="#" class="session-open">Open everyrow session &#x2197;</a>`:"";

  if(tot>0){
    const pDone=comp/tot*100,pRun=run/tot*100,pFail=fail/tot*100;
    h+=`<div class="bar-bg">`;
    if(pDone>0)h+=`<div class="seg seg-done" style="width:${pDone}%">${pDone>=10?Math.round(pDone)+"%":""}</div>`;
    if(pRun>0)h+=`<div class="seg seg-run" style="width:${pRun}%"></div>`;
    if(pFail>0)h+=`<div class="seg seg-fail" style="width:${pFail}%"></div>`;
    h+=`</div>`;

    h+=`<div class="info">`;
    if(done){
      const cls=d.status==="completed"?"status-done":"status-fail";
      h+=`<span class="${cls}">${d.status}</span>`;
      h+=`<span>${comp}/${tot}${fail?` (${fail} failed)`:""}</span>`;
      if(elapsed)h+=`<span>${fmtTime(elapsed)}</span>`;
    }else{
      h+=`<span>${comp}/${tot}</span>`;
      const eta=comp>0&&elapsed>0?Math.round((tot-comp)/(comp/elapsed)):0;
      if(eta>0)h+=`<span class="eta">~${fmtTime(eta)} remaining</span>`;
      if(elapsed)h+=`<span class="eta">${fmtTime(elapsed)} elapsed</span>`;
    }
    h+=`</div>`;

    if(!done){
      h+=`<div class="seg-legend">`;
      if(comp)h+=`<span class="l-done">${comp} done</span>`;
      if(run)h+=`<span class="l-run">${run} running</span>`;
      if(fail)h+=`<span class="l-fail">${fail} failed</span>`;
      if(pend)h+=`<span>${pend} pending</span>`;
      h+=`</div>`;
    }
  }else if(d.status){
    h+=`<div class="info">${d.status}${elapsed?` &mdash; ${fmtTime(elapsed)}`:""}</div>`;
  }

  el.innerHTML=h;

  const link=el.querySelector(".session-open");
  if(link){link.addEventListener("click",e=>{
    e.preventDefault();
    app.openLink({url:url}).catch(()=>window.open(url,"_blank"));
  });}

  if(done&&!wasDone){wasDone=true;el.classList.add("flash")}
  if(done&&pollTimer){clearInterval(pollTimer);pollTimer=null}
}

function fmtTime(s){
  if(s<60)return s+"s";
  const m=Math.floor(s/60),sec=s%60;
  return m+"m"+((sec>0)?(" "+sec+"s"):"");
}

function startPoll(){
  pollTimer=setInterval(async()=>{
    try{const r=await fetch(pollUrl);if(r.ok)render(await r.json())}catch{}
  },5000);
}

await app.connect();
</script></body></html>""".replace("SCRIPT_SRC", _APP_SCRIPT_SRC)
