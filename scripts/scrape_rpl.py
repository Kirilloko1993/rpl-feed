#!/usr/bin/env python3
"""Парсер расписания РПЛ (текущий сезон) с championat.com → JSON feed.

Источники:
  - календарь: https://www.championat.com/football/_russiapl.html
      <a href=".../match/<id>/"><span class="_win|_no|_live"
           title="DD.MM.YYYY. N-й тур. Home - Away (H : A)"></span></a>
  - логотипы: таблица турнира /football/_russiapl/tournament/<id>/table/
      <span class="table-item__logo"><img src="...team/logo/<n>.png"/></span>
      <span class="table-item__name">ЦСКА</span>

Всё отдаётся серверно — нужен только stdlib (urllib + re).

Использование: python3 scrape_rpl.py data/rpl.json
При пустом/битом результате файл НЕ перезаписывается (exit 3),
чтобы в фиде не оказалось мусора.
"""
import urllib.request
import re
import json
import sys
from datetime import datetime, timezone

URL = "https://www.championat.com/football/_russiapl.html"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Календарь. Атрибуты в HTML бывают и в одинарных, и в двойных кавычках.
SPAN = re.compile(
    r'''href=["']/football/_russiapl/tournament/\d+/match/(\d+)/["']\s*>\s*<span class=["']_(\w+)["']\s+title=["']([^"']+)["']'''
)
TITLE = re.compile(
    r"(\d{2})\.(\d{2})\.(\d{4})\.\s*(.+?)\s*\.\s*(.+?)\s*-\s*([^()]+?)(?:\s*\(\s*(\d+)\s*:\s*(\d+)\s*\))?$"
)
TOURNAMENT = re.compile(r"/football/_russiapl/tournament/(\d+)/match/")
# Таблица турнира: логотип + русское название команды.
TEAM_ROW = re.compile(
    r'''class="table-item"[^>]*>\s*<span class="table-item__logo">\s*<img src="([^"]+)"\s*/?>\s*</span>\s*<span class="table-item__name">([^<]+)</span>'''
)


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001 — ретраим любые сетевые сбои
            last = e
            import time
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"не удалось скачать {url}: {last}")


def parse_calendar(html: str) -> list[dict]:
    out = []
    for m in SPAN.finditer(html):
        mid, cls, title = m.group(1), m.group(2), m.group(3)
        dm = TITLE.match(title)
        if not dm:
            continue
        dd, mm, yyyy, rnd, home, away, hs, as_ = dm.groups()
        home, away = home.strip(), away.strip()
        if hs is not None:
            status = "FINISHED" if cls != "_live" else "LIVE"
            score = [int(hs), int(as_)]
        else:
            status = "LIVE" if cls == "_live" else "SCHEDULED"
            score = None
        out.append({
            "id": mid,
            "date": f"{yyyy}-{mm}-{dd}",
            "round": rnd.strip(),
            "home": home,
            "away": away,
            "homeScore": score[0] if score else None,
            "awayScore": score[1] if score else None,
            "competition": "Российская Премьер-Лига",
            "status": status,
        })
    return out


def parse_teams(table_html: str) -> dict[str, str]:
    """Название команды (рус.) -> URL логотипа (полный размер, без /s/60x60/)."""
    teams = {}
    for m in TEAM_ROW.finditer(table_html):
        logo, name = m.group(1), m.group(2).strip()
        full = logo.replace("/s/60x60/team/logo/", "/team/logo/")
        teams[name] = full
    return teams


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/rpl.json"
    try:
        html = fetch(URL)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    fixtures = parse_calendar(html)
    if len(fixtures) < 20:  # меньше 20 матчей — источник явно сломался/изменился
        print(f"ERROR: подозрительно мало матчей ({len(fixtures)}), файл не трогаю", file=sys.stderr)
        return 3

    # Логотипы: таблица текущего сезона (id берём из календаря).
    logos: dict[str, str] = {}
    tm = TOURNAMENT.search(html)
    if tm:
        try:
            table_html = fetch(f"https://www.championat.com/football/_russiapl/tournament/{tm.group(1)}/table/")
            logos = parse_teams(table_html)
        except RuntimeError as e:
            print(f"WARN: таблица недоступна, фид без логотипов: {e}", file=sys.stderr)
    if logos:
        missing = sorted(({f["home"] for f in fixtures} | {f["away"] for f in fixtures}) - set(logos))
        if missing:
            print(f"WARN: нет логотипов для: {missing}", file=sys.stderr)
        for f in fixtures:
            f["homeTeamCrest"] = logos.get(f["home"])
            f["awayTeamCrest"] = logos.get(f["away"])

    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "competition": "Российская Премьер-Лига",
        "season": "2026/2027",
        "fixtures": sorted(fixtures, key=lambda f: (f["date"], f["id"])),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    played = sum(1 for x in fixtures if x["homeScore"] is not None)
    crests = sum(1 for x in fixtures if x.get("homeTeamCrest"))
    print(f"OK: {len(fixtures)} матчей (сыграно {played}, с крестами {crests}) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
