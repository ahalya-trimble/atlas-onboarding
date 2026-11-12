(function () {
  const D = window.ATLAS, $ = (s, r = document) => r.querySelector(s);
  const KEY = "atlas-explorer-v2";
  const EMO = /[\p{Extended_Pictographic}\uFE0F\u200D\u20E3]/gu;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const md = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|\s)_([^_]+)_/g, "$1<i>$2</i>");
  const phaseOf = id => D.phases.find(p => p.id === id);
  const lessonsOf = pid => D.lessons.filter(l => l.phase === pid);
  const byId = id => D.lessons.find(l => l.id === ((D.legacyIds || {})[id] || id));

  let checkout = "";
  const emptyState = () => ({ done: {}, quiz: {}, xp: 0, unlock: false, profile: null, updatedAt: 0 });
  const storageKey = () => checkout ? KEY + ":" + checkout : KEY;
  const readState = key => { try { return Object.assign(emptyState(), JSON.parse(localStorage.getItem(key) || "null") || {}); } catch (e) { return emptyState(); } };
  let S = readState(KEY);
  const migrate = () => { const m = D.legacyIds || {}; ["done", "quiz"].forEach(k => { const o = S[k] || {}; Object.keys(m).forEach(old => { if (old in o) { o[m[old]] = o[old]; delete o[old]; } }); }); };
  migrate();
  const localWork = () => !!(S.profile || S.skipProfile || S.xp || Object.keys(S.done || {}).length || Object.keys(S.quiz || {}).length);

  const save = () => { S.updatedAt = Math.max(Date.now(), (S.updatedAt || 0) + 1); if (checkout) S.checkout = checkout; try { localStorage.setItem(storageKey(), JSON.stringify(S)); } catch (e) {} pushProgress(); };

  /* ---------- personalization ---------- */
  const ROLES = {
    technician: { label: "Service technician", blurb: "You repair instruments in Atlas. We start with the desktop repair workflow.", path: ["atlas-overview", "atlas-startup-navigation", "atlas-access-and-licensing", "technician-workflow", "service-case-details", "service-content", "device-plugins", "warranty-and-support", "offline-and-sync", "installation-and-recovery", "desktop-ai-assistant", "baseline-calibration", "eatlas-overview", "atlas-eatlas-architecture"] },
    manager: { label: "Service manager", blurb: "You manage cases and licenses in eAtlas. We start with the web side.", path: ["atlas-overview", "eatlas-overview", "eatlas-management", "eatlas-content", "technician-workflow", "service-case-details", "atlas-access-and-licensing", "atlas-eatlas-architecture", "master-data-sync", "ems-licensing"] },
    developer: { label: "Developer", blurb: "You will change the code. Concepts first, then a guided source tour.", path: [] },
    qa: { label: "QA / tester", blurb: "You verify behavior. Workflows and rules first, then how data moves.", path: ["atlas-overview", "technician-workflow", "service-case-details", "warranty-and-support", "offline-and-sync", "baseline-calibration", "eatlas-overview", "eatlas-management", "atlas-eatlas-architecture", "master-data-sync"] },
    support: { label: "Support / operations", blurb: "You help people who are stuck. Access, recovery and data pipelines first.", path: ["atlas-overview", "atlas-startup-navigation", "atlas-access-and-licensing", "offline-and-sync", "installation-and-recovery", "technician-workflow", "warranty-and-support", "eatlas-overview", "atlas-eatlas-architecture", "master-data-sync", "ems-licensing", "instrument-constants-pipeline"] }
  };
  const role = () => (S.profile && ROLES[S.profile.role]) || null;
  const order = () => { const p = role() ? role().path : []; return [...p.map(byId), ...D.lessons.filter(l => !p.includes(l.id))].filter(Boolean); };
  const isRec = id => role() && role().path.includes(id);
  const profileLine = () => S.profile ? `Learner profile: role=${ROLES[S.profile.role].label}; experience=${S.profile.exp}; goal=${S.profile.goal || "learn Atlas and eAtlas"}.` : "";

  const LEVELS = [["Beginner", 0], ["Associate", 150], ["Practitioner", 400], ["Specialist", 800], ["Expert", 1300]];
  const level = () => { let l = LEVELS[0]; for (const x of LEVELS) if (S.xp >= x[1]) l = x; return l[0]; };
  const codeUnlocked = () => S.unlock || D.phases.filter(p => !p.code).every(p => lessonsOf(p.id).every(l => S.done[l.id]));
  const pct = pid => { const ls = lessonsOf(pid); return Math.round(100 * ls.filter(l => S.done[l.id]).length / ls.length); };
  const nextLesson = () => order().find(l => !S.done[l.id] && (!phaseOf(l.phase).code || codeUnlocked()));

  /* ---------- chrome ---------- */
  function renderTop() {
    const total = D.lessons.length, done = D.lessons.filter(l => S.done[l.id]).length;
    $("#xp").innerHTML = `<span class="lvl">${S.profile ? esc(S.profile.name) + " · " : ""}${level()}</span><div class="bar"><i style="width:${Math.round(100 * done / total)}%"></i></div><span class="xpn">${done} of ${total} lessons</span>`;
  }
  function renderSide() {
    const cur = (location.hash.match(/lesson\/(.+)/) || [])[1], h = location.hash.replace("#/", "");
    $("#side").innerHTML = `<a class="nav ${!cur && /^(home)?$/.test(h) ? "on" : ""}" href="#/home">Overview</a><a class="nav ${h === "setup" ? "on" : ""}" href="#/setup">Setup guide</a>` +
      D.phases.map(p => {
        const lock = p.code && !codeUnlocked();
        return `<div class="ph" style="--c:${p.color}"><div class="phh"><b>${p.n}. ${p.name}</b><em>${pct(p.id)}%</em></div>` +
          lessonsOf(p.id).map(l => `<a class="nav ${cur === l.id ? "on" : ""} ${isRec(l.id) ? "rec" : ""}" href="#/lesson/${l.id}"><span class="dot ${S.done[l.id] ? "ok" : lock ? "lk" : ""}"></span>${esc(l.title)}</a>`).join("") + `</div>`;
      }).join("") +
      `<div class="ph"><a class="nav ${h === "glossary" ? "on" : ""}" href="#/glossary">Glossary</a><a class="nav ${h === "summary" ? "on" : ""}" href="#/summary">Save-state summary</a><a class="nav" href="#" data-profile>Edit my profile</a></div>`;
    $("#side [data-profile]").onclick = e => { e.preventDefault(); profileModal(); };
  }

  /* ---------- hero animation + flowchart + diagrams ---------- */
  function heroSvg() {
    const N = ["Technician", "Atlas.exe", "OData Service", "Atlas SQL", "eAtlas", "Service Manager"];
    const w = 118, g = 36, x = i => 8 + i * (w + g);
    const L = [[0, 1], [1, 2], [2, 3], [4, 3], [5, 4]];
    return `<svg class="herosvg fc" viewBox="0 0 900 200" aria-label="Atlas at a glance">
      ${L.map(([a, b], i) => { const x1 = a < b ? x(a) + w : x(a), x2 = a < b ? x(b) : x(b) + w; return `<path id="hp${i}" d="M${x1},58 L${x2},58" class="edge flow"/><circle r="4.5" class="pkt"><animateMotion dur="${2.2 + i * .3}s" repeatCount="indefinite" begin="${i * .35}s"><mpath href="#hp${i}"/></animateMotion></circle>`; }).join("")}
      <path d="M${x(1) + w / 2},78 L${x(1) + w / 2},138" class="edge"/><path d="M${x(3) + w / 2},138 L${x(3) + w / 2},78" class="edge flow" id="hs"/><circle r="4.5" class="pkt"><animateMotion dur="2s" repeatCount="indefinite"><mpath href="#hs"/></animateMotion></circle>
      ${N.map((t, i) => `<g class="hn"><rect x="${x(i)}" y="38" width="${w}" height="40" rx="9"/><text x="${x(i) + w / 2}" y="63" text-anchor="middle">${t}</text></g>`).join("")}
      <g class="hn"><rect x="${x(1)}" y="138" width="${w}" height="40" rx="9"/><text x="${x(1) + w / 2}" y="163" text-anchor="middle">Local MongoDB</text></g>
      <g class="hn"><rect x="${x(3)}" y="138" width="${w}" height="40" rx="9"/><text x="${x(3) + w / 2}" y="163" text-anchor="middle">Salesforce TWoD</text></g>
      <text x="${x(0)}" y="22" class="cap">Desktop side</text><text x="${x(4)}" y="22" class="cap">Web side</text></svg>`;
  }

  function flowchart(v) {
    const cx = 250, W = 780, gap = 42; let y = 16; const nodes = [], edges = [];
    const fo = (x, yy, w, hh, t, cls) => `<foreignObject x="${x}" y="${yy}" width="${w}" height="${hh}"><div xmlns="http://www.w3.org/1999/xhtml" class="fot ${cls || ""}">${esc(t)}</div></foreignObject>`;
    v.items.forEach((n, i) => {
      const h = n.k === "d" ? 100 : 50, cy = y + h / 2;
      if (n.k === "d") nodes.push(`<polygon class="fc-d" points="${cx - 170},${cy} ${cx},${y} ${cx + 170},${cy} ${cx},${y + h}"/>` + fo(cx - 105, cy - 34, 210, 68, n.t));
      else nodes.push(`<rect class="${n.k === "s" ? "fc-s" : "fc-p"}" x="${cx - 150}" y="${y}" width="300" height="${h}" rx="${n.k === "s" ? 25 : 9}"/>` + fo(cx - 140, y + 3, 280, h - 6, n.t));
      if (n.stop) nodes.push(`<path class="edge" d="M${cx + 170},${cy} L${cx + 225},${cy}" marker-end="url(#fa)"/><text class="elab" x="${cx + 182}" y="${cy - 6}">${esc(n.no || "No")}</text><rect class="fc-x" x="${cx + 226}" y="${cy - 29}" width="290" height="58" rx="9"/>` + fo(cx + 232, cy - 26, 278, 52, n.stop, "x"));
      if (i < v.items.length - 1) edges.push(`<path class="edge" d="M${cx},${y + h} L${cx},${y + h + gap}" marker-end="url(#fa)"/>${n.k === "d" ? `<text class="elab" x="${cx + 8}" y="${y + h + 24}">Yes</text>` : ""}`);
      n._cy = cy; y += h + gap;
    });
    const H = y - gap + 16, p = `M${cx},${v.items[0]._cy} L${cx},${v.items[v.items.length - 1]._cy}`;
    return `<div class="fchead">${esc(v.title)}</div><svg class="fcsvg fc" viewBox="0 0 ${W} ${H}" role="img"><defs><marker id="fa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>
      ${edges.join("")}${nodes.join("")}<circle r="6" class="pkt"><animateMotion dur="${v.items.length * 1.6}s" repeatCount="indefinite" path="${p}"/></circle></svg>`;
  }

  const MOCK = {
    "Product Details": ["Product Details", "Identify the unit (serial or auto-detect). Tabs: Overview, Service Bulletin, Service Case History. Then open a service case."],
    "My Service Cases": ["My Service Cases", "Cases assigned to or opened by the technician. A manager's eAtlas assignment shows up here."],
    "Dashboard": ["Dashboard", "Embedded Chromium showing eAtlas pages (cases, licenses, authorizations). The eAtlas URL comes from OData."],
    "Settings": ["Settings", "Application settings, including launching Baseline Calibration Software."],
    "Help / About": ["Help and About", "Help library and About information."]
  };
  function mock() {
    return `<div class="mock"><div class="mockbar"><i></i><i></i><i></i><span>Atlas.exe (illustrative layout built from the docs)</span></div><div class="mockbody"><nav>${Object.keys(MOCK).map((k, i) => `<button class="${i ? "" : "on"}" data-mock="${esc(k)}">${esc(MOCK[k][0])}</button>`).join("")}</nav>
      <div class="mockmain" data-mockmain><h4>${MOCK["Product Details"][0]}</h4><p>${MOCK["Product Details"][1]}</p></div></div></div>`;
  }
  const NODES = {
    tech: [30, 30, "Technician", "#3b82f6", "Uses Atlas.exe on a Windows PC."],
    atlas: [30, 150, "Atlas.exe", "#3b82f6", "WPF desktop app (AlmanacApp/Almanac). Hub of the whole product."],
    mongo: [30, 270, "Local MongoDB", "#2a9d8f", "Local copy of server data; used offline and for fast reads. Rebuilt by Force Sync or Reset."],
    inst: [30, 390, "Instrument + plugins", "#c9a227", "Detector and operation DLLs/EXEs implementing the Almanac API; they report pass/fail."],
    mtp: [345, 30, "MTP", "#c9a227", "External system giving sales and warranty by serial. Also receives DWCR claims."],
    odata: [345, 150, "OData Service", "#3b82f6", "Primary backend (/odata on IIS). Cases, catalog, sync, licensing actions, MTP lookups."],
    sql: [345, 270, "Atlas SQL", "#d4893a", "ONE shared SQL database used by both OData and eAtlas."],
    ems: [345, 390, "EMS v4", "#6366a8", "Entitlements for Atlas application seats. AtlasEMSIntegrationService writes licenses into SQL."],
    mgr: [660, 30, "Service Manager", "#8b5cf6", "Uses eAtlas in a browser to see company cases and licenses and to assign cases."],
    eatlas: [660, 150, "eAtlas", "#8b5cf6", "Web app, secondary REST API for the desktop, and the embedded Dashboard."],
    sync: [660, 270, "TWoD Sync (05:00)", "#2a9d8f", "Azure WebJob. Incremental Salesforce to Atlas SQL (companies, users, catalog, bulletins)."],
    twod: [660, 390, "Salesforce (TWoD)", "#2a9d8f", "System of record for products, companies, users, bulletins and authorizations."]
  };
  const EDGES = [
    ["tech", "atlas", "uses", [[115, 86], [115, 150]], 0], ["atlas", "mongo", "cache / offline", [[115, 206], [115, 270]], 0],
    ["atlas", "inst", "plugins", [[30, 178], [12, 178], [12, 418], [30, 418]], 0], ["atlas", "odata", "primary", [[200, 178], [345, 178]], 1],
    ["atlas", "eatlas", "dashboard + /api", [[115, 150], [115, 122], [745, 122], [745, 150]], 1], ["odata", "mtp", "sales/warranty", [[430, 150], [430, 86]], 0],
    ["odata", "sql", "EF6", [[430, 206], [430, 270]], 0], ["eatlas", "sql", "EF Core", [[745, 206], [745, 238], [500, 238], [500, 270]], 0],
    ["mgr", "eatlas", "browser", [[745, 86], [745, 150]], 0], ["sync", "sql", "daily write", [[660, 298], [515, 298]], 1],
    ["twod", "sync", "queryAll", [[745, 390], [745, 326]], 0], ["ems", "sql", "licenses", [[430, 390], [430, 326]], 0]
  ];
  function arch() {
    const W = 170, H = 56;
    return `<svg class="arch fc" viewBox="0 0 860 470" role="img" aria-label="Atlas architecture"><defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>
      ${EDGES.map(e => `<g><polyline points="${e[3].map(p => p.join(",")).join(" ")}" class="edge ${e[4] ? "flow" : ""}" marker-end="url(#ah)"/><text x="${e[3][Math.floor(e[3].length / 2)][0] + 6}" y="${e[3][Math.floor(e[3].length / 2)][1] - 4}" class="elab">${e[2]}</text></g>`).join("")}
      ${Object.entries(NODES).map(([k, n]) => `<g class="node" data-node="${k}" tabindex="0" role="button" aria-label="${esc(n[2])}" style="--c:${n[3]}"><rect x="${n[0]}" y="${n[1]}" width="${W}" height="${H}" rx="12"/><text x="${n[0] + W / 2}" y="${n[1] + 33}" text-anchor="middle">${esc(n[2])}</text></g>`).join("")}</svg>
      <div class="stepinfo" data-archinfo>Select any box to see what it does. Animated lines show the main data flow.</div>`;
  }
  function dsDemo() {
    return `<div class="ds"><div class="dsctl"><label>DataSource <select data-ds><option>Cache</option><option>Server</option><option selected>CacheOrServer</option><option>ServerOrCache</option></select></label>
      <label>Network <select data-net><option value="1">Online</option><option value="0">Offline</option></select></label>
      <label>Mongo has data? <select data-mongo><option value="1">Yes</option><option value="0">No (empty)</option></select></label></div><div class="dsout" data-dsout></div></div>`;
  }
  function dsCalc(root) {
    const ds = $("[data-ds]", root).value, on = $("[data-net]", root).value === "1", mg = $("[data-mongo]", root).value === "1";
    let path = [], res = ""; const M = "Local MongoDB", O = "OData (server)";
    if (ds === "Cache") { path = [M]; res = mg ? "Returns cached data." : "Returns nothing (cache only)."; }
    else if (ds === "Server") { path = [O]; res = on ? "Returns server data." : "Fails: offline."; }
    else if (ds === "CacheOrServer") { path = [M]; if (mg) res = "Cache hit, done."; else { path.push(O); res = on ? "Cache empty, fell back to OData." : "Cache empty and offline: nothing."; } }
    else { if (on) { path = [O]; res = "Prefers server, done."; } else { path = [O + " (unreachable)", M]; res = mg ? "Server unreachable, used cache." : "Both unavailable."; } }
    $("[data-dsout]", root).innerHTML = path.map(p => `<span class="hop">${p}</span>`).join("<span class='arrow'>&rarr;</span>") + `<p>${res}</p>`;
  }

  function viz1(v) {
    const t = v.type;
    if (t === "cards") return `<div class="cards">${v.items.map((c, i) => `<div class="card"><span class="cn">${i + 1}</span><b>${esc(c.t)}</b><span>${md(c.d)}</span></div>`).join("")}</div>`;
    if (t === "steps") return `<div class="flowbar"><button class="play" data-play>Play walkthrough</button><span>or click any step</span></div><div class="steps flow" data-steps>${v.items.map((c, i) => `${i ? `<span class="conn"><i></i></span>` : ""}<button class="step" data-i="${i}"><span class="num">${i + 1}</span><b>${esc(c.t.replace(/^\d+\s+/, ""))}</b></button>`).join("")}</div>
      <div class="stepinfo" data-info>Select a step to read its detail.</div><script type="application/json" data-json>${JSON.stringify(v.items).replace(/</g, "\\u003c")}</script>`;
    if (t === "compare") return `<div class="cmp"><div class="cmph" style="--c:${v.lc}">${v.lt}</div><div class="cmph" style="--c:${v.rc}">${v.rt}</div>` +
      v.rows.map(r => `<div class="cmpl">${r[0] ? `<em>${esc(r[0])}</em>` : ""}</div><div></div><div class="cmpc" style="--c:${v.lc}">${md(r[1])}</div><div class="cmpc" style="--c:${v.rc}">${md(r[2])}</div>`).join("") + `</div>`;
    if (t === "timeline") return `<div class="tl">${v.items.map(c => `<div class="tli" style="--c:${c.c}"><time>${c.time}</time><div><b>${esc(c.t)}</b><span>${md(c.d)}</span></div></div>`).join("")}</div>`;
    if (t === "tree") return `<div class="tree"><div class="root">${esc(v.root)}</div>${v.items.map(([p, d]) => `<button class="tn" data-copy="${esc(p)}"><code>${esc(p)}</code><span>${md(d)}</span></button>`).join("")}</div><div class="hint">Click a path to copy it, then paste it into Visual Studio search (Ctrl+T for files, Ctrl+Shift+F for text).</div>`;
    if (t === "mock") return mock();
    if (t === "arch") return arch();
    if (t === "datasource") return dsDemo();
    if (t === "flowchart") return flowchart(v);
    return "";
  }
  const viz = v => (Array.isArray(v) ? v : [v]).map(x => `<div class="vz">${viz1(x)}</div>`).join("");

  /* ---------- video ---------- */
  function videoBlock(l) {
    const v = l.video, d = D.videos[v.key] || {}, local = d.file;
    const url = local || `https://drive.google.com/file/d/${d.id}/view`;
    const poster = `<button class="poster" ${local ? `data-local="${esc(local)}"` : `data-vid="${esc(d.id)}"`}><span class="pl"></span><b>${esc(d.title || "")}</b><small>${local ? "Click to play" : "Click to load the video player"}</small></button>`;
    const main = local || v.embed ? poster : `<div class="vidnote"><b>${esc(d.title || "")}</b><span>Open the recording and jump to the chapters listed here.</span></div>`;
    const open = local
      ? `<a class="btn ghost" href="${esc(local)}" download>Save the video</a>`
      : `<a class="btn ghost" target="_blank" rel="noopener" href="${url}">Open in Google Drive</a>`;
    return `<h2 class="sec">Watch this</h2><div class="vid"><div class="vidmain">${main}</div>
      <div class="vidside"><div class="vtag">Recommended chapters for this lesson</div><ul>${(v.chapters || []).map(c => `<li>${esc(c)}</li>`).join("")}</ul><p class="vn">${esc(d.note || "")}</p>${open}</div></div>`;
  }

  /* ---------- key-term highlighting ---------- */
  function hl(text, terms) {
    let t = text; (terms || []).forEach(k => { const w = k.replace(/ \(.*\)/, ""); if (!t.includes("**" + w) && t.includes(w)) t = t.replace(w, "**" + w + "**"); });
    return md(t);
  }

  /* ---------- views ---------- */
  function home() {
    const nx = nextLesson(), r = role(), done = D.lessons.filter(l => S.done[l.id]).length;
    return `<section class="hero"><div class="eyebrow">${S.profile ? "Welcome, " + esc(S.profile.name) : "Onboarding guide"}</div><h1>Atlas Explorer</h1>
      <p>A visual guide to the <b>ATLAS desktop</b> and <b>eATLAS web</b> applications. We start with the concepts, then move into the source code.${r ? ` <b>Your path:</b> ${esc(r.label)}. ${esc(r.blurb)}` : ""}</p>
      <div class="row">${nx ? `<a class="btn big" href="#/lesson/${nx.id}">${done ? "Continue" : "Start"}: ${esc(nx.title)}</a>` : `<span class="btn big">All lessons complete</span>`}<a class="btn ghost" href="#/setup">Setup guide</a><a class="btn ghost" href="#" data-ask-open>Ask the tutor</a></div>${heroSvg()}</section>
      <h2 class="sec">Learning path</h2><div class="map">` +
      D.phases.map(p => {
        const lock = p.code && !codeUnlocked(), ls = lessonsOf(p.id);
        return `<article class="isle" style="--c:${p.color}"><div class="ring" style="--p:${pct(p.id)}"><span>${p.n}</span></div>
        <h3>${p.name}</h3><p>${p.sub}</p><small>${ls.filter(l => S.done[l.id]).length} of ${ls.length} lessons complete</small>
        <div class="chips">${ls.map(l => `<a class="chip ${S.done[l.id] ? "ok" : ""} ${isRec(l.id) ? "rec" : ""}" href="#/lesson/${l.id}" title="${esc(l.tag)}">${esc(l.title)}</a>`).join("")}</div>
        ${lock ? `<div class="lock">Locked until islands 1 to 4 are done. <a href="#" data-unlock>Skip ahead</a></div>` : ""}</article>`;
      }).join("") + `</div>
      <h2 class="sec">How this works</h2><div class="cards3">
      <div class="card"><b>One idea at a time</b><span>Each lesson has a picture, key points, a mini-quiz and the source doc.</span></div>
      <div class="card"><b>Ask questions</b><span>Use <i>Ask the tutor</i> (bottom right) here, or the ATLAS Tutor agent in VS Code for code-level answers.</span></div>
      <div class="card"><b>Source-grounded</b><span>Every lesson lists the repository doc it was written from.</span></div>
      <div class="card"><b>Save state</b><span>Progress is saved on this computer, in a local file. Export a summary any time.</span></div></div>`;
  }

  function lessonView(l) {
    const p = phaseOf(l.phase), locked = p.code && !codeUnlocked();
    const idx = D.lessons.indexOf(l), prev = D.lessons[idx - 1], next = D.lessons[idx + 1], num = p.n + "." + (lessonsOf(p.id).indexOf(l) + 1);
    if (locked) return `<div class="lessonhead" style="--c:${p.color}"><h1>${esc(l.title)}</h1><p>The Source Code island unlocks after islands 1 to 4. That way you know the story before reading the code.</p><a class="btn" href="#" data-unlock>Skip ahead</a> <a class="btn ghost" href="#/home">Back to overview</a></div>`;
    const q = l.quiz;
    return `<div class="lessonhead" style="--c:${p.color}"><div class="crumb">${p.n}. ${p.name}${isRec(l.id) ? " &middot; recommended for you" : ""}</div><h1><span class="ib">${num}</span>${esc(l.title)}</h1><div class="tag">${esc(l.tag)}</div></div>
      <div class="hookbox" style="--c:${p.color}"><b>In short:</b> ${md(l.hook)}</div>
      ${l.goals && l.goals.length ? `<div class="goals"><b>After this lesson you can</b><ul>${l.goals.map(g => `<li>${esc(g)}</li>`).join("")}</ul></div>` : ""}
      <div class="viz" style="--c:${p.color}">${viz(l.viz)}</div>
      ${l.video ? videoBlock(l) : ""}
      ${l.shot ? `<figure class="shot"><img src="assets/screens/${l.shot}.png" alt="${esc(l.title)} screenshot"/><figcaption>Screenshot slot: <code>explorer/assets/screens/${l.shot}.png</code></figcaption></figure>` : ""}
      <h2 class="sec">Key points</h2><ul class="pts" style="--c:${p.color}">${l.points.map(x => `<li>${hl(x, l.terms)}</li>`).join("")}</ul>
      ${l.terms.length ? `<h2 class="sec">New words</h2><div class="terms">${l.terms.map(t => `<div class="term"><b>${esc(t)}</b><span>${md(D.glossary[t] || "")}</span></div>`).join("")}</div>` : ""}
      ${l.try ? `<div class="try"><b>Try it in your IDE:</b> ${md(l.try)}</div>` : ""}
      <h2 class="sec">Check yourself</h2><div class="quiz" data-quiz><p><b>${md(q.q)}</b></p>${q.o.map((o, i) => `<button class="opt" data-a="${i}">${esc(o)}</button>`).join("")}<div class="why" data-why></div></div>
            <h2 class="sec">Ask next <small>(click to copy, then paste into the ATLAS Tutor chat in VS Code)</small></h2><div class="prompts">${l.prompts.map(x => `<button class="prompt" data-copy="${esc((profileLine() ? profileLine() + " " : "") + x)}">${esc(x)}</button>`).join("")}</div>
      <div class="live" data-live="${esc(l.src.join("|"))}" data-secs="${esc(JSON.stringify(l.secs || {}))}"></div>
      <div class="src">Source-grounded in: ${l.src.map(s => `<a class="srcl" href="#/doc/${encodeURI(s)}" title="Open this document"><code>${esc(s)}</code></a>`).join(" ")}<br><small>Drafted from repo docs. Verify against your Atlas revision. Anything marked "assumption" is not taken from a diagram.</small></div>
      <div class="foot">${prev ? `<a class="btn ghost" href="#/lesson/${prev.id}">&larr; ${esc(prev.title)}</a>` : "<span></span>"}
      <button class="btn big ${S.done[l.id] ? "ghost" : ""}" data-done="${l.id}">${S.done[l.id] ? "Completed (click to undo)" : "Mark as complete"}</button>
      ${next ? `<a class="btn" href="#/lesson/${next.id}">${esc(next.title)} &rarr;</a>` : "<span></span>"}</div>`;
  }

  const SETUP = [
    ["Check what you need", "You need Git, Python 3.10 or newer, VS Code with GitHub Copilot, and your Atlas checkout (the folder that contains Atlas.sln). Check the first two in PowerShell:", ["git --version", "python --version"]],
    ["Get the onboarding repository", "Clone it anywhere outside the Atlas folder, then enter it.", ["git clone https://github.com/ahalya-trimble/atlas-onboarding.git", "cd atlas-onboarding"]],
    ["Run the one-step installer", "Double-click setup.bat, or run it with your Atlas path. It installs the ATLAS Tutor agent and the visual guide, and creates only untracked, git-excluded files inside the Atlas checkout. Your product files are never changed.", ['.\\setup.bat "C:\\Users\\<you>\\Documents\\atlas_v2.0"']],
    ["Use the agent (ask questions)", "Open the Atlas folder in VS Code, open Copilot Chat, choose the ATLAS Tutor agent, and send:", ["Hi"]],
    ["Open the visual guide", "The installer opens it for you. Next time, double-click this file inside your Atlas checkout:", ["<atlas>\\.atlas-onboarding\\Open Atlas Explorer.bat"]],
    ["Personalize it", "On first launch enter your first name and role. Your path, recommended lessons and copied prompts adapt. Prompts you copy carry a profile line so the agent adapts too (it does not store your name).", []],
    ["Add your own screenshots", "Save PNGs into explorer/assets/screens/ using the file names listed in that folder's README, then run setup.bat again to copy them in.", []],
    ["Update or remove", "Pull new changes and run setup again to update. Add -Remove to uninstall; your learning progress is kept.", ["git pull", '.\\setup.bat "C:\\path\\to\\atlas_v2.0"', '.\\setup.bat "C:\\path\\to\\atlas_v2.0" -Remove']]
  ];
  const TROUBLE = [["'python' is not recognized", "Install Python 3.10+ from python.org, tick 'Add to PATH', then reopen the terminal."], ["Installer says 'Refusing to overwrite' or 'tracked file'", "Something already exists at that path. Read the message; the installer never overwrites files it does not own."], ["Agent not in the Copilot list", "Reload VS Code (Ctrl+Shift+P, Developer: Reload Window) and re-open the Atlas folder."], ["Diagrams look unstyled", "Open index.html from the installed explorer folder, not from a copy that lost its css and js folders."], ["Video does not play", "The Google Drive recording needs your Trimble sign-in and access. Use 'Open in Google Drive'."]];
  function setup() {
    return `<div class="lessonhead" style="--c:#3b82f6"><h1>Setup guide</h1><div class="tag">From zero to learning in about five minutes</div></div>
      <div class="setup">${SETUP.map((s, i) => `<div class="sstep"><span class="sn">${i + 1}</span><div><b>${esc(s[0])}</b><p>${md(s[1])}</p>${s[2].map(c => `<button class="cmd" data-copy="${esc(c)}"><code>${esc(c)}</code><em>copy</em></button>`).join("")}</div></div>`).join("")}</div>
      <h2 class="sec">If something goes wrong</h2><div class="terms">${TROUBLE.map(t => `<div class="term"><b>${esc(t[0])}</b><span>${md(t[1])}</span></div>`).join("")}</div>`;
  }
  function glossary() {
    return `<div class="lessonhead" style="--c:#c9a227"><h1>Glossary</h1><div class="tag">Every unfamiliar word in one place</div></div><input class="search" placeholder="Filter terms" data-gs/>
      <div class="terms big" data-gl>${Object.entries(D.glossary).map(([k, v]) => `<div class="term"><b>${esc(k)}</b><span>${md(v)}</span></div>`).join("")}</div>`;
  }
  function summaryText() {
    const done = D.lessons.filter(l => S.done[l.id]), left = D.lessons.filter(l => !S.done[l.id]), nx = nextLesson();
    const terms = [...new Set(done.flatMap(l => l.terms))];
    return ["# Atlas Save State Summary", `_${new Date().toLocaleString()}_  |  Level: ${level()}`, profileLine(), "",
      "## What I learned", ...(done.length ? done.map(l => `- **${l.title}** - ${l.tag}`) : ["- (nothing yet)"]), "",
      "## Terms defined", ...(terms.length ? terms.map(t => `- **${t}**: ${D.glossary[t]}`) : ["- (none yet)"]), "",
      "## Quiz results", ...D.lessons.filter(l => l.id in S.quiz).map(l => `- ${S.quiz[l.id] ? "correct" : "review"}: ${l.title}`), "",
      "## Next step", nx ? `- **${nx.title}** - try: "${nx.prompts[0]}"` : "- Everything explored. Re-run the capstone.", "",
      "## Still to do", ...left.map(l => `- ${l.title}`), "", "_Paste this into the ATLAS Tutor chat to resume._"].join("\n");
  }
  function summary() {
    return `<div class="lessonhead" style="--c:#6366a8"><h1>Save-state summary</h1><div class="tag">Copy it and paste it into your tutor chat to resume later</div></div>
      <pre class="sumtxt">${esc(summaryText())}</pre>
      <div class="row"><button class="btn" data-copy-sum>Copy</button><button class="btn ghost" data-dl>Download .md</button><button class="btn ghost danger" data-reset>Reset progress</button></div>`;
  }

  /* ---------- profile modal ---------- */
  function profileModal(first) {
    const p = S.profile || { name: "", role: "technician", exp: "new to Atlas", goal: "" };
    const where = LIVE
      ? "Saved in this browser and in .atlas-onboarding/state/explorer-progress.json on this computer. It sets your recommended path and is copied into prompts you send to the tutor."
      : "Stored only in this browser until you start the guide with Open Atlas Explorer.bat. It sets your recommended path and is copied into prompts you send to the tutor.";
    const prev = document.activeElement;
    const m = document.createElement("div"); m.className = "modal";
    m.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-labelledby="profile-title"><h2 id="profile-title">${first ? "Welcome. Let's personalize your guide" : "Your profile"}</h2><p class="mut">${esc(where)}</p>
      <label>First name<input data-n value="${esc(p.name)}" placeholder="e.g. Ahalya"/></label>
      <label>Your role<select data-r>${Object.entries(ROLES).map(([k, v]) => `<option value="${k}" ${p.role === k ? "selected" : ""}>${v.label}</option>`).join("")}</select></label>
      <label>Experience with Atlas<select data-e>${["new to Atlas", "some experience", "experienced"].map(x => `<option ${p.exp === x ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>What do you want to achieve? (optional)<input data-g value="${esc(p.goal)}" placeholder="e.g. fix eAtlas assignment bugs"/></label>
      <div class="row"><button class="btn" data-ok>Save</button><button class="btn ghost" data-skip>${first ? "Skip for now" : "Cancel"}</button></div></div>`;
    document.body.appendChild(m);
    const dlg = $(".dlg", m);
    const focusables = () => [...dlg.querySelectorAll("input, select, button")];
    const close = () => { document.removeEventListener("keydown", trap); m.remove(); if (prev && prev.focus) prev.focus(); };
    function trap(e) {
      if (e.key === "Escape") { e.preventDefault(); $("[data-skip]", m).click(); return; }
      if (e.key !== "Tab") return;
      const items = focusables(); if (!items.length) return;
      const firstEl = items[0], lastEl = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    }
    document.addEventListener("keydown", trap);
    $("[data-ok]", m).onclick = () => { S.profile = { name: $("[data-n]", m).value.trim() || "Explorer", role: $("[data-r]", m).value, exp: $("[data-e]", m).value, goal: $("[data-g]", m).value.trim() }; save(); close(); route(); };
    $("[data-skip]", m).onclick = () => { if (first) { S.skipProfile = true; save(); } close(); };
    focusables()[0].focus();
  }

  /* ---------- offline ask helper ---------- */
  const STOP = new Set("the a an is are of to in on and or for how what why when where does do can i it this that with from my be as at by about".split(" "));
  const tok = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(w => w.length > 1 && !STOP.has(w));
  const CORPUS = () => D.lessons.map(l => ({ l, text: [l.title, l.tag, l.hook, ...l.points, ...l.terms, ...l.prompts].join(" ") }));
  function answer(q) {
    const qt = tok(q); if (!qt.length) return `<p>Type a question about Atlas, eAtlas, licensing, offline, DWCR, sync, and so on.</p>`;
    const gl = Object.entries(D.glossary).filter(([k]) => q.toLowerCase().includes(k.toLowerCase().replace(/ \(.*\)/, "")));
    const scored = CORPUS().map(c => { const ct = tok(c.text), tl = tok(c.l.title); let sc = 0; qt.forEach(w => { const n = ct.filter(x => x === w || (w.length > 3 && x.startsWith(w))).length; sc += Math.min(n, 3); if (tl.includes(w)) sc += 3; }); return { c, sc }; }).filter(x => x.sc > 0).sort((a, b) => b.sc - a.sc).slice(0, 2);
    let h = "";
    gl.slice(0, 2).forEach(([k, v]) => h += `<div class="ans"><b>${esc(k)}</b><p>${md(v)}</p></div>`);
    scored.forEach(({ c }) => {
      const best = c.l.points.map(p => ({ p, s: tok(p).filter(w => qt.includes(w)).length })).sort((a, b) => b.s - a.s).slice(0, 2).map(x => x.p);
      h += `<div class="ans"><b>${esc(c.l.title)}</b><p>${md(c.l.hook)}</p><ul>${best.map(p => `<li>${md(p)}</li>`).join("")}</ul><a href="#/lesson/${c.l.id}" data-close>Open lesson</a> <span class="mut">Source: ${c.l.src.map(esc).join(", ")}</span></div>`;
    });
    if (!h) h = `<p>I could not find that in the guide. Try different words, or ask the ATLAS Tutor agent in VS Code, which can read the actual source.</p>`;
    return h + `<div class="repo" data-repo="${esc(q)}"></div><button class="btn ghost" data-copy="${esc((profileLine() ? profileLine() + " " : "") + q)}">Copy as a prompt for the ATLAS Tutor agent</button>`;
  }
  function askPanel() {
    const d = document.createElement("div"); d.id = "ask"; d.innerHTML = `<button class="askfab" data-ask-open>Ask the tutor</button>
      <div class="askbox" hidden><div class="askh"><b>Ask the tutor</b><button data-ask-close aria-label="Close">&times;</button></div>
      <div class="askb" data-askb><p class="mut">This helper searches the guide offline. For answers from the real source code, copy your question into the ATLAS Tutor agent in VS Code.</p><div class="sug">${["What is DWCR?", "Why does Atlas need MongoDB?", "How does a manager assignment reach a technician?", "What runs at 05:00?"].map(x => `<button class="chip" data-q="${esc(x)}">${esc(x)}</button>`).join("")}</div></div>
      <form class="askf"><input placeholder="Ask about Atlas or eAtlas" autocomplete="off"/><button class="btn">Ask</button></form></div>`;
    document.body.appendChild(d);
    const box = $(".askbox", d), body = $("[data-askb]", d), inp = $("input", d);
    const ask = q => { if (!q.trim()) return; body.insertAdjacentHTML("beforeend", `<div class="me">${esc(q)}</div><div class="bot">${answer(q)}</div>`); body.scrollTop = body.scrollHeight; body.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => copy(b.dataset.copy)); body.querySelectorAll("[data-close]").forEach(a => a.addEventListener("click", () => box.hidden = true)); repoSearch(body, box); };
    d.addEventListener("click", e => { const t = e.target; if (t.closest("[data-ask-close]")) box.hidden = true; if (t.dataset.q) ask(t.dataset.q); });
    $("form", d).onsubmit = e => { e.preventDefault(); ask(inp.value); inp.value = ""; };
    document.addEventListener("click", e => { if (e.target.closest("[data-ask-open]")) { e.preventDefault(); box.hidden = false; inp.focus(); } });
  }

  /* ---------- live source docs (local, read-only, nothing is stored in the browser) ---------- */
  let LIVE = false;
  const api = (path, opt) => fetch(path, Object.assign({ headers: { "X-Requested-With": "atlas-explorer" }, cache: "no-store" }, opt)).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  const hasApi = () => api("/api/health").then(h => {
    LIVE = true;
    if (!h || !h.atlas) return;
    checkout = h.atlas;
    if (localStorage.getItem(storageKey())) { S = readState(storageKey()); migrate(); return; }
    const legacy = readState(KEY);
    const claimed = legacy.checkout && legacy.checkout !== checkout;
    const legacyWork = legacy.profile || legacy.skipProfile || legacy.xp || Object.keys(legacy.done || {}).length;
    if (!claimed && !legacy.checkout && legacyWork) {
      legacy.checkout = checkout;
      S = legacy;
      try { localStorage.setItem(KEY, JSON.stringify(legacy)); localStorage.setItem(storageKey(), JSON.stringify(legacy)); } catch (e) {}
    } else S = emptyState();
    migrate();
  }, () => { LIVE = false; });
  const q2 = p => encodeURIComponent(p);

  const chipsFor = (heads, want) => { const w = (want || []).map(x => x.toLowerCase()); const m = heads.filter(h => w.includes(h.text.toLowerCase())); return m.length ? m : heads.slice(0, 6); };

  /* progress is kept in one local file on this computer (and in the browser as a backup) */
  let pushT = null, syncWarned = false;
  function applyState(next) {
    S = Object.assign(emptyState(), next); migrate();
    try { localStorage.setItem(storageKey(), JSON.stringify(S)); } catch (e) {}
  }
  function pushProgress() {
    if (!LIVE) return; clearTimeout(pushT);
    pushT = setTimeout(() => fetch("/api/progress", { method: "POST", headers: { "X-Requested-With": "atlas-explorer", "Content-Type": "application/json" }, body: JSON.stringify(S), cache: "no-store" }).then(r => {
      if (r.status === 409) return r.json().then(body => { if (body.explorer) applyState(body.explorer); });
      if (!r.ok) throw new Error(r.status);
      syncWarned = false;
    }).catch(() => { if (!syncWarned) { syncWarned = true; toast("Progress stayed in this browser. It was not saved to the file on this computer."); } }), 400);
  }
  function loadProgress() {
    if (!LIVE) return Promise.resolve();
    return api("/api/progress").then(r => {
      const disk = r.explorer, diskT = disk ? (+disk.updatedAt || 0) : 0, localT = +S.updatedAt || 0;
      if (disk && (diskT > localT || (!localWork() && !localT))) applyState(disk);
      else if (localWork() || localT > diskT) pushProgress();
    }).catch(() => toast("Could not read progress saved on this computer."));
  }

  function loadLive(el) {
    if (!LIVE) { el.innerHTML = `<p class="mut">Start the guide with <code>Open Atlas Explorer.bat</code> to open the cited documents and see live updates.</p>`; return; }
    const paths = el.dataset.live;
    api("/api/outline?paths=" + q2(paths)).then(o => {
      const secs = JSON.parse(el.dataset.secs || "{}");
      const rows = Object.entries(o).map(([p, d]) => {
        if (d.status === "missing") return `<div class="lrow bad"><b>${esc(p)}</b> <span class="lb bad">Missing in this Atlas revision</span></div>`;
        const badge = d.status === "changed" ? `<span class="lb warn">Changed since you last reviewed</span>` : `<span class="lb ok">Up to date</span>`;
        return `<div class="lrow"><a href="#/doc/${encodeURI(p)}"><b>${esc(d.title)}</b></a> ${badge}<div class="mut">${esc(p)}</div>${d.summary ? `<p>${esc(d.summary)}</p>` : ""}<div class="chips">${chipsFor(d.headings, secs[p]).map(h => `<a class="chip" href="#/doc/${encodeURI(p)}::${h.line}">${esc(h.text)}</a>`).join("")}</div></div>`;
      }).join("");
      const changed = Object.values(o).some(d => d.status === "changed");
      el.innerHTML = `<h2 class="sec">Live from the Atlas docs</h2>${changed ? `<div class="drift">A source document changed after this lesson was written. Read the live text below, then mark it reviewed. The lesson wording above may be out of date.</div>` : ""}${rows}${changed ? `<button class="btn ghost" data-accept>Mark these documents as reviewed</button>` : ""}`;
      const b = el.querySelector("[data-accept]");
      if (b) b.onclick = () => api("/api/accept", { method: "POST", headers: { "X-Requested-With": "atlas-explorer", "Content-Type": "application/json" }, body: JSON.stringify({ paths: paths.split("|") }) }).then(() => { toast("Marked as reviewed"); loadLive(el); });
      strip(el);
    }).catch(() => { el.innerHTML = ""; });
  }

  function repoSearch(body, box) {
    const el = [...body.querySelectorAll("[data-repo]")].pop(); if (!el || !LIVE) return;
    api("/api/search?q=" + q2(el.dataset.repo)).then(r => {
      if (!r.results.length) return;
      el.innerHTML = `<div class="ans"><b>In the Atlas docs</b>${r.results.slice(0, 4).map(x => `<div class="hit"><a href="#/doc/${encodeURI(x.path)}::${x.hits[0].line}" data-close>${esc(x.title)}</a> <span class="mut">${esc(x.path)}</span>${x.hits.map(h => `<div class="snip">line ${h.line}: ${esc(h.text)}</div>`).join("")}</div>`).join("")}</div>`;
      el.querySelectorAll("[data-close]").forEach(a => a.addEventListener("click", () => box.hidden = true));
      body.scrollTop = body.scrollHeight;
    }).catch(() => { });
  }

  /* safe, minimal markdown: all text is escaped first; only local doc links are followed */
  function mdDoc(text, base) {
    const lines = text.split(/\r?\n/), out = []; let i = 0;
    const inl = t => esc(t).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "[image: $1]")
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => {
        const raw = u.replace(/&amp;/g, "&");
        if (/^https:\/\//i.test(raw)) return `<a href="${esc(raw)}" target="_blank" rel="noopener noreferrer">${t}</a>`;
        if (/^[a-z]+:/i.test(raw) || raw.startsWith("#")) return t;
        const parts = (base + "/" + raw.split("#")[0]).split("/"), st = [];
        parts.forEach(x => { if (x === "..") st.pop(); else if (x && x !== ".") st.push(x); });
        return /\.(md|txt)$/i.test(st.join("/")) ? `<a href="#/doc/${encodeURI(st.join("/"))}">${t}</a>` : t;
      });
    const LI = /^\s*([-*]|\d+\.)\s+/;
    while (i < lines.length) {
      const ln = lines[i], n = i + 1;
      if (/^\s*```/.test(ln)) { const buf = []; i++; while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]); i++; out.push(`<pre data-l="${n}"><code>${esc(buf.join("\n"))}</code></pre>`); continue; }
      const h = ln.match(/^(#{1,4})\s+(.*)$/); if (h) { out.push(`<h${h[1].length + 1} data-l="${n}">${inl(h[2])}</h${h[1].length + 1}>`); i++; continue; }
      if (/^\s*\|/.test(ln) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
        const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => inl(c.trim()));
        const head = cells(ln); i += 2; const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(cells(lines[i++]));
        out.push(`<div class="tw" data-l="${n}"><table><thead><tr>${head.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`); continue;
      }
      if (LI.test(ln)) { const items = []; while (i < lines.length && LI.test(lines[i])) items.push(inl(lines[i++].replace(LI, ""))); out.push(`<ul data-l="${n}">${items.map(x => `<li>${x}</li>`).join("")}</ul>`); continue; }
      if (/^\s*>/.test(ln)) { const buf = []; while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, "")); out.push(`<blockquote data-l="${n}">${inl(buf.join(" "))}</blockquote>`); continue; }
      if (!ln.trim()) { i++; continue; }
      const buf = []; while (i < lines.length && lines[i].trim() && !/^(\s*```|#{1,4}\s|\s*\||\s*([-*]|\d+\.)\s|\s*>)/.test(lines[i])) buf.push(lines[i++]);
      if (!buf.length) buf.push(lines[i++]);
      out.push(`<p data-l="${n}">${inl(buf.join(" "))}</p>`);
    }
    return out.join("");
  }
  const docShell = raw => `<div class="docview"><a class="back" href="#/home" data-back>&larr; Back</a><div data-doc><p class="mut">Loading the document...</p></div></div>`;
  function loadDoc(root, raw) {
    const [pth, ln] = decodeURI(raw).split("::"), box = $("[data-doc]", root);
    const bk = $("[data-back]", root); if (bk) bk.onclick = e => { e.preventDefault(); history.back(); };
    if (!LIVE) { box.innerHTML = `<h1>${esc(pth)}</h1><p>This document opens only when the guide is started with <code>Open Atlas Explorer.bat</code>, because the browser cannot read your Atlas folder directly.</p>`; return; }
    api("/api/doc?path=" + q2(pth)).then(d => {
      const base = d.path.split("/").slice(0, -1).join("/"), line = +ln || 0;
      const ide = n => `/${d.abs.replace(/^\//, "")}${n ? ":" + n : ""}`;
      box.innerHTML = `<div class="dochead"><span class="mut">${esc(d.path)}</span><span class="ide"><a href="vscode://file${encodeURI(ide(line))}">Open in VS Code</a><a href="cursor://file${encodeURI(ide(line))}">Open in Cursor</a></span></div><div class="mdoc">${mdDoc(d.text, base)}</div><p class="mut">Read-only view of your local copy. Secret-looking values are hidden. Nothing here is saved in the browser.</p>`;
      if (line) { const els = [...box.querySelectorAll("[data-l]")].filter(e => +e.dataset.l <= line); const t = els[els.length - 1]; if (t) { t.classList.add("flash"); t.scrollIntoView({ block: "center" }); } }
      strip(box);
    }).catch(() => { box.innerHTML = `<h1>${esc(pth)}</h1><p>This path is not available. Only documentation files (docs folder, AGENTS.md, README.md) can be opened.</p>`; });
  }

  /* ---------- text polish: no emoji anywhere ---------- */
  function strip(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n;
    while ((n = w.nextNode())) { EMO.lastIndex = 0; if (EMO.test(n.nodeValue)) { EMO.lastIndex = 0; n.nodeValue = n.nodeValue.replace(EMO, "").replace(/^\s{2,}/, " "); } }
  }

  /* ---------- router ---------- */
  function route() {
    const h = location.hash.replace(/^#\/?/, ""), m = $("#main");
    let html;
    if (h.startsWith("lesson/")) { const l = byId(h.slice(7)); html = l ? lessonView(l) : home(); }
    else if (h.startsWith("doc/")) html = docShell(h.slice(4));
    else if (h === "glossary") html = glossary();
    else if (h === "summary") html = summary();
    else if (h === "setup") html = setup();
    else html = home();
    m.innerHTML = html; window.scrollTo(0, 0); $("#side").classList.remove("open");
    wire(m); if (h.startsWith("doc/")) loadDoc(m, h.slice(4)); renderTop(); renderSide(); strip(m); strip($("#side")); strip($("#xp"));
  }
  function toast(t) { const e = $("#toast"); e.textContent = t; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 1600); }
  function copy(t) { (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => toast("Copied to clipboard"), () => { const a = document.createElement("textarea"); a.value = t; document.body.appendChild(a); a.select(); try { document.execCommand("copy"); toast("Copied to clipboard"); } catch (e) { } a.remove(); }); }

  function wire(root) {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .06 });
    root.querySelectorAll(".pts li,.term,.tli,.tn,.quiz,.cmpc,.cmph,.prompt,.isle,.card,.vz,.hookbox,.vid,.sstep").forEach((e, i) => { e.classList.add("rv"); e.style.transitionDelay = (i % 6) * 50 + "ms"; io.observe(e); });
    root.querySelectorAll("[data-unlock]").forEach(a => a.onclick = e => { e.preventDefault(); S.unlock = true; save(); route(); });
    root.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => copy(b.dataset.copy));
    root.querySelectorAll("[data-live]").forEach(loadLive);
    root.querySelectorAll("[data-vid]").forEach(b => b.onclick = () => { b.parentNode.innerHTML = `<iframe src="https://drive.google.com/file/d/${b.dataset.vid}/preview" allow="autoplay; fullscreen" allowfullscreen title="Video"></iframe>`; });
    root.querySelectorAll("[data-local]").forEach(b => b.onclick = () => { b.parentNode.innerHTML = `<video src="${b.dataset.local}" controls autoplay playsinline title="Video"></video>`; });
    root.querySelectorAll("[data-steps]").forEach(w => {
      const items = JSON.parse(w.parentNode.querySelector("[data-json]").textContent), info = w.parentNode.querySelector("[data-info]");
      const bs = [...w.querySelectorAll(".step")], pb = w.parentNode.querySelector("[data-play]"); let tm = null;
      const show = i => { bs.forEach((x, k) => { x.classList.toggle("on", k === i); x.classList.toggle("past", k < i); }); w.querySelectorAll(".conn").forEach((c, k) => c.classList.toggle("lit", k < i)); const it = items[i]; info.innerHTML = `<b>${i + 1}. ${esc(it.t.replace(/^\d+\s+/, ""))}</b> &mdash; ${md(it.d)}`; strip(info); };
      bs.forEach((b, i) => b.onclick = () => { clearInterval(tm); pb.textContent = "Play walkthrough"; show(i); });
      pb.onclick = () => { clearInterval(tm); let i = 0; show(0); pb.textContent = "Playing..."; tm = setInterval(() => { i++; if (i >= bs.length) { clearInterval(tm); pb.textContent = "Replay"; return; } show(i); }, 1700); };
    });
    root.querySelectorAll("[data-mock]").forEach(b => b.onclick = () => { root.querySelectorAll("[data-mock]").forEach(x => x.classList.remove("on")); b.classList.add("on"); const d = MOCK[b.dataset.mock]; $("[data-mockmain]", root).innerHTML = `<h4>${d[0]}</h4><p>${d[1]}</p>`; });
    root.querySelectorAll("[data-node]").forEach(g => { const f = () => { root.querySelectorAll("[data-node]").forEach(x => x.classList.remove("on")); g.classList.add("on"); const n = NODES[g.dataset.node]; $("[data-archinfo]", root).innerHTML = `<b>${esc(n[2])}</b> &mdash; ${md(n[4])}`; }; g.onclick = f; g.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); f(); } }; });
    const ds = $(".ds", root); if (ds) { ds.querySelectorAll("select").forEach(s => s.onchange = () => dsCalc(ds)); dsCalc(ds); }
    const qz = $("[data-quiz]", root);
    if (qz) {
      const lid = location.hash.split("/")[2], l = byId(lid);
      qz.querySelectorAll(".opt").forEach(b => b.onclick = () => {
        if (qz.classList.contains("answered")) return; qz.classList.add("answered");
        const ok = +b.dataset.a === l.quiz.a; b.classList.add(ok ? "good" : "bad"); qz.querySelectorAll(".opt")[l.quiz.a].classList.add("good");
        $("[data-why]", qz).innerHTML = (ok ? "Correct. " : "Not quite. ") + md(l.quiz.why);
        if (!(lid in S.quiz)) { if (ok) S.xp += 25; S.quiz[lid] = ok; save(); renderTop(); }
      });
      if (lid in S.quiz) { qz.classList.add("answered"); qz.querySelectorAll(".opt")[l.quiz.a].classList.add("good"); $("[data-why]", qz).innerHTML = (S.quiz[lid] ? "You answered this correctly. " : "") + md(l.quiz.why); }
    }
    const dn = $("[data-done]", root);
    if (dn) dn.onclick = () => { const id = dn.dataset.done; if (S.done[id]) { delete S.done[id]; S.xp = Math.max(0, S.xp - 50); } else { S.done[id] = 1; S.xp += 50; toast("Lesson complete"); } save(); setTimeout(route, 250); };
    const gs = $("[data-gs]", root); if (gs) gs.oninput = () => root.querySelectorAll("[data-gl] .term").forEach(t => t.style.display = t.textContent.toLowerCase().includes(gs.value.toLowerCase()) ? "" : "none");
    const cs = $("[data-copy-sum]", root); if (cs) cs.onclick = () => copy(summaryText());
    const dl = $("[data-dl]", root); if (dl) dl.onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([summaryText()], { type: "text/markdown" })); a.download = "atlas-save-state.md"; a.click(); };
    const rs = $("[data-reset]", root); if (rs) rs.onclick = () => { if (confirm(LIVE ? "Reset all progress and profile? This clears this browser and the saved file on this computer, including work that has not finished syncing." : "Reset all progress and profile? This clears unsynced work in this browser. A saved file on this computer is unchanged until the guide server is running.")) { S = emptyState(); save(); route(); } };
  }

  $("#menu").onclick = () => $("#side").classList.toggle("open");
  $("#theme").onclick = () => { const d = document.documentElement; d.dataset.theme = d.dataset.theme === "light" ? "dark" : "light"; try { localStorage.setItem(KEY + "-theme", d.dataset.theme); } catch (e) { } };
  try { const t = localStorage.getItem(KEY + "-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { }
  window.addEventListener("hashchange", route);
  document.addEventListener("error", e => { const t = e.target; if (t && t.tagName === "IMG" && t.parentNode) t.parentNode.classList.add("empty"); }, true);
  askPanel(); hasApi().then(loadProgress).then(() => { route(); if (!S.profile && !S.skipProfile) profileModal(true); });
})();
