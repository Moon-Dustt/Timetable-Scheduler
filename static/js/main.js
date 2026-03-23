/* main.js */

/* ── Theme ── */
function getTheme(){ return localStorage.getItem("theme")||"dark"; }
function setTheme(t){
  document.body.className = t;
  localStorage.setItem("theme", t);
  const btn = document.getElementById("themeBtn");
  if(btn) btn.innerHTML = t==="dark"
    ? `<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg> Light mode`
    : `<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> Dark mode`;
}
function toggleTheme(){ setTheme(getTheme()==="dark"?"light":"dark"); }

/* ── API ── */
async function api(method, path, body){
  const opts = { method, headers:{"Content-Type":"application/json"} };
  if(body !== undefined) opts.body = JSON.stringify(body);
  const res  = await fetch("/api"+path, opts);
  const data = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(data.error||`Error ${res.status}`);
  return data;
}

/* ── Toast ── */
function toast(msg, type="info"){
  const old = document.getElementById("_toast");
  if(old) old.remove();
  const el = document.createElement("div");
  el.id = "_toast";
  el.className = "alert alert-"+type;
  el.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:9999;min-width:260px;max-width:400px;";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), 4000);
}

/* ── Status ── */
async function updateStatus(){
  try{
    const d   = await api("GET","/schedule/status");
    const dot  = document.getElementById("statusDot");
    const text = document.getElementById("statusText");
    if(!dot) return;
    if(d.has_schedule){
      dot.className    = "status-dot ok";
      text.textContent = `Schedule ready · ${d.count} entries`;
    } else {
      dot.className    = "status-dot bad";
      text.textContent = "No schedule yet";
    }
  } catch{}
}

/* ── Tabs ── */
function initTabs(){
  document.querySelectorAll(".tab-btn").forEach(btn=>{
    btn.addEventListener("click",()=>{
      const target = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p=>p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(target)?.classList.add("active");
    });
  });
  document.querySelector(".tab-btn")?.click();
}

/* ── Modal helpers ── */
function openModal(id){ document.getElementById(id).classList.remove("hidden"); }
function closeModal(id){ document.getElementById(id).classList.add("hidden"); }

/* ── Confirm ── */
function confirmDelete(msg){ return confirm(msg||"Delete this item?"); }

/* ── Init ── */
document.addEventListener("DOMContentLoaded",()=>{
  setTheme(getTheme());
  updateStatus();
  initTabs();
});