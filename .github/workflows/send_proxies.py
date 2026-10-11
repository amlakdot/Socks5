import os
import requests
import time
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/socks5.txt",
]

def get_proxies():
    proxies = set()
    for url in PROXY_SOURCES:
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            for line in r.text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.add(line)
        except Exception as e:
            print(f"Error fetching {url}: {e}")
    return sorted(proxies)

def get_last_command():
    """آخرین دستور /Txt یا /file کاربر را پیدا می‌کند"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"limit": 50, "timeout": 5}, timeout=10)
        data = r.json()
        if not data.get("ok"):
            return "file"  # پیش‌فرض

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
        return last_command
    except Exception as e:
        print(f"Error getting updates: {e}")
        return "file"

def send_text(text: str):
    """ارسال متن (در صورت طولانی بودن تقسیم می‌شود)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    max_len = 4000
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        payload = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }
        requests.post(url, json=payload, timeout=15)
        time.sleep(0.3)

def send_file(content: str, filename: str = "socks5.txt"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    files = {
        "document": (filename, content.encode("utf-8"))
    }
    data = {
        "chat_id": CHAT_ID,
        "caption": f"🔄 SOCKS5 Proxies • {datetime.now().strftime('%Y-%m-%d %H:%M')}\nتعداد: {content.count(chr(10)) + 1}"
    }
    requests.post(url, data=data, files=files, timeout=30)

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN or CHAT_ID is missing!")
        return

    proxies = get_proxies()
    if not proxies:
        print("No proxies found!")
        return

    content = "\n".join(proxies)
    mode = get_last_command()
    print(f"Mode: {mode} | Proxies: {len(proxies)}")

    if mode == "txt":
        header = f"🔄 SOCKS5 Proxies • {datetime.now().strftime('%Y-%m-%d %H:%M')}\nتعداد: {len(proxies)}\n\n"
        send_text(header + content)
    else:
        send_file(content)

if __name__ == "__main__":
    main()
