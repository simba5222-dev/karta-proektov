#!/usr/bin/env python3
"""Собирает карту проектов из data.json и style.css в двух видах.

    python3 build.py              → index.html   для сервера (отметки в localStorage)
    python3 build.py --artifact   → artifact.html для claude.ai (отметки в общей базе)
    ./deploy.sh                   → собрать серверный вид и выложить в /var/www/karta

Правится только data.json. Тексты в нём — готовый HTML внутри абзаца: можно писать
<code>, <b>, <em>. Экранирования нет намеренно, файл пишем мы сами.
"""

from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

TYPE_SLUG = {
    "решение": "reshenie",
    "сделано": "sdelano",
    "выяснено": "vyyasneno",
    "открыто": "otkryto",
}


def ru_date(iso: str) -> str:
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# ---------------------------------------------------------------- темы
# Артефакты claude.ai знают три состояния темы: системную (на корне ничего не
# проставлено) и два явных выбора через data-theme. Простого prefers-color-scheme
# там мало — при явно выбранной теме он не сработает. Поэтому для артефакта тот же
# набор токенов раскладывается в две защищённые ветки.

DARK_BLOCK = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\}\s*\}",
    re.DOTALL,
)


def css_for_artifact(css: str) -> str:
    m = DARK_BLOCK.search(css)
    if not m:
        raise SystemExit("в style.css не найден блок тёмной темы — правило поменялось?")
    tokens = m.group(1)
    replacement = (
        "@media (prefers-color-scheme:dark){\n"
        "  :root:not([data-theme=\"light\"]){" + tokens + "}\n"
        "}\n"
        ":root[data-theme=\"dark\"]{" + tokens + "}"
    )
    return css[:m.start()] + replacement + css[m.end():]


# ---------------------------------------------------------------- серверы

def render_servers(servers: list) -> str:
    """Где что стоит и почему именно там.

    Это главное, чего не хватало карте: разделение по серверам продиктовано
    не удобством, а географией — каждый сервис стоит там, где его пускают.
    """
    out = ['<div class="servers">']
    for s in servers:
        out.append('<div class="srv">')
        out.append('<div class="srv-head">')
        out.append(f'<h3>{s["name"]}</h3>')
        out.append(f'<span class="srv-addr">{s["addr"]}</span>')
        out.append("</div>")
        out.append(f'<p class="srv-why"><b>Почему здесь:</b> {s["why"]}</p>')
        out.append('<ul class="srv-list">')
        for item in s["runs"]:
            out.append(f'<li><b>{item["what"]}</b>{item["note"]}</li>')
        out.append("</ul>")
        if s.get("cannot"):
            out.append('<p class="srv-cant"><b>Что отсюда недоступно:</b> ' + s["cannot"] + "</p>")
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- блокеры

def render_blockers(blockers: list) -> str:
    out = ['<div class="deps">']
    for b in blockers:
        cls = " is-warn" if b.get("cls") == "warn" else ""
        cheap = ' <span class="cheap">· минутное дело</span>' if b.get("cheap") else ""
        out.append(f'<div class="dep{cls}">')
        out.append(f'<div class="cause"><b>{b["title"]}{cheap}</b>'
                   f'<span class="who">{b["who"]}</span></div>')
        out.append('<div class="arrow">→</div><div class="effects">')
        for e in b["effects"]:
            out.append(f'<span class="tagv">{e}</span>')
        out.append("</div></div>")
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- алгоритм

def render_step(s: dict) -> str:
    out = [f'<div class="step {s.get("state", "wait")}">',
           f'<div class="rail"><div class="dot">{s["n"]}</div></div>',
           f'<div class="txt"><b>{s["title"]}</b>']
    if s.get("detail"):
        out.append(f'<div class="det">{s["detail"]}</div>')
    if s.get("fork"):
        out.append('<div class="fork">')
        for br in s["fork"]:
            blocked = " blocked" if br.get("blocked") else ""
            out.append(f'<div class="branch{blocked}"><div class="bl">{br["label"]}</div>'
                       f'<p>{br["text"]}</p></div>')
        out.append("</div>")
    if s.get("par"):
        out.append('<div class="par">')
        for ln in s["par"]:
            out.append(f'<div class="lane"><b>{ln["label"]}</b>{ln["text"]}</div>')
        out.append("</div>")
    if s.get("after"):
        out.append(f'<div class="det" style="margin-top:9px">{s["after"]}</div>')
    if s.get("flag"):
        f = s["flag"]
        cls = " w" if f.get("cls") == "w" else ""
        out.append(f'<span class="flag{cls}">{f["text"]}</span>')
    out.append("</div></div>")
    return "\n".join(out)


# ---------------------------------------------------------------- проект

def render_project(p: dict) -> str:
    out = [f'<div class="head" id="p-{p["id"]}"><h2>{p["name"]}</h2>'
           f'<span class="aside" id="c-{p["id"]}">—</span></div>',
           '<div class="project"><div class="p-head">',
           f'<h3>{p["subtitle"]}</h3>',
           f'<span class="pill {p["status"]["cls"]}">{p["status"]["label"]}</span>',
           '<div class="p-meta">']
    for m in p["meta"]:
        out.append(f"<span>{m}</span>")
    out.append("</div></div>")

    if p.get("algorithm"):
        out.append('<div class="block">'
                   f'<p class="block-label">{p.get("algorithm_label", "Алгоритм")}</p>'
                   '<div class="flow">')
        for s in p["algorithm"]:
            out.append(render_step(s))
        out.append("</div></div>")

    out.append('<div class="cols"><div>')
    out.append(f'<p class="block-label">{p.get("done_label", "Уже работает")}</p><ul>')
    for d in p["done"]:
        out.append(f'<li class="di"><span class="t">✓</span><span>{d}</span></li>')
    out.append("</ul></div>")

    out.append(f'<div><p class="block-label">Осталось</p><ul data-todo="{p["id"]}">')
    for t in p["todo"]:
        crit = " crit" if t.get("crit") else ""
        why = f'<span class="why">{t["why"]}</span>' if t.get("why") else ""
        out.append(f'<li><label class="todo{crit}"><input type="checkbox" id="{t["id"]}">'
                   f'<span class="tt"><strong>{t["text"]}</strong>{why}</span></label></li>')
    out.append("</ul></div></div>")

    out.append(f'<div class="prog"><span>осталось</span><div class="bar">'
               f'<i data-bar="{p["id"]}"></i></div><span data-cnt="{p["id"]}">—</span></div>')
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- журнал

def render_journal(journal: list) -> str:
    out = []
    for day in sorted(journal, key=lambda d: d["date"], reverse=True):
        n = len(day["entries"])
        out.append('<div class="day">'
                   f'<div class="day-date"><span>{ru_date(day["date"])}</span>'
                   f'<span class="n">{n} {plural(n, "запись", "записи", "записей")}</span></div>'
                   '<div class="entries">')
        for e in day["entries"]:
            out.append(f'<div class="entry t-{TYPE_SLUG.get(e["type"], "")}">')
            out.append(f'<div class="top"><span class="type">{e["type"]}</span>'
                       f'<h4>{e["title"]}</h4>')
            if e.get("who"):
                out.append(f'<span class="who">{e["who"]}</span>')
            out.append("</div>")
            if e.get("text"):
                out.append(f'<p>{e["text"]}</p>')
            if e.get("why"):
                out.append(f'<div class="why"><b>Почему:</b> {e["why"]}</div>')
            if e.get("tags"):
                out.append('<div class="tags">')
                for t in e["tags"]:
                    out.append(f'<span class="tag">{t}</span>')
                out.append("</div>")
            out.append("</div>")
        out.append("</div></div>")
    return "\n".join(out)


# ---------------------------------------------------------------- поведение

COUNTERS = """
  function refresh(){
    var lists = document.querySelectorAll("ul[data-todo]");
    for (var i = 0; i < lists.length; i++){
      var key = lists[i].getAttribute("data-todo");
      var boxes = lists[i].querySelectorAll("input[type=checkbox]");
      var n = 0;
      for (var j = 0; j < boxes.length; j++) if (boxes[j].checked) n++;
      var bar = document.querySelector("[data-bar='" + key + "']");
      if (bar) bar.style.width = Math.round(n / boxes.length * 100) + "%";
      var txt = n + " из " + boxes.length + " закрыто";
      var cnt = document.querySelector("[data-cnt='" + key + "']");
      if (cnt) cnt.textContent = txt;
      var head = document.getElementById("c-" + key);
      if (head) head.textContent = txt;
    }
  }
"""

SCRIPT_LOCAL = """
(function(){
  var KEY = "karta-checks-v1";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  function save(){ try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
""" + COUNTERS + """
  var all = document.querySelectorAll(".todo input[type=checkbox]");
  for (var i = 0; i < all.length; i++){
    (function(cb){
      if (state[cb.id]) cb.checked = true;
      cb.addEventListener("change", function(){
        if (cb.checked) state[cb.id] = 1; else delete state[cb.id];
        save(); refresh();
      });
    })(all[i]);
  }
  refresh();
})();
"""

SCRIPT_DB = """
(function(){
  var dbNS = null;
  var boxes = document.querySelectorAll(".todo input[type=checkbox]");
""" + COUNTERS + """
  function say(msg){
    var n = document.getElementById("sync");
    if (n) n.textContent = msg;
  }
  for (var i = 0; i < boxes.length; i++){
    boxes[i].disabled = true;
    (function(cb){
      cb.addEventListener("change", function(){
        refresh();
        if (!dbNS) return;
        dbNS.doc("checks/" + cb.id)
          .set({ done: cb.checked, at: new Date().toISOString() })
          .catch(function(){ say("Отметку не удалось сохранить — попробуйте ещё раз."); });
      });
    })(boxes[i]);
  }
  refresh();

  (async function(){
    var ns = null;
    try { ns = await claude.use("db"); } catch (e) { ns = null; }
    if (!ns){
      say("Хранилище отметок недоступно в этом просмотре — карта открыта только для чтения.");
      return;
    }
    dbNS = ns;
    for (var i = 0; i < boxes.length; i++) boxes[i].disabled = false;
    say("Отметки синхронизированы.");
    try {
      ns.collection("checks").onSnapshot(function(snap){
        var docs = (snap && snap.docs) ? snap.docs : [];
        var map = {};
        for (var i = 0; i < docs.length; i++){
          var d = docs[i];
          var key = String(d.id).replace(/^checks\\//, "");
          var val = (typeof d.data === "function") ? d.data() : d;
          if (val && val.done) map[key] = true;
        }
        for (var j = 0; j < boxes.length; j++) boxes[j].checked = !!map[boxes[j].id];
        refresh();
      });
    } catch (e) {
      say("Отметки можно ставить, но прошлые не загрузились.");
    }
  })();
})();
"""


# ---------------------------------------------------------------- страница

def render_body(data: dict, artifact: bool) -> str:
    total = sum(len(d["entries"]) for d in data["journal"])
    nb = len(data["blockers"])

    nav = ['<div class="nav">']
    for p in data["projects"]:
        nav.append(f'<a href="#p-{p["id"]}">{p["name"]}</a>')
    nav.append('<a href="#servers">Как всё устроено</a>')
    nav.append('<a href="#journal">Журнал работ</a></div>')

    parts = [
        '<div class="wrap">',
        f'<p class="eyebrow">{data["eyebrow"]} · обновлено {ru_date(data["updated"])}</p>',
        f'<h1>{data["h1"]}</h1>',
        f'<p class="lede">{data["lede"]}</p>',
        "\n".join(nav),
        '<div class="head"><h2>Что держит работу</h2>'
        f'<span class="aside">{nb} {plural(nb, "действие", "действия", "действий")}'
        " · только ваши</span></div>",
        render_blockers(data["blockers"]),
        '<div class="head" id="servers"><h2>Как всё устроено</h2>'
        '<span class="aside">два сервера · разделены по географии</span></div>',
        render_servers(data["servers"]),
        '<div class="legend">'
        '<span><i class="key ok"></i> шаг работает</span>'
        '<span><i class="key stop"></i> здесь всё встало</span>'
        '<span><i class="key wait"></i> шаг написан, но не проверен на деле</span></div>',
    ]
    for p in data["projects"]:
        parts.append(render_project(p))

    parts.append('<div class="head" id="journal"><h2>Журнал работ</h2>'
                 f'<span class="aside">{total} '
                 f'{plural(total, "запись", "записи", "записей")} · новые сверху</span></div>')
    parts.append(render_journal(data["journal"]))

    notes = data["notes_artifact"] if artifact else data["notes"]
    parts.append('<div class="note">')
    for n in notes:
        parts.append(f"<p>{n}</p>")
    if artifact:
        parts.append('<div class="sync" id="sync">Подключаюсь к хранилищу отметок…</div>')
    parts.append("</div></div>")
    return "\n".join(parts)


def build(artifact: bool = False) -> str:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"),
                      object_pairs_hook=collections.OrderedDict)
    css = (HERE / "style.css").read_text(encoding="utf-8")
    body = render_body(data, artifact)

    if artifact:
        # Артефакт сам оборачивает файл в скелет документа: свои <html>, <head> и
        # <body> добавлять нельзя, только заголовок, стили и содержимое.
        extra = ("\n.sync{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
                 "font-size:11.5px;color:var(--ink-3);margin-top:10px}\n")
        return "\n".join([
            f"<title>{data['title_artifact']}</title>",
            f"<style>{css_for_artifact(css)}{extra}</style>",
            body,
            f"<script>{SCRIPT_DB}</script>",
        ])

    return "\n".join([
        "<!doctype html>",
        '<html lang="ru"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="robots" content="noindex, nofollow">',
        f"<title>{data['title']}</title>",
        f"<style>{css}</style>",
        "</head><body>",
        body,
        f"<script>{SCRIPT_LOCAL}</script>",
        "</body></html>",
    ])


if __name__ == "__main__":
    as_artifact = "--artifact" in sys.argv
    html = build(as_artifact)
    out = HERE / ("artifact.html" if as_artifact else "index.html")
    out.write_text(html, encoding="utf-8")
    print(f"собрано: {out} ({len(html.encode('utf-8')) / 1024:.0f} КБ)")
