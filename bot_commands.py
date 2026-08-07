import os
import json
import re
import sys
import urllib.request
import urllib.parse

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BOT_STATE_FILE = "bot_state.json"
TRACKED_FILE = "tracked_ids.json"

ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def load_tracked_ids():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r") as f:
            return json.load(f).get("ids", [])
    return []


def save_tracked_ids(ids):
    with open(TRACKED_FILE, "w") as f:
        json.dump({"ids": ids}, f)


def resolve_steam_id(text):
    """Accepts a raw SteamID64, a /profiles/<id> URL, or a /id/<vanity> URL. Returns steamid64 or None."""
    text = text.strip()

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


def load_last_update_id():
    if os.path.exists(BOT_STATE_FILE):
        with open(BOT_STATE_FILE, "r") as f:
            return json.load(f).get("last_update_id", 0)
    return 0


def save_last_update_id(update_id):
    with open(BOT_STATE_FILE, "w") as f:
        json.dump({"last_update_id": update_id}, f)


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


def main():
    last_update_id = load_last_update_id()
    result = get_updates(last_update_id + 1)

    highest_update_id = last_update_id
    tracked_ids = load_tracked_ids()
    tracked_changed = False

    for update in result.get("result", []):
        highest_update_id = max(highest_update_id, update["update_id"])
        message = update.get("message", {})
        text = message.get("text", "").strip()
        sender_chat_id = str(message.get("chat", {}).get("id", ""))

        if sender_chat_id != str(TELEGRAM_CHAT_ID):
            # Ignore messages from anyone other than the bot's owner
            continue

        if text == "/start":
            send_telegram_message("\n".join(format_status_lines(tracked_ids)))

        elif text == "/list":
            if tracked_ids:
                send_telegram_message("Отслеживаю:\n" + "\n".join(tracked_ids))
            else:
                send_telegram_message("Список пуст. Добавь через /add <ссылка или SteamID>.")

        elif text.startswith("/add"):
            arg = text[len("/add"):].strip()
            if not arg:
                send_telegram_message("Использование: /add <ссылка на профиль или SteamID64>")
                continue
            steam_id = resolve_steam_id(arg)
            if not steam_id:
                send_telegram_message("Не смог распознать SteamID из этой ссылки/текста.")
                continue
            if steam_id in tracked_ids:
                send_telegram_message("Этот аккаунт уже отслеживается.")
                continue
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

    if tracked_changed:
        save_tracked_ids(tracked_ids)

    if highest_update_id != last_update_id:
        save_last_update_id(highest_update_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
