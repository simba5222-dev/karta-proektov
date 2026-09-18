#!/bin/bash
# Stop-хук: не дать закончить ответ, оставив карту недособранной или невыложенной.
#
# Карта — не просто страница, а лента работы: владелец читает её по ссылке и
# судит по ней о состоянии дел. Поэтому вред здесь тихий: правка в data.json,
# которую не собрали, и собранная страница, которую не выложили, выглядят как
# сделанная работа, но владелец видит вчерашнее.
#
# Exit 0 — разрешить, exit 2 — заблокировать (stderr уходит Claude).

set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-/home/claude/karta}" || exit 0

ERRORS=""
TODAY=$(date +%F)

# 1. data.json обязан быть валидным JSON: build.py на битом файле упадёт, а
#    выложенная страница останется вчерашней.
if ! err=$(python3 -c "import json,sys; json.load(open('data.json',encoding='utf-8'))" 2>&1); then
    ERRORS="${ERRORS}  data.json — битый JSON: $(echo "$err" | tail -1)
"
fi

# 2. Секреты на страницу не выносить. Она отдаётся по ссылке, и хотя вход
#    закрыт basic-авторизацией, пароль от неё знают несколько человек.
SECRETS=$(grep -nE -e 'sk-[A-Za-z0-9_-]{20,}' \
                   -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
                   -e '(TOKEN|PASSWORD|API_KEY|SECRET)[[:space:]]*[=:][[:space:]]*[A-Za-z0-9_-]{8,}' \
                   data.json 2>/dev/null | head -5)
[ -n "$SECRETS" ] && ERRORS="${ERRORS}  Похоже на секрет в data.json (страница видна по ссылке):
$(echo "$SECRETS" | cut -c1-160 | sed 's/^/    /')
"

# 3. Синтаксис изменённых .py (core.quotepath=false — иначе кириллические имена
#    приходят экранированными и файл проверку минует).
PY_FILES=$(
    {
        git -c core.quotepath=false diff --name-only HEAD -- '*.py' 2>/dev/null
        git -c core.quotepath=false diff --cached --name-only -- '*.py' 2>/dev/null
        git -c core.quotepath=false ls-files --others --exclude-standard -- '*.py' 2>/dev/null
    } | sort -u
)
if [ -n "$PY_FILES" ]; then
    while IFS= read -r file; do
        [ -f "$file" ] || continue
        if ! err=$(python3 -c "import sys; src=open(sys.argv[1], encoding='utf-8').read(); compile(src, sys.argv[1], 'exec')" "$file" 2>&1); then
            ERRORS="${ERRORS}  Синтаксическая ошибка в ${file}: $(echo "$err" | tail -1)
"
        fi
    done <<< "$PY_FILES"
fi

# 4. data.json правили, а карту не собирали — правка существует только у нас.
if [ -f index.html ] && [ data.json -nt index.html ]; then
    ERRORS="${ERRORS}  data.json новее index.html — карта не собрана. Запустите: ./deploy.sh
"
fi

# 5. Собрали, но не выложили: владелец по ссылке видит прежнюю версию.
if [ -f index.html ] && [ -r /var/www/karta/index.html ]; then
    if ! cmp -s index.html /var/www/karta/index.html; then
        ERRORS="${ERRORS}  index.html отличается от выложенного в /var/www/karta — владелец видит старую карту. Запустите: ./deploy.sh
"
    fi
fi

if [ -n "$ERRORS" ]; then
    printf 'Задача не закончена — карта и то, что видит владелец, разошлись:\n%s\nПочините и повторите.\n' "$ERRORS" >&2
    exit 2
fi

# 6. Мягкое напоминание про журнал — один раз в день, чтобы не бубнить.
MARK=".claude/.journal-reminded-${TODAY}"
if [ ! -f "$MARK" ] && ! grep -q "\"${TODAY}\"" data.json 2>/dev/null; then
    echo "Напоминание: в журнале карты нет записей за ${TODAY}. В конце сеанса дописать, что делали и что решили, затем ./deploy.sh" >&2
    touch "$MARK" 2>/dev/null
    find .claude -maxdepth 1 -name '.journal-reminded-*' ! -name "*${TODAY}" -delete 2>/dev/null
fi

# 7. Маркер задачи остался, хотя коммиты были.
if [ -f .claude/current-task.md ]; then
    COMMITS=$(git log --oneline --since='3 hours ago' 2>/dev/null | wc -l)
    if [ "$COMMITS" -gt 0 ]; then
        echo "Напоминание: .claude/current-task.md ещё на месте. Если задача закрыта — удалите маркер и обновите NEXT_SESSION.md." >&2
    fi
fi

exit 0
