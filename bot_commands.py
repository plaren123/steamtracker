import os
import json
import sys
import urllib.request
import urllib.parse

STEAM_API_KEY = os.environ["STEAM_API_KEY"]
STEAM_ID = os.environ["STEAM_ID"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BOT_STATE_FILE = "bot_state.json"

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
        return None
    return players[0]


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
        player = get_player_summary()
        if player is None:
            send_telegram_message(
                "â³ Ð¡Ð»ÐµÐ¶Ñ Ð·Ð° Ð°ÐºÐºÐ°ÑÐ½ÑÐ¾Ð¼. ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¿Ð¾Ð»ÑÑÐ¸ÑÑ ÑÐµÐºÑÑÐ¸Ð¹ ÑÑÐ°ÑÑÑ â Ð¿ÑÐ¾Ð²ÐµÑÑ ÑÐ½Ð¾Ð²Ð° ÑÐµÑÐµÐ· 5 Ð¼Ð¸Ð½ÑÑ."
            )
        else:
            persona_state = player.get("personastate", 0)
            persona_name = player.get("personaname", "Ð°ÐºÐºÐ°ÑÐ½Ñ")
            is_online = persona_state in ONLINE_STATES
            if is_online:
                send_telegram_message(f"ð¢ {persona_name} ÑÐ¶Ðµ Ð² ÑÐµÑÐ¸!")
            else:
                send_telegram_message(
                    f"â³ Ð¡Ð»ÐµÐ¶Ñ Ð·Ð° {persona_name}. Ð¡ÐµÐ¹ÑÐ°Ñ Ð¾ÑÑÐ»Ð°Ð¹Ð½ â Ð½Ð°Ð¿Ð¸ÑÑ, ÐºÐ°Ðº ÑÐ¾Ð»ÑÐºÐ¾ Ð·Ð°Ð¹Ð´ÑÑ Ð² ÑÐµÑÑ."
                )

    if highest_update_id != last_update_id:
        save_last_update_id(highest_update_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
