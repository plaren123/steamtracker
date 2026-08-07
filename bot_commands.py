#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_commands.py - dual-mode Telegram bot for SteamTracker

- Run with --once (or in CI/GITHUB_ACTIONS) to process updates once and exit.
- Run without args to run as a long-polling daemon.
"""
import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# Required env vars
try:
    STEAM_API_KEY = os.environ["STEAM_API_KEY"]
    TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
except KeyError as e:
    print(f"Missing environment variable: {e}", file=sys.stderr)
    # If running in --once mode in CI, it's helpful to exit non-zero so CI shows failure.
    # But when running as daemon, raising is also fine.
    sys.exit(1)

BOT_STATE_FILE = "bot_state.json"
TRACKED_FILE = "tracked_ids.json"
SESSIONS_FILE = "sessions.json"

# Steam personastate values considered "online"
ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sessions(sessions):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f)


def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours and minutes:
        return f"{hours} ч {minutes} мин"
    if hours:
        return f"{hours} ч"
    return f"{minutes} мин"


def compute_stats_lines(steam_ids, players_by_id):
    sessions = load_sessions()
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


def load_tracked_ids():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("ids", [])
    return []


def save_tracked_ids(ids):
    with open(TRACKED_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": ids}, f)


def resolve_steam_id(text):
    """Accepts a raw SteamID64, a /profiles/<id> URL, or a /id/<vanity> URL. Returns steamid64 or None."""
    text = (text or "").strip()

    # raw 17-digit SteamID64
    if re.fullmatch(r"\d{17}", text):
        return text

    # /profiles/<id> URL
    m = re.search(r"/profiles/(\d{17})", text)
    if m:
        return m.group(1)

    # /id/<vanity> URL or bare vanity name
    m = re.search(r"/id/([^/]+)", text)
    vanity = m.group(1) if m else (text if re.fullmatch(r"[A-Za-z0-9_-]+", text) else None)
    if vanity:
        url = (
            "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
            f"?key={STEAM_API_KEY}&vanityurl={urllib.parse.quote(vanity)}"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.load(resp)
            result = data.get("response", {})
            if result.get("success") == 1:
                return result.get("steamid")
        except Exception as e:
            print(f"Resolve vanity error: {e}", file=sys.stderr)

    return None


def get_player_summaries(steam_ids):
    if not steam_ids:
        return {}
    ids_param = ",".join(steam_ids)
    url = (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        f"?key={STEAM_API_KEY}&steamids={ids_param}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"GetPlayerSummaries error: {e}", file=sys.stderr)
        return {}
    players = data.get("response", {}).get("players", [])
    return {p["steamid"]: p for p in players}


def load_last_update_id():
    if os.path.exists(BOT_STATE_FILE):
        with open(BOT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_update_id", 0)
    return 0


def save_last_update_id(update_id):
    with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_update_id": update_id}, f)


def get_updates(offset, timeout=60):
    # Uses long-polling when timeout > 0
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        f"?offset={offset}&timeout={timeout}"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout + 5) as resp:
            return json.load(resp)
    except Exception as e:
        print(f"getUpdates error: {e}", file=sys.stderr)
        return {"ok": False, "result": []}


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }).encode()
    req = urllib.request.Request(url, data=payload)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as e:
        print(f"sendMessage error: {e}", file=sys.stderr)


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


def process_single_update(update, tracked_ids):
    """Process one update dict. Returns True if tracked_ids changed."""
    tracked_changed = False
    message = update.get("message", {}) or {}
    text = message.get("text", "").strip() if message.get("text") else ""
    sender_chat_id = str(message.get("chat", {}).get("id", ""))

    if sender_chat_id != str(TELEGRAM_CHAT_ID):
        # Ignore messages from anyone other than the bot's owner
        return False

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
            players_by_id = get_player_summaries(tracked_ids)
            send_telegram_message("\n".join(compute_stats_lines(tracked_ids, players_by_id)))

    elif text.startswith("/add"):
        arg = text[len("/add"):].strip()
        if not arg:
            send_telegram_message("Использование: /add <ссылка на профиль или SteamID64>")
            return False
        steam_id = resolve_steam_id(arg)
        if not steam_id:
            send_telegram_message("Не смог распознать SteamID из этой ссылки/текста.")
            return False
        if steam_id in tracked_ids:
            send_telegram_message("Этот аккаунт уже отслеживается.")
            return False
        tracked_ids.append(steam_id)
        tracked_changed = True
        send_telegram_message(f"Добавил {steam_id} в список отслеживания ✅")

    elif text.startswith("/remove"):
        arg = text[len("/remove"):].strip()
        steam_id = resolve_steam_id(arg) if arg else None
        if steam_id and steam_id in tracked_ids:
            tracked_ids.remove(steam_id)
            tracked_changed = True
            send_telegram_message(f"Убрал {steam_id} из списка ✅")
        else:
            send_telegram_message("Не нашёл такой ID в списке отслеживания.")

    return tracked_changed


def process_updates_once():
    """Perform one pass of getUpdates and exit (CI/cron friendly)."""
    last_update_id = load_last_update_id()
    result = get_updates(last_update_id + 1, timeout=0)  # short non-long-polling call
    highest_update_id = last_update_id
    tracked_ids = load_tracked_ids()
    tracked_changed = False

    for update in result.get("result", []):
        highest_update_id = max(highest_update_id, update.get("update_id", highest_update_id))
        try:
            changed = process_single_update(update, tracked_ids)
            if changed:
                tracked_changed = True
        except Exception as e:
            print(f"Error processing update: {e}", file=sys.stderr)

    if tracked_changed:
        save_tracked_ids(tracked_ids)

    if highest_update_id != last_update_id:
        save_last_update_id(highest_update_id)


def main_loop(poll_interval=1, long_timeout=60):
    last_update_id = load_last_update_id()
    tracked_ids = load_tracked_ids()

    print(f"Bot starting (long polling timeout={long_timeout}s). Last update id: {last_update_id}")

    backoff = 1
    while True:
        try:
            result = get_updates(last_update_id + 1, timeout=long_timeout)
            highest_update_id = last_update_id
            tracked_changed = False

            for update in result.get("result", []):
                highest_update_id = max(highest_update_id, update.get("update_id", highest_update_id))
                try:
                    changed = process_single_update(update, tracked_ids)
                    if changed:
                        tracked_changed = True
                except Exception as e:
                    print(f"Error processing update: {e}", file=sys.stderr)

            if tracked_changed:
                save_tracked_ids(tracked_ids)

            if highest_update_id != last_update_id:
                last_update_id = highest_update_id
                save_last_update_id(last_update_id)

            # reset backoff on successful loop
            backoff = 1

        except KeyboardInterrupt:
            print("Stopping bot (KeyboardInterrupt).")
            break
        except Exception as e:
            print(f"Bot loop error: {e}", file=sys.stderr)
            # exponential backoff capped
            time.sleep(min(backoff, 60))
            backoff = min(backoff * 2, 60)
            continue

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        # Run once if asked explicitly or when running inside GitHub Actions
        if "--once" in sys.argv or os.environ.get("GITHUB_ACTIONS"):
            process_updates_once()
        else:
            main_loop()
    except KeyboardInterrupt:
        print("Stopping bot.")
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
