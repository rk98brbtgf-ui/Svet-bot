import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Kyiv")
SUMMARY_HOUR = 7
LATE_MINUTES = 90


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


SCHEDULE = load("schedule.json", {})


def get_outages(day: date):
    result = []
    for start_s, end_s in SCHEDULE.get(day.isoformat(), []):
        start = datetime.combine(day, time.fromisoformat(start_s), TZ)
        if end_s == "24:00":
            end = datetime.combine(day + timedelta(days=1), time(0, 0), TZ)
        else:
            end = datetime.combine(day, time.fromisoformat(end_s), TZ)
        result.append((start, end))
    return sorted(result)


def merged_outages(day: date):
    items = []
    for offset in (-1, 0, 1):
        items += get_outages(day + timedelta(days=offset))
    items.sort()
    out = []
    for s, e in items:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def day_text(day: date) -> str:
    outs = get_outages(day)
    if not outs:
        return "📅 График на сегодня: отключений нет"
    lines = "\n".join(f"🔴 {fmt(s)} – {fmt(e)}" for s, e in outs)
    return f"📅 График на сегодня:\n{lines}"


def build_events(now: datetime):
    events = {}
    today = now.date()
    for day in (today - timedelta(days=1), today):
        outs = merged_outages(day)
        for s, e in outs:
            events[f"off-{s.isoformat()}"] = (
                s, f"🔴 Света нет. Включат в {fmt(e)}", False)
            later = [s2 for s2, _ in outs if s2 > e]
            tail = (f"Следующее отключение в {fmt(later[0])}"
                    if later else "Следующих отключений по графику нет")
            events[f"on-{e.isoformat()}"] = (e, f"🟢 Свет есть. {tail}", False)
    events[f"summary-{today.isoformat()}"] = (
        datetime.combine(today, time(SUMMARY_HOUR, 0), TZ),
        day_text(today), True)
    return events


def send(text: str) -> bool:
    url = f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": os.environ["CHAT_ID"], "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return r.status == 200
    except Exception as exc:
        print("Ошибка отправки:", type(exc).__name__)
        return False


def main():
    state = load("state.json", {"sent": []})
    sent = list(state["sent"])
    now = datetime.now(TZ)
    changed = False
    events = build_events(now)
    for key, (when, text, late_ok) in sorted(events.items(), key=lambda kv: kv[1][0]):
        if key in sent or when > now:
            continue
        if not late_ok and now - when > timedelta(minutes=LATE_MINUTES):
            continue
        if send(text):
            sent.append(key)
            changed = True
            print("Отправлено:", key)
    if changed:
        with open("state.json", "w", encoding="utf-8") as f:
            json.dump({"sent": sent[-300:]}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
