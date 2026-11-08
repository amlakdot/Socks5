import os
import sys
import re
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
ALL_PROXIES_FILE = Path("all_proxies.txt")  # تاریخچه همه پروکسی‌های دیده‌شده

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
        except Exception:
            return 0
    return 0


def save_last_update_id(update_id: int):
    LAST_UPDATE_FILE.write_text(str(update_id) + "\n", encoding="utf-8")


def normalize_proxy(line: str) -> str | None:
    """
    هر فرمتی را به شکل تمیز host:port تبدیل می‌کند.
    فقط IPv4:port (یا در صورت لزوم hostname:port) استخراج می‌شود.
    خطوط کثیف (فلگ کشور، latency، ISP، هدر، آدرس کریپتو و ...) نادیده گرفته می‌شوند.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "://" in line:
        line = line.split("://", 1)[1]
    if "@" in line:
        line = line.split("@", 1)[1]
    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})\b", line)
    if m:
        ip, port = m.group(1), m.group(2)
        try:
            p = int(port)
            if 1 <= p <= 65535:
                return f"{ip}:{port}"
        except ValueError:
            pass
        return None
    m = re.search(r"([a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?):(\d{1,5})\b", line)
    if m:
        host, port = m.group(1), m.group(2)
        try:
            p = int(port)
            if 1 <= p <= 65535 and "." in host:
                return f"{host}:{port}"
        except ValueError:
            pass
    return None


def load_known_proxies() -> set[str]:
    """بارگذاری پروکسی‌های قبلی از فایل تاریخچه (نرمال‌شده)"""
    if ALL_PROXIES_FILE.exists():
        result = set()
        for line in ALL_PROXIES_FILE.read_text(encoding="utf-8").splitlines():
            n = normalize_proxy(line)
            if n:
                result.add(n)
        return result
    return set()


def save_known_proxies(proxies: set[str]):
    """ذخیره کل پروکسی‌های دیده‌شده (مرتب‌شده و تمیز)"""
    sorted_list = sorted(proxies)
    ALL_PROXIES_FILE.write_text("\n".join(sorted_list) + "\n", encoding="utf-8")
    log(f"Saved {len(sorted_list)} known proxies to {ALL_PROXIES_FILE}")


def _run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({r.returncode}): {err}")
    return r


def commit_and_push(message: str):
    """Commit + push فایل‌های state. همیشه [skip ci] می‌گذارد."""
    try:
        _run_git(["git", "config", "user.name", "Proxy Bot"])
        _run_git(["git", "config", "user.email", "bot@github.com"])

        files = ["sources.txt", "mode.txt", "last_update_id.txt", "all_proxies.txt"]
        existing = [f for f in files if Path(f).exists()]
        if not existing:
            log("No state files to commit.")
            return

        _run_git(["git", "add", "--"] + existing)

        diff = _run_git(["git", "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            log("No changes to commit.")
            return

        full_msg = f"{message} [skip ci]"
        _run_git(["git", "commit", "-m", full_msg])

        pull = _run_git(["git", "pull", "--rebase", "--autostash"], check=False)
        if pull.returncode != 0:
            log(f"git pull --rebase warning: {(pull.stderr or pull.stdout or '').strip()}")

        _run_git(["git", "push"])
        log("Changes committed and pushed (with [skip ci]).")
    except Exception as e:
        log(f"Git error (history may NOT persist): {e}")


def send_message(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        log("Cannot send: BOT_TOKEN or CHAT_ID missing")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    max_len = 4000
    success = True
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        payload = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, json=payload, timeout=20)
            data = r.json()
            if not data.get("ok"):
                log(f"sendMessage error: {r.text}")
                success = False
        except Exception as e:
            log(f"sendMessage exception: {e}")
            success = False
        time.sleep(0.35)
    return success


def send_document(filename: str, content: str, caption: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        log("Cannot send: BOT_TOKEN or CHAT_ID missing")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    files = {"document": (filename, content.encode("utf-8"))}
    data = {
        "chat_id": CHAT_ID,
        "caption": caption
    }
    try:
        r = requests.post(url, data=data, files=files, timeout=40)
        resp = r.json()
        if not resp.get("ok"):
            log(f"sendDocument error ({filename}): {r.text}")
            return False
        log(f"Sent document: {filename}")
        return True
    except Exception as e:
        log(f"sendDocument exception ({filename}): {e}")
        return False


def get_proxies_from_url(url: str) -> tuple[list[str], str | None]:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        proxies = []
        for line in r.text.splitlines():
            n = normalize_proxy(line)
            if n:
                proxies.append(n)
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
                    send_message("📭 هیچ منبعی تعریف نشده.")
                else:
                    lines = [f"{i}. `{s}`" for i, s in enumerate(sources, 1)]
                    send_message("📋 لیست منابع:\n\n" + "\n".join(lines))

            elif cmd == "/add":
                if len(parts) < 2:
                    send_message("❌ استفاده صحیح:\n/add https://example.com/proxies.txt")
                    continue
                new_url = parts[1].strip()
                if not new_url.startswith("http"):
                    send_message("❌ آدرس باید با http شروع شود.")
                    continue
                if new_url in sources:
                    send_message("ℹ️ این منبع قبلاً وجود دارد.")
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

            elif cmd in ("/help", "/start"):
                help_text = (
                    "📖 دستورات موجود:\n\n"
                    "/txt – ارسال به صورت متن\n"
                    "/file – ارسال به صورت فایل\n"
                    "/list – لیست منابع\n"
                    "/add <url> – اضافه کردن منبع\n"
                    "/del <شماره یا url> – حذف منبع\n"
                    "/stat – وضعیت منابع\n"
                    "/help – همین راهنما"
                )
                send_message(help_text)

    except Exception as e:
        log(f"Error processing commands: {e}")

    return sources, mode, changed, highest_update_id


def send_proxies(
    new_proxies: list[str],
    current_proxies: list[str],
    archive_proxies: list[str],
    mode: str,
) -> bool:
    """
    ارسال سه فایل:
      - جدید.txt   → فقط پروکسی‌های جدید این دور
      - کل.txt     → کل پروکسی‌های استخراج‌شده از منابع این دور
      - آرشیو.txt  → کل تاریخچه (همه پروکسی‌های دیده‌شده تا الان)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_content = "\n".join(new_proxies) if new_proxies else ""
    current_content = "\n".join(current_proxies)
    archive_content = "\n".join(archive_proxies)

    new_caption = f"🆕 پروکسی‌های جدید • {now_str}\nتعداد جدید: {len(new_proxies)}"
    current_caption = f"📦 کل پروکسی‌ها (این دور) • {now_str}\nتعداد: {len(current_proxies)}"
    archive_caption = f"🗄 آرشیو کامل • {now_str}\nتعداد آرشیو: {len(archive_proxies)}"

    if mode == "txt":
        if new_proxies:
            ok1 = send_message(
                f"🆕 پروکسی‌های جدید • {now_str}\nتعداد: {len(new_proxies)}\n\n{new_content}"
            )
        else:
            ok1 = send_message(f"🆕 هیچ پروکسی جدیدی پیدا نشد • {now_str}")
            log("No new proxies to send as text")

        ok2 = send_message(
            f"📦 کل پروکسی‌ها (این دور) • {now_str}\nتعداد: {len(current_proxies)}\n\n{current_content}"
        )

        ok3 = send_message(
            f"🗄 آرشیو کامل • {now_str}\nتعداد آرشیو: {len(archive_proxies)}\n"
            f"(به خاطر حجم بالا فقط تعداد نمایش داده شد – از حالت /file استفاده کنید)"
        )

        success = ok1 and ok2 and ok3
        if success:
            log("Sent all three as TEXT (archive summary only)")
        return success

    else:
        if new_proxies:
            ok1 = send_document("جدید.txt", new_content, new_caption)
        else:
            ok1 = send_message(f"🆕 هیچ پروکسی جدیدی پیدا نشد • {now_str}")
            log("No new proxies – skipped sending جدید.txt")

        time.sleep(0.4)
        ok2 = send_document("کل.txt", current_content, current_caption)

        time.sleep(0.4)
        ok3 = send_document("آرشیو.txt", archive_content, archive_caption)

        success = ok1 and ok2 and ok3
        if success:
            log("Sent all three as FILE (جدید + کل + آرشیو)")
        return success


def main():
    log("=== Starting Proxy Sender ===")

    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR: BOT_TOKEN or CHAT_ID missing!")
        sys.exit(1)

    sources = load_sources()
    mode = load_mode()
    log(f"Loaded {len(sources)} sources | mode = {mode}")

    sources, mode, changed, highest_update_id = process_commands(sources, mode)

    last_id = load_last_update_id()
    if highest_update_id > last_id:
        save_last_update_id(highest_update_id)
        changed = True

    if changed:
        save_sources(sources)
        save_mode(mode)
        commit_and_push("chore: update sources / mode / last_update_id")

    # ========== استخراج پروکسی‌ها ==========
    all_proxies_set: set[str] = set()
    for src in sources:
        proxies, _ = get_proxies_from_url(src)
        all_proxies_set.update(proxies)
        log(f"  → {len(proxies)} from {src[:60]}...")

    current_proxies = sorted(all_proxies_set)
    log(f"Total unique proxies this run: {len(current_proxies)}")

    if not current_proxies:
        log("No proxies found!")
        send_message("⚠️ هیچ پروکسی‌ای از منابع فعلی دریافت نشد.")
        sys.exit(0)

    # ========== مقایسه با تاریخچه ==========
    known = load_known_proxies()
    log(f"Known proxies from previous runs: {len(known)}")

    new_set = all_proxies_set - known
    new_proxies = sorted(new_set)
    log(f"New proxies (not seen before): {len(new_proxies)}")

    # آرشیو به‌روز (قبلی + جدیدهای این دور)
    updated_known = known | all_proxies_set
    archive_proxies = sorted(updated_known)
    log(f"Archive size after this run: {len(archive_proxies)}")

    # ========== ارسال سه فایل ==========
    try:
        ok = send_proxies(new_proxies, current_proxies, archive_proxies, mode)
        if not ok:
            log("ERROR: Failed to send proxies to Telegram")
            sys.exit(1)
    except Exception as e:
        log(f"ERROR while sending: {e}")
        sys.exit(1)

    # ========== ذخیره و پوش آرشیو ==========
    save_known_proxies(updated_known)
    commit_and_push(f"chore: update all_proxies.txt (+{len(new_proxies)} new)")

    log("=== Finished successfully ===")


if __name__ == "__main__":
    main()
