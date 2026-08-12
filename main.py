import time
import traceback

import bot_commands
import check_status


CHECK_INTERVAL = 30


def run_safely(name, function):
    try:
        function()
    except Exception as e:
        print(f"[ERROR] {name}: {e}", flush=True)
        traceback.print_exc()


def main():
    print("Steam Tracker started", flush=True)
    print(f"Check interval: {CHECK_INTERVAL} seconds", flush=True)

    while True:
        # Обрабатываем команды Telegram
        run_safely("bot_commands", bot_commands.main)

        # Проверяем статусы Steam
        run_safely("check_status", check_status.main)

        print(
            f"Waiting {CHECK_INTERVAL} seconds before next check...",
            flush=True
        )

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
