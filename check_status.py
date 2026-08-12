import os
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime

import gist_storage

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Steam personastate values:
# 0 - Offline, 1 - Online, 2 - Busy, 3 - Away, 4 - Snooze, 5 - Looking to trade, 6 - Looking to play
ONLINE_STATES = {1, 2, 3, 4, 5, 6}


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
    data = gist_storage.load_data()
    steam_ids = data.get("tracked_ids", [])
    if not steam_ids:
        print("DEBUG: no tracked ids yet")
        return

    players_by_id = get_player_summaries(steam_ids)
    state = data.setdefault("state", {})
    sessions = data.setdefault("sessions", {})
    now_iso = datetime.utcnow().isoformat()

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

    gist_storage.save_data(data)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
