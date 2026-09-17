#!/usr/bin/env python3
"""Собрать карту проектов в формате XMind из того же `data.json`.

    python3 build_xmind.py                  → export/карта-проектов.xmind и .opml
    python3 build_xmind.py --to /куда/либо  положить ещё и туда (например, в Загрузки мака)

Источник данных — тот же `data.json`, что и у страницы: две карты из одного
файла не разойдутся. HTML-разметка из текстов вычищается, длинные пояснения
уходят в заметки темы, а не в её заголовок.

Кладётся два файла:

* `.xmind` — родной формат XMind 2020 и новее (zip с `content.json`).
* `.opml` — на случай, если版 XMind окажется старой или карту захочется
  открыть в другом редакторе: OPML понимают почти все.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
COUNTER = {"n": 0}


def clean(text: str) -> str:
    """Убрать разметку и лишние пробелы — в карту идёт человеческий текст."""
    text = re.sub(r"<br\s*/?>", " ", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&mdash;", "—").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def topic(title: str, children: list | None = None, note: str = "") -> dict:
    COUNTER["n"] += 1
    node: dict = {"id": f"t{COUNTER['n']}", "class": "topic", "title": clean(title)[:200]}
    if note:
        node["notes"] = {"plain": {"content": clean(note)[:1200]}}
    if children:
        node["children"] = {"attached": children}
    return node


def project_branch(p: dict) -> dict:
    """Проект: статус, чем живёт, шаги алгоритма."""
    kids = [topic(f"Состояние: {p['status']['label']}")]
    if p.get("meta"):
        kids.append(topic("Чем устроен", [topic(m) for m in p["meta"]]))

    steps = []
    for step in p.get("algorithm", []):
        mark = {"ok": "✓", "wait": "…", "bad": "✗"}.get(step.get("state", ""), "·")
        steps.append(topic(f"{mark} {step.get('n', '')}. {step.get('title', '')}",
                           note=step.get("text", "")))
    if steps:
        kids.append(topic(p.get("algorithm_label", "Как работает"), steps))

    for key, label in (("facts", "Факты"), ("details", "Подробности"),
                       ("next", "Что дальше")):
        items = p.get(key)
        if isinstance(items, list) and items:
            kids.append(topic(label, [
                topic(i if isinstance(i, str) else i.get("title", ""),
                      note="" if isinstance(i, str) else i.get("text", ""))
                for i in items
            ]))
    return topic(f"{p['name']} — {p.get('subtitle', '')}".strip(" —"), kids)


def server_branch(s: dict) -> dict:
    runs = [topic(r.get("what", ""), note=r.get("note", "")) for r in s.get("runs", [])]
    kids = [topic(s.get("addr", ""))]
    if s.get("why"):
        kids.append(topic("Почему именно здесь", note=s["why"]))
    if runs:
        kids.append(topic("Что крутится", runs))
    return topic(s.get("name", "Сервер"), kids)


def journal_branch(journal: list, days: int = 3) -> dict:
    kids = []
    for day in journal[:days]:
        entries = [
            topic(f"[{e.get('type', '')}] {e.get('title', '')}",
                  note=(clean(e.get("text", "")) +
                        (f"\n\nПочему: {clean(e['why'])}" if e.get("why") else "")))
            for e in day.get("entries", [])
        ]
        kids.append(topic(day.get("date", ""), entries))
    return topic("Журнал работ", kids)


def sheets(data: dict, extra: list[dict]) -> list[dict]:
    projects = [project_branch(p) for p in data.get("projects", [])]
    servers = [server_branch(s) for s in data.get("servers", [])]
    blockers = [
        topic(b.get("title", ""),
              [topic(e) for e in b.get("effects", [])],
              note=b.get("who", ""))
        for b in data.get("blockers", [])
    ]
    alts = [topic(a.get("name", ""), note=a.get("what", ""))
            for a in data.get("alternatives", [])]

    main = topic(clean(data.get("h1", "Проекты")), projects)
    infra = topic("Инфраструктура и риски", [
        topic("Серверы", servers),
        topic("Узкие места", blockers),
        *([topic("Рассмотренные альтернативы", alts)] if alts else []),
        *extra,
    ])
    story = journal_branch(data.get("journal", []))

    return [
        {"id": "s1", "class": "sheet", "title": "Проекты", "rootTopic": main},
        {"id": "s2", "class": "sheet", "title": "Инфраструктура", "rootTopic": infra},
        {"id": "s3", "class": "sheet", "title": "Журнал", "rootTopic": story},
    ]


def write_xmind(path: Path, content: list[dict]) -> None:
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}
    metadata = {"creator": {"name": "karta/build_xmind.py"}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))


def opml_node(node: dict) -> str:
    text = escape(node.get("title", ""))
    note = node.get("notes", {}).get("plain", {}).get("content", "")
    attrs = f'text="{text}"'
    if note:
        attrs += f' _note="{escape(note)}"'
    kids = node.get("children", {}).get("attached", [])
    if not kids:
        return f"<outline {attrs}/>"
    inner = "".join(opml_node(k) for k in kids)
    return f"<outline {attrs}>{inner}</outline>"


def write_opml(path: Path, content: list[dict], title: str) -> None:
    body = "".join(opml_node(sheet["rootTopic"]) for sheet in content)
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        f"  <head><title>{escape(title)}</title></head>\n"
        f"  <body>{body}</body>\n</opml>\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", action="append", default=[],
                    help="куда ещё положить готовые файлы")
    args = ap.parse_args()

    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))

    # То, чего в data.json пока нет: свежие находки этой сессии.
    extra = [topic("Найдено 17.09.2026", [
        topic("Боевой сервер открыт наружу",
              [topic("вход по паролю разрешён"), topic("вход под root разрешён"),
               topic("файрвол выключен"), topic("5700 подборов пароля за сутки"),
               topic("fail2ban поставлен 17.09 — частично закрывает")],
              note="Порт 22 доступен всему интернету, там записи разговоров и токены."),
        topic("Резервных копий нет",
              [topic("база дашборда с разбором"), topic("676 МБ записей разговоров"),
               topic("на боевом ещё 324 МБ")],
              note="Снимок сервера в панели Timeweb — единственный рубеж, и он ручной."),
        topic("Разбор прозвона запускается руками",
              [topic("таймера нет"), topic("17.09 упал и день остался пустым"),
               topic("сторож поставлен: диагностика в 6:00 и отчёт в 7:00")]),
    ])]

    content = sheets(data, extra)
    out = HERE / "export"
    out.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    xmind = out / f"карта-проектов-{stamp}.xmind"
    opml = out / f"карта-проектов-{stamp}.opml"
    write_xmind(xmind, content)
    write_opml(opml, content, clean(data.get("h1", "Проекты")))

    made = [xmind, opml]
    for target in args.to:
        dst = Path(target)
        dst.mkdir(parents=True, exist_ok=True)
        for f in (xmind, opml):
            shutil.copy2(f, dst / f.name)
            made.append(dst / f.name)

    for f in made:
        print(f"{f}  ({f.stat().st_size / 1024:.0f} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
