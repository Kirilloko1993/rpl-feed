# rpl-feed

Расписание Российской Премьер-Лиги (текущий сезон) как JSON feed.

- Источник: [championat.com](https://www.championat.com/football/_russiapl.html) (публичная HTML-страница, календарь отдаётся серверно)
- Скрейпер: `scripts/scrape_rpl.py` (только stdlib: urllib + re, без браузера/ключей)
- Расписание: GitHub Actions, каждые 30 минут
- Фиды:
  - `data/rpl.json` — матчи РПЛ (дата, тур, команды, счёт, статус)

## Сырой URL фида

```
https://raw.githubusercontent.com/Kirilloko1993/rpl-feed/main/data/rpl.json
```

## Формат

```json
{
  "updatedAt": "2026-08-05T...+00:00",
  "source": "https://www.championat.com/football/_russiapl.html",
  "competition": "Российская Премьер-Лига",
  "season": "2026/2027",
  "fixtures": [
    {
      "id": "1318846",
      "date": "2026-07-25",
      "round": "1-й тур",
      "home": "Акрон",
      "away": "Зенит",
      "homeScore": 0,
      "awayScore": 5,
      "competition": "Российская Премьер-Лига",
      "status": "FINISHED"
    }
  ]
}
```

Статусы: `FINISHED` (счёт заполнен), `LIVE`, `SCHEDULED` (счёт null).

## Локальный запуск

```bash
python3 scripts/scrape_rpl.py data/rpl.json
```

При сбое источника файл не перезаписывается (exit 2/3), чтобы фид не протух.
