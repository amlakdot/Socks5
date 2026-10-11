import os
import sys
import requests
import time
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/socks5.txt",
]

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_proxies():
    proxies = set()
    for url in PROXY_SOURCES:
        try:
            log(f"Fetching: {url}")
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            count = 0
            for line in r.text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and ":" in line:
                    proxies.add(line)
                    count += 1
            log(f"  → {count} proxies from this source")
        except Exception as e:
            log(f"  → Error: {e}")
    return sorted(proxies)

def get_last_command():
    """آخرین دستور /Txt یا /file را پیدا می‌کند"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        log("Checking last command from Telegram...")
        r = requests.get(url, params={"limit": 30, "timeout": 5}, timeout=15)
        data = r.json()

        if not data.get("ok"):
            log(f"getUpdates failed: {data}")
            return "file"

        last_command = "file"
        for update in data.get("result", []):
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue
            if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
                continue
            text = (msg.get("text") or "").strip().lower()
            if text in ("/txt", "/file"):
                last_command = text[1:]  # txt یا file
                log(f"Found command: /{last_command}")
        return last_command
    except Exception as e:
        log(f"Error in get_last_command: {e}")
        return "file"

def send_text(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    max_len = 4000
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        payload = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }
        r = requests.post(url, json=payload, timeout=20)
        if not r.json().get("ok"):
            log(f"sendMessage error: {r.text}")
        time.sleep(0.4)

def send_file(content: str, filename: str = "socks5.txt"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    files = {
        "document": (filename, content.encode("utf-8"))
    }
    data = {
        "chat_id": CHAT_ID,
        "caption": f"🔄 SOCKS5 Proxies • {datetime.now().strftime('%Y-%m-%d %H:%M')}\nتعداد: {len(content.splitlines())}"
    }
    r = requests.post(url, data=data, files=files, timeout=40)
    if not r.json().get("ok"):
        log(f"sendDocument error: {r.text}")
        raise Exception("Failed to send document")

def main():
    log("=== Starting Proxy Sender ===")

    if not BOT_TOKEN:
        log("ERROR: BOT_TOKEN is missing!")
        sys.exit(1)
    if not CHAT_ID:
        log("ERROR: CHAT_ID is missing!")
        sys.exit(1)

    log(f"CHAT_ID = {CHAT_ID}")

    proxies = get_proxies()
    if not proxies:
        log("ERROR: No proxies found from any source!")
        sys.exit(1)

    content = "\n".join(proxies)
    log(f"Total unique proxies: {len(proxies)}")

    mode = get_last_command()
    log(f"Selected mode: {mode}")

    try:
        if mode == "txt":
            header = f"🔄 SOCKS5 Proxies • {datetime.now().strftime('%Y-%m-%d %H:%M')}\nتعداد: {len(proxies)}\n\n"
            send_text(header + content)
            log("Sent as TEXT successfully")
        else:
            send_file(content)
            log("Sent as FILE successfully")
    except Exception as e:
        log(f"ERROR while sending: {e}")
        sys.exit(1)

    log("=== Finished successfully ===")

if __name__ == "__main__":
    main()
