#!/usr/bin/env python3
"""Собирает index.html карты проектов из data.json и style.css.

Запуск:  python3 build.py          — собрать рядом, в index.html
         ./deploy.sh               — собрать и выложить в /var/www/karta

Правится только data.json. Тексты в нём — это готовый HTML внутри абзаца:
можно писать <code>, <b>, <em>. Экранирования нет намеренно, файл пишем мы сами.
"""

from __future__ import annotations

import json
import pathlib
import datetime

HERE = pathlib.Path(__file__).resolve().parent

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# слаг для css-класса типа записи журнала
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


# ---------------------------------------------------------------- блокеры

def render_blockers(blockers: list) -> str:
    out = ['<div class="deps">']
    for b in blockers:
        cls = " is-warn" if b.get("cls") == "warn" else ""
        cheap = ' <span class="cheap">· минутное дело</span>' if b.get("cheap") else ""
        out.append(f'<div class="dep{cls}">')
        out.append('<div class="cause">')
        out.append(f'<b>{b["title"]}{cheap}</b>')
        out.append(f'<span class="who">{b["who"]}</span>')
        out.append("</div>")
        out.append('<div class="arrow">→</div>')
        out.append('<div class="effects">')
        for e in b["effects"]:
            out.append(f'<span class="tagv">{e}</span>')
        out.append("</div></div>")
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- алгоритм

def render_step(s: dict) -> str:
    out = [f'<div class="step {s.get("state", "wait")}">',
           f'<div class="rail"><div class="dot">{s["n"]}</div></div>',
           '<div class="txt">',
           f'<b>{s["title"]}</b>']
    if s.get("detail"):
        out.append(f'<div class="det">{s["detail"]}</div>')

    if s.get("fork"):
        out.append('<div class="fork">')
        for br in s["fork"]:
            blocked = " blocked" if br.get("blocked") else ""
            out.append(f'<div class="branch{blocked}">')
            out.append(f'<div class="bl">{br["label"]}</div>')
            out.append(f'<p>{br["text"]}</p></div>')
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
           '<div class="project">',
           '<div class="p-head">',
           f'<h3>{p["subtitle"]}</h3>',
           f'<span class="pill {p["status"]["cls"]}">{p["status"]["label"]}</span>',
           '<div class="p-meta">']
    for m in p["meta"]:
        out.append(f"<span>{m}</span>")
    out.append("</div></div>")

    if p.get("algorithm"):
        out.append('<div class="block">')
        out.append(f'<p class="block-label">{p.get("algorithm_label", "Алгоритм")}</p>')
        out.append('<div class="flow">')
        for s in p["algorithm"]:
            out.append(render_step(s))
        out.append("</div></div>")

    out.append('<div class="cols">')
    out.append("<div>")
    out.append(f'<p class="block-label">{p.get("done_label", "Уже работает")}</p><ul>')
    for d in p["done"]:
        out.append(f'<li class="di"><span class="t">✓</span><span>{d}</span></li>')
    out.append("</ul></div>")

    out.append('<div><p class="block-label">Осталось</p>')
    out.append(f'<ul data-todo="{p["id"]}">')
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
    days = sorted(journal, key=lambda d: d["date"], reverse=True)
    out = []
    for day in days:
        n = len(day["entries"])
        out.append('<div class="day">')
        out.append(f'<div class="day-date"><span>{ru_date(day["date"])}</span>'
                   f'<span class="n">{n} {plural(n, "запись", "записи", "записей")}</span></div>')
        out.append('<div class="entries">')
        for e in day["entries"]:
            slug = TYPE_SLUG.get(e["type"], "")
            out.append(f'<div class="entry t-{slug}">')
            out.append('<div class="top">')
            out.append(f'<span class="type">{e["type"]}</span>')
            out.append(f'<h4>{e["title"]}</h4>')
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


# ---------------------------------------------------------------- страница

SCRIPT = """
(function(){
  var KEY = "karta-checks-v1";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  function save(){ try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
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


def build() -> str:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    css = (HERE / "style.css").read_text(encoding="utf-8")

    total_entries = sum(len(d["entries"]) for d in data["journal"])

    nav = ['<div class="nav">']
    for p in data["projects"]:
        nav.append(f'<a href="#p-{p["id"]}">{p["name"]}</a>')
    nav.append('<a href="#journal">Журнал работ</a>')
    nav.append("</div>")

    parts = [
        "<!doctype html>",
        '<html lang="ru"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="robots" content="noindex, nofollow">',
        f"<title>{data['title']}</title>",
        f"<style>{css}</style>",
        "</head><body><div class=\"wrap\">",
        f'<p class="eyebrow">{data["eyebrow"]} · обновлено {ru_date(data["updated"])}</p>',
        f"<h1>{data['h1']}</h1>",
        f'<p class="lede">{data["lede"]}</p>',
        "\n".join(nav),

        '<div class="head"><h2>Что держит работу</h2>'
        f'<span class="aside">{len(data["blockers"])} '
        f'{plural(len(data["blockers"]), "действие", "действия", "действий")} · только ваши</span></div>',
        render_blockers(data["blockers"]),
        '<div class="legend">'
        '<span><i class="key ok"></i> шаг работает</span>'
        '<span><i class="key stop"></i> здесь всё встало</span>'
        '<span><i class="key wait"></i> шаг написан, но не проверен на деле</span>'
        "</div>",
    ]

    for p in data["projects"]:
        parts.append(render_project(p))

    parts.append('<div class="head" id="journal"><h2>Журнал работ</h2>'
                 f'<span class="aside">{total_entries} '
                 f'{plural(total_entries, "запись", "записи", "записей")} · новые сверху</span></div>')
    parts.append(render_journal(data["journal"]))

    parts.append('<div class="note">')
    for n in data["notes"]:
        parts.append(f"<p>{n}</p>")
    parts.append("</div>")

    parts.append(f"</div><script>{SCRIPT}</script></body></html>")
    return "\n".join(parts)


if __name__ == "__main__":
    html = build()
    out = HERE / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"собрано: {out} ({len(html.encode('utf-8')) / 1024:.0f} КБ)")
