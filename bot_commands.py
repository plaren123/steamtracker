import os
import json
import sys
import urllib.request
import urllib.parse

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
STEAM_IDS = [s.strip() for s in os.environ["STEAM_ID"].split(",") if s.strip()]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BOT_STATE_FILE = "bot_state.json"

ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def get_player_summaries():
    ids_param = ",".join(STEAM_IDS)
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


def main():
    last_update_id = load_last_update_id()
    result = get_updates(last_update_id + 1)

    highest_update_id = last_update_id
    saw_start = False

    for update in result.get("result", []):
        highest_update_id = max(highest_update_id, update["update_id"])
        message = update.get("message", {})
        text = message.get("text", "")
        if text.strip() == "/start":
            saw_start = True

    if saw_start:
        players_by_id = get_player_summaries()
        lines = []
        for steam_id in STEAM_IDS:
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
        send_telegram_message("\n".join(lines))

    if highest_update_id != last_update_id:
        save_last_update_id(highest_update_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
