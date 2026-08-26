#!/usr/bin/env python3
"""Расписание РПЛ (текущий сезон) через публичный API Sofascore → JSON feed.

Зачем не championat.com: с 26.08.2026 сайт закрыт за SberID-авторизацией
(JS-челлендж), обычный HTTP-клиент контент больше не получает — скрейп упал
6+ ранов подряд. Sofascore отдаёт всё сразу одним API: дату/время (epoch),
счёт, статус, тур. Без ключей, но блокирует python-urllib по TLS-фингерпринту,
поэтому качаем curl'ом (есть и на ubuntu-latest, и локально).

Эндпоинты:
  - сезоны:  /unique-tournament/203/seasons            (берём последний)
  - матчи:   /unique-tournament/{ut}/season/{s}/events/last/{page}   (сыгранные)
             /unique-tournament/{ut}/season/{s}/events/next/{page}   (будущие)

Названия команд у Sofascore английские («CSKA Moscow»), а в фиде исторически
короткие русские («ЦСКА») — их даёт словарь TEAM_RU ниже. Неизвестной команде
уходит английское имя + WARN в лог.

Использование: python3 scrape_rpl.py data/rpl.json
При пустом/битом результате файл НЕ перезаписывается (exit 3),
чтобы в фиде не оказалось мусора.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

UT_RPL = 203  # Russian Premier League на Sofascore
API = f"https://api.sofascore.com/api/v1/unique-tournament/{UT_RPL}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
MSK = timezone(timedelta(hours=3))  # Москва, постоянное UTC+3 (без перевода часов)
MAX_PAGES = 20                      # страховка от бесконечной пагинации

# Sofascore team id -> короткое русское название (как в старом championat-фиде,
# чтобы ничего не «переключилось» и не переносилось в UI).
TEAM_RU = {
    2325: "ЦСКА",
    7517: "Балтика",
    5131: "Ахмат",
    285689: "Акрон",
    362016: "Динамо Мх",   # Динамо Махачкала
    2315: "Динамо М",      # Динамо Москва
    34425: "Краснодар",
    2326: "Ростов",
    2323: "Спартак М",
    2317: "Факел",
    2322: "Крылья Советов",
    2320: "Локомотив М",
    24118: "Оренбург",
    322699: "Родина",
    2333: "Рубин",
    2321: "Зенит",
}


def fetch_json(url: str, retries: int = 3):
    """GET через curl (sofascore режет python-urllib по TLS), с ретраями."""
    last = None
    for i in range(retries):
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "30", "-A", UA, url],
            capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except ValueError as e:
                last = e
        last = RuntimeError(f"curl rc={r.returncode}: {r.stderr.strip()[:200]}")
        import time
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"не удалось скачать {url}: {last}")


def latest_season() -> dict:
    seasons = fetch_json(f"{API}/seasons").get("seasons", [])
    if not seasons:
        raise RuntimeError("список сезонов пуст")
    return seasons[0]  # отсортированы от нового к старому


def fetch_events(kind: str, season_id: int) -> list:
    out, seen = [], set()
    for page in range(MAX_PAGES):
        evs = fetch_json(f"{API}/season/{season_id}/events/{kind}/{page}").get("events", [])
        if not evs:
            break
        for e in evs:
            if e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)
    return out


def team_name(team: dict) -> str:
    tid = team.get("id")
    name = TEAM_RU.get(tid)
    if name is None:
        name = (team.get("name") or "").strip()
        print(f"WARN: нет русского названия для team id={tid}, беру '{name}'", file=sys.stderr)
    return name


def to_fixture(e: dict) -> dict | None:
    home, away = e.get("homeTeam"), e.get("awayTeam")
    if not home or not away:
        return None
    ts = e.get("startTimestamp")
    if not ts:
        return None
    msk = datetime.fromtimestamp(int(ts), tz=MSK)

    stype = (e.get("status") or {}).get("type", "")
    status = {"finished": "FINISHED", "inprogress": "LIVE"}.get(stype, "SCHEDULED")

    def score(side):
        obj = e.get(f"{side}Score") or {}
        val = obj.get("current")
        return int(val) if isinstance(val, (int, float)) else None

    rnd = (e.get("roundInfo") or {}).get("round")
    return {
        "id": str(e["id"]),
        "date": msk.strftime("%Y-%m-%d"),
        "time": msk.strftime("%H:%M"),
        "round": f"{rnd}-й тур" if rnd else "",
        "home": team_name(home),
        "away": team_name(away),
        "homeScore": score("home"),
        "awayScore": score("away"),
        "competition": "Российская Премьер-Лига",
        "status": status,
        "homeTeamCrest": f"https://img.sofascore.com/api/v1/team/{home.get('id')}/image",
        "awayTeamCrest": f"https://img.sofascore.com/api/v1/team/{away.get('id')}/image",
    }


def main() -> int:
    try:
        season = latest_season()
        events = fetch_events("last", season["id"]) + fetch_events("next", season["id"])
    except RuntimeError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    fixtures = [f for f in (to_fixture(e) for e in events) if f]
    # дедуп на случай гонки между last/next
    fixtures = list({f["id"]: f for f in fixtures}.values())
    if len(fixtures) < 20:  # меньше 20 матчей — источник явно сломался/изменился
        print(f"ERROR: подозрительно мало матчей ({len(fixtures)}), файл не трогаю", file=sys.stderr)
        return 3

    year = season.get("year", "")
    m = re.match(r"(\d{2})/(\d{2})", year)
    season_label = f"20{m.group(1)}/{m.group(2)}" if m else year

    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": API,
        "competition": "Российская Премьер-Лига",
        "season": season_label,
        "fixtures": sorted(fixtures, key=lambda f: (f["date"], f["time"], f["id"])),
    }
    with open(sys.argv[1] if len(sys.argv) > 1 else "data/rpl.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    played = sum(1 for x in fixtures if x["homeScore"] is not None)
    with_time = sum(1 for x in fixtures if x.get("time"))
    teams = sorted({x["home"] for x in fixtures} | {x["away"] for x in fixtures})
    print(f"OK: {len(fixtures)} матчей (сыграно {played}, со временем {with_time}, "
          f"команд {len(teams)}, сезон {season_label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
