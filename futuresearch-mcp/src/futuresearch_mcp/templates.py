"""MCP App UI HTML template for the unified session widget."""

_APP_SCRIPT_SRC = "https://unpkg.com/@modelcontextprotocol/ext-apps@1.0.1/app-with-deps"


UNIFIED_HTML = """<!DOCTYPE html>
<html><head><meta name="referrer" content="no-referrer"><meta name="color-scheme" content="light dark">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#fff;--bg-alt:#fafafa;--bg-hover:rgba(77,79,189,0.05);
  --bg-selected:rgba(77,79,189,0.10);--bg-toolbar:#f4f4f5;
  --text:#333;--text-sec:#525252;--text-dim:#a3a3a3;
  --border:rgba(0,0,0,0.08);--border-light:rgba(0,0,0,0.04);
  --accent:#4D4FBD;
  --research-dot:#9294F0;
  --pop-bg:#fff;--pop-shadow:0 4px 20px rgba(0,0,0,0.12);
  --toast-bg:#333;--toast-text:#fff;
  --btn-bg:#f5f5f5;--btn-hover:#e5e5e5;--btn-text:#333;
  --btn-accent-bg:#4D4FBD;--btn-accent-text:#fff;--btn-accent-hover:#1D1F8A;
  --input-bg:#fff;--input-border:#e5e5e5;--input-focus:#4D4FBD;
  --seg-done:#2d7a3e;--seg-run:#4D4FBD;--seg-fail:#e53935;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#111111;--bg-alt:#1a1a1a;--bg-hover:rgba(146,148,240,0.08);
  --bg-selected:rgba(146,148,240,0.12);--bg-toolbar:#1a1a1a;
  --text:#e4e4e7;--text-sec:#a1a1aa;--text-dim:#71717a;
  --border:rgba(255,255,255,0.08);--border-light:rgba(255,255,255,0.04);
  --accent:#9294F0;
  --research-dot:#9294F0;
  --pop-bg:#1e1e1e;--pop-shadow:0 4px 20px rgba(0,0,0,0.5);
  --toast-bg:#e4e4e7;--toast-text:#111111;
  --btn-bg:#262626;--btn-hover:#404040;--btn-text:#e4e4e7;
  --btn-accent-bg:#4D4FBD;--btn-accent-text:#fff;--btn-accent-hover:#9294F0;
  --input-bg:#1e1e1e;--input-border:#3f3f46;--input-focus:#9294F0;
  --seg-done:#B8E6A0;--seg-run:#9294F0;--seg-fail:#e53935;
}}
*{box-sizing:border-box}
body{font-family:'JetBrains Mono',ui-monospace,monospace;margin:0;padding:0;color:var(--text);background:var(--bg);font-size:13px;height:0;overflow:hidden}

/* ── Progress section ── */
.progress-section{padding:12px 12px 0}
.bar-bg{width:100%;background:var(--border-light);border-radius:2px;overflow:hidden;height:14px;margin:8px 0;display:flex}
.seg{height:100%;transition:width .5s ease;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:500;color:#fff;overflow:hidden;white-space:nowrap}
.seg-done{background:var(--seg-done)}.seg-run{background:var(--seg-run)}.seg-fail{background:var(--seg-fail)}.seg-pend{background:transparent}
.prog-info{font-size:12px;color:var(--text-sec);margin:6px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap;letter-spacing:0.01em}
.status-done{color:var(--seg-done);font-weight:500}.status-fail{color:var(--seg-fail);font-weight:500}
.eta{color:var(--text-dim);font-size:10px}
@keyframes flash{0%,100%{background:transparent}50%{background:rgba(45,122,62,.1)}}
.flash{animation:flash 1s ease 3}

/* ── Tab bar ── */
.tab-bar{display:flex;gap:0;border-bottom:1px solid var(--border);margin:0 12px 8px}
.tab-btn{padding:6px 16px;border:none;background:none;font-size:10px;font-weight:600;color:var(--text-dim);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s,border-color .15s;text-transform:uppercase;letter-spacing:0.05em}
.tab-btn:hover{color:var(--text)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}

/* ── Activity list (expandable aggregate cards) ── */
.activity-tab{padding:0 12px;max-height:320px;overflow-y:auto}
.activity-list{margin:0;padding:0;list-style:none}
.agg-item{margin:0 0 4px;border:1px solid var(--border);border-radius:4px;overflow:hidden;background:var(--bg);transition:background-color .15s ease}
.agg-item:last-child{margin-bottom:0}
.agg-header{display:flex;align-items:flex-start;gap:6px;padding:8px 12px;cursor:pointer;user-select:none;transition:background-color .15s ease;border-left:2px solid var(--accent)}
.agg-header:hover{background:var(--bg-hover)}
.agg-chevron{font-size:9px;color:var(--text-dim);flex-shrink:0;transition:transform .2s;margin-top:3px}
.agg-item.open .agg-chevron{transform:rotate(90deg)}
.agg-text{flex:1;font-size:12px;color:var(--text);line-height:1.5;font-style:italic}
.agg-ts{font-size:9px;color:var(--text-dim);flex-shrink:0;font-variant-numeric:tabular-nums;margin-top:2px}
.agg-micros{display:none;border-top:1px solid var(--border);padding:0;margin:0;list-style:none;background:var(--bg-alt)}
.agg-item.open .agg-micros{display:block}
.agg-micros li{padding:5px 12px 5px 24px;font-size:11px;color:var(--text-sec);line-height:1.5;border-bottom:1px solid var(--border-light)}
.agg-micros li:last-child{border-bottom:none}
.agg-micro-row{font-size:9px;color:var(--text-dim);margin-right:4px;font-weight:500}

/* ── Results table ── */
#toolbar{display:flex;align-items:center;gap:8px;padding:8px 4px;margin-bottom:8px;flex-wrap:wrap}
#toolbar #sum{font-weight:500;font-size:11px;flex:1;min-width:150px;color:var(--text-sec)}
#toolbar button{padding:5px 12px;border:1px solid var(--border);border-radius:4px;font-size:11px;font-weight:500;cursor:pointer;background:var(--btn-bg);color:var(--btn-text);transition:background-color .15s ease}
#toolbar button:hover:not(:disabled){background:var(--btn-hover)}
#toolbar button:disabled{opacity:.4;cursor:default}
#toolbar #copyBtn:not(:disabled){background:var(--btn-accent-bg);color:var(--btn-accent-text);border-color:transparent}
#toolbar #copyBtn:not(:disabled):hover{background:var(--btn-accent-hover)}
.wrap{max-height:520px;overflow:auto;border:1px solid var(--border);border-radius:4px 4px 0 0}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}
th,td{padding:6px 10px;text-align:left}
.hdr-row th{background:var(--bg-toolbar);position:sticky;top:0;z-index:3;border-bottom:1px solid var(--border);font-size:10px;font-weight:600;white-space:nowrap;cursor:pointer;user-select:none;transition:background-color .15s ease;text-transform:uppercase;letter-spacing:0.05em;color:var(--accent)}
.hdr-row th:hover{background:var(--bg-hover)}
.sort-arrow{font-size:9px;margin-left:3px;opacity:.4}
.sort-arrow.active{opacity:1;color:var(--accent)}
.flt-row th{position:sticky;top:30px;z-index:3;background:var(--bg-toolbar);padding:4px;border-bottom:1px solid var(--border);cursor:default}
.flt-row input{width:100%;padding:3px 6px;border:1px solid var(--input-border);border-radius:4px;font-size:10px;background:var(--input-bg);color:var(--text);outline:none;transition:border-color .15s ease;font-family:inherit}
.flt-row input:focus{border-color:var(--input-focus)}
.flt-row input::placeholder{color:var(--text-dim)}
td{border-bottom:1px solid var(--border-light);max-width:400px;vertical-align:top;word-wrap:break-word;white-space:pre-wrap;position:relative;transition:background-color .15s ease}
td:hover{background:var(--bg-hover)}
td.has-research::after{content:"";position:absolute;top:6px;right:4px;width:6px;height:6px;border-radius:50%;background:var(--research-dot);opacity:.6}
tr.selected td{background:var(--bg-selected)!important}
td.cell-focused{outline:1px solid var(--accent);outline-offset:-1px;z-index:2}
tr:nth-child(even) td{background:var(--bg-alt)}
tr:nth-child(even).selected td{background:var(--bg-selected)!important}
a{color:var(--accent);text-decoration:none;word-break:break-all}
a:hover{text-decoration:underline;text-underline-offset:2px}
.row-num{position:sticky;left:0;z-index:1;background:var(--bg);width:40px;min-width:40px;max-width:40px;text-align:center;color:var(--text-dim);font-size:10px;font-variant-numeric:tabular-nums;cursor:pointer;user-select:none;padding:6px 4px;box-shadow:2px 0 4px rgba(0,0,0,.04)}
tr:nth-child(even) .row-num{background:var(--bg-alt)}
.hdr-row .row-num{z-index:4;font-weight:600;color:var(--text-sec);cursor:default;background:var(--bg-toolbar)}
.flt-row .row-num{z-index:4;cursor:default;background:var(--bg-toolbar)}
tr.selected .row-num{background:var(--bg-selected)!important}
.popover{position:fixed;background:var(--pop-bg);border:1px solid var(--border);border-radius:4px;box-shadow:var(--pop-shadow);max-width:min(720px,90vw);min-width:280px;max-height:min(500px,70vh);z-index:100;overflow:hidden;opacity:0;transform:translateY(-4px);transition:opacity .15s,transform .15s;pointer-events:none;display:flex;flex-direction:column}
.popover.visible{opacity:1;transform:translateY(0);pointer-events:auto}
.pop-hdr{padding:8px 12px;font-size:10px;font-weight:600;color:var(--text-sec);border-bottom:1px solid var(--border-light);background:var(--bg-alt);text-transform:uppercase;letter-spacing:0.03em}
.pop-body{padding:10px 12px;font-size:11px;line-height:1.5;white-space:pre-wrap;overflow-y:auto;color:var(--text);flex:1}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(60px);background:var(--toast-bg);color:var(--toast-text);padding:6px 16px;border-radius:4px;font-size:11px;font-weight:500;opacity:0;transition:opacity .2s,transform .2s;pointer-events:none;z-index:200}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.resize-handle{height:4px;background:var(--border-light);cursor:ns-resize;border-radius:0 0 4px 4px;transition:background .15s;margin-top:-1px;border:1px solid var(--border);border-top:none}
.resize-handle:hover,.resize-handle.active{background:var(--accent);opacity:.4}
#expandBtn{font-size:14px;padding:5px 8px}
body.fullscreen .wrap{max-height:calc(100vh - 80px)!important}
body.fullscreen .resize-handle{display:none}
.copy-modal{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:300;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .2s}
.copy-modal.show{opacity:1;pointer-events:auto}
.copy-modal-box{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:16px;max-width:600px;width:90%;max-height:80vh;display:flex;flex-direction:column;gap:8px}
.copy-modal-box textarea{width:100%;height:300px;font-family:inherit;font-size:11px;border:1px solid var(--border);border-radius:4px;padding:8px;background:var(--input-bg);color:var(--text);resize:vertical}
.copy-modal-box .modal-btns{display:flex;gap:8px;justify-content:flex-end}
.copy-modal-box button{padding:6px 16px;border:1px solid var(--border);border-radius:4px;background:var(--btn-bg);color:var(--btn-text);cursor:pointer;font-size:11px;font-family:inherit}
.done-banner{position:fixed;top:0;left:0;right:0;background:var(--seg-done);color:#fff;padding:10px 16px;z-index:250;display:flex;align-items:center;gap:10px;font-size:12px;font-weight:500;box-shadow:0 2px 8px rgba(0,0,0,.15);transform:translateY(-100%);transition:transform .3s ease}
.done-banner.show{transform:translateY(0)}
.done-banner .banner-text{flex:1}
.done-banner .banner-close{background:none;border:none;color:#fff;font-size:18px;cursor:pointer;padding:0 4px;line-height:1;opacity:.8}
.done-banner .banner-close:hover{opacity:1}
.session-link{margin-bottom:6px;font-size:11px;display:flex;align-items:center;gap:8px}
.session-link a{font-weight:500}
.session-link .spacer{flex:1}
.col-resize-handle{position:absolute;top:0;right:-2px;width:4px;height:100%;cursor:col-resize;z-index:5;user-select:none}
.col-resize-handle:hover{background:var(--accent);opacity:.3}
body.col-resizing,body.col-resizing *{cursor:col-resize!important;user-select:none!important}
body.row-resizing,body.row-resizing *{cursor:row-resize!important;user-select:none!important}
.cell-text{display:inline}
.cell-more,.cell-less{cursor:pointer;color:var(--accent);font-size:10px;margin-left:4px;white-space:nowrap;font-weight:500;padding:1px 4px;border-radius:3px;background:rgba(77,79,189,0.08)}
.cell-more:hover,.cell-less:hover{text-decoration:underline;text-underline-offset:2px;background:rgba(77,79,189,0.15)}
.export-btns{display:inline-flex;gap:2px}
.export-btns a{font-family:inherit}
#globalSearch{padding:4px 8px;border:1px solid var(--input-border);border-radius:4px;font-size:11px;background:var(--input-bg);color:var(--text);outline:none;width:160px;transition:border-color .15s ease,width .2s ease;font-family:inherit}
#globalSearch:focus{border-color:var(--input-focus);width:220px}
#globalSearch::placeholder{color:var(--text-dim)}
.col-ghost{position:fixed;background:var(--bg-toolbar);border:1px solid var(--accent);border-radius:4px;padding:4px 8px;font-size:11px;font-weight:600;opacity:.85;pointer-events:none;z-index:200;white-space:nowrap}
body.col-dragging,body.col-dragging *{cursor:grabbing!important;user-select:none!important}
.hdr-row th.drag-over-left{box-shadow:inset 3px 0 0 var(--accent)}
.hdr-row th.drag-over-right{box-shadow:inset -3px 0 0 var(--accent)}
/* ── Widget frame ── */
.widget-frame{border:1px solid var(--border);border-radius:4px;margin:4px;overflow:hidden}
</style></head><body>
<div class="widget-frame" id="widgetFrame" style="display:none">

<!-- ── Progress section (hidden until progress mode) ── -->
<div id="progressSection" class="progress-section" style="display:none">
  <div id="progressContent"></div>
</div>

<!-- ── Tab bar (hidden until progress mode) ── -->
<div id="tabBar" class="tab-bar" style="display:none">
  <button class="tab-btn active" data-tab="activity">Activity</button>
  <button class="tab-btn" data-tab="results">Results</button>
  <span style="flex:1"></span>
  <button id="expandBtn" title="Toggle fullscreen" style="font-size:13px;padding:4px 8px;border:none;background:none;color:var(--text-dim);cursor:pointer;margin-bottom:-1px">&#x2922;</button>
</div>

<!-- ── Activity tab ── -->
<div id="activityTab" class="activity-tab" style="display:none">
  <ul class="activity-list" id="activityList"></ul>
</div>

<!-- ── Results tab (full table UI) ── -->
<div id="resultsTab" style="display:none">
<div style="display:flex;align-items:center;gap:8px;padding:0 0 6px"><input id="globalSearch" type="text" placeholder="Search all columns..." style="flex:1"></div>
<div id="toolbar">
  <span id="sum">Loading...</span>
  <button id="selAllBtn">Select all</button>
  <button id="copyBtn" disabled>Copy CSV (0)</button>
  <span class="export-btns"><button id="exportLink" title="Copy CSV download link to clipboard">Download CSV</button></span>
</div>
<div class="wrap" id="wrap" style="max-height:520px"><table id="tbl"></table></div>
<div class="resize-handle" id="resizeHandle"></div>
</div>
</div><!-- close widget-frame -->

<div id="pop" class="popover"><div class="pop-hdr"></div><div class="pop-body"></div></div>
<div id="doneBanner" class="done-banner"><span class="banner-text">Task complete — ask Claude to get the results.</span><button class="banner-close" id="closeBanner">&times;</button></div>
<div id="toast" class="toast">Copied!</div>
<div id="copyModal" class="copy-modal"><div class="copy-modal-box"><div style="font-weight:600;font-size:13px">Select all and copy (Cmd+C / Ctrl+C)</div><textarea id="copyArea" readonly></textarea><div class="modal-btns"><button id="closeCopyModal">Close</button></div></div></div>
<script type="module">
import*as _SDK from"SCRIPT_SRC";
const App=_SDK.App;
function applyTheme(){try{_SDK.applyDocumentTheme?.()}catch{}try{_SDK.applyHostStyleVariables?.()}catch{}try{_SDK.applyHostFonts?.()}catch{}}

const app=new App({name:"FutureSearch",version:"3.0.0"});
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
const widgetFrame=document.getElementById("widgetFrame");

/* ── progress & tab elements ── */
const progressSection=document.getElementById("progressSection");
const progressContent=document.getElementById("progressContent");
const tabBar=document.getElementById("tabBar");
const activityTab=document.getElementById("activityTab");
const activityList=document.getElementById("activityList");
const resultsTab=document.getElementById("resultsTab");

let sessionUrl="",csvUrl="",pollToken="",downloadUrl="";
const TRUNC=200;
let didDrag=false;
const copyFmt="csv";
let widgetActive=false;
const S={rows:[],allCols:[],filteredIdx:[],sortCol:null,sortDir:0,filters:{},globalQuery:"",selected:new Set(),lastClick:null,isFullscreen:false,focusedCell:null};

/* ── progress state ── */
let pollUrl=null,pollTimer=null,wasDone=false,pollCursor=null;
let progressMode=false,resultsFetched=false;
let currentTaskId=null;
const aggHistory=[];  /* [{aggregate,micros:[{text,row_index}],ts}] */
let activeTab="activity";

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
function truncSafe(s,len){if(s.length<=len)return s;let t=s.slice(0,len);const urlRe=/(https?:\\/\\/[^\\s<>"'\\]]+)$/;const m=t.match(urlRe);if(m){const full=s.slice(m.index).match(/^https?:\\/\\/[^\\s<>"'\\]]+/);if(full&&full[0].length>m[1].length)t=s.slice(0,m.index+full[0].length);}return t;}
function linkify(s){const parts=[];const mdRe=/\\[(.+?)\\]\\((https?:\\/\\/[^)]+)\\)/g;let last=0,m;while((m=mdRe.exec(s))!==null){if(m.index>last)parts.push({type:"text",v:s.slice(last,m.index)});parts.push({type:"link",title:m[1],url:m[2]});last=mdRe.lastIndex;}if(last<s.length)parts.push({type:"text",v:s.slice(last)});let out="";for(const p of parts){if(p.type==="link"){out+='<a href="'+escAttr(p.url)+'" target="_blank" rel="noopener noreferrer">'+esc(p.title)+"</a>";continue;}const t=p.v;const urlRe=/(https?:\\/\\/[^\\s<>"'\\)]+)/g;let ul=0,um;while((um=urlRe.exec(t))!==null){if(um.index>ul)out+=esc(t.slice(ul,um.index));out+='<a href="'+escAttr(um[1])+'" target="_blank" rel="noopener noreferrer">'+esc(um[1])+"</a>";ul=urlRe.lastIndex;}if(ul<t.length)out+=esc(t.slice(ul));}return out;}

/* ── tab switching ── */
function switchTab(tab){
  activeTab=tab;
  tabBar.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
  activityTab.style.display=tab==="activity"?"block":"none";
  resultsTab.style.display=tab==="results"?"block":"none";
}
tabBar.addEventListener("click",e=>{
  const btn=e.target.closest(".tab-btn");
  if(btn)switchTab(btn.dataset.tab);
});

/* ── expand/collapse aggregate items ── */
activityList.addEventListener("click",e=>{
  const item=e.target.closest(".agg-item");
  if(!item)return;
  /* only toggle if clicking the header area, not inside micro-summaries */
  if(e.target.closest(".agg-micros"))return;
  item.classList.toggle("open");
});

/* ── progress rendering ── */
function fmtTime(s){
  if(s<60)return s+"s";
  const m=Math.floor(s/60),sec=s%60;
  return m+"m"+((sec>0)?(" "+sec+"s"):"");
}

function renderProgress(d){
  const comp=d.completed||0,tot=d.total||0,fail=d.failed||0,run=d.running||0;
  const done=["completed","failed","revoked"].includes(d.status);
  const elapsed=d.elapsed_s||0;

  /* accumulate aggregate + micro-summaries as expandable entries */
  if(d.aggregate_summary){
    const now=new Date();
    const ts=now.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    const micros=(d.summaries||[]).map(s=>({text:s.summary||String(s),row_indices:s.row_indices||null,row_index:s.row_index}));
    /* only add if aggregate text is new */
    const lastAgg=aggHistory.length?aggHistory[aggHistory.length-1].aggregate:"";
    if(d.aggregate_summary!==lastAgg){
      aggHistory.push({aggregate:d.aggregate_summary,micros,ts});
      if(aggHistory.length>30)aggHistory.splice(0,aggHistory.length-30);
    }
  } else if(d.summaries&&d.summaries.length){
    /* fallback: no aggregate, just micro-summaries — create a placeholder entry */
    const now=new Date();
    const ts=now.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
    const micros=d.summaries.map(s=>({text:s.summary||String(s),row_indices:s.row_indices||null,row_index:s.row_index}));
    const fallbackAgg=micros[0]?.text||"Agent activity";
    const lastAgg=aggHistory.length?aggHistory[aggHistory.length-1].aggregate:"";
    if(fallbackAgg!==lastAgg){
      aggHistory.push({aggregate:fallbackAgg,micros,ts});
      if(aggHistory.length>30)aggHistory.splice(0,aggHistory.length-30);
    }
  }
  if(d.cursor)pollCursor=d.cursor;

  let h="";
  if(tot>0){
    const pDone=comp/tot*100,pRun=run/tot*100,pFail=fail/tot*100;
    h+=`<div class="bar-bg">`;
    if(pDone>0)h+=`<div class="seg seg-done" style="width:${pDone}%">${pDone>=10?Math.round(pDone)+"%":""}</div>`;
    if(pRun>0)h+=`<div class="seg seg-run" style="width:${pRun}%"></div>`;
    if(pFail>0)h+=`<div class="seg seg-fail" style="width:${pFail}%"></div>`;
    h+=`</div>`;
    h+=`<div class="prog-info">`;
    if(done){
      const cls=d.status==="completed"?"status-done":"status-fail";
      h+=`<span class="${esc(cls)}">${esc(d.status)}</span>`;
      h+=`<span>${comp}/${tot}${fail?` (${fail} failed)`:""}</span>`;
      if(elapsed)h+=`<span>${fmtTime(elapsed)}</span>`;
    }else{
      h+=`<span>${comp}/${tot}</span>`;
      if(elapsed)h+=`<span class="eta">${fmtTime(elapsed)} elapsed</span>`;
      if(comp)h+=`<span>${comp} done</span>`;
      if(run)h+=`<span>${run} running</span>`;
      if(fail)h+=`<span>${fail} failed</span>`;
      const pend=Math.max(0,tot-comp-fail-run);
      if(pend)h+=`<span>${pend} pending</span>`;
      const eta=comp>0&&elapsed>0?Math.round((tot-comp)/(comp/elapsed)):0;
      if(eta>0)h+=`<span class="eta">~${fmtTime(eta)} remaining</span>`;
    }
    h+=`</div>`;
  }else if(d.status){
    h+=`<div class="prog-info">${esc(d.status)}${elapsed?` &mdash; ${fmtTime(elapsed)}`:""}</div>`;
  }
  progressContent.innerHTML=h;

  /* render expandable aggregate activity list (newest first) */
  if(aggHistory.length){
    /* remember which items are expanded */
    const openSet=new Set();
    activityList.querySelectorAll(".agg-item.open").forEach(el=>{
      const idx=el.dataset.aggIdx;if(idx!=null)openSet.add(idx);
    });
    let al="";
    for(let i=aggHistory.length-1;i>=0;i--){
      const a=aggHistory[i];
      const hasMicros=a.micros&&a.micros.length>0;
      const isOpen=openSet.has(String(i));
      al+=`<li class="agg-item${isOpen?" open":""}" data-agg-idx="${i}">`;
      al+=`<div class="agg-header">`;
      if(hasMicros)al+=`<span class="agg-chevron">&#9654;</span>`;
      al+=`<span class="agg-text">${esc(a.aggregate)}</span>`;
      al+=`<span class="agg-ts">${esc(a.ts)}</span>`;
      al+=`</div>`;
      if(hasMicros){
        al+=`<ul class="agg-micros">`;
        for(const m of a.micros){
          let rowLabel="";
          if(m.row_indices&&m.row_indices.length>1){rowLabel=`<span class="agg-micro-row">Rows ${m.row_indices.map(r=>r+1).join(", ")}</span>`;}
          else if(m.row_index!=null){rowLabel=`<span class="agg-micro-row">Row ${m.row_index+1}</span>`;}
          al+=`<li>${rowLabel}${esc(m.text)}</li>`;
        }
        al+=`</ul>`;
      }
      al+=`</li>`;
    }
    activityList.innerHTML=al;
  }

  if(done&&!wasDone){
    wasDone=true;
    progressSection.classList.add("flash");
    /* auto-fetch results on completion */
    if(!resultsFetched)autoFetchResults();
    showDoneBanner();
  }
  if(done&&pollTimer){clearInterval(pollTimer);pollTimer=null;}
}


/* ── show completion banner ── */
const doneBanner=document.getElementById("doneBanner");
document.getElementById("closeBanner").addEventListener("click",()=>doneBanner.classList.remove("show"));
function showDoneBanner(){doneBanner.classList.add("show");}

/* ── auto-fetch results on completion ── */
async function autoFetchResults(){
  if(resultsFetched)return;
  resultsFetched=true;
  if(!downloadUrl||!pollToken){return;}
  try{
    csvUrl=downloadUrl+(downloadUrl.includes("?")?"&":"?")+"token="+encodeURIComponent(pollToken);
    const jsonUrl=csvUrl+"&format=json";
    let dataResp=await fetch(jsonUrl);
    if(dataResp.status===404){
      await new Promise(r=>setTimeout(r,2000));
      dataResp=await fetch(jsonUrl);
    }
    if(!dataResp.ok){resultsFetched=false;return;}
    const data=await dataResp.json();
    /* activate results UI */
    showResultsUI();
    processData(data);
    updateSessionLink();
    switchTab("results");
  }catch(e){
    resultsFetched=false;
  }
}

/* ── show widget UI ── */
function showResultsUI(){
  widgetActive=true;
  document.body.style.height="auto";document.body.style.overflow="visible";document.body.style.padding="0";
  widgetFrame.style.display="block";
  resultsTab.style.display="block";
  resultsTab.style.padding="0 12px 12px";
}

function enterProgressMode(d){
  progressMode=true;
  document.body.style.height="auto";document.body.style.overflow="visible";document.body.style.padding="0";
  widgetFrame.style.display="block";
  progressSection.style.display="block";
  tabBar.style.display="flex";
  activityTab.style.display="block";
  resultsTab.style.display="none";
  sessionUrl=d.session_url||sessionUrl;
  if(d.task_id)currentTaskId=d.task_id;
  /* Extract task_id from progress_url as fallback */
  if(!currentTaskId&&d.progress_url){const m=d.progress_url.match(/progress\\/([0-9a-f-]+)/);if(m)currentTaskId=m[1];}
  if(d.poll_token)pollToken=d.poll_token;
  if(d.download_url)downloadUrl=d.download_url;
  renderProgress(d);
}

/* ── polling ── */
function startPoll(){
  const opts=pollToken?{headers:{"Authorization":"Bearer "+pollToken}}:{};
  pollTimer=setInterval(async()=>{
    try{
      let url=pollUrl;
      if(pollCursor)url+=(url.includes("?")?"&":"?")+"cursor="+encodeURIComponent(pollCursor);
      const r=await fetch(url,opts);if(r.ok)renderProgress(await r.json());
    }catch{}
  },10000);
}

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
  if(obj.research!=null&&typeof obj.research==="object"&&!Array.isArray(obj.research)){
    for(const[k,v]of Object.entries(obj.research)){
      if(v!=null)research[k]=typeof v==="string"?v:String(v);
    }
  }
  const display=flat(obj);
  delete display.research;
  return{display,research};
}

function processData(data){
  if(!Array.isArray(data))data=[data];
  if(!data.length){sum.textContent="No results";tbl.innerHTML="";return;}
  S.rows=data.map(r=>flatWithResearch(r));
  const colSet=new Set();
  S.rows.forEach(r=>{for(const k of Object.keys(r.display))colSet.add(k)});
  const all=[...colSet];
  const visible=all.filter(k=>k!=="research"&&!k.startsWith("research."));
  S.allCols=[...visible.filter(k=>!k.includes(".")),...visible.filter(k=>k.includes("."))];
  S.sortCol=null;S.sortDir=0;S.filters={};S.globalQuery="";globalSearchEl.value="";S.selected.clear();S.lastClick=null;
  S.filteredIdx=S.rows.map((_,i)=>i);
  renderTable();
}

/* --- filter & sort --- */
function applyFilterAndSort(){
  let idx=S.rows.map((_,i)=>i);
  if(S.globalQuery){
    const gq=S.globalQuery.toLowerCase();
    idx=idx.filter(i=>{const row=S.rows[i].display;return Object.values(row).some(v=>v!=null&&String(v).toLowerCase().includes(gq));});
  }
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
const globalSearchEl=document.getElementById("globalSearch");
globalSearchEl.addEventListener("input",()=>{S.globalQuery=globalSearchEl.value;clearTimeout(filterTimer);filterTimer=setTimeout(()=>applyFilterAndSort(),150);});

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

  /* clear focusedCell if its row is no longer visible */
  if(S.focusedCell){const fs=new Set(S.filteredIdx);if(!fs.has(S.focusedCell.idx))S.focusedCell=null;}

  let h='<thead><tr class="hdr-row"><th class="row-num">#</th>';
  for(const c of cols){
    let arrow='<span class="sort-arrow">&#9650;</span>';
    if(S.sortCol===c)arrow=S.sortDir===1?'<span class="sort-arrow active">&#9650;</span>':'<span class="sort-arrow active">&#9660;</span>';
    h+='<th data-col="'+escAttr(c)+'" style="position:relative">'+esc(c)+arrow+'<div class="col-resize-handle"></div></th>';
  }
  h+='</tr><tr class="flt-row"><th class="row-num"></th>';
  for(const c of cols){
    h+='<th><input data-col="'+escAttr(c)+'" placeholder="Filter..." value="'+escAttr(S.filters[c]||"")+'"></th>';
  }
  h+='</tr></thead><tbody>';
  let rowNum=0;
  for(const i of S.filteredIdx){
    rowNum++;
    const row=S.rows[i],sel=S.selected.has(i)?' class="selected"':"";
    h+='<tr data-idx="'+i+'"'+sel+'><td class="row-num">'+rowNum+'</td>';
    for(const c of cols){
      const hasR=getResearch(row,c)!=null;
      const focused=S.focusedCell&&S.focusedCell.idx===i&&S.focusedCell.col===c;
      const v=row.display[c];
      let cls=hasR?(focused?' class="has-research cell-focused"':' class="has-research"'):(focused?' class="cell-focused"':"");
      const dc=' data-col="'+escAttr(c)+'"';
      if(v==null){h+="<td"+cls+dc+"></td>";}
      else{const s=String(v);
        if(s.length>TRUNC)h+='<td'+cls+dc+'><span class="cell-text">'+linkify(truncSafe(s,TRUNC))+'</span><span class="cell-more">&hellip; more</span></td>';
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
  const col=th.dataset.col;if(!col)return;
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
    td.querySelector(".cell-text").innerHTML=linkify(truncSafe(full,TRUNC));
    less.textContent="\\u2026 more";less.className="cell-more";
    return;
  }
});

/* --- selection (# column click toggles, shift extends range) --- */
tbl.addEventListener("click",e=>{
  if(e.target.closest(".hdr-row")||e.target.closest(".flt-row"))return;
  const td=e.target.closest("td");if(!td)return;
  const tr=td.closest("tbody tr");if(!tr)return;
  const idx=parseInt(tr.dataset.idx,10);if(isNaN(idx))return;

  if(td.classList.contains("row-num")){
    if(S.focusedCell){S.focusedCell=null;tbl.querySelectorAll("td.cell-focused").forEach(c=>c.classList.remove("cell-focused"));}
    if(e.shiftKey&&S.lastClick!=null){
      const posA=S.filteredIdx.indexOf(S.lastClick),posB=S.filteredIdx.indexOf(idx);
      if(posA>=0&&posB>=0){const lo=Math.min(posA,posB),hi=Math.max(posA,posB);for(let p=lo;p<=hi;p++)S.selected.add(S.filteredIdx[p]);}
    }else{
      if(S.selected.has(idx))S.selected.delete(idx);else S.selected.add(idx);
    }
    S.lastClick=idx;updateSelection();updateCopyBtn();
    return;
  }

  if(e.target.closest("a")||e.target.closest(".cell-more")||e.target.closest(".cell-less"))return;
  const col=td.dataset.col;if(!col)return;
  const prev=S.focusedCell;
  if(prev){const oldTd=tbl.querySelector('tbody tr[data-idx="'+prev.idx+'"] td[data-col="'+CSS.escape(prev.col)+'"]');if(oldTd)oldTd.classList.remove("cell-focused");}
  if(prev&&prev.idx===idx&&prev.col===col){S.focusedCell=null;}
  else{S.focusedCell={idx,col};td.classList.add("cell-focused");}
});

/* --- double-click data cell to copy value --- */
tbl.addEventListener("dblclick",e=>{
  if(e.target.closest(".col-resize-handle"))return;
  if(e.target.closest(".hdr-row")||e.target.closest(".flt-row"))return;
  const td=e.target.closest("tbody td");if(!td||td.classList.contains("row-num"))return;
  const tr=td.closest("tr");if(!tr)return;
  const idx=parseInt(tr.dataset.idx,10),col=td.dataset.col;
  if(isNaN(idx)||!col)return;
  const v=S.rows[idx]?.display[col];if(v==null)return;
  copyToClipboard(String(v)).then(ok=>{if(ok)showToast("Cell copied");});
});

function updateSelection(){
  tbl.querySelectorAll("tbody tr").forEach(tr=>{
    const idx=parseInt(tr.dataset.idx,10);tr.classList.toggle("selected",S.selected.has(idx));
  });
}
function updateCopyBtn(){const n=S.selected.size;const fl=copyFmt.toUpperCase();copyBtn.textContent=n>0?"Copy "+fl+" ("+n+")":"Copy "+fl;copyBtn.disabled=n===0;}

/* --- select all --- */
selAllBtn.addEventListener("click",()=>{
  if(S.selected.size===S.filteredIdx.length){S.selected.clear();showToast("Selection cleared");}
  else{S.selected.clear();S.filteredIdx.forEach(i=>S.selected.add(i));showToast("Selected all "+S.filteredIdx.length+" rows");}
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
  /* Clipboard API often fails in sandboxed iframes — try it first,
     fall back to execCommand, then show modal for manual copy. */
  try{await navigator.clipboard.writeText(text);showToast(msg);return;}catch{}
  try{if(execCopy(text)){showToast(msg);return;}}catch{}
  showCopyModal(text);
});
closeCopyModal.addEventListener("click",()=>copyModal.classList.remove("show"));
copyModal.addEventListener("click",e=>{if(e.target===copyModal)copyModal.classList.remove("show");});
function showToast(msg){toast.textContent=msg;toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),2000);}


/* --- popover --- */
let popTimer=null,popTarget=null,popVisible=false;

function showPopover(td){
  const tr=td.closest("tr");const idx=parseInt(tr.dataset.idx,10);const col=td.dataset.col;
  const row=S.rows[idx];if(!row)return;
  const text=getResearch(row,col);if(text==null)return;
  popHdr.textContent="research."+col.replace(/^research\\./,"");
  popBody.innerHTML=linkify(text);
  const rect=td.getBoundingClientRect();
  let left=rect.left,top=rect.bottom-8;
  pop.classList.add("visible");popVisible=true;
  const pw=pop.offsetWidth,ph=pop.offsetHeight;
  if(left+pw>window.innerWidth-8)left=window.innerWidth-pw-8;
  if(left<8)left=8;
  if(top+ph>window.innerHeight-8)top=rect.top-ph+8;
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
    if(popVisible)popTimer=setTimeout(()=>{if(!pop.matches(":hover"))hidePopover();},400);
  }
});
pop.addEventListener("mouseleave",()=>{clearTimeout(popTimer);hidePopover();});
document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){
    if(copyModal.classList.contains("show")){copyModal.classList.remove("show");return;}
    if(S.focusedCell){S.focusedCell=null;tbl.querySelectorAll("td.cell-focused").forEach(c=>c.classList.remove("cell-focused"));return;}
    if(popVisible)hidePopover();
    return;
  }
  if((e.metaKey||e.ctrlKey)&&e.key==="c"){
    const ae=document.activeElement;
    if(ae&&(ae.tagName==="INPUT"||ae.tagName==="TEXTAREA"))return;
    if(copyModal.classList.contains("show"))return;
    if(S.selected.size>0){
      e.preventDefault();
      const text=buildCopyText();
      const msg="Copied "+S.selected.size+" row"+(S.selected.size>1?"s":"")+" as "+copyFmt.toUpperCase();
      copyToClipboard(text).then(ok=>{if(ok)showToast(msg);else showCopyModal(text);});
      return;
    }
    if(S.focusedCell){
      e.preventDefault();
      const v=S.rows[S.focusedCell.idx]?.display[S.focusedCell.col];
      if(v!=null)copyToClipboard(String(v)).then(ok=>{if(ok)showToast("Cell copied");});
    }
  }
});

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
  dragCol=th.dataset.col;if(!dragCol)return;dragStartX=e.clientX;dragStartY=e.clientY;colDragging=false;
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
    const hdrs=[...tbl.querySelectorAll(".hdr-row th")].filter(h=>h.dataset.col);
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
    const hdrs=[...tbl.querySelectorAll(".hdr-row th")].filter(h=>h.dataset.col);
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

function getDownloadUrl(){
  if(downloadUrl&&pollToken){
    return downloadUrl+(downloadUrl.includes("?")?"&":"?")+"token="+encodeURIComponent(pollToken);
  }
  return csvUrl;
}
function updateDownloadLink(){updateSessionLink();}
document.getElementById("exportLink")?.addEventListener("click",()=>{
  const url=getDownloadUrl();
  if(!url){showToast("No download link yet");return;}
  app.openLink({url}).catch(()=>showCopyModal(url));
});

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

function updateSessionLink(){}

/* --- data loading (for standalone results entry) --- */
async function fetchFullResultsWithFreshToken(hasPreview,total){
  const base=getDownloadUrl();
  if(!base){if(!hasPreview)sum.textContent="Download link expired";return;}
  const url=base+(base.includes("?")?"&":"?")+"format=json&include_research=1";
  fetchFullResults(url,{},hasPreview,total);
}
function fetchFullResults(url,opts,hasPreview,total){
  if(!hasPreview)sum.textContent="Loading"+(total?" "+total+" rows":"")+"...";
  fetch(url,opts).then(r=>{
    if(!r.ok)throw new Error(r.status+" "+r.statusText);
    return r.json();
  }).then(data=>processData(data)).catch(err=>{
    if(hasPreview){showToast("Full load failed, showing preview");}
    else{
      sum.innerHTML=esc("Failed to load: "+err.message)+' <button id="retryBtn" style="margin-left:8px;padding:2px 10px;border:1px solid var(--border);border-radius:4px;background:var(--btn-bg);color:var(--btn-text);cursor:pointer;font-size:12px">Retry</button>';
      document.getElementById("retryBtn")?.addEventListener("click",()=>fetchFullResultsWithFreshToken(hasPreview,total));
    }
  });
}

/* ── fetch last aggregate summary (for re-mount when task already done) ── */
async function backfillSummaries(prefetched){

  let d=prefetched;
  if(!d){
    if(!pollUrl||!pollToken)return;
    try{
      const opts=pollToken?{headers:{"Authorization":"Bearer "+pollToken}}:{};
      const r=await fetch(pollUrl,opts);
      if(!r.ok)return;
      d=await r.json();
    }catch{return;}
  }
  /* Timeline rehydration: stored aggregates with their micro-summaries */
  if(d.timeline&&d.timeline.length){
    for(const entry of d.timeline){
      const ts=new Date(entry.created_at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
      const micros=(entry.micro_summaries||[]).map(s=>({text:s.summary||String(s),row_indices:s.row_indices||null,row_index:s.row_index}));
      aggHistory.push({aggregate:entry.summary,micros,ts});
    }
    if(d.cursor)pollCursor=d.cursor;
    if(aggHistory.length>30)aggHistory.splice(0,aggHistory.length-30);

  }
  /* Render current state (progress bar + activity list) */
  renderProgress(d);
}

/* ── ontoolresult: unified entry point ── */
app.ontoolresult=({content,structuredContent})=>{

  /* Entry 1: structuredContent from futuresearch_status (widget data) */
  if(structuredContent&&structuredContent.progress_url){
    enterProgressMode(structuredContent);
    pollUrl=structuredContent.progress_url;
    /* Claude.ai caches the original tool result — structuredContent.status
       may be stale (e.g. "running" even though the task completed).
       Always do a one-off fetch to get current status before deciding path. */
    (async()=>{
      try{
        const opts=structuredContent.poll_token?{headers:{"Authorization":"Bearer "+structuredContent.poll_token}}:{};
        const r=await fetch(pollUrl,opts);
        if(!r.ok){if(!pollTimer)startPoll();return;}
        const d=await r.json();
        const currentStatus=d.status||structuredContent.status;
        const done=["completed","failed","revoked"].includes(currentStatus);

        /* Always backfill stored timeline on mount (covers mid-execution re-mount too) */
        await backfillSummaries(d);
        if(done){
          wasDone=true;
          if(!resultsFetched)autoFetchResults();
        } else if(!pollTimer){
          startPoll();
        }
      }catch(e){

        if(!pollTimer)startPoll();
      }
    })();
    return;
  }

  /* Entry 2: content JSON from submission tools (progress_url embedded in text) */
  if(content){
    const t=content.find(c=>c.type==="text");
    if(t){
      try{
        const d=JSON.parse(t.text);
        if(d.progress_url){
          enterProgressMode(d);
          pollUrl=d.progress_url;
          /* Same live-check as Entry 1 — cached status may be stale */
          (async()=>{
            try{
              const opts=d.poll_token?{headers:{"Authorization":"Bearer "+d.poll_token}}:{};
              const r2=await fetch(pollUrl,opts);
              if(!r2.ok){if(!pollTimer)startPoll();return;}
              const d2=await r2.json();
              const currentStatus=d2.status||d.status;
              const done2=["completed","failed","revoked"].includes(currentStatus);
              await backfillSummaries(d2);
              if(done2){
                wasDone=true;
                if(!resultsFetched)autoFetchResults();
              } else if(!pollTimer){
                startPoll();
              }
            }catch(e2){
              if(!pollTimer)startPoll();
            }
          })();
          return;
        }
      }catch{}
    }
  }

  /* Legacy: standalone results data (kept for compatibility) */
  if(structuredContent){
    const meta=structuredContent;
    const isWidget=meta.fetch_full_results||meta.preview||Array.isArray(meta);
    if(!isWidget)return;
    showResultsUI();
    if(meta.session_url&&!sessionUrl){sessionUrl=meta.session_url;updateSessionLink();}
    if(meta.poll_token){pollToken=meta.poll_token;}
    if(meta.download_url){downloadUrl=meta.download_url;}
    if(meta.csv_url){csvUrl=meta.csv_url;updateDownloadLink();}
    if(meta.fetch_full_results){
      if(meta.preview)processData(meta.preview);
      fetchFullResultsWithFreshToken(!!meta.preview,meta.total);
    }else if(meta.preview){processData(meta.preview);}
    else if(Array.isArray(meta)){processData(meta);}
  }
};

await app.connect();
applyTheme();
</script></body></html>""".replace("SCRIPT_SRC", _APP_SCRIPT_SRC)
