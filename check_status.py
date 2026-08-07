import os
import json
import sys
import urllib.request
import urllib.parse

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
STEAM_ID = os.environ["STEAM_ID"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "state.json"

# Steam personastate values:
# 0 - Offline, 1 - Online, 2 - Busy, 3 - Away, 4 - Snooze, 5 - Looking to trade, 6 - Looking to play
ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def get_player_summary():
    url = (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        f"?key={STEAM_API_KEY}&steamids={STEAM_ID}"
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    players = data.get("response", {}).get("players", [])
    if not players:
        raise RuntimeError("No player data returned — check STEAM_ID / API key / profile privacy.")
    return players[0]


def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"was_online": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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
    player = get_player_summary()
    persona_state = player.get("personastate", 0)
    persona_name = player.get("personaname", "Unknown")
    is_online = persona_state in ONLINE_STATES

    print(f"DEBUG: name={persona_name} personastate={persona_state} is_online={is_online} communityvisibilitystate={player.get('communityvisibilitystate')}")

    last_state = load_last_state()
    was_online = last_state.get("was_online", False)

    if is_online and not was_online:
        send_telegram_message(f"🟢 {persona_name} только что зашёл(ла) в Steam!")
    elif not is_online and was_online:
        send_telegram_message(f"⚪️ {persona_name} вышел(ла) из сети.")

    save_state({"was_online": is_online})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
