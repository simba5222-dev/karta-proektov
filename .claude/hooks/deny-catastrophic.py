#!/usr/bin/env python3
"""PreToolUse: запреты, которые в этом проекте не имеют законного применения.

Механизм, а не заметка в CLAUDE.md: правило в тексте работает первые полчаса
сессии, дальше контекст забит задачей и правило тихо пропускается.

Два важных свойства, оба выстраданы на хуках ASR:
  * команда разбирается ПОСЕГМЕНТНО (`;`, `&`, `|`, перевод строки), иначе
    безобидная команда блокируется из-за похожей подстроки в соседнем сегменте;
  * матчится только НАСТОЯЩИЙ вызов в начале сегмента. Упоминание команды в
    тексте, документации или heredoc командой не является.

Этот хук ловит и Bash, и правку файлов (Edit/Write): index.html здесь
генерируется, и руками его не трогают.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # непонятный ввод — не блокируем

tool = data.get("tool_name", "")
tool_input = data.get("tool_input") or {}


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


GENERATED = (
    "ЗАПРЕЩЕНО: index.html и artifact.html собираются из data.json скриптом build.py — "
    "правка руками пропадёт при ближайшей сборке, а расхождение заметят не сразу. "
    "Правьте data.json (или сам build.py, если дело в разметке) и запускайте ./deploy.sh."
)

# --- правка файлов -------------------------------------------------------
if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if re.search(r"/(index|artifact)\.html$", path):
        deny(GENERATED)
    sys.exit(0)

# --- команды -------------------------------------------------------------
cmd = tool_input.get("command", "") or ""
segments = re.split(r"[;&|\n]+", cmd)


def invoked(segment: str, command: str) -> bool:
    """Сегмент действительно вызывает эту команду (можно через sudo и путь)."""
    pattern = rf"^\s*(?:\w+=\S*\s+)*(?:sudo\s+(?:-\S+\s+)*)?(?:\S*/)?{command}\b"
    return bool(re.search(pattern, segment))


for seg in segments:
    # 1. Правка собранной страницы в обход data.json.
    if (invoked(seg, "sed") or invoked(seg, "tee") or invoked(seg, "cat")) and re.search(
        r">\s*\S*(index|artifact)\.html|-i\b[^|;]*\b(index|artifact)\.html", seg
    ):
        deny(GENERATED)

    # 2. Единственный источник правды — data.json, истории карты нет нигде больше:
    # у репозитория нет remote, журнал работ существует только здесь.
    if invoked(seg, "rm") and re.search(r"\bdata\.json\b", seg):
        deny(
            "ЗАПРЕЩЕНО: data.json — единственный источник карты и журнала работ. "
            "Remote у репозитория нет, копия только в резервном архиве. "
            "Нужно переписать содержимое — правьте файл, а не удаляйте его."
        )

    # 3. Выложенная страница отдаётся nginx; сносить каталог целиком незачем,
    # deploy.sh кладёт файл поверх.
    if invoked(seg, "rm") and "/var/www/karta" in seg:
        deny(
            "ЗАПРЕЩЕНО: /var/www/karta — то, что сейчас отдаётся по ссылке владельцу. "
            "Выкладка идёт поверх через ./deploy.sh, удалять каталог не нужно."
        )

    # 4. Смена владельца в каталогах проектов: сервисы работают под claude.
    if (invoked(seg, "chown") or invoked(seg, "chgrp")) and "/home/claude" in seg:
        deny(
            "ЗАПРЕЩЕНО: chown/chgrp в /home/claude ломает доступ сервисам, которые "
            "работают под пользователем claude. Каталоги открыты группе claude через "
            "setgid, у agent umask 002 — права уже настроены."
        )

    # 5. Подмена деплой-ключа токеном аккаунта.
    if invoked(seg, "gh") and re.search(r"\bauth\s+login\b", seg):
        deny(
            "ЗАПРЕЩЕНО: gh auth login кладёт на машину токен всего аккаунта GitHub. "
            "У карты remote нет вовсе; если он появится — заводится отдельный "
            "деплой-ключ на один репозиторий."
        )

sys.exit(0)
