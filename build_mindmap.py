#!/usr/bin/env python3
"""Собрать карту компании как ментальную карту — холст, ветки, масштаб.

    python3 build_mindmap.py        → mindmap.html
    ./deploy.sh                     соберёт и выложит вместе с картой состояния

Зачем отдельная страница. Карта состояния (`index.html`) отвечает на вопрос
«как идут дела» и читается сверху вниз. Здесь другой вопрос — **что откуда
следует**: ветки расходятся от центра, любую можно свернуть, приблизить и
дорисовать свою связь между узлами, которые в дереве стоят далеко друг от друга.

Источники — те же файлы, что и у страницы состояния:

* `data.json` — направления, их шаги, сделанное и оставшееся, журнал работ;
* `mapdata.json` — ветки, которых на странице состояния нет (связка с 1С,
  серверы, деньги), и заранее заданные связи между узлами.

Ничего не дублируется: правится один раз в данных, и обе страницы меняются
вместе. Сторонних библиотек нет — страница должна открываться и без интернета.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Виды узлов: цвет и подпись в легенде. Смысл важнее красоты — по цвету должно
# быть сразу понятно, требует узел действия или уже закрыт.
KINDS = {
    "сделано": ("ok", "работает"),
    "решение": ("accent", "решение принято"),
    "выяснено": ("accent", "выяснено"),
    "план": ("wait", "в плане"),
    "вопрос": ("warn", "ждёт ответа"),
    "риск": ("stop", "риск или дыра"),
    "перспектива": ("wait", "перспектива"),
    "открыто": ("warn", "открыто"),
}


def clean(text: str) -> str:
    """Убрать разметку: в карту идёт человеческий текст, а не HTML."""
    text = re.sub(r"<br\s*/?>", " ", str(text or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&mdash;", "—").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def as_kind(value) -> str:
    """Вид узла из разных форм данных: строка, словарь статуса или пусто."""
    if isinstance(value, dict):
        value = value.get("cls") or value.get("label") or ""
    value = str(value or "").strip().lower()
    mapping = {"ok": "сделано", "stop": "риск", "warn": "вопрос", "wait": "план",
               "работает": "сделано"}
    value = mapping.get(value, value)
    return value if value in KINDS else "план"


def node(title: str, kind: str = "", note: str = "", children: list | None = None) -> dict:
    out: dict = {"t": clean(title), "k": as_kind(kind)}
    if note:
        out["n"] = clean(note)
    if children:
        out["c"] = children
    return out


def from_extra(raw: dict) -> dict:
    return node(raw.get("title", ""), raw.get("kind", ""), raw.get("note", ""),
                [from_extra(c) for c in raw.get("children", [])])


def project_branch(p: dict) -> dict:
    kids = []
    algorithm = p.get("algorithm") or []
    if algorithm:
        kids.append(node(p.get("algorithm_label") or "Как устроено", "план", "",
                         [node(s.get("title", ""), s.get("state", ""),
                               s.get("detail") or s.get("text", "")) for s in algorithm]))
    done = p.get("done") or []
    if done:
        kids.append(node(p.get("done_label") or "Сделано", "сделано", "",
                         [node(x if isinstance(x, str) else (x.get("title") or x.get("text", "")),
                               "сделано", "" if isinstance(x, str) else x.get("text", ""))
                          for x in done]))
    todo = p.get("todo") or []
    if todo:
        kids.append(node("Осталось", "вопрос", "",
                         [node(x if isinstance(x, str) else (x.get("title") or x.get("text", "")),
                               "вопрос", "" if isinstance(x, str) else x.get("why", ""))
                          for x in todo]))
    return node(p.get("name", ""), p.get("status") or "план", p.get("subtitle", ""), kids)


def journal_branch(journal: list, days: int = 5) -> dict:
    kids = []
    for day in journal[:days]:
        entries = [node(e.get("title", ""),
                        {"решение": "решение", "сделано": "сделано", "выяснено": "выяснено",
                         "открыто": "открыто"}.get(e.get("type", ""), "план"),
                        f"Почему: {clean(e['why'])}" if e.get("why")
                        else clean(e.get("text", ""))[:400])
                   for e in day.get("entries", [])]
        kids.append(node(day.get("date", ""), "план", f"{len(entries)} записей", entries))
    return node("Журнал работ", "план", "Что решали и почему — по дням", kids)


def blockers_branch(blockers: list) -> dict:
    return node("Что держит работу", "риск", "Только ваши действия",
                [node(b.get("title", ""), "риск", clean(b.get("who", "")))
                 for b in blockers])


def add_ids(tree: dict, path: str = "0") -> None:
    """Устойчивый идентификатор узла — путь от корня.

    По нему живут связи, дорисованные руками: пока ветка стоит на своём месте,
    связь переживает пересборку карты.
    """
    tree["id"] = path
    for i, child in enumerate(tree.get("c", [])):
        add_ids(child, f"{path}.{i}")


def collect(tree: dict, counter: Counter) -> None:
    counter[tree.get("k") or "план"] += 1
    for child in tree.get("c", []):
        collect(child, counter)


def build() -> str:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    extra = json.loads((HERE / "mapdata.json").read_text(encoding="utf-8"))

    children = [blockers_branch(data.get("blockers", []))]
    children += [project_branch(p) for p in data.get("projects", [])]
    children += [from_extra(b) for b in extra.get("ветки", [])]
    children.append(journal_branch(data.get("journal", [])))
    root = node("Техно-Ресурс", "план", "Все направления, задачи и решения", children)
    add_ids(root)

    counter: Counter = Counter()
    collect(root, counter)
    legend = "".join(
        f'<span class="lg {KINDS[k][0]}" data-kind="{k}"><i></i>{KINDS[k][1]}'
        f' <b>{counter.get(k, 0)}</b></span>'
        for k in KINDS if counter.get(k))

    page = PAGE
    page = page.replace("/*TREE*/", json.dumps(root, ensure_ascii=False))
    page = page.replace("/*RELATIONS*/", json.dumps(extra.get("связи", []), ensure_ascii=False))
    page = page.replace("/*KINDS*/", json.dumps({k: v[0] for k, v in KINDS.items()},
                                                ensure_ascii=False))
    page = page.replace("{{LEGEND}}", legend)
    page = page.replace("{{TOTAL}}", str(sum(counter.values())))
    page = page.replace("{{UPDATED}}", date.fromisoformat(data["updated"]).strftime("%d.%m.%Y"))
    return page


PAGE = r"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Карта компании — Техно-Ресурс</title>
<style>
:root{
  --bg:#eaeeef; --surface:#fff; --surface-2:#f4f7f8; --sunken:#e3e9ea;
  --ink:#14202a; --ink-2:#485965; --ink-3:#7b8d99;
  --line:#ccd6d9; --line-2:#b4c1c6;
  --accent:#0b5e6e; --accent-soft:#dcedf0;
  --ok:#3d6a41; --ok-soft:#e4efe3;
  --warn:#8f4d0e; --warn-soft:#faecd9;
  --stop:#8f2e2d; --stop-soft:#f8e3e1;
  --wait:#4c5a97; --wait-soft:#e2e6f5;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#101820; --surface:#18232b; --surface-2:#141d24; --sunken:#0d151b;
  --ink:#e6eef1; --ink-2:#a8b9c3; --ink-3:#788a95;
  --line:#293640; --line-2:#3a4b55;
  --accent:#5ab6c6; --accent-soft:#112f37;
  --ok:#8bc28e; --ok-soft:#1a2a1d;
  --warn:#dfa35b; --warn-soft:#31240f;
  --stop:#e78a80; --stop-soft:#361d1b;
  --wait:#98a6e0; --wait-soft:#1b2036;
}}
*{box-sizing:border-box} html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);overflow:hidden;
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.top{position:absolute;top:0;left:0;right:0;z-index:5;background:var(--surface);
  border-bottom:1px solid var(--line);padding:9px 14px}
.top h1{margin:0;font-size:17px;display:inline-block}
.top .sub{font-size:12px;color:var(--ink-3);margin-left:10px}
.tools{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-top:8px}
input[type=search]{flex:0 1 240px;padding:6px 9px;font:inherit;font-size:13px;
  border:1px solid var(--line-2);border-radius:3px;background:var(--surface-2);color:var(--ink)}
button{padding:6px 10px;font:inherit;font-size:13px;cursor:pointer;color:var(--ink);
  border:1px solid var(--line-2);border-radius:3px;background:var(--surface-2)}
button:hover{background:var(--sunken)}
button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.legend{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px;font-size:12px;color:var(--ink-2)}
.lg{cursor:pointer;user-select:none;display:inline-flex;align-items:center;gap:4px}
.lg i{width:8px;height:8px;border-radius:50%;display:inline-block}
.lg b{font-variant-numeric:tabular-nums;color:var(--ink-3)}
.lg.off{opacity:.3}
.lg.ok i{background:var(--ok)} .lg.accent i{background:var(--accent)}
.lg.warn i{background:var(--warn)} .lg.stop i{background:var(--stop)}
.lg.wait i{background:var(--wait)}
#map{position:absolute;inset:0;top:0;width:100vw;height:100vh;cursor:grab}
#map.grabbing{cursor:grabbing}
#map.linking{cursor:crosshair}
.node rect{stroke-width:1.5}
.node text{font:13px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  fill:var(--ink);pointer-events:none}
.node .cnt{font-size:11px;fill:var(--ink-3)}
.node.dim{opacity:.22}
.node.picked rect{stroke-dasharray:4 3}
.link{fill:none;stroke:var(--line-2);stroke-width:1.6}
.rel{fill:none;stroke:var(--accent);stroke-width:1.8;stroke-dasharray:6 4;marker-end:url(#arrow)}
.rel-label{font-size:11px;fill:var(--accent)}
.panel{position:absolute;left:14px;bottom:14px;max-width:420px;background:var(--surface);
  border:1px solid var(--line);border-radius:3px;padding:11px 13px;font-size:13px;
  box-shadow:0 4px 18px rgba(0,0,0,.12);display:none}
.panel b{display:block;margin-bottom:4px}
.panel .k{font-size:11.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em}
.panel p{margin:5px 0 0;color:var(--ink-2)}
.hint{position:absolute;right:14px;bottom:14px;font-size:12px;color:var(--ink-3);
  background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:7px 10px}
</style></head><body>

<div class="top">
  <h1>Карта компании</h1><span class="sub">Техно-Ресурс · {{TOTAL}} узлов · обновлено {{UPDATED}}</span>
  <div class="tools">
    <input type="search" id="q" placeholder="искать — «дельта», «ВАТС», «1С»">
    <button id="fit">вписать</button>
    <button id="zin">+</button>
    <button id="zout">−</button>
    <button id="expand">развернуть всё</button>
    <button id="collapse">свернуть</button>
    <button id="link">дорисовать связь</button>
    <button id="export">связи в файл</button>
    <a href="./" style="font-size:13px;color:var(--accent);margin-left:6px">карта состояния</a>
  </div>
  <div class="legend" id="legend">{{LEGEND}}</div>
</div>

<svg id="map"><defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
          orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker>
</defs>
<g id="canvas"><g id="links"></g><g id="rels"></g><g id="nodes"></g></g></svg>

<div class="panel" id="panel"></div>
<div class="hint">колесо — масштаб · тянуть — двигать · клик по узлу — свернуть ветку ·
  двойной клик — приблизить ветку</div>

<script>
const TREE = /*TREE*/;
const PRESET_RELS = /*RELATIONS*/;
const KINDS = /*KINDS*/;
const CSSVAR = n => getComputedStyle(document.documentElement).getPropertyValue('--' + n).trim();

const NODE_W = 210, LINE_H = 16, PAD_Y = 9, GAP_Y = 10, LEVEL_W = 262;
const svg = document.getElementById('map');
const canvas = document.getElementById('canvas');
const gLinks = document.getElementById('links'), gRels = document.getElementById('rels'),
      gNodes = document.getElementById('nodes');
const panel = document.getElementById('panel');
const byId = {};

// Связи, дорисованные руками, живут в браузере: страница статическая, писать
// их некуда. Кнопка «связи в файл» отдаёт их, чтобы положить в mapdata.json —
// тогда они станут общими и переживут смену браузера.
let rels = PRESET_RELS.slice();
try { rels = rels.concat(JSON.parse(localStorage.getItem('karta-rels') || '[]')); } catch (e) {}

function index(n, depth = 0, parent = null){
  byId[n.id] = n; n.depth = depth; n.parent = parent;
  n.collapsed = depth >= 1 && (n.c || []).length > 0;
  n.lines = wrap(n.t);
  n.h = Math.max(30, n.lines.length * LINE_H + PAD_Y * 2);
  (n.c || []).forEach(c => index(c, depth + 1, n));
}
function wrap(text, max = 26){
  const words = (text || '').split(' '), out = []; let line = '';
  for (const w of words){
    if ((line + ' ' + w).trim().length > max && line){ out.push(line); line = w; }
    else line = (line + ' ' + w).trim();
    if (out.length === 3) break;
  }
  if (line && out.length < 3) out.push(line);
  if (out.length === 3 && words.join(' ').length > out.join(' ').length + 1) out[2] += '…';
  return out;
}
index(TREE);

// Раскладка: корень в центре, ветки расходятся вправо и влево — как в XMind.
// Высота поддерева считается снизу вверх, потом узлы расставляются сверху вниз.
function visibleKids(n){ return n.collapsed ? [] : (n.c || []); }
function measure(n){
  const kids = visibleKids(n);
  n.sub = kids.length ? kids.reduce((s, k) => s + measure(k), 0) + GAP_Y * (kids.length - 1)
                      : n.h;
  return n.sub;
}
function place(n, x, top, dir){
  n.x = x; n.dir = dir;
  const kids = visibleKids(n);
  n.y = top + n.sub / 2;
  let cy = top;
  for (const k of kids){ place(k, x + dir * LEVEL_W, cy, dir); cy += k.sub + GAP_Y; }
}
function layout(){
  const kids = visibleKids(TREE);
  // Балансируем: крупные ветки раскидываем по сторонам поочерёдно.
  const sizes = kids.map(k => { measure(k); return k.sub; });
  const order = kids.map((k, i) => i).sort((a, b) => sizes[b] - sizes[a]);
  const right = [], left = []; let rh = 0, lh = 0;
  for (const i of order){ if (rh <= lh){ right.push(kids[i]); rh += sizes[i]; }
                          else { left.push(kids[i]); lh += sizes[i]; } }
  right.sort((a, b) => kids.indexOf(a) - kids.indexOf(b));
  left.sort((a, b) => kids.indexOf(a) - kids.indexOf(b));
  const span = Math.max(rh, lh);
  let cy = -span / 2;
  for (const k of right){ place(k, LEVEL_W, cy, 1); cy += k.sub + GAP_Y; }
  cy = -span / 2;
  for (const k of left){ place(k, -LEVEL_W, cy, -1); cy += k.sub + GAP_Y; }
  TREE.x = 0; TREE.y = 0; TREE.dir = 1; TREE.sub = span;
}

function edge(a, b){
  const ax = a.x + (b.dir > 0 ? NODE_W / 2 : -NODE_W / 2), ay = a.y;
  const bx = b.x - b.dir * NODE_W / 2, by = b.y;
  const mx = (ax + bx) / 2;
  return `M${ax},${ay} C${mx},${ay} ${mx},${by} ${bx},${by}`;
}
function el(tag, attrs, parent){
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

let picking = false, picked = null;

function draw(){
  layout();
  gLinks.textContent = ''; gNodes.textContent = ''; gRels.textContent = '';
  const drawn = [];
  (function walk(n){
    drawn.push(n);
    for (const k of visibleKids(n)){ el('path', {class: 'link', d: edge(n, k)}, gLinks); walk(k); }
  })(TREE);

  for (const n of drawn){
    const g = el('g', {class: 'node', 'data-id': n.id,
                       transform: `translate(${n.x - NODE_W / 2},${n.y - n.h / 2})`}, gNodes);
    const color = CSSVAR(KINDS[n.k] || 'wait');
    el('rect', {x: 0, y: 0, width: NODE_W, height: n.h, rx: 5,
                fill: n.depth === 0 ? color : CSSVAR('surface'),
                stroke: color, 'stroke-width': n.depth <= 1 ? 2 : 1.4}, g);
    const t = el('text', {x: 11, y: PAD_Y + 12,
                          fill: n.depth === 0 ? '#fff' : CSSVAR('ink')}, g);
    n.lines.forEach((ln, i) => {
      const ts = el('tspan', {x: 11, dy: i ? LINE_H : 0}, t); ts.textContent = ln; });
    const kids = (n.c || []).length;
    if (kids){
      const badge = el('text', {class: 'cnt', x: NODE_W - 9, y: n.h - 8,
                                'text-anchor': 'end'}, g);
      badge.textContent = (n.collapsed ? '+' : '−') + kids;
    }
    if (picked === n.id) g.classList.add('picked');
    g.addEventListener('click', ev => { ev.stopPropagation(); onNode(n); });
    g.addEventListener('dblclick', ev => { ev.stopPropagation(); focus(n); });
    g.addEventListener('mouseenter', () => showPanel(n));
  }

  // Связи поверх дерева: пунктир со стрелкой между любыми двумя узлами.
  for (const r of rels){
    const a = byId[r.a], b = byId[r.b];
    if (!a || !b || a.x === undefined || b.x === undefined) continue;
    if (!drawn.includes(a) || !drawn.includes(b)) continue;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - 60;
    el('path', {class: 'rel', color: CSSVAR('accent'),
                d: `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`}, gRels);
    if (r.label){
      const lab = el('text', {class: 'rel-label', x: mx, y: my + 10,
                              'text-anchor': 'middle'}, gRels);
      lab.textContent = r.label;
    }
  }
  applyFilter();
}

function onNode(n){
  if (picking){
    if (!picked){ picked = n.id; draw(); return; }
    if (picked !== n.id){
      const label = prompt('Подпись связи (можно пусто):', '') || '';
      rels.push({a: picked, b: n.id, label});
      localStorage.setItem('karta-rels', JSON.stringify(
        rels.filter(r => !PRESET_RELS.includes(r))));
    }
    picked = null; picking = false;
    document.getElementById('link').classList.remove('on');
    svg.classList.remove('linking');
    draw(); return;
  }
  if ((n.c || []).length){ n.collapsed = !n.collapsed; draw(); remember(); }
}

function showPanel(n){
  panel.style.display = 'block';
  panel.innerHTML = '<span class="k">' + (KINDS[n.k] ? n.k : '') + '</span><b>' +
    esc(n.t) + '</b>' + (n.n ? '<p>' + esc(n.n) + '</p>' : '');
}
function esc(s){ return (s || '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

// Масштаб и перетаскивание
let k = 0.8, tx = 0, ty = 0;
function apply(){ canvas.setAttribute('transform', `translate(${tx},${ty}) scale(${k})`); }
// Размер холста спрашиваем у всех, кто может ответить: в момент загрузки svg
// иногда ещё не имеет ширины, и карта вписывалась в триста пикселей.
function viewW(){ return Math.max(600, svg.getBoundingClientRect().width,
  document.documentElement.clientWidth || 0, window.innerWidth || 0); }
function viewH(){ return Math.max(400, svg.getBoundingClientRect().height,
  document.documentElement.clientHeight || 0, window.innerHeight || 0); }
function fit(){
  const box = canvas.getBBox();
  if (!box.width || !box.height) return;
  // Размер берём с запасом на случай, если холст ещё не получил высоту:
  // отрицательный масштаб один раз уже вывернул карту наизнанку.
  const W = viewW(), H = viewH();
  k = Math.max(0.15, Math.min((W - 90) / box.width, (H - 210) / box.height, 1.4));
  tx = W / 2 - (box.x + box.width / 2) * k;
  ty = (H + 120) / 2 - (box.y + box.height / 2) * k;
  apply();
}
function focus(n){
  const W = viewW(), H = viewH();
  k = 1.1; tx = W / 2 - n.x * k; ty = (H + 120) / 2 - n.y * k; apply();
}
svg.addEventListener('wheel', e => {
  e.preventDefault();
  const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const nk = Math.min(3, Math.max(0.15, k * (e.deltaY < 0 ? 1.12 : 0.89)));
  tx = mx - (mx - tx) * nk / k; ty = my - (my - ty) * nk / k; k = nk; apply();
}, {passive: false});
let drag = null;
svg.addEventListener('mousedown', e => { drag = {x: e.clientX - tx, y: e.clientY - ty};
  svg.classList.add('grabbing'); });
window.addEventListener('mousemove', e => {
  if (!drag) return; tx = e.clientX - drag.x; ty = e.clientY - drag.y; apply(); });
window.addEventListener('mouseup', () => { drag = null; svg.classList.remove('grabbing'); });

// Кнопки
document.getElementById('fit').onclick = fit;
document.getElementById('zin').onclick = () => { k = Math.min(3, k * 1.2); apply(); };
document.getElementById('zout').onclick = () => { k = Math.max(0.15, k / 1.2); apply(); };
document.getElementById('expand').onclick = () => {
  (function all(n){ n.collapsed = false; (n.c || []).forEach(all); })(TREE);
  draw(); fit(); remember(); };
document.getElementById('collapse').onclick = () => {
  (function all(n){ if (n.depth >= 1) n.collapsed = (n.c || []).length > 0;
                    (n.c || []).forEach(all); })(TREE); draw(); fit(); remember(); };
document.getElementById('link').onclick = e => {
  picking = !picking; picked = null;
  e.target.classList.toggle('on', picking);
  svg.classList.toggle('linking', picking);
  if (picking) alert('Щёлкните по двум узлам — между ними появится связь.');
  draw();
};
document.getElementById('export').onclick = () => {
  const mine = JSON.parse(localStorage.getItem('karta-rels') || '[]');
  const blob = new Blob([JSON.stringify({"связи": mine}, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'связи.json'; a.click();
};

// Поиск: совпавшие узлы подсвечиваются, путь до них раскрывается.
const q = document.getElementById('q');
q.addEventListener('input', () => {
  const needle = q.value.trim().toLowerCase();
  if (needle){
    (function open(n){
      const hit = ((n.t || '') + ' ' + (n.n || '')).toLowerCase().includes(needle);
      let below = false;
      (n.c || []).forEach(c => { if (open(c)) below = true; });
      if (below) n.collapsed = false;
      n.hit = hit;
      return hit || below;
    })(TREE);
  } else {
    (function clear(n){ n.hit = false; (n.c || []).forEach(clear); })(TREE);
  }
  draw();
  if (needle) fit();
});

let hiddenKinds = [];
document.querySelectorAll('.lg').forEach(elem => {
  elem.onclick = () => {
    elem.classList.toggle('off');
    hiddenKinds = [...document.querySelectorAll('.lg.off')].map(x => x.dataset.kind);
    applyFilter();
  };
});
function applyFilter(){
  const needle = q.value.trim().toLowerCase();
  document.querySelectorAll('.node').forEach(g => {
    const n = byId[g.dataset.id];
    const hiddenKind = hiddenKinds.includes(n.k);
    const missed = needle && !n.hit;
    g.classList.toggle('dim', hiddenKind || missed);
  });
}

// Что было свёрнуто в прошлый раз — помним: карта большая, и каждый раз
// раскрывать одну и ту же ветку утомительно. Адрес с ?open=all открывает всё.
const OPEN_KEY = 'karta-open';
if (new URLSearchParams(location.search).get('open') === 'all'){
  (function all(n){ n.collapsed = false; (n.c || []).forEach(all); })(TREE);
} else {
  try {
    const saved = JSON.parse(localStorage.getItem(OPEN_KEY) || '[]');
    if (saved.length) (function apply(n){
      n.collapsed = (n.c || []).length > 0 && !saved.includes(n.id);
      (n.c || []).forEach(apply);
    })(TREE);
  } catch (e) {}
}
function remember(){
  const open = [];
  (function walk(n){ if (!n.collapsed && (n.c || []).length) open.push(n.id);
                     (n.c || []).forEach(walk); })(TREE);
  try { localStorage.setItem(OPEN_KEY, JSON.stringify(open)); } catch (e) {}
}

svg.addEventListener('click', () => { panel.style.display = 'none'; });
draw(); fit();
// Ещё раз, когда браузер закончил раскладку: первый расчёт бывает по нулевым
// размерам.
requestAnimationFrame(fit);
window.addEventListener('load', fit);
window.addEventListener('resize', fit);
</script></body></html>
"""


def main() -> int:
    out = HERE / "mindmap.html"
    out.write_text(build(), encoding="utf-8")
    print(f"собрано: {out.name} ({out.stat().st_size // 1024} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
