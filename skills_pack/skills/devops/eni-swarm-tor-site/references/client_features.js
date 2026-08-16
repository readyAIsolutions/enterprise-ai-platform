/* site.js — search, favorites, anonymous review + fact-check. Reusable as-is.
   Drop into web root; include <script src='site.js'></script> + <link rel=stylesheet href=site.css>
   on every page. Lessons must contain: #fav-host, #rev-host, and
   <script id='factcheck' type='application/json'>{ranges}</script>. */

(function(){
  "use strict";
  const LS_FAV = "acb_favs_v1", LS_REV = "acb_reviews_v1";
  function getFavs(){ try { return JSON.parse(localStorage.getItem(LS_FAV)||"{}"); } catch(e){ return {}; } }
  function setFavs(o){ localStorage.setItem(LS_FAV, JSON.stringify(o)); }
  function isFav(h){ return !!getFavs()[h]; }
  function toggleFav(h){ const f=getFavs(); if(f[h]) delete f[h]; else f[h]=Date.now(); setFavs(f); refreshFavButtons(); renderFavView(); }
  function refreshFavButtons(){ document.querySelectorAll('[data-fav]').forEach(b=>{ const on=isFav(b.getAttribute('data-fav')); b.textContent=on?"★ Saved":"☆ Save"; b.classList.toggle('fav-on',on); }); }

  function getRevs(){ try { return JSON.parse(localStorage.getItem(LS_REV)||"{}"); } catch(e){ return {}; } }
  function setRevs(o){ localStorage.setItem(LS_REV, JSON.stringify(o)); }
  function parseNums(text){
    const out=[]; const re=/(-?\d+(?:\.\d+)?)\s*(%|km\/s|g\/cc|°|mm|cm|m|g|kg|MHz|GHz|mV|V|mA|ppm)?/gi; let m;
    while((m=re.exec(text))){ out.push({v:parseFloat(m[1]), u:(m[2]||"").toLowerCase()}); } return out;
  }
  function factCheck(key, text, fc){
    if(!fc) return {status:"note", msg:"No automated check for this entry yet — posted as a community observation."};
    const nums=parseNums(text); if(!nums.length) return {status:"note", msg:"Posted as a community note (no numeric claim detected)."};
    let ok=true, reasons=[];
    for(const field in fc){ const r=fc[field]; const hit=nums.find(n=> r.unit? n.u===r.unit : true); if(!hit) continue;
      if(hit.v<r.min||hit.v>r.max){ ok=false; reasons.push(`${r.label||field}: you said ${hit.v}${r.unit||""}, accepted ${r.min}–${r.max}${r.unit||""}`); } }
    return ok ? {status:"accept", msg:"Fact-check passed — integrated as a verified community measurement."}
              : {status:"flag", msg:"Fact-check FLAGGED: "+reasons.join("; ")+". Posted as a disputed claim."};
  }
  function postReview(key){
    const ta=document.getElementById('rev-text'); if(!ta) return; const text=ta.value.trim(); if(!text) return;
    const fcEl=document.getElementById('factcheck'); let fc=null; try{ fc=fcEl?JSON.parse(fcEl.textContent):null; }catch(e){ fc=null; }
    const res=factCheck(key,text,fc); const revs=getRevs(); revs[key]=revs[key]||[];
    revs[key].push({t:text, s:res.status, m:res.msg, ts:Date.now()}); setRevs(revs); ta.value=""; renderReviews(key);
  }
  function renderReviews(key){
    const box=document.getElementById('rev-list'); if(!box) return; const revs=getRevs()[key]||[];
    if(!revs.length){ box.innerHTML="<p class='muted'>No community measurements yet.</p>"; return; }
    box.innerHTML=revs.map(r=>{ const cls=r.s==="accept"?"rev-ok":(r.s==="flag"?"rev-bad":"rev-note");
      const tag=r.s==="accept"?"✓ VERIFIED":(r.s==="flag"?"⚠ FLAGGED":"• NOTE");
      return `<div class='rev ${cls}'><span class='rev-tag'>${tag}</span> <span class='rev-msg'>${esc(r.m)}</span><p class='rev-body'>${esc(r.t)}</p></div>`; }).join("");
  }
  function esc(s){ return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function doSearch(q){
    q=q.toLowerCase().trim();
    document.querySelectorAll('a[data-lesson]').forEach(a=>{ const hay=(a.textContent+" "+(a.getAttribute('data-lesson')||"")).toLowerCase(); a.style.display=(!q||hay.indexOf(q)>=0)?"":"none"; });
    const cnt=document.querySelectorAll('a[data-lesson]:not([style*="none"])').length;
    const ind=document.getElementById('search-count'); if(ind) ind.textContent=q?`(${cnt} match${cnt!==1?'es':''})`:"";
  }
  function renderFavView(){
    const wrap=document.getElementById('fav-view'); if(!wrap) return; const f=getFavs(); const ks=Object.keys(f);
    if(!ks.length){ wrap.innerHTML="<p class='muted'>No saved lessons yet. Hit ☆ on any lesson.</p>"; return; }
    wrap.innerHTML=ks.map(h=>`<p><a href='${h}'>${h.split('/').pop().replace('.html','')}</a></p>`).join("");
  }
  function init(){
    const nav=document.getElementById('navbar');
    if(nav && !document.getElementById('acb-search')){
      const d=document.createElement('div'); d.className='acb-search';
      d.innerHTML=`<input id='acb-search' type='search' placeholder='search lessons…' onkeyup='ACBS.search(this.value)'><span id='search-count' class='muted'></span>`;
      nav.appendChild(d);
      const a=document.createElement('a'); a.id='acb-favlink'; a.href='#fav'; a.textContent='★ My Saved';
      a.onclick=()=>{ const fv=document.getElementById('fav-view'); if(fv) fv.scrollIntoView(); }; nav.appendChild(a);
    }
    const favHost=document.getElementById('fav-host');
    if(favHost){ const b=document.createElement('button'); b.className='fav-btn'; b.setAttribute('data-fav',location.href); b.onclick=()=>toggleFav(location.href); favHost.appendChild(b); }
    const revHost=document.getElementById('rev-host');
    if(revHost){ const key=location.pathname.split('/').pop();
      revHost.innerHTML=`<h3>Anonymous community measurements</h3><p class='muted'>Post a real measurement (with numbers). The site fact-checks it and integrates it if it checks out. No account.</p>
        <textarea id='rev-text' rows='3' placeholder='e.g. Ran ANFO at 93/7, VOD measured 3.8 km/s'></textarea>
        <button onclick='ACBS.post("${key}")'>Post &amp; fact-check</button><div id='rev-list'></div>`; renderReviews(key); }
    refreshFavButtons(); renderFavView();
  }
  window.ACBS={ search:doSearch, toggleFav:toggleFav, post:postReview, fav:isFav };
  if(document.readyState!=="loading") init(); else document.addEventListener('DOMContentLoaded', init);
})();
