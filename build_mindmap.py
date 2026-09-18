#!/usr/bin/env python3
"""Собрать карту-дерево всей компании в одну страницу.

    python3 build_mindmap.py        → mindmap.html
    ./deploy.sh                     соберёт и выложит вместе с картой состояния

Зачем отдельная страница. Карта состояния (`index.html`) отвечает на вопрос
«как идут дела» и читается сверху вниз. Здесь другой вопрос: **что откуда
следует**. Дерево сворачивается и разворачивается, ищется по тексту и
раскрашено по смыслу — видно, где решение, где открытый вопрос, а где риск.

Источники — те же файлы, что и у страницы состояния:

* `data.json` — направления, их шаги, сделанное и оставшееся, журнал работ;
* `mapdata.json` — ветки, которых на странице состояния нет: связка с 1С,
  хозяйство серверов, деньги.

Ничего не дублируется: правится один раз в данных, и обе страницы меняются
вместе. Сторонних библиотек нет — страница должна открываться и без интернета.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Виды узлов: цвет и подпись в легенде. Смысл важнее красоты — по цвету
# должно быть сразу понятно, требует узел действия или уже закрыт.
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
    """Вид узла из разных форм данных: строка, словарь статуса или пусто.

    В data.json статус направления записан словарём {label, cls} — карта
    состояния показывает его как плашку. Здесь нужен только вид.
    """
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
    """Ветка из mapdata.json — она уже написана деревом."""
    return node(raw.get("title", ""), raw.get("kind", ""), raw.get("note", ""),
                [from_extra(c) for c in raw.get("children", [])])


def project_branch(p: dict) -> dict:
    """Направление из data.json: как устроено, что сделано, что осталось."""
    kids = []
    algorithm = p.get("algorithm") or []
    if algorithm:
        kids.append(node(p.get("algorithm_label") or "Как устроено", "план",
                         "", [node(s.get("title", ""), s.get("state", ""),
                               s.get("detail") or s.get("text", "")) for s in algorithm]))
    done = p.get("done") or []
    if done:
        kids.append(node(p.get("done_label") or "Сделано", "сделано", "",
                         [node(x if isinstance(x, str) else (x.get("title") or x.get("text", "")), "сделано",
                               "" if isinstance(x, str) else x.get("text", "")) for x in done]))
    todo = p.get("todo") or []
    if todo:
        kids.append(node("Осталось", "вопрос", "",
                         [node(x if isinstance(x, str) else (x.get("title") or x.get("text", "")), "вопрос",
                               "" if isinstance(x, str) else (x.get("why", "")))
                          for x in todo]))
    return node(p.get("name", ""), p.get("status") or "план", p.get("subtitle", ""), kids)


def journal_branch(journal: list, days: int = 5) -> dict:
    """Последние дни журнала: решения и находки, из которых всё следует."""
    kids = []
    for day in journal[:days]:
        entries = [node(e.get("title", ""),
                        {"решение": "решение", "сделано": "сделано",
                         "выяснено": "выяснено", "открыто": "открыто"}.get(e.get("type", ""), "план"),
                        (f"Почему: {clean(e['why'])}" if e.get("why")
                         else clean(e.get("text", ""))[:500]))
                   for e in day.get("entries", [])]
        kids.append(node(day.get("date", ""), "план", f"{len(entries)} записей", entries))
    return node("Журнал работ", "план", "Что решали и почему — по дням", kids)


def blockers_branch(blockers: list) -> dict:
    return node("Что держит работу", "риск", "Только ваши действия",
                [node(b.get("title", ""), "риск", clean(b.get("who", "")))
                 for b in blockers])


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
    root = node("Техно-Ресурс", "план",
                "Все направления, задачи и решения одним деревом", children)

    counter: Counter = Counter()
    collect(root, counter)
    legend = "".join(
        f'<span class="lg {KINDS[k][0]}" data-kind="{html.escape(k)}">'
        f'<i></i>{html.escape(KINDS[k][1])} <b>{counter.get(k, 0)}</b></span>'
        for k in KINDS if counter.get(k))

    return PAGE.format(
        updated=date.fromisoformat(data["updated"]).strftime("%d.%m.%Y"),
        total=sum(counter.values()),
        legend=legend,
        data=json.dumps(root, ensure_ascii=False),
        kinds=json.dumps({k: v[0] for k, v in KINDS.items()}, ensure_ascii=False),
    )


PAGE = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Карта компании — Техно-Ресурс</title>
<style>
:root{{
  --bg:#eaeeef; --surface:#fff; --surface-2:#f4f7f8; --sunken:#e3e9ea;
  --ink:#14202a; --ink-2:#485965; --ink-3:#7b8d99;
  --line:#ccd6d9; --line-2:#b4c1c6;
  --accent:#0b5e6e; --accent-soft:#dcedf0;
  --ok:#3d6a41; --ok-soft:#e4efe3;
  --warn:#8f4d0e; --warn-soft:#faecd9;
  --stop:#8f2e2d; --stop-soft:#f8e3e1;
  --wait:#4c5a97; --wait-soft:#e2e6f5;
}}
@media (prefers-color-scheme:dark){{:root{{
  --bg:#101820; --surface:#18232b; --surface-2:#141d24; --sunken:#0d151b;
  --ink:#e6eef1; --ink-2:#a8b9c3; --ink-3:#788a95;
  --line:#293640; --line-2:#3a4b55;
  --accent:#5ab6c6; --accent-soft:#112f37;
  --ok:#8bc28e; --ok-soft:#1a2a1d;
  --warn:#dfa35b; --warn-soft:#31240f;
  --stop:#e78a80; --stop-soft:#361d1b;
  --wait:#98a6e0; --wait-soft:#1b2036;
}}}}
*{{box-sizing:border-box}} html,body{{margin:0}}
body{{background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
.top{{position:sticky;top:0;z-index:5;background:var(--surface);
  border-bottom:1px solid var(--line);padding:12px 18px}}
.top h1{{margin:0 0 2px;font-size:20px;letter-spacing:-.01em}}
.top .sub{{font-size:12.5px;color:var(--ink-3)}}
.tools{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}}
input[type=search]{{flex:1 1 220px;min-width:180px;padding:7px 10px;font:inherit;
  border:1px solid var(--line-2);border-radius:3px;background:var(--surface-2);color:var(--ink)}}
button{{padding:7px 11px;font:inherit;font-size:13.5px;cursor:pointer;color:var(--ink);
  border:1px solid var(--line-2);border-radius:3px;background:var(--surface-2)}}
button:hover{{background:var(--sunken)}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:9px;font-size:12.5px;color:var(--ink-2)}}
.lg{{cursor:pointer;user-select:none;display:inline-flex;align-items:center;gap:5px}}
.lg i{{width:9px;height:9px;border-radius:50%;display:inline-block}}
.lg b{{font-variant-numeric:tabular-nums;color:var(--ink-3);font-weight:600}}
.lg.off{{opacity:.35}}
.lg.ok i{{background:var(--ok)}} .lg.accent i{{background:var(--accent)}}
.lg.warn i{{background:var(--warn)}} .lg.stop i{{background:var(--stop)}}
.lg.wait i{{background:var(--wait)}}
.wrap{{padding:16px 18px 60px;max-width:1100px}}
ul{{list-style:none;margin:0;padding-left:20px}}
ul.root{{padding-left:0}}
li{{position:relative;margin:2px 0;padding-left:2px}}
li:not(.root-item)::before{{content:"";position:absolute;left:-12px;top:14px;width:10px;
  height:1px;background:var(--line-2)}}
ul:not(.root)::before{{content:"";position:absolute;left:8px;top:0;bottom:12px;width:1px;
  background:var(--line-2)}}
ul:not(.root){{position:relative}}
.row{{display:flex;align-items:flex-start;gap:7px;padding:4px 8px;border-radius:3px;
  background:var(--surface);border:1px solid transparent}}
.row:hover{{border-color:var(--line)}}
.row.has-kids{{cursor:pointer}}
.tw{{width:14px;flex:0 0 14px;color:var(--ink-3);font-size:11px;line-height:20px;text-align:center}}
.dot{{width:9px;height:9px;border-radius:50%;flex:0 0 9px;margin-top:6px}}
.ttl{{flex:1;min-width:0}}
.ttl b{{font-weight:600}}
.note{{display:block;font-size:12.5px;color:var(--ink-2);margin-top:2px}}
.count{{font-size:11.5px;color:var(--ink-3);font-variant-numeric:tabular-nums}}
li.collapsed > ul{{display:none}}
li.hidden{{display:none}}
mark{{background:var(--accent-soft);color:inherit;padding:0 2px;border-radius:2px}}
.dot.ok{{background:var(--ok)}} .dot.accent{{background:var(--accent)}}
.dot.warn{{background:var(--warn)}} .dot.stop{{background:var(--stop)}}
.dot.wait{{background:var(--wait)}}
.row.lvl1{{background:var(--surface-2);border-color:var(--line)}}
.row.lvl1 .ttl b{{font-size:16px}}
.foot{{margin-top:28px;font-size:12.5px;color:var(--ink-3)}}
.foot a{{color:var(--accent)}}
</style></head><body>
<div class="top">
  <h1>Карта компании</h1>
  <div class="sub">Техно-Ресурс · {total} узлов · обновлено {updated}</div>
  <div class="tools">
    <input type="search" id="q" placeholder="искать по карте — например «дельта» или «ВАТС»">
    <button id="all">развернуть всё</button>
    <button id="none">свернуть до направлений</button>
  </div>
  <div class="legend" id="legend">{legend}</div>
</div>
<div class="wrap"><ul class="root" id="tree"></ul>
  <div class="foot">Дерево собирается из тех же данных, что и
    <a href="./">карта состояния</a>: правится один раз, меняется везде.</div>
</div>
<script>
const DATA = {data};
const KINDS = {kinds};
const tree = document.getElementById('tree');

function render(n, level){{
  const li = document.createElement('li');
  if (level === 0) li.className = 'root-item';
  const kids = n.c || [];
  const row = document.createElement('div');
  row.className = 'row' + (kids.length ? ' has-kids' : '') + (level === 1 ? ' lvl1' : '');
  row.innerHTML =
    '<span class="tw">' + (kids.length ? '▾' : '') + '</span>' +
    '<span class="dot ' + (KINDS[n.k] || 'wait') + '"></span>' +
    '<span class="ttl"><b>' + esc(n.t) + '</b>' +
    (kids.length ? ' <span class="count">' + kids.length + '</span>' : '') +
    (n.n ? '<span class="note">' + esc(n.n) + '</span>' : '') + '</span>';
  li.appendChild(row);
  if (kids.length){{
    const ul = document.createElement('ul');
    kids.forEach(k => ul.appendChild(render(k, level + 1)));
    li.appendChild(ul);
    // По умолчанию открыты только направления: первый экран должен давать
    // обзор, а не простыню. Глубже разворачивается по клику или поиском.
    if (level >= 1) li.classList.add('collapsed');
    row.addEventListener('click', e => {{
      e.stopPropagation();
      li.classList.toggle('collapsed');
      row.querySelector('.tw').textContent = li.classList.contains('collapsed') ? '▸' : '▾';
    }});
    if (li.classList.contains('collapsed')) row.querySelector('.tw').textContent = '▸';
  }}
  li.dataset.kind = n.k || '';
  li.dataset.text = ((n.t || '') + ' ' + (n.n || '')).toLowerCase();
  return li;
}}
function esc(s){{ return (s || '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[c]); }}

(DATA.c || []).forEach(n => tree.appendChild(render(n, 0)));

document.getElementById('all').onclick = () => {{
  document.querySelectorAll('li.collapsed').forEach(li => {{
    li.classList.remove('collapsed');
    const tw = li.querySelector('.tw'); if (tw) tw.textContent = '▾';
  }});
}};
document.getElementById('none').onclick = () => {{
  document.querySelectorAll('#tree li').forEach(li => {{
    if (!li.querySelector('ul')) return;
    const deep = li.parentElement.closest('li');
    if (deep) {{
      li.classList.add('collapsed');
      const tw = li.querySelector('.tw'); if (tw) tw.textContent = '▸';
    }}
  }});
}};

// Поиск: показываем совпавшие узлы вместе с их родителями и раскрываем путь.
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const needle = q.value.trim().toLowerCase();
  const all = document.querySelectorAll('#tree li');
  if (!needle){{
    all.forEach(li => {{ li.classList.remove('hidden'); li.querySelectorAll('mark').forEach(unmark); }});
    return;
  }}
  all.forEach(li => li.classList.add('hidden'));
  all.forEach(li => {{
    if (!li.dataset.text.includes(needle)) return;
    li.classList.remove('hidden');
    let p = li.parentElement.closest('li');
    while (p){{ p.classList.remove('hidden', 'collapsed');
      const tw = p.querySelector('.tw'); if (tw && p.querySelector('ul')) tw.textContent = '▾';
      p = p.parentElement.closest('li'); }}
    li.querySelectorAll(':scope > .row ul').forEach(() => {{}});
  }});
}});
function unmark(m){{ m.replaceWith(m.textContent); }}

// Легенда работает как фильтр: клик прячет узлы этого вида.
document.querySelectorAll('.lg').forEach(el => {{
  el.onclick = () => {{
    el.classList.toggle('off');
    const hidden = [...document.querySelectorAll('.lg.off')].map(x => x.dataset.kind);
    document.querySelectorAll('#tree li').forEach(li => {{
      li.style.display = hidden.includes(li.dataset.kind) ? 'none' : '';
    }});
  }};
}});
</script></body></html>
"""


def main() -> int:
    out = HERE / "mindmap.html"
    out.write_text(build(), encoding="utf-8")
    size = out.stat().st_size // 1024
    print(f"собрано: {out.name} ({size} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
