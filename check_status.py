import os
import json
import sys
import urllib.request
import urllib.parse

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "state.json"
TRACKED_FILE = "tracked_ids.json"
SESSIONS_FILE = "sessions.json"

# Steam personastate values:
# 0 - Offline, 1 - Online, 2 - Busy, 3 - Away, 4 - Snooze, 5 - Looking to trade, 6 - Looking to play
ONLINE_STATES = {1, 2, 3, 4, 5, 6}


def load_tracked_ids():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r") as f:
            return json.load(f).get("ids", [])
    return []


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


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_sessions(sessions):
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f)


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
    steam_ids = load_tracked_ids()
    if not steam_ids:
        print("DEBUG: no tracked ids yet")
        return

    players_by_id = get_player_summaries(steam_ids)
    state = load_state()
    sessions = load_sessions()
    now_iso = __import__("datetime").datetime.utcnow().isoformat()

    for steam_id in steam_ids:
        player = players_by_id.get(steam_id)
        if player is None:
            print(f"DEBUG: {steam_id} - no data returned (check ID / API key / privacy)")
            continue

        persona_state = player.get("personastate", 0)
        persona_name = player.get("personaname", steam_id)
        is_online = persona_state in ONLINE_STATES

        print(f"DEBUG: name={persona_name} steamid={steam_id} personastate={persona_state} is_online={is_online}")

        prev = state.get(steam_id, {"was_online": False})
        was_online = prev.get("was_online", False)

        acc_sessions = sessions.setdefault(steam_id, [])

        if is_online and not was_online:
            send_telegram_message(f"🟢 {persona_name} только что зашёл(ла) в Steam!")
            acc_sessions.append({"start": now_iso, "end": None})
        elif not is_online and was_online:
            send_telegram_message(f"⚪️ {persona_name} вышел(ла) из сети.")
            for s in reversed(acc_sessions):
                if s["end"] is None:
                    s["end"] = now_iso
                    break

        state[steam_id] = {"was_online": is_online}

    save_state(state)
    save_sessions(sessions)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
