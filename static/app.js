"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

const state = {
  tree: null,
  nodes: new Map(),      // path -> node (dirs keyed by "dir/" path, root "")
  stems: new Map(),      // lowercase stem -> [paths]
  counts: {},
  current: null,         // { kind: "page"|"dir", path }
  expanded: new Set(store.get("expanded", [])),
  rows: new Map(),       // node key -> row element
};

/* ---------- api ---------- */

async function api(method, route, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch("/api/" + route, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

/* ---------- path helpers ---------- */

const dirOf = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");

function joinPath(base, rel) {
  const parts = rel.startsWith("/") ? [] : base ? base.split("/") : [];
  for (const seg of rel.replace(/^\/+/, "").split("/")) {
    if (seg === "" || seg === ".") continue;
    if (seg === "..") parts.pop(); else parts.push(seg);
  }
  return parts.join("/");
}

const dirKey = (p) => (p ? p + "/" : "");
const pageHref = (p) => "#/" + encodeURI(p);

function slugify(s) {
  return s.toLowerCase().trim().replace(/<[^>]+>/g, "").replace(/[^\w\- ]+/g, "").replace(/\s+/g, "-");
}

/* ---------- theme ---------- */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("#hljs-light").disabled = theme === "dark";
  $("#hljs-dark").disabled = theme !== "dark";
  mermaid.initialize({ startOnLoad: false, theme: theme === "dark" ? "dark" : "default", securityLevel: "strict" });
}

let theme = store.get("theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
applyTheme(theme);
$("#theme").onclick = () => {
  theme = theme === "dark" ? "light" : "dark";
  store.set("theme", theme);
  applyTheme(theme);
  route.force = true;
  route();
};

/* ---------- markdown ---------- */

let slugCounts = {};

marked.use({
  gfm: true,
  renderer: {
    code(code, lang) {
      lang = (lang || "").trim().split(/\s+/)[0].toLowerCase();
      if (lang === "mermaid") return `<pre class="mermaid">${esc(code)}</pre>`;
      const html = lang && hljs.getLanguage(lang)
        ? hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
        : esc(code);
      return `<pre><code class="hljs language-${esc(lang)}">${html}</code></pre>`;
    },
    heading(text, level, raw) {
      let slug = slugify(raw);
      if (slugCounts[slug] !== undefined) slug += "-" + ++slugCounts[slug]; else slugCounts[slug] = 0;
      return `<h${level} id="${esc(slug)}">${text}</h${level}>`;
    },
  },
  extensions: [{
    name: "wikilink",
    level: "inline",
    start: (src) => src.indexOf("[["),
    tokenizer(src) {
      const m = /^\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]/.exec(src);
      if (m) return { type: "wikilink", raw: m[0], target: m[1].trim(), label: (m[2] || m[1]).trim() };
    },
    renderer: (t) => `<a data-wiki="${esc(t.target)}">${esc(t.label)}</a>`,
  }],
});

function splitFrontmatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!m) return { meta: null, body: text };
  try {
    const meta = jsyaml.load(m[1]);
    return { meta: meta && typeof meta === "object" ? meta : null, body: text.slice(m[0].length) };
  } catch {
    return { meta: { "(invalid frontmatter)": m[1] }, body: text.slice(m[0].length) };
  }
}

function renderMeta(meta) {
  if (!meta || !Object.keys(meta).length) return "";
  const cell = (v) => {
    if (Array.isArray(v) && v.every((x) => typeof x !== "object")) return v.map((x) => `<span class="tag">${esc(x)}</span>`).join("");
    if (v instanceof Date) return esc(v.toISOString().slice(0, 10));
    if (v && typeof v === "object") return `<pre>${esc(jsyaml.dump(v).trim())}</pre>`;
    return esc(v ?? "");
  };
  const rows = Object.entries(meta).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${cell(v)}</td></tr>`).join("");
  return `<div class="frontmatter"><table>${rows}</table></div>`;
}

function resolveWiki(target, fromDir) {
  let [name, anchor] = target.split("#");
  name = name.trim().replace(/\.md$/i, "");
  let path = null;
  if (name.includes("/")) {
    for (const cand of [joinPath(fromDir, name), joinPath("", name)]) {
      if (state.nodes.has(cand + ".md")) { path = cand + ".md"; break; }
      const d = state.nodes.get(dirKey(cand));
      if (d) { path = d.index || dirKey(cand); break; }
    }
  } else if (name) {
    const hits = state.stems.get(name.toLowerCase()) || [];
    // prefer the closest match to the current folder
    path = hits.slice().sort((a, b) => sharedPrefix(b, fromDir) - sharedPrefix(a, fromDir))[0] || null;
  } else {
    path = state.current?.path;
  }
  return path ? { path, anchor } : null;
}

const sharedPrefix = (a, b) => { let i = 0; while (i < a.length && a[i] === b[i]) i++; return i; };

function fixLinks(root, pagePath) {
  const base = dirOf(pagePath);
  for (const a of root.querySelectorAll("a[data-wiki]")) {
    const r = resolveWiki(a.dataset.wiki, base);
    if (r) a.href = pageHref(r.path) + (r.anchor ? "#" + slugify(r.anchor) : "");
    else { a.classList.add("broken"); a.title = "No page found: " + a.dataset.wiki; }
  }
  for (const a of root.querySelectorAll("a[href]:not([data-wiki])")) {
    const href = a.getAttribute("href");
    if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) {
      a.target = "_blank"; a.rel = "noopener noreferrer"; continue;
    }
    if (href.startsWith("#")) { a.href = pageHref(pagePath) + "#" + href.slice(1); continue; }
    const [raw, anchor] = href.split("#");
    const p = joinPath(base, decodeURI(raw.split("?")[0]));
    const suffix = anchor ? "#" + anchor : "";
    if (/\.md$/i.test(p)) {
      a.href = pageHref(p) + suffix;
      if (!state.nodes.has(p)) { a.classList.add("broken"); a.title = "Missing page: " + p; }
    } else if (state.nodes.has(dirKey(p)) || p === "") {
      const d = state.nodes.get(dirKey(p));
      a.href = pageHref(d.index || dirKey(p));
    } else {
      a.href = "/kb/" + encodeURI(p); a.target = "_blank";
    }
  }
  for (const img of root.querySelectorAll("img[src]")) {
    const src = img.getAttribute("src");
    if (!/^([a-z]+:|\/\/)/i.test(src)) img.src = "/kb/" + encodeURI(joinPath(base, decodeURI(src)));
  }
}

/* ---------- tree ---------- */

function indexTree(node) {
  state.nodes.set(dirKey(node.path), node);
  for (const c of node.children) {
    if (c.type === "dir") { c.parent = node; indexTree(c); continue; }
    c.parent = node;
    state.nodes.set(c.path, c);
    const stem = c.name.toLowerCase();
    if (!state.stems.has(stem)) state.stems.set(stem, []);
    state.stems.get(stem).push(c.path);
  }
  // folder name also resolves as wikilink to its index
  if (node.index && node.path) {
    const stem = node.name.toLowerCase();
    if (!state.stems.has(stem)) state.stems.set(stem, []);
    if (!state.stems.get(stem).includes(node.index)) state.stems.get(stem).push(node.index);
  }
}

function dirCount(node, deep) {
  let n = node.index ? state.counts[node.index] || 0 : 0;
  if (!deep) return n;
  for (const c of node.children) {
    if (c.type === "dir") n += dirCount(c, true);
    else if (c.path !== node.index) n += state.counts[c.path] || 0;
  }
  return n;
}

function badge(n) { return n ? `<span class="badge">${n}</span>` : ""; }

function renderTree() {
  state.rows.clear();
  const build = (node) => {
    const ul = document.createElement("ul");
    for (const c of node.children) {
      if (c.type === "file" && c.path === node.index) continue;
      const li = document.createElement("li");
      const row = document.createElement("div");
      if (c.type === "dir") {
        const key = dirKey(c.path);
        const open = state.expanded.has(key);
        row.className = "row dir" + (c.index ? "" : " noindex");
        row.innerHTML = `<span class="caret${open ? " open" : ""}">▶</span><span class="label">${esc(c.name)}</span>`;
        row.title = c.path;
        const sub = build(c);
        sub.hidden = !open;
        row.querySelector(".caret").onclick = (e) => { e.stopPropagation(); toggleDir(c, sub, row); };
        row.onclick = () => {
          if (!state.expanded.has(key) || !c.index) toggleDir(c, sub, row, true);
          location.hash = pageHref(c.index || key);
        };
        state.rows.set(key, row);
        li.append(row, sub);
        updateDirBadge(c, row);
      } else {
        row.className = "row file";
        row.innerHTML = `<span class="caret"></span><span class="label">${esc(c.name)}</span>${badge(state.counts[c.path])}`;
        row.title = c.path;
        row.onclick = () => (location.hash = pageHref(c.path));
        state.rows.set(c.path, row);
        li.append(row);
      }
      ul.append(li);
    }
    return ul;
  };
  $("#tree").replaceChildren(build(state.tree));
  markActive();
}

function updateDirBadge(node, row) {
  row.querySelector(".badge")?.remove();
  const n = dirCount(node, !state.expanded.has(dirKey(node.path)));
  if (n) row.insertAdjacentHTML("beforeend", badge(n));
}

function toggleDir(node, sub, row, forceOpen) {
  const key = dirKey(node.path);
  const open = forceOpen ?? !state.expanded.has(key);
  if (open) state.expanded.add(key); else state.expanded.delete(key);
  sub.hidden = !open;
  row.querySelector(".caret").classList.toggle("open", open);
  updateDirBadge(node, row);
  store.set("expanded", [...state.expanded]);
}

function markActive() {
  for (const r of document.querySelectorAll(".row.active")) r.classList.remove("active");
  if (!state.current) return;
  let node = state.nodes.get(state.current.path);
  if (!node) return;
  // an index page is represented by its folder row
  if (node.type === "file" && node.parent?.index === node.path && node.parent.path) node = node.parent;
  const key = node.type === "dir" ? dirKey(node.path) : node.path;
  // expand ancestors
  let changed = false;
  for (let p = node.parent; p && p.path; p = p.parent) {
    const k = dirKey(p.path);
    if (!state.expanded.has(k)) { state.expanded.add(k); changed = true; }
  }
  if (changed) { store.set("expanded", [...state.expanded]); return renderTree(); }
  const row = state.rows.get(key);
  if (row) { row.classList.add("active"); row.scrollIntoView({ block: "nearest" }); }
}

async function loadTree() {
  const d = await api("GET", "tree");
  state.tree = d.tree;
  state.counts = d.counts;
  state.nodes.clear(); state.stems.clear();
  indexTree(d.tree);
  $("#kb-name").textContent = d.root;
  $("#notes-file").textContent = "Saved to " + d.notesFile;
  renderTree();
}

async function refreshCounts() {
  state.counts = (await api("GET", "tree")).counts;
  renderTree();
}

/* ---------- pages ---------- */

function renderCrumbs(path) {
  const parts = path.replace(/\/$/, "").split("/").filter(Boolean);
  const node = state.nodes.get(path);
  if (node?.type === "file" && node.parent?.index === path) parts.pop();
  else if (parts.length) parts[parts.length - 1] = parts[parts.length - 1].replace(/\.md$/i, "");
  const out = [`<a href="#/">${esc(state.tree.name)}</a>`];
  let acc = "";
  parts.forEach((seg, i) => {
    acc = acc ? acc + "/" + seg : seg;
    if (i === parts.length - 1) { out.push(`<span>${esc(seg)}</span>`); return; }
    const d = state.nodes.get(dirKey(acc));
    out.push(`<a href="${pageHref(d?.index || dirKey(acc))}">${esc(seg)}</a>`);
  });
  $("#crumbs").innerHTML = out.join('<span class="sep">/</span>');
}

async function showPage(path, anchor) {
  const content = $("#content");
  let data;
  try { data = await api("GET", "page?path=" + encodeURIComponent(path)); }
  catch (e) { content.innerHTML = `<h1>Not found</h1><p>${esc(path)}</p>`; return; }
  const { meta, body } = splitFrontmatter(data.text);
  slugCounts = {};
  const html = renderMeta(meta) + marked.parse(body);
  content.innerHTML = DOMPurify.sanitize(html, { ADD_ATTR: ["target"] });
  fixLinks(content, path);
  document.title = data.title + " — KB";
  const nodes = [...content.querySelectorAll("pre.mermaid")];
  if (nodes.length) mermaid.run({ nodes }).catch((e) => console.warn("mermaid", e));
  scrollToAnchor(anchor);
}

function showDir(node) {
  const items = node.children
    .map((c) => {
      const href = c.type === "dir" ? pageHref(c.index || dirKey(c.path)) : pageHref(c.path);
      return `<li>${c.type === "dir" ? "📁" : "📄"} <a href="${href}">${esc(c.name)}</a></li>`;
    }).join("");
  $("#content").innerHTML = `<h1>${esc(node.name)}</h1><ul class="folder-list">${items || "<li>(empty)</li>"}</ul>`;
  document.title = node.name + " — KB";
  $("#main").scrollTop = 0;
}

function scrollToAnchor(anchor) {
  const el = anchor && document.getElementById(decodeURIComponent(anchor));
  if (el) el.scrollIntoView(); else $("#main").scrollTop = 0;
}

async function route() {
  if (!state.tree) return;
  const raw = location.hash.replace(/^#\/?/, "");
  const [p, anchor] = raw.split("#");
  let path = decodeURI(p || "");
  if (path === "" && state.tree.index) path = state.tree.index;

  const same = state.current?.path === path;
  if (path.endsWith("/") || path === "") {
    const node = state.nodes.get(path);
    state.current = { kind: "dir", path };
    renderCrumbs(path);
    if (node) showDir(node); else $("#content").innerHTML = "<h1>Not found</h1>";
  } else {
    state.current = { kind: "page", path };
    renderCrumbs(path);
    if (same && !route.force) scrollToAnchor(anchor); else await showPage(path, anchor);
  }
  route.force = false;
  markActive();
  if (!same) loadNotes();
}

window.addEventListener("hashchange", route);

/* ---------- notes ---------- */

const notesList = $("#notes-list");
const hideDone = $("#hide-done");
hideDone.checked = store.get("hideDone", false);
notesList.classList.toggle("hide-done", hideDone.checked);
hideDone.onchange = () => { store.set("hideDone", hideDone.checked); notesList.classList.toggle("hide-done", hideDone.checked); };

async function loadNotes() {
  const cur = state.current;
  const panel = $("#notes");
  if (!cur || cur.kind !== "page") {
    panel.classList.add("disabled");
    $("#notes-target").textContent = "Open a page to add notes.";
    notesList.replaceChildren();
    $("#notes-count").hidden = true;
    return;
  }
  panel.classList.remove("disabled");
  $("#notes-target").textContent = cur.path;
  const notes = await api("GET", "notes?path=" + encodeURIComponent(cur.path));
  if (state.current !== cur) return;
  renderNotes(notes);
}

function renderNotes(notes) {
  const open = notes.filter((n) => !n.done).length;
  $("#notes-count").hidden = !open;
  $("#notes-count").textContent = open;
  if (!notes.length) { notesList.innerHTML = '<li class="empty">No notes for this page yet.</li>'; return; }
  notesList.replaceChildren(...notes.map(noteEl));
}

function noteEl(n) {
  const li = document.createElement("li");
  li.className = "note" + (n.done ? " done" : "");
  li.innerHTML = `
    <div class="top"><input type="checkbox" ${n.done ? "checked" : ""} title="Mark done"><div class="text"></div></div>
    <div class="meta"><span>${esc(n.stamp)}</span><span class="acts"><button class="edit">edit</button><button class="del">delete</button></span></div>`;
  li.querySelector(".text").textContent = n.text;
  const path = state.current.path;
  li.querySelector("input").onchange = (e) => noteOp("PATCH", { path, id: n.id, done: e.target.checked });
  li.querySelector(".del").onclick = () => { if (confirm("Delete this note?")) noteOp("DELETE", { path, id: n.id }); };
  li.querySelector(".edit").onclick = () => {
    const ta = document.createElement("textarea");
    ta.value = n.text; ta.rows = Math.max(3, n.text.split("\n").length + 1);
    const textDiv = li.querySelector(".text");
    textDiv.replaceWith(ta); ta.focus();
    let finished = false;
    const done = (save) => {
      if (finished) return;
      finished = true;
      if (save && ta.value.trim() && ta.value !== n.text) noteOp("PATCH", { path, id: n.id, text: ta.value });
      else ta.replaceWith(textDiv);
    };
    ta.onkeydown = (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); done(true); }
      if (e.key === "Escape") done(false);
    };
    ta.onblur = () => done(true);
  };
  return li;
}

async function noteOp(method, body) {
  try { await api(method, "notes", body); }
  catch (e) { alert("Notes error: " + e.message); }
  await loadNotes();
  refreshCounts();
}

$("#note-form").onsubmit = async (e) => {
  e.preventDefault();
  const ta = $("#note-text");
  if (!ta.value.trim() || state.current?.kind !== "page") return;
  await noteOp("POST", { path: state.current.path, text: ta.value });
  ta.value = "";
};
$("#note-text").onkeydown = (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("#note-form").requestSubmit(); }
};

/* ---------- search ---------- */

const searchBox = $("#search");
let searchTimer;
searchBox.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(doSearch, 150); };
searchBox.onkeydown = (e) => {
  if (e.key === "Escape") { searchBox.value = ""; doSearch(); searchBox.blur(); }
  if (e.key === "Enter") $("#results .hit")?.click();
};

async function doSearch() {
  const q = searchBox.value.trim();
  const results = $("#results");
  $("#tree").hidden = !!q;
  results.hidden = !q;
  if (!q) return;
  const hits = await api("GET", "search?q=" + encodeURIComponent(q));
  if (searchBox.value.trim() !== q) return;
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp("(" + terms.join("|") + ")", "gi");
  const hl = (s) => esc(s).replace(re, "<mark>$1</mark>");
  results.innerHTML = hits.length
    ? hits.map((h) => `<a class="hit" href="${pageHref(h.path)}"><b>${hl(h.title)}</b><small>${esc(h.path)}</small><span class="snip">${hl(h.snippet)}</span></a>`).join("")
    : '<div class="empty">No matches.</div>';
}

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) { e.preventDefault(); searchBox.focus(); searchBox.select(); }
});

/* ---------- misc ---------- */

$("#refresh").onclick = async () => { await loadTree(); route.force = true; await route(); };

for (const [k, v] of Object.entries(store.get("widths", {}))) document.documentElement.style.setProperty(k, v);
for (const rz of document.querySelectorAll(".resizer")) {
  rz.onpointerdown = (e) => {
    e.preventDefault();
    rz.classList.add("dragging");
    const left = rz.dataset.for === "sidebar";
    const prop = left ? "--side-w" : "--notes-w";
    const move = (ev) => {
      const w = Math.min(600, Math.max(180, left ? ev.clientX : window.innerWidth - ev.clientX));
      document.documentElement.style.setProperty(prop, w + "px");
    };
    const up = () => {
      rz.classList.remove("dragging");
      removeEventListener("pointermove", move); removeEventListener("pointerup", up);
      const widths = store.get("widths", {});
      widths[prop] = getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
      store.set("widths", widths);
    };
    addEventListener("pointermove", move); addEventListener("pointerup", up);
  };
}

loadTree().then(route).catch((e) => { $("#content").innerHTML = `<h1>Error</h1><p>${esc(e.message)}</p>`; });
