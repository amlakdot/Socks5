import os
import sys
import requests
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SOURCES_FILE = Path("sources.txt")
MODE_FILE = Path("mode.txt")
LAST_UPDATE_FILE = Path("last_update_id.txt")

DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/refs/heads/master/socks5.txt",
]

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_sources() -> list[str]:
    if SOURCES_FILE.exists():
        sources = [line.strip() for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        if sources:
            return sources
    return DEFAULT_SOURCES.copy()

def save_sources(sources: list[str]):
    SOURCES_FILE.write_text("\n".join(sources) + "\n", encoding="utf-8")

def load_mode() -> str:
    if MODE_FILE.exists():
        mode = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        if mode in ("txt", "file"):
            return mode
    return "file"

def save_mode(mode: str):
    MODE_FILE.write_text(mode + "\n", encoding="utf-8")

def load_last_update_id() -> int:
    if LAST_UPDATE_FILE.exists():
        try:
            return int(LAST_UPDATE_FILE.read_text(encoding="utf-8").strip())
        except:
            return 0
    return 0

def save_last_update_id(update_id: int):
    LAST_UPDATE_FILE.write_text(str(update_id) + "\n", encoding="utf-8")

def commit_and_push(message: str):
    try:
        subprocess.run(["git", "config", "user.name", "Proxy Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bot@github.com"], check=True)
        subprocess.run(["git", "add", "sources.txt", "mode.txt", "last_update_id.txt"], check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True)
            subprocess.run(["git", "push"], check=True)
            log("Changes committed and pushed.")
        else:
            log("No changes to commit.")
    except Exception as e:
        log(f"Git error: {e}")

def send_message(text: str):
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
        time.sleep(0.3)

def get_proxies_from_url(url: str) -> tuple[list[str], str | None]:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        proxies = []
        for line in r.text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                proxies.append(line)
        last_modified = r.headers.get("Last-Modified")
        return proxies, last_modified
    except Exception as e:
        log(f"Error fetching {url}: {e}")
        return [], None

def process_commands(sources: list[str], mode: str) -> tuple[list[str], str, bool, int]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    changed = False
    last_update_id = load_last_update_id()
    highest_update_id = last_update_id

    try:
        # فقط آپدیت‌های جدید بعد از آخرین update_id
        params = {
            "offset": last_update_id + 1,
            "limit": 50,
            "timeout": 5
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if not data.get("ok"):
            log(f"getUpdates failed: {data}")
            return sources, mode, False, last_update_id

        updates = data.get("result", [])
        log(f"Received {len(updates)} new updates (after update_id {last_update_id})")

        for update in updates:
            update_id = update.get("update_id", 0)
            if update_id > highest_update_id:
                highest_update_id = update_id

            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue
            if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
                continue

            text = (msg.get("text") or "").strip()
            if not text:
                continue

            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "/txt":
                if mode != "txt":
                    mode = "txt"
                    changed = True
                    send_message("✅ حالت ارسال به متن تغییر کرد.")
                else:
                    send_message("ℹ️ حالت ارسال هم‌اکنون روی متن است.")

            elif cmd == "/file":
                if mode != "file":
                    mode = "file"
                    changed = True
                    send_message("✅ حالت ارسال به فایل تغییر کرد.")
                else:
                    send_message("ℹ️ حالت ارسال هم‌اکنون روی فایل است.")

            elif cmd == "/list":
                if not sources:
                    send_message("📭 هیچ منبعی وجود ندارد.")
                else:
                    msg_text = "📋 لیست منابع فعلی:\n\n"
                    for i, src in enumerate(sources, 1):
                        msg_text += f"{i}. `{src}`\n"
                    send_message(msg_text)

            elif cmd == "/add":
                if len(parts) < 2:
                    send_message("❌ استفاده صحیح:\n/add https://example.com/proxies.txt")
                    continue
                new_url = parts[1].strip()
                if not new_url.startswith("http"):
                    send_message("❌ آدرس باید با http یا https شروع شود.")
                    continue
                if new_url in sources:
                    send_message("⚠️ این منبع از قبل وجود دارد.")
                else:
                    sources.append(new_url)
                    changed = True
                    send_message(f"✅ منبع اضافه شد:\n`{new_url}`")

            elif cmd == "/del":
                if len(parts) < 2:
                    send_message("❌ استفاده صحیح:\n/del 2   یا   /del https://...")
                    continue
                target = parts[1].strip()

                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(sources):
                        removed = sources.pop(idx)
                        changed = True
                        send_message(f"🗑 منبع حذف شد:\n`{removed}`")
                    else:
                        send_message("❌ شماره نامعتبر است.")
                else:
                    if target in sources:
                        sources.remove(target)
                        changed = True
                        send_message(f"🗑 منبع حذف شد:\n`{target}`")
                    else:
                        send_message("❌ این منبع پیدا نشد.")

            elif cmd == "/stat":
                if not sources:
                    send_message("📭 هیچ منبعی برای بررسی وجود ندارد.")
                    continue

                send_message("⏳ در حال بررسی منابع... لطفاً صبر کنید.")
                report = "📊 وضعیت منابع:\n\n"
                now = datetime.now(timezone.utc)

                for i, src in enumerate(sources, 1):
                    proxies, last_mod = get_proxies_from_url(src)
                    count = len(proxies)

                    if last_mod:
                        try:
                            dt = datetime.strptime(last_mod, "%a, %d %b %Y %H:%M:%S %Z")
                            dt = dt.replace(tzinfo=timezone.utc)
                            hours_ago = (now - dt).total_seconds() / 3600
                            time_info = f"{hours_ago:.1f} ساعت پیش"
                        except Exception:
                            time_info = last_mod
                    else:
                        time_info = "نامشخص"

                    status = "✅" if count > 0 else "❌"
                    report += f"{status} منبع {i}\n"
                    report += f"• تعداد: `{count}`\n"
                    report += f"• آخرین آپدیت: `{time_info}`\n"
                    report += f"• آدرس: `{src[:70]}{'...' if len(src) > 70 else ''}`\n\n"

                send_message(report)

    except Exception as e:
        log(f"Error processing commands: {e}")

    return sources, mode, changed, highest_update_id

def send_proxies(proxies: list[str], mode: str):
    content = "\n".join(proxies)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    if mode == "txt":
        header = f"🔄 SOCKS5 Proxies • {now_str}\nتعداد: {len(proxies)}\n\n"
        send_message(header + content)
        log("Sent as TEXT")
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        files = {"document": ("socks5.txt", content.encode("utf-8"))}
        data = {
            "chat_id": CHAT_ID,
            "caption": f"🔄 SOCKS5 Proxies • {now_str}\nتعداد: {len(proxies)}"
        }
        r = requests.post(url, data=data, files=files, timeout=40)
        if not r.json().get("ok"):
            log(f"sendDocument error: {r.text}")
            raise Exception("Failed to send document")
        log("Sent as FILE")

def main():
    log("=== Starting Proxy Sender ===")

    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR: BOT_TOKEN or CHAT_ID missing!")
        sys.exit(1)

    sources = load_sources()
    mode = load_mode()
    log(f"Loaded {len(sources)} sources | mode = {mode}")

    sources, mode, changed, highest_update_id = process_commands(sources, mode)

    # ذخیره آخرین update_id حتی اگر دستوری نبود
    last_id = load_last_update_id()
    if highest_update_id > last_id:
        save_last_update_id(highest_update_id)
        changed = True

    if changed:
        save_sources(sources)
        save_mode(mode)
        commit_and_push("chore: update sources / mode / last_update_id")

    all_proxies = set()
    for src in sources:
        proxies, _ = get_proxies_from_url(src)
        all_proxies.update(proxies)
        log(f"  → {len(proxies)} from {src[:50]}...")

    proxies = sorted(all_proxies)
    log(f"Total unique proxies: {len(proxies)}")

    if not proxies:
        log("No proxies found!")
        send_message("⚠️ هیچ پروکسی‌ای از منابع فعلی دریافت نشد.")
        sys.exit(0)

    try:
        send_proxies(proxies, mode)
    except Exception as e:
        log(f"ERROR while sending: {e}")
        sys.exit(1)

    log("=== Finished successfully ===")

if __name__ == "__main__":
    main()
