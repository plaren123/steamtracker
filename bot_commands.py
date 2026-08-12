import os
import json
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import gist_storage

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def resolve_steam_id(text, api_key):
    text = text.strip()

    if re.fullmatch(r"\d{17}", text):
        return text

    m = re.search(r"/profiles/(\d{17})", text)
    if m:
        return m.group(1)

    m = re.search(r"/id/([^/]+)", text)
    vanity = m.group(1) if m else (text if re.fullmatch(r"[A-Za-z0-9_-]+", text) else None)
    if vanity:
        url = (
            "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
            f"?key={api_key}&vanityurl={urllib.parse.quote(vanity)}"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.load(resp)
            result = data.get("response", {})
            if result.get("success") == 1:
                return result.get("steamid")
        except Exception:
            pass

    return None


def get_player_summaries(steam_ids):
    if not steam_ids:
        return {}
    ids_param = ",".join(steam_ids)
    url = (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        f"?key={STEAM_API_KEY}&steamids={ids_param}"
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    players = data.get("response", {}).get("players", [])
    return {p["steamid"]: p for p in players}


def get_updates(offset):
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        f"?offset={offset}&timeout=0"
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }).encode()
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def format_status_lines(steam_ids):
    if not steam_ids:
        return ["Пока нет отслеживаемых аккаунтов. Добавь через /add <ссылка или SteamID>."]
    players_by_id = get_player_summaries(steam_ids)
    lines = []
    for steam_id in steam_ids:
        player = players_by_id.get(steam_id)
        if player is None:
            lines.append(f"❔ {steam_id}: не удалось получить статус")
            continue
        persona_state = player.get("personastate", 0)
        persona_name = player.get("personaname", steam_id)
        is_online = persona_state in ONLINE_STATES
        if is_online:
            lines.append(f"🟢 {persona_name}: уже в сети")
        else:
            lines.append(f"⏳ {persona_name}: оффлайн, слежу")
    return lines


def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours and minutes:
        return f"{hours} ч {minutes} мин"
    if hours:
        return f"{hours} ч"
    return f"{minutes} мин"


def compute_stats_lines(steam_ids, sessions):
    players_by_id = get_player_summaries(steam_ids)
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=today_start.weekday())

    lines = []
    for steam_id in steam_ids:
        player = players_by_id.get(steam_id)
        name = player.get("personaname", steam_id) if player else steam_id
        acc_sessions = sessions.get(steam_id, [])

        today_total = 0.0
        week_total = 0.0
        for s in acc_sessions:
            start = datetime.fromisoformat(s["start"])
            end = datetime.fromisoformat(s["end"]) if s["end"] else now

            overlap_today = min(end, now) - max(start, today_start)
            if overlap_today.total_seconds() > 0:
                today_total += overlap_today.total_seconds()

            overlap_week = min(end, now) - max(start, week_start)
            if overlap_week.total_seconds() > 0:
                week_total += overlap_week.total_seconds()

        lines.append(
            f"📊 {name}: сегодня {format_duration(today_total)}, за неделю {format_duration(week_total)}"
        )
    return lines


def main():
    data = gist_storage.load_data()
    bot_state = data.setdefault("bot_state", {"last_update_id": 0})
    tracked_ids = data.setdefault("tracked_ids", [])
    sessions = data.setdefault("sessions", {})

    last_update_id = bot_state.get("last_update_id", 0)
    result = get_updates(last_update_id + 1)

    highest_update_id = last_update_id
    changed = False

    for update in result.get("result", []):
        highest_update_id = max(highest_update_id, update["update_id"])
        message = update.get("message", {})
        text = message.get("text", "").strip()
        sender_chat_id = str(message.get("chat", {}).get("id", ""))

        if sender_chat_id != str(TELEGRAM_CHAT_ID):
            continue

        if text == "/start":
            send_telegram_message("\n".join(format_status_lines(tracked_ids)))

        elif text == "/list":
            if tracked_ids:
                send_telegram_message("Отслеживаю:\n" + "\n".join(tracked_ids))
            else:
                send_telegram_message("Список пуст. Добавь через /add <ссылка или SteamID>.")

        elif text == "/stats":
            if not tracked_ids:
                send_telegram_message("Список пуст. Добавь через /add <ссылка или SteamID>.")
            else:
                send_telegram_message("\n".join(compute_stats_lines(tracked_ids, sessions)))

        elif text.startswith("/add"):
            arg = text[len("/add"):].strip()
            if not arg:
                send_telegram_message("Использование: /add <ссылка на профиль или SteamID64>")
                continue
            steam_id = resolve_steam_id(arg, STEAM_API_KEY)
            if not steam_id:
                send_telegram_message("Не смог распознать SteamID из этой ссылки/текста.")
                continue
            if steam_id in tracked_ids:
                send_telegram_message("Этот аккаунт уже отслеживается.")
                continue
            tracked_ids.append(steam_id)
            changed = True
            send_telegram_message(f"Добавил {steam_id} в список отслеживания ✅")

        elif text.startswith("/remove"):
            arg = text[len("/remove"):].strip()
            steam_id = resolve_steam_id(arg, STEAM_API_KEY) if arg else None
            if steam_id and steam_id in tracked_ids:
                tracked_ids.remove(steam_id)
                changed = True
                send_telegram_message(f"Убрал {steam_id} из списка ✅")
            else:
                send_telegram_message("Не нашёл такой ID в списке отслеживания.")

    if highest_update_id != last_update_id:
        bot_state["last_update_id"] = highest_update_id
        changed = True

    if changed:
        gist_storage.save_data(data)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
