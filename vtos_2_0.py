#!/usr/bin/env python3
# VTOS — Vibecoded Terminal Operating System
# Python terminal environment for Linux

import curses
import os
import sys
import time
import shutil
import socket
import subprocess
import platform
import ast
import operator
import json
import calendar as calendar_module
import datetime as datetime_module
import shlex
import hashlib
import hmac
import secrets
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

VERSION = "2.0"
HOME = Path.home()
CONFIG = HOME / ".config" / "vtos"
DATA = HOME / ".local" / "share" / "vtos"
NOTES = DATA / "notes.txt"
ORIGINAL_TZ = os.environ.get("TZ")   # TZ of the shell VTOS was started from

CONFIG.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────

THEMES = {
    "cyan": {
        "accent": curses.COLOR_CYAN,
        "secondary": curses.COLOR_BLUE,
    },
    "green": {
        "accent": curses.COLOR_GREEN,
        "secondary": curses.COLOR_CYAN,
    },
    "magenta": {
        "accent": curses.COLOR_MAGENTA,
        "secondary": curses.COLOR_BLUE,
    },
    "amber": {"accent": curses.COLOR_YELLOW, "secondary": curses.COLOR_RED},
    "red": {"accent": curses.COLOR_RED, "secondary": curses.COLOR_YELLOW},
    "blue": {"accent": curses.COLOR_BLUE, "secondary": curses.COLOR_CYAN},
    "white": {"accent": curses.COLOR_WHITE, "secondary": curses.COLOR_MAGENTA},
}

theme_name = "cyan"
SETTINGS = {"theme":"cyan", "time_format":"24h", "date_format":"%d.%m.%Y",
            "timezone":"local", "refresh_rate":1, "show_seconds":True, "confirm_external":True, "dashboard_extra":True,
            "show_hidden":False, "file_icons":True, "process_sort":"memory", "confirm_kill":True,
            "week_start":"monday", "package_list":100, "clock_style":"blocks"}
DEFAULT_SETTINGS = dict(SETTINGS)


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_BLACK, THEMES.get(theme_name, THEMES["cyan"])["accent"])
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_GREEN, -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)
    curses.init_pair(6, curses.COLOR_RED, -1)
    curses.init_pair(7, curses.COLOR_MAGENTA, -1)
    curses.init_pair(8, curses.COLOR_BLUE, -1)
    curses.init_pair(9, THEMES.get(theme_name, THEMES["cyan"])["accent"], -1)
    curses.init_pair(10, THEMES.get(theme_name, THEMES["cyan"])["accent"], -1)


def accent():
    return 9

def refresh_theme_pairs():
    theme = THEMES.get(theme_name, THEMES["cyan"])
    try:
        curses.init_pair(2, curses.COLOR_BLACK, theme["accent"])
        curses.init_pair(9, theme["accent"], -1)
        curses.init_pair(10, theme["accent"], -1)
    except curses.error:
        pass


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def safe_add(win, y, x, text, color=1):
    try:
        height, width = win.getmaxyx()
        if y < height and x < width:
            win.addstr(y, x, str(text)[:max(0, width - x - 1)],
                       curses.color_pair(color))
    except curses.error:
        pass


def center(win, y, text, color=1):
    try:
        _, width = win.getmaxyx()
        x = max(0, (width - len(str(text))) // 2)
        safe_add(win, y, x, text, color)
    except Exception:
        pass


def box(win, title="", color=None):
    if color is None:
        color = accent()

    try:
        win.attron(curses.color_pair(color))
        win.border()
        if title:
            safe_add(win, 0, 2, f" {title} ", color)
        win.attroff(curses.color_pair(color))
    except curses.error:
        pass


def wait_key(win, message="Press any key to continue"):
    h, w = win.getmaxyx()
    safe_add(win, h - 2, 2, message, 5)
    status_bar(win)
    win.refresh()
    win.getch()


def clear(win):
    win.erase()
    status_bar(win)
    win.refresh()


def header(win, title):
    win.erase()
    h, w = win.getmaxyx()

    safe_add(win, 0, 2, f" Vibecoded Terminal Operating System {VERSION} ", accent())
    safe_add(win, 0, max(2, w - len(title) - 4), title, 7)

    try:
        win.hline(1, 1, curses.ACS_HLINE, w - 2)
    except curses.error:
        pass


def prompt(win, message):
    h, w = win.getmaxyx()

    safe_add(win, h - 3, 2, message, 5)
    safe_add(win, h - 2, 2, "> ", 4)

    curses.echo()
    curses.curs_set(1)

    try:
        result = win.getstr(h - 2, 4, max(1, w - 6)).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        result = ""

    curses.noecho()
    curses.curs_set(0)

    return result


def child_env():
    # The VTOS timezone setting must not leak into programs launched from VTOS.
    env = dict(os.environ)
    if ORIGINAL_TZ is None: env.pop("TZ", None)
    else: env["TZ"] = ORIGINAL_TZ
    return env


def run_external(win, command):
    """Temporarily leave curses to run an external command."""
    try:
        if SETTINGS.get("confirm_external",True):
            if prompt(win,"Run external command? y/N: ").strip().lower()!="y": return
        curses.def_prog_mode()
        curses.endwin()

        subprocess.run(command, shell=True, env=child_env())

        input("\nPress Enter to return to VTOS...")
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter...")
    finally:
        curses.reset_prog_mode()
        curses.curs_set(0)
        win.clear()
        status_bar(win)
        win.refresh()


def pointer_line(win, y, x, text, is_selected, color=1):
    # Selection arrow is drawn in the theme color, the selected text keeps the highlight.
    if is_selected:
        safe_add(win, y, x, "▶", accent())
        safe_add(win, y, x + 2, text, 2)
    else:
        safe_add(win, y, x + 2, text, color)


def get_terminal_size(win):
    return win.getmaxyx()


def bar(value, maximum, length=20):
    if maximum <= 0:
        return "░" * length

    filled = int((value / maximum) * length)
    filled = min(length, max(0, filled))

    return "█" * filled + "░" * (length - filled)




def apply_timezone():
    zone = SETTINGS.get("timezone", "local")
    if zone == "local":
        if ORIGINAL_TZ is None: os.environ.pop("TZ", None)
        else: os.environ["TZ"] = ORIGINAL_TZ
    else: os.environ["TZ"] = zone
    if hasattr(time, "tzset"): time.tzset()

def clock_text():
    fmt = ("%I:%M:%S %p" if SETTINGS["time_format"] == "12h" else "%H:%M:%S") if SETTINGS.get("show_seconds", True) else ("%I:%M %p" if SETTINGS["time_format"] == "12h" else "%H:%M")
    return time.strftime(fmt)

def date_text():
    try: return time.strftime(SETTINGS["date_format"])
    except Exception: return time.strftime("%d.%m.%Y")

def compact_date_text():
    # Short variant of the chosen date format (weekday/month names abbreviated).
    fmt = SETTINGS.get("date_format", "%d.%m.%Y").replace("%A", "%a").replace("%B", "%b")
    try: return time.strftime(fmt)
    except Exception: return time.strftime("%d.%m.%Y")

def clock_format():
    # Same format string that clock_text() uses; needed by apps that format other timezones.
    if SETTINGS.get("time_format") == "12h":
        return "%I:%M:%S %p" if SETTINGS.get("show_seconds", True) else "%I:%M %p"
    return "%H:%M:%S" if SETTINGS.get("show_seconds", True) else "%H:%M"

# ─────────────────────────────────────────────
# Network indicator (top bar), battery, big clock
# ─────────────────────────────────────────────

NET_STATE = {"time": None, "bytes": None, "speed": 0.0}

def net_rx_bytes():
    # Total received bytes of all interfaces except loopback (Linux).
    total = 0
    try:
        for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
            name, _, data = line.partition(":")
            if name.strip() == "lo" or not data.split(): continue
            total += int(data.split()[0])
    except Exception:
        return None
    return total

def net_speed():
    # Download speed in bytes/sec. It is re-measured once per refresh interval from Settings,
    # extra redraws (key presses) keep the last measured value.
    now = time.monotonic()
    interval = max(0.25, float(SETTINGS.get("refresh_rate", 1)))
    last = NET_STATE["time"]
    if last is None:
        NET_STATE.update(time=now, bytes=net_rx_bytes(), speed=0.0)
    elif now - last >= interval * 0.9:
        current = net_rx_bytes()
        if current is not None and NET_STATE["bytes"] is not None:
            NET_STATE["speed"] = max(0.0, (current - NET_STATE["bytes"]) / (now - last))
        NET_STATE.update(time=now, bytes=current)
    return NET_STATE["speed"]

def format_speed(bytes_per_sec):
    if bytes_per_sec < 1024: text = f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 ** 2: text = f"{bytes_per_sec / 1024:.1f} KB/s"
    elif bytes_per_sec < 1024 ** 3: text = f"{bytes_per_sec / 1024 ** 2:.1f} MB/s"
    else: text = f"{bytes_per_sec / 1024 ** 3:.1f} GB/s"
    return text.rjust(11)

def wifi_level():
    # 0 = no signal at all (no Wi-Fi adapter / not connected), 1..5 = signal strength.
    try:
        lines = Path("/proc/net/wireless").read_text().splitlines()[2:]
    except Exception:
        return 0
    best = 0
    for line in lines:
        parts = line.replace(":", " ").split()
        if len(parts) < 4: continue
        try:
            link = float(parts[2].rstrip(".")); level = float(parts[3].rstrip("."))
        except ValueError:
            continue
        if link > 0: percent = min(100.0, link / 70.0 * 100.0)
        elif level < 0: percent = max(0.0, min(100.0, 2 * (level + 100)))
        else: percent = 0.0
        if percent <= 0: continue
        best = max(best, 5 if percent >= 80 else 4 if percent >= 60 else 3 if percent >= 40 else 2 if percent >= 20 else 1)
    return best

def ethernet_connected(root="/sys/class/net"):
    # True if a physical (non-wireless, non-virtual) Ethernet adapter has a link.
    try:
        for path in Path(root).iterdir():
            if path.name == "lo" or (path / "wireless").exists() or (path / "phy80211").exists(): continue
            if "/devices/virtual/" in str(path.resolve()): continue
            if (path / "type").read_text().strip() != "1": continue
            state = (path / "operstate").read_text().strip()
            carrier = ""
            try: carrier = (path / "carrier").read_text().strip()
            except Exception: pass
            if state == "up" or (state == "unknown" and carrier == "1"): return True
    except Exception:
        pass
    return False

def wifi_text(level):
    return "✕" * 5 if level <= 0 else "●" * level + "○" * (5 - level)

def battery_charging(battery):
    try:
        for path in sorted(Path("/sys/class/power_supply").glob("BAT*")):
            status = (path / "status").read_text().strip().lower()
            if status: return status == "charging"
    except Exception:
        pass
    return bool(battery.power_plugged) and float(battery.percent) < 100


# Big digital clock: every glyph is 5 rows high; digits are 5 columns wide, the colon is 3.
CLOCK_GLYPHS = {
    "blocks": {
        "0": ["█████", "█   █", "█   █", "█   █", "█████"],
        "1": ["  █  ", " ██  ", "  █  ", "  █  ", " ███ "],
        "2": ["█████", "    █", "█████", "█    ", "█████"],
        "3": ["█████", "    █", "█████", "    █", "█████"],
        "4": ["█   █", "█   █", "█████", "    █", "    █"],
        "5": ["█████", "█    ", "█████", "    █", "█████"],
        "6": ["█████", "█    ", "█████", "█   █", "█████"],
        "7": ["█████", "    █", "    █", "    █", "    █"],
        "8": ["█████", "█   █", "█████", "█   █", "█████"],
        "9": ["█████", "█   █", "█████", "    █", "█████"],
        ":": ["   ", " █ ", "   ", " █ ", "   "],
    },
    "slashes": {
        "0": [" ___ ", "/   \\", "|   |", "|   |", "\\___/"],
        "1": ["  _  ", " /|  ", "  |  ", "  |  ", " _|_ "],
        "2": [" ___ ", "/   \\", "  __/", " /   ", "/____"],
        "3": [" ___ ", "/   \\", "  __/", "    \\", "\\___/"],
        "4": ["  /| ", " / | ", "/__|_", "   | ", "   | "],
        "5": [" ____", "|    ", "|___ ", "    \\", "\\___/"],
        "6": [" ___ ", "/    ", "|___ ", "|   \\", "\\___/"],
        "7": ["_____", "    /", "   / ", "  /  ", " /   "],
        "8": [" ___ ", "/   \\", "\\___/", "/   \\", "\\___/"],
        "9": [" ___ ", "/   \\", "\\___|", "    |", "\\___/"],
        ":": ["   ", " . ", "   ", " . ", "   "],
    },
}
CLOCK_WIDTH = 27   # "HH:MM" = 4 digits + colon + 4 gaps
CLOCK_HEIGHT = 5

def big_clock_time():
    # Returns ("HH:MM", "AM"/"PM"/"") following the clock format chosen in Settings.
    if SETTINGS.get("time_format") == "12h":
        return time.strftime("%I:%M"), time.strftime("%p")
    return time.strftime("%H:%M"), ""

def big_clock_lines(text, style=None):
    glyphs = CLOCK_GLYPHS.get(style or SETTINGS.get("clock_style", "blocks"), CLOCK_GLYPHS["blocks"])
    return [" ".join(glyphs[ch][row] for ch in text if ch in glyphs) for row in range(CLOCK_HEIGHT)]

def draw_big_clock(win, y, x, color=None):
    # Big HH:MM clock in the theme color (also used on the lock screen).
    text, suffix = big_clock_time()
    for row, line in enumerate(big_clock_lines(text)):
        safe_add(win, y + row, x, line, accent() if color is None else color)
    if suffix:
        safe_add(win, y + CLOCK_HEIGHT, x + CLOCK_WIDTH - len(suffix), suffix, accent() if color is None else color)


def draw_top_datetime(win, width, left_end=54, speed_text="", wifi=""):   # wifi = link text: ETHERNET or the Wi-Fi circles
    # Right-aligned "speed  wifi  date  time" in the top bar. The time is always drawn;
    # when space is short, the speed, then the date, are shortened or dropped.
    clock = clock_text()
    free = width - 2 - left_end
    full, compact = date_text(), compact_date_text()
    with_speed = [p for p in (speed_text, wifi) if p]
    without_speed = [wifi] if wifi else []
    options = []
    for group in (with_speed, without_speed):
        for date in (full, compact):
            options.append(" | ".join(group + [date, clock]))
    options.append(" | ".join(without_speed + [clock]))
    options.append(clock)
    text = next((t for t in options if len(t) <= free), clock)
    safe_add(win, 0, max(0, width - len(text) - 2), text, accent())


def process_sort_key(info):
    mode = SETTINGS.get("process_sort", "memory")
    if mode == "cpu": return -(info.get("cpu_percent") or 0)
    if mode == "pid": return info.get("pid") or 0
    return -(info.get("memory_percent") or 0)

def timed_key(win):
    win.timeout(max(250, int(1000 * SETTINGS.get("refresh_rate", 1))))
    try: key = win.getch()
    finally: win.timeout(-1)
    return key

def status_bar(win):
    # No persistent bottom bar in VTOS 2.0; app-local hints are drawn by each app.
    return

def calendar_app(win):
    today=datetime_module.date.today(); shown=today.replace(day=1); selected_day=today.day
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," CALENDAR ",accent())
        sunday_first=SETTINGS.get("week_start","monday")=="sunday"
        calendar_module.setfirstweekday(6 if sunday_first else 0)
        center(win,2,shown.strftime("%B %Y"),accent()); center(win,4,"Su Mo Tu We Th Fr Sa" if sunday_first else "Mo Tu We Th Fr Sa Su",5)
        weeks=calendar_module.monthcalendar(shown.year,shown.month)
        for r,week in enumerate(weeks):
            y=6+r
            if y>=h-5: break
            x=max(2,(w-20)//2)
            for c,d in enumerate(week):
                if d:
                    col=2 if (shown.year==today.year and shown.month==today.month and d==today.day) else (accent() if d==selected_day else 1)
                    safe_add(win,y,x+c*3,f"{d:2}",col)
        center(win,h-5,f"Selected: {shown.replace(day=selected_day).strftime('%d.%m.%Y')} | Today: {today.strftime('%d.%m.%Y')}",4)
        center(win,h-3,"←/→ month  ↑/↓ week  t today  q exit",5)
        status_bar(win); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        if key in (curses.KEY_LEFT,ord('h')): shown=(shown-datetime_module.timedelta(days=1)).replace(day=1); selected_day=min(selected_day,calendar_module.monthrange(shown.year,shown.month)[1])
        elif key in (curses.KEY_RIGHT,ord('l')): shown=(shown+datetime_module.timedelta(days=32)).replace(day=1); selected_day=min(selected_day,calendar_module.monthrange(shown.year,shown.month)[1])
        elif key==ord('t'): shown=today.replace(day=1); selected_day=today.day
        elif key==curses.KEY_UP: selected_day=max(1,selected_day-7)
        elif key==curses.KEY_DOWN: selected_day=min(calendar_module.monthrange(shown.year,shown.month)[1],selected_day+7)

def process_manager(win):
    if not psutil:
        win.erase(); center(win,4,"Install python3-psutil",5); wait_key(win); return
    selected=0; offset=0
    while True:
        win.erase(); h,w=win.getmaxyx()
        safe_add(win,0,2," PROCESS MANAGER ",accent()); safe_add(win,1,2,"↑↓ select | k terminate | PgUp/PgDn scroll | q exit",5)
        procs=[]
        for proc in psutil.process_iter(["pid","name","memory_percent","cpu_percent"]):
            try: procs.append(proc.info)
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        procs.sort(key=process_sort_key)
        selected=min(selected,max(0,len(procs)-1)); visible=max(1,h-5)
        offset=max(0,min(offset,max(0,len(procs)-visible)))
        if selected<offset: offset=selected
        if selected>=offset+visible: offset=selected-visible+1
        safe_add(win,2,2,f"{'PID':>7} {'PROCESS':<27} {'CPU':>7} {'RAM':>7}",accent())
        for i,p in enumerate(procs[offset:offset+visible]):
            idx=i+offset
            line=f"{p.get('pid',0):>7} {str(p.get('name') or '?')[:27]:<27} {p.get('cpu_percent') or 0:6.1f}% {p.get('memory_percent') or 0:6.1f}%"
            safe_add(win,3+i,2,line,2 if idx==selected else 1)
        status_bar(win); win.refresh(); key=timed_key(win)
        if key in (ord("q"),27): return
        elif key==curses.KEY_UP: selected=max(0,selected-1)
        elif key==curses.KEY_DOWN: selected=min(max(0,len(procs)-1),selected+1)
        elif key==curses.KEY_NPAGE: selected=min(max(0,len(procs)-1),selected+visible)
        elif key==curses.KEY_PPAGE: selected=max(0,selected-visible)
        elif key==ord("k") and procs:
            p=procs[selected]
            if SETTINGS.get("confirm_kill",True):
                safe_add(win,h-2,2,f"Terminate {p['name']} PID {p['pid']}? y/N",6); win.refresh()
                confirmed=win.getch() in (ord("y"),ord("Y"))
            else: confirmed=True
            if confirmed:
                try: psutil.Process(p["pid"]).terminate()
                except Exception as e: safe_add(win,h-2,2,str(e)[:w-4],6); win.refresh(); time.sleep(1)

def disk_usage_app(win):
    offset=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," DISK & APPLICATION STORAGE ",accent())
        rows=[]
        try:
            for part in (psutil.disk_partitions(all=False) if psutil else []):
                try:
                    d=psutil.disk_usage(part.mountpoint)
                    # Same layout, bar length and colors as DISK in SYSTEM MONITOR.
                    rows.append((f"DISK     {d.percent:5.1f}%  {bar(d.percent, 100)}", "", 5))
                    rows.append((f"         {d.used / 1024**3:.1f} / {d.total / 1024**3:.1f} GB", "", 1))
                    rows.append(("", "", 1))
                except (PermissionError,OSError): continue
        except Exception: pass
        rows += [("INSTALLED PACKAGE SIZE (apt/dpkg)", "", 1)]
        if shutil.which("dpkg-query"):
            try:
                output=subprocess.check_output(["dpkg-query","-W","-f=${Installed-Size}\t${binary:Package}\n"],text=True,stderr=subprocess.DEVNULL)
                packages=[]
                for line in output.splitlines():
                    bits=line.split("\t",1)
                    if len(bits)==2:
                        try: packages.append((int(bits[0]),bits[1]))
                        except ValueError: pass
                packages.sort(reverse=True)
                rows += [(f"{size/1024:7.1f} MiB  {name}", "", 1) for size,name in packages[:int(SETTINGS.get("package_list",100))]]
            except Exception: rows.append(("Unable to read dpkg package sizes", "", 1))
        else: rows.append(("dpkg-query not found", "", 1))
        visible=max(1,h-4); offset=max(0,min(offset,max(0,len(rows)-visible)))
        for i,row in enumerate(rows[offset:offset+visible]):
            line,_,row_color=row
            safe_add(win,2+i,2,line[:w-4],row_color)
        safe_add(win,h-1,2,"↑↓ scroll | PgUp/PgDn | q return",5); win.refresh(); key=timed_key(win)
        if key in (ord("q"),27): return
        elif key==curses.KEY_UP: offset=max(0,offset-1)
        elif key==curses.KEY_DOWN: offset=min(max(0,len(rows)-visible),offset+1)
        elif key==curses.KEY_NPAGE: offset=min(max(0,len(rows)-visible),offset+visible)
        elif key==curses.KEY_PPAGE: offset=max(0,offset-visible)


def text_editor(win):
    raw=prompt(win,"File path: ").strip()
    if not raw: return
    path=Path(raw).expanduser()
    if not path.is_absolute(): path=Path.cwd()/path
    try: lines=path.read_text(encoding="utf-8",errors="replace").splitlines() if path.exists() else [""]
    except Exception as e:
        win.erase(); center(win,4,f"Cannot open: {e}",6); wait_key(win); return
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2,f" TEXT EDITOR — {path.name} ",accent())
        for i,line in enumerate(lines[:max(1,h-5)]): safe_add(win,2+i,2,line[:w-4],1)
        safe_add(win,h-2,2,"a append line | s save | q exit",5); status_bar(win); win.refresh()
        key=timed_key(win)
        if key in (ord("q"),27): return
        elif key==ord("a"): lines.append(prompt(win,"Text: "))
        elif key==ord("s"):
            try:
                path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(lines)+"\n",encoding="utf-8")
                safe_add(win,h-2,2,"Saved.",4); win.refresh(); time.sleep(.5)
            except Exception as e: safe_add(win,h-2,2,f"Save error: {e}"[:w-4],6); win.refresh(); time.sleep(1)

def file_search(win):
    query=prompt(win,"Filename contains: ").strip()
    if not query: return
    found=[]
    for base,dirs,files in os.walk(Path.cwd()):
        dirs[:]=[d for d in dirs if d not in {".git","__pycache__",".cache"}]
        for name in dirs+files:
            if query.casefold() in name.casefold():
                found.append(str(Path(base)/name))
                if len(found)>=300: break
        if len(found)>=300: break
    text_viewer(win,"FILE SEARCH","\n".join(found) if found else "No matches found.")


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────

def dashboard(win):
    logo_art = [
        '                           █████          █████          ',
        '                                                         ',
        '                           █████             █████       ',
        '                                                         ',
        '█████        █████  ██████████████████          █████    ',
        '                                                         ',
        '  █████     █████          █████                    █████',
        '                                                         ',
        '   █████  █████            █████                █████    ',
        '                                                         ',
        '     ████████              █████             █████       ',
        '                                                         ',
        '       █████                ██████████    █████          ',
    ]
    base=1+len(logo_art)
    try:
        win.keypad(True)
    except Exception:
        pass
    offset=0
    while True:
        win.erase(); h,w=win.getmaxyx()
        for row, art_line in enumerate(logo_art): center(win,1+row,art_line,accent())
        center(win,base+2,f"Vibecoded Terminal Operating System | Version {VERSION}",accent())
        try: win.hline(base+4,2,curses.ACS_HLINE,w-4)
        except curses.error: pass
        full_details=SETTINGS.get("dashboard_extra",True)
        content=["", "— ABOUT SYSTEM —",
            f"User: {os.getenv('USER','user')}",
            f"Host: {platform.node()}"]
        if full_details:
            content += [f"OS / Distribution: {platform.platform()}",
                f"Architecture: {platform.machine()}"]
        content += [f"Python: {platform.python_version()}"]
        if full_details:
            content += [f"Shell: {os.getenv('SHELL','unknown')}",
                f"Terminal: {os.getenv('TERM','unknown')}",
                f"Current directory: {Path.cwd()}"]
        if psutil:
            content += [f"CPU: {platform.processor() or 'Unknown'} | {psutil.cpu_count(logical=False) or '?'} physical / {psutil.cpu_count() or '?'} logical",
                f"RAM installed: {psutil.virtual_memory().total/1024**3:.2f} GB"]
        try:
            du=shutil.disk_usage('/')
            content += [f"Root disk: {du.used/1024**3:.1f} GB used / {du.total/1024**3:.1f} GB total"]
        except Exception: pass
        content += ["", "GitHub: https://github.com/andischeee/vt-OS.py"]
        top=base+6
        available=max(1,h-top-2)
        max_offset=max(0,len(content)-available)
        offset=max(0,min(offset,max_offset))
        for i,line in enumerate(content[offset:offset+available]):
            safe_add(win,top+i,3,line,accent() if line.startswith("—") or line.startswith("GitHub:") else 1)
        safe_add(win,h-2,2,"↑↓ scroll | PgUp/PgDn | q / ESC return",5)
        win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: offset=max(0,offset-1)
        elif key==curses.KEY_DOWN: offset=min(max_offset,offset+1)
        elif key==curses.KEY_NPAGE: offset=min(max_offset,offset+available)
        elif key==curses.KEY_PPAGE: offset=max(0,offset-available)


# ─────────────────────────────────────────────
# File manager
# ─────────────────────────────────────────────

def file_manager(win):
    current = Path.cwd()
    selected = 0
    scroll = 0

    while True:
        win.erase()
        h, w = win.getmaxyx()

        safe_add(win, 0, 2, " FILE MANAGER ", accent())
        safe_add(win, 1, 2, str(current), 5)

        try:
            items = sorted(
                current.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except (PermissionError, OSError):
            items = []

        if not SETTINGS.get("show_hidden", False):
            items = [p for p in items if not p.name.startswith(".")]

        entries = [Path("..")] + items
        selected = max(0, min(selected, len(entries) - 1))

        list_height = max(1, h - 5)

        if selected >= scroll + list_height:
            scroll = selected - list_height + 1
        if selected < scroll:
            scroll = selected

        for i, item in enumerate(entries[scroll:scroll + list_height]):
            idx = i + scroll
            y = 3 + i

            if item.name == "..":
                name = "↰  Parent directory"
                is_dir = True
            else:
                is_dir = item.is_dir()
                if SETTINGS.get("file_icons", True):
                    name = ("📁 " if is_dir else "📄 ") + item.name
                else:
                    name = item.name + ("/" if is_dir else "")

            color = 2 if idx == selected else (accent() if is_dir else 1)
            safe_add(win, y, 2, name, color)

        safe_add(win, h - 2, 2,
                 "↑↓ Navigate  ENTER Open  BACKSPACE Up  q Exit", 5)

        status_bar(win)

        win.refresh()
        key = timed_key(win)

        if key == 27:
            return
        elif key == ord("q"):
            return None

        elif key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)

        elif key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(entries) - 1, selected + 1)

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            current = current.parent
            selected = 0
            scroll = 0

        elif key in (10, 13, curses.KEY_ENTER):
            item = entries[selected]

            if item.name == "..":
                current = current.parent
                selected = 0
                scroll = 0
                continue

            target = current / item

            if target.is_dir():
                current = target
                selected = 0
                scroll = 0

            else:
                try:
                    if target.stat().st_size > 2_000_000:
                        run_external(win, f"less {shlex_quote(str(target))}")
                    else:
                        text = target.read_text(errors="replace")
                        text_viewer(win, target.name, text)
                except Exception as e:
                    win.erase()
                    center(win, 5, f"Cannot open file: {e}", 6)
                    wait_key(win)


def shlex_quote(text):
    import shlex
    return shlex.quote(text)


# ─────────────────────────────────────────────
# Text viewer
# ─────────────────────────────────────────────

def text_viewer(win, title, text):
    lines = text.splitlines() or [""]
    offset = 0

    while True:
        win.erase()
        h, w = win.getmaxyx()

        safe_add(win, 0, 2, f" {title} ", accent())

        visible = max(1, h - 4)

        for i, line in enumerate(lines[offset:offset + visible]):
            safe_add(win, 2 + i, 1, line[:w - 2], 1)

        safe_add(win, h - 1, 2, "↑↓ Scroll  PgUp/PgDn  q Close", 5)
        status_bar(win)
        win.refresh()

        key = timed_key(win)

        if key in (ord("q"), 27):
            return
        elif key in (curses.KEY_UP, ord("k")):
            offset = max(0, offset - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            offset = min(max(0, len(lines) - visible), offset + 1)
        elif key == curses.KEY_NPAGE:
            offset = min(max(0, len(lines) - visible), offset + visible)
        elif key == curses.KEY_PPAGE:
            offset = max(0, offset - visible)


# ─────────────────────────────────────────────
# System monitor
# ─────────────────────────────────────────────

def system_monitor(win):
    process_offset=0
    while True:
        win.erase()
        h, w = win.getmaxyx()

        safe_add(win, 0, 2, " SYSTEM MONITOR ", accent())
        safe_add(win, 1, 2, f"Refresh: {SETTINGS.get('refresh_rate', 1)} sec | ↑↓ scroll processes | q: exit", 5)

        if psutil:
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            swap = psutil.swap_memory()

            safe_add(win, 3, 2, f"CPU      {cpu:5.1f}%  {bar(cpu, 100)}", 4)
            safe_add(win, 5, 2,
                     f"RAM      {memory.percent:5.1f}%  "
                     f"{bar(memory.percent, 100)}", 3)

            safe_add(win, 6, 2,
                     f"         {memory.used / 1024**3:.2f} / "
                     f"{memory.total / 1024**3:.2f} GB", 1)

            safe_add(win, 8, 2,
                     f"DISK     {disk.percent:5.1f}%  "
                     f"{bar(disk.percent, 100)}", 5)

            safe_add(win, 9, 2,
                     f"         {disk.used / 1024**3:.1f} / "
                     f"{disk.total / 1024**3:.1f} GB", 1)

            safe_add(win, 11, 2,
                     f"SWAP     {swap.percent:5.1f}%  "
                     f"{bar(swap.percent, 100)}", 7)

            safe_add(win, 13, 2, "TOP PROCESSES", 3)

            try:
                processes = sorted(
                    psutil.process_iter(
                        ["pid", "name", "memory_percent", "cpu_percent"]
                    ),
                    key=lambda p: process_sort_key(p.info)
                )

                visible=max(1,h-17); process_offset=max(0,min(process_offset,max(0,len(processes)-visible)))
                for i, p in enumerate(processes[process_offset:process_offset+visible]):
                    info = p.info
                    name = (info["name"] or "?")[:24]
                    safe_add(
                        win, 14 + i, 2,
                        f"{info['pid']:>6} {name:<25} "
                        f"RAM {info['memory_percent'] or 0:5.1f}%  "
                        f"CPU {info['cpu_percent'] or 0:5.1f}%",
                        1
                    )

            except Exception:
                pass

        else:
            center(win, 5, "Install python3-psutil for monitoring", 5)

        status_bar(win)

        win.refresh()
        win.timeout(max(250, int(1000 * SETTINGS.get("refresh_rate", 1))))
        key = win.getch()
        win.timeout(-1)
        win.timeout(-1)

        if key in (ord("q"), 27):
            return
        elif key==curses.KEY_DOWN: process_offset+=1
        elif key==curses.KEY_UP: process_offset=max(0,process_offset-1)
        elif key==curses.KEY_NPAGE: process_offset+=max(1,h-17)
        elif key==curses.KEY_PPAGE: process_offset=max(0,process_offset-max(1,h-17))


# ─────────────────────────────────────────────
# Network tools
# ─────────────────────────────────────────────

def monitor_hub(win):
    modes = [("System Monitor", system_monitor), ("Process Manager", process_manager), ("Disk & Installed Apps", disk_usage_app)]
    selected = 0
    while True:
        win.erase(); h,w=win.getmaxyx()
        safe_add(win,0,2," SYSTEM CENTER ",accent())
        safe_add(win,2,2,"←→ select module | ENTER open | q return",5)
        for i,(name,fn) in enumerate(modes):
            pointer_line(win,4+i,3,name,i==selected)
        status_bar(win); win.refresh()
        key=timed_key(win)
        if key in (ord("q"),27): return
        if key in (curses.KEY_LEFT,curses.KEY_UP): selected=(selected-1)%len(modes)
        elif key in (curses.KEY_RIGHT,curses.KEY_DOWN): selected=(selected+1)%len(modes)
        elif key in (10,13,curses.KEY_ENTER): modes[selected][1](win)

def games_app(win):
    try: win.keypad(True)
    except Exception: pass
    games=[("Snake",snake_app),("2048",game_2048)]
    selected=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," GAMES ",accent())
        safe_add(win,2,2,"↑↓ select | ENTER play | q return",5)
        for i,(name,fn) in enumerate(games): pointer_line(win,4+i,3,name,i==selected)
        safe_add(win,h-2,2,"VTOS Games",5); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: selected=max(0,selected-1)
        elif key==curses.KEY_DOWN: selected=min(len(games)-1,selected+1)
        elif key in (10,13,curses.KEY_ENTER) and games[selected][1]: games[selected][1](win)


def snake_app(win):
    import random
    try: win.keypad(True)
    except Exception: pass
    h,w=win.getmaxyx()
    presets=[("Small",22,10),("Medium",32,14),("Large",min(48,w-8),min(20,h-9))]
    selected=0; field_idx=1; speed_idx=1; food_idx=0
    speeds=[150,115,85,60]; food_counts=[1,2,3]
    record_file=DATA/"snake_record.json"
    try: record=int(json.loads(record_file.read_text()).get("record",0))
    except Exception: record=0
    def settings_menu():
        nonlocal selected,field_idx,speed_idx,food_idx
        while True:
            win.erase(); safe_add(win,0,2," SNAKE SETTINGS ",accent())
            opts=[("Field size",presets[field_idx][0]),("Speed",["Slow","Normal","Fast","Very fast"][speed_idx]),("Food count",str(food_counts[food_idx])),("Start game","ENTER")]
            for i,(label,value) in enumerate(opts): safe_add(win,4+i,3,f"{label:<16}: {value}",2 if i==selected else 1)
            safe_add(win,h-2,2,"↑↓ choose option | ←→ adjust | ENTER start | q games menu",5); win.refresh(); k=timed_key(win)
            if k in (ord('q'),27): return False
            if k==curses.KEY_UP: selected=max(0,selected-1)
            elif k==curses.KEY_DOWN: selected=min(3,selected+1)
            elif k in (curses.KEY_LEFT,curses.KEY_RIGHT):
                direction=-1 if k==curses.KEY_LEFT else 1
                if selected==0: field_idx=(field_idx+direction)%len(presets)
                elif selected==1: speed_idx=(speed_idx+direction)%len(speeds)
                elif selected==2: food_idx=(food_idx+direction)%len(food_counts)
            elif k in (10,13,curses.KEY_ENTER) and selected==3: return True
    while settings_menu():
        _,field_w,field_h=presets[field_idx]
        field_w=max(14,min(field_w,w-8)); field_h=max(8,min(field_h,h-9))
        def make_food(body, foods):
            free=[(yy,xx) for yy in range(1,field_h-1) for xx in range(1,field_w-1) if (yy,xx) not in body]
            random.shuffle(free); return free[:foods]
        snake=[(field_h//2,field_w//2),(field_h//2,field_w//2-1),(field_h//2,field_w//2-2)]
        direction=(0,1); foods=make_food(snake,food_counts[food_idx]); score=0; gameover=False
        while not gameover:
            win.erase(); safe_add(win,0,2," SNAKE ",accent()); safe_add(win,1,2,f"Score {score} | Record {record} | ←↑↓→ move | q quit",5)
            # Visible enclosure: + corners, - horizontal edges, | vertical edges.
            safe_add(win,3,3,"+"+"-"*(field_w-2)+"+",accent())
            safe_add(win,3+field_h-1,3,"+"+"-"*(field_w-2)+"+",accent())
            for yy in range(1,field_h-1):
                safe_add(win,3+yy,3,"|",accent())
                safe_add(win,3+yy,3+field_w-1,"|",accent())
            for yy,xx in snake: safe_add(win,3+yy,3+xx,"█",accent())
            for yy,xx in foods: safe_add(win,3+yy,3+xx,"●",5)
            win.refresh(); win.timeout(int(speeds[speed_idx]*(1.65 if direction[0] else 1.0))); k=win.getch(); win.timeout(-1)
            if k in (ord('q'),27): gameover=True; break
            dirs={curses.KEY_UP:(-1,0),curses.KEY_DOWN:(1,0),curses.KEY_LEFT:(0,-1),curses.KEY_RIGHT:(0,1)}
            if k in dirs and dirs[k]!=( -direction[0],-direction[1]): direction=dirs[k]
            head=(snake[0][0]+direction[0],snake[0][1]+direction[1]); eating=head in foods
            hit=head[0]<=0 or head[0]>=field_h-1 or head[1]<=0 or head[1]>=field_w-1 or head in (snake if eating else snake[:-1])
            if hit:
                gameover=True
                break
            snake.insert(0,head)
            if eating:
                score+=10; foods.remove(head)
                if not foods: foods=make_food(snake,food_counts[food_idx])
                if score>record:
                    record=score
                    try: record_file.write_text(json.dumps({"record":record}),encoding="utf-8")
                    except Exception: pass
            else: snake.pop()
        if score>record: record=score
        win.erase(); center(win,4,"GAME OVER" if score else "GAME ENDED",6); center(win,6,f"Score: {score} | Record: {record}",5)
        center(win,8,"ENTER — restart with settings | q — games menu",1); win.refresh()
        while True:
            k=timed_key(win)
            if k in (ord('q'),27): break
            if k in (10,13,curses.KEY_ENTER): break
        if k in (ord('q'),27): break


def game_2048(win):
    import random
    size=4; board=[[0]*size for _ in range(size)]; score=0
    def spawn():
        empty=[(r,c) for r in range(size) for c in range(size) if not board[r][c]]
        if empty:
            r,c=random.choice(empty); board[r][c]=4 if random.random()<0.1 else 2
    def move(direction):
        nonlocal score
        changed=False
        for i in range(size):
            line=[board[i][j] for j in range(size)] if direction in ('left','right') else [board[j][i] for j in range(size)]
            if direction in ('right','down'): line.reverse()
            compact=[v for v in line if v]; merged=[]; j=0
            while j<len(compact):
                if j+1<len(compact) and compact[j]==compact[j+1]: merged.append(compact[j]*2); score+=compact[j]*2; j+=2
                else: merged.append(compact[j]); j+=1
            merged += [0]*(size-len(merged))
            if direction in ('right','down'): merged.reverse()
            old=[board[i][j] for j in range(size)] if direction in ('left','right') else [board[j][i] for j in range(size)]
            if merged!=old: changed=True
            if direction in ('left','right'):
                board[i]=merged
            else:
                for j,v in enumerate(merged): board[j][i]=v
        return changed
    spawn(); spawn()
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," 2048 ",accent()); safe_add(win,1,2,f"Score {score} | Arrow keys move | q exit",5)
        for r in range(size):
            for c in range(size):
                val=board[r][c]; safe_add(win,4+r*3, max(2,(w-25)//2+c*7),f"{val or '.':^5}",accent() if val>=128 else 2 if val else 1)
        safe_add(win,h-2,2,"Merge identical tiles to reach 2048",5); win.refresh(); k=timed_key(win)
        if k in (ord('q'),27): return
        dirs={curses.KEY_LEFT:'left',curses.KEY_RIGHT:'right',curses.KEY_UP:'up',curses.KEY_DOWN:'down'}
        if k in dirs and move(dirs[k]): spawn()


def network_app(win):
    options=[("Network configuration (nmtui)","nmtui"),("Ping Google","ping -c 4 google.com"),("Show IP addresses","ip addr"),("Routing table","ip route"),("Internet connectivity test","curl -I --max-time 5 https://google.com"),("DNS lookup","getent hosts example.com")]
    selected=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," NETWORK ",accent())
        try: host=socket.gethostname(); ip=socket.gethostbyname(host)
        except Exception: host,ip="Unknown","Unavailable"
        safe_add(win,2,3,f"Hostname: {host}",4); safe_add(win,3,3,f"Local IP: {ip}",3)
        for i,(name,cmd) in enumerate(options): pointer_line(win,6+i,3,name,i==selected)
        safe_add(win,h-2,2,"↑↓/←→ select | ENTER run | q return",5)
        status_bar(win); win.refresh(); key=timed_key(win)
        if key in (ord("q"),27): return
        if key in (curses.KEY_UP,curses.KEY_LEFT): selected=(selected-1)%len(options)
        elif key in (curses.KEY_DOWN,curses.KEY_RIGHT): selected=(selected+1)%len(options)
        elif key in (10,13,curses.KEY_ENTER): run_external(win,options[selected][1])

_ALLOWED_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

def safe_calculate(expression):
    import math
    tree = ast.parse(expression, mode="eval")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)

        if isinstance(node, ast.Constant) and isinstance(
                node.value, (int, float)):
            return node.value

        if isinstance(node, ast.BinOp):
            op = _ALLOWED_OPERATORS.get(type(node.op))
            if not op:
                raise ValueError("Operator not allowed")
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > 100:
                    raise ValueError("Power too large")
                # Bound the size of the result, not only the exponent (nested powers froze the app).
                if isinstance(left, int) and isinstance(right, int) and right > 0 and abs(left).bit_length() * right > 14000:
                    raise ValueError("Result too large")
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = _ALLOWED_OPERATORS.get(type(node.op))
            if not op:
                raise ValueError("Operator not allowed")
            return op(evaluate(node.operand))

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            funcs={"sqrt":math.sqrt,"sin":math.sin,"cos":math.cos,"tan":math.tan,
                   "asin":math.asin,"acos":math.acos,"atan":math.atan,"log":math.log,
                   "log10":math.log10,"ln":math.log,"abs":abs,"round":round,
                   "ceil":math.ceil,"floor":math.floor,"factorial":math.factorial}
            fn=funcs.get(node.func.id)
            if fn is None or node.keywords: raise ValueError("Function not allowed")
            args=[evaluate(a) for a in node.args]
            if node.func.id=="factorial" and (not args or args[0]<0 or int(args[0])!=args[0] or args[0]>100): raise ValueError("factorial expects integer 0..100")
            return fn(*args)
        if isinstance(node, ast.Name) and node.id in ("pi","e"):
            return math.pi if node.id=="pi" else math.e
        raise ValueError("Invalid expression")

    return evaluate(tree)


def calculator(win):
    history = []

    while True:
        win.erase()
        h, w = win.getmaxyx()

        safe_add(win, 0, 2, " CALCULATOR ", accent())
        safe_add(win, 2, 2, "+ | - | * | / | // | % | **   ||   sqrt | sin | cos | tan | asin | acos | atan | log | ln | abs | round | ceil | floor | factorial   ||   pi | e", 5)

        for i, item in enumerate(history[-8:]):
            safe_add(win, 4 + i, 2, item, 1)

        expression = prompt(win, "Expression (q to exit): ")

        if expression.lower() == "q":
            return

        if not expression.strip():
            continue

        try:
            result = safe_calculate(expression)
            history.append(f"{expression} = {result}")
        except Exception as e:
            history.append(f"{expression} → Error: {e}")


# ─────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────

def notes_app(win):
    while True:
        win.erase()
        h, w = win.getmaxyx()

        safe_add(win, 0, 2, " VTOS NOTES ", accent())

        try:
            content = NOTES.read_text(errors="replace")
        except Exception:
            content = ""

        lines = content.splitlines()

        for i, line in enumerate(lines[:h - 5]):
            safe_add(win, 2 + i, 2, line[:w - 4], 1)

        safe_add(win, h - 2, 2,
                 "a Add line | c Clear | q Exit", 5)

        status_bar(win)

        win.refresh()
        key = timed_key(win)

        if key == ord("q"):
            return

        elif key == ord("a"):
            new_line = prompt(win, "Write note: ")
            if new_line:
                with NOTES.open("a", encoding="utf-8") as f:
                    f.write(new_line + "\n")

        elif key == ord("c"):
            safe_add(win, h - 3, 2, "Clear notes? y/N", 6)
            status_bar(win)
            win.refresh()

            if win.getch() in (ord("y"), ord("Y")):
                NOTES.write_text("", encoding="utf-8")


# ─────────────────────────────────────────────
# Application launcher
# ─────────────────────────────────────────────

APP_CONFIG=CONFIG/"apps.json"
DEFAULT_APPS=[("Firefox","firefox"),("Chromium","chromium"),("File manager","xdg-open ~"),("Text editor","xed"),("LibreOffice","libreoffice"),("VLC","vlc"),("Steam","steam"),("Terminal","x-terminal-emulator")]
def apps_app(win):
    try: options=json.loads(APP_CONFIG.read_text(encoding="utf8"))
    except Exception: options=[list(x) for x in DEFAULT_APPS]
    selected=0; offset=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," APPLICATIONS ",accent()); safe_add(win,2,2,"↑↓ select | ENTER launch | a add | d delete | q return",5)
        visible=max(1,h-8); offset=max(0,min(offset, max(0,len(options)-visible)))
        for i,(name,cmd) in enumerate(options[offset:offset+visible]):
            idx=i+offset; pointer_line(win,4+i,2,name,idx==selected)
        safe_add(win,h-3,2,f"{len(options)} apps | {selected+1 if options else 0}/{len(options)}",4); status_bar(win); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        if key==curses.KEY_UP: selected=max(0,selected-1); offset=max(0,offset-1 if selected<offset else offset)
        elif key==curses.KEY_DOWN: selected=min(len(options)-1,selected+1) if options else 0; offset=selected if selected>=offset+visible else offset
        elif key in (10,13,curses.KEY_ENTER) and options: run_external(win,options[selected][1])
        elif key==ord('a'):
            name=prompt(win,"Application name: ").strip(); cmd=prompt(win,"Command: ").strip()
            if name and cmd: options.append([name,cmd]); APP_CONFIG.write_text(json.dumps(options,indent=2),encoding="utf8"); selected=len(options)-1
        elif key==ord('d') and options:
            if prompt(win,f"Delete {options[selected][0]}? y/N: ").lower()=='y': options.pop(selected); selected=min(selected,max(0,len(options)-1)); APP_CONFIG.write_text(json.dumps(options,indent=2),encoding="utf8")

def stopwatch_app(win):
    try: win.keypad(True)
    except Exception: pass
    running=False; started=0.0; elapsed=0.0
    while True:
        win.erase(); h,w=win.getmaxyx(); now=time.monotonic()
        current=elapsed+(now-started if running else 0)
        hours=int(current//3600); mins=int((current%3600)//60); secs=int(current%60); millis=int((current-int(current))*1000)
        safe_add(win,0,2," STOPWATCH ",accent()); center(win,4,f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}",accent())
        center(win,7,"s start/stop | r reset | q return",5); win.refresh()
        win.timeout(30 if running else max(250,int(1000*SETTINGS.get("refresh_rate",1))))
        try: k=win.getch()
        finally: win.timeout(-1)
        if k in (ord('q'),27): return
        elif k==ord('s'):
            if running: elapsed+=now-started; running=False
            else: started=now; running=True
        elif k==ord('r'): elapsed=0; started=now if running else 0


def shell_app(win):
    run_external(win, os.environ.get("SHELL", "/bin/bash"))


# ─────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────

SETTING_CATEGORIES=[
    ("APPEARANCE",[("Theme","theme"),("Clock face style","clock_style"),("Desktop system details","dashboard_extra"),("File manager icons","file_icons")]),
    ("TIME & DATE",[("Clock format","time_format"),("Show seconds","show_seconds"),("Date format","date_format"),("Timezone","timezone"),("System time","system_time"),("Calendar week starts","week_start")]),
    ("PERFORMANCE",[("Refresh interval","refresh_rate"),("Process sort","process_sort"),("Package list size","package_list")]),
    ("FILES",[("Show hidden files","show_hidden")]),
    ("SAFETY",[("Lock password","lock_password"),("Confirm external commands","confirm_external"),("Confirm process kill","confirm_kill")]),
    ("MAINTENANCE",[("Reset settings","reset")]),
]

SETTING_HELP={
    "theme":"Accent color for highlights, borders, bars and the clock.",
    "clock_style":"Big clock on the main menu and lock screen: Blocks (█) or Slashes ( _ - \\ / . | ).",
    "dashboard_extra":"On: full About System on Desktop. Off: only user, host, Python, CPU, RAM, disk.",
    "file_icons":"On: 📁/📄 icons in File Manager. Off: plain names, folders end with /.",
    "time_format":"24h (14:30) or 12h (02:30 PM) clock in the top bar and apps.",
    "show_seconds":"Show or hide seconds in the clock.",
    "date_format":"Date style in the top bar (e.g. 27.11.2026, 2026-11-27, full weekday).",
    "timezone":"Timezone used for VTOS clocks only; the Linux system time stays the same.",
    "system_time":"Set the Linux system clock manually (runs sudo timedatectl).",
    "week_start":"First day of the week in Calendar: Monday or Sunday.",
    "refresh_rate":"How often screens refresh, in seconds. Lower = smoother, more CPU.",
    "process_sort":"Order of processes in System Monitor and Process Manager.",
    "package_list":"How many of the largest installed packages Disk shows.",
    "show_hidden":"Show files and folders starting with a dot in File Manager.",
    "lock_password":"Password for the lock screen. ENTER creates one (typed twice) or removes it (asks for the current password).",
    "confirm_external":"Ask y/N before running external commands (apps, ping, shell).",
    "confirm_kill":"Ask y/N before terminating a process in Process Manager.",
    "reset":"Restore every setting to its default value (asks for confirmation).",
}


def settings_app(win):
    global theme_name
    choices=[]; rows=[]
    for category,items in SETTING_CATEGORIES:
        rows.append(("header",category)); rows.append(("blank",None))
        for label,keyname in items:
            choices.append((label,keyname)); rows.append(("setting",len(choices)-1)); rows.append(("help",len(choices)-1)); rows.append(("blank",None))
    scroll=0
    selected=0
    notice=None
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," SETTINGS ",accent())
        values={"theme":theme_name,"time_format":SETTINGS["time_format"],"date_format":SETTINGS["date_format"],"timezone":SETTINGS["timezone"],"refresh_rate":f'{SETTINGS["refresh_rate"]} sec',"show_seconds":"On" if SETTINGS.get("show_seconds",True) else "Off","system_time":"Set manually (sudo)","confirm_external":"On" if SETTINGS.get("confirm_external",True) else "Off","dashboard_extra":"On" if SETTINGS.get("dashboard_extra",True) else "Off",
                "show_hidden":"On" if SETTINGS.get("show_hidden",False) else "Off","file_icons":"On" if SETTINGS.get("file_icons",True) else "Off",
                "process_sort":{"memory":"RAM","cpu":"CPU","pid":"PID"}.get(SETTINGS.get("process_sort","memory"),"RAM"),"confirm_kill":"On" if SETTINGS.get("confirm_kill",True) else "Off",
                "week_start":"Sunday" if SETTINGS.get("week_start","monday")=="sunday" else "Monday","package_list":f'{SETTINGS.get("package_list",100)} packages',"reset":"ENTER to reset","lock_password":"Set" if lock_password_exists() else "Not set","clock_style":"Slashes" if SETTINGS.get("clock_style","blocks")=="slashes" else "Blocks"}
        visible=max(3,h-7)
        sel_row=next(r for r,(kind,val) in enumerate(rows) if kind=="setting" and val==selected)
        top_row=sel_row-2 if sel_row>=2 and rows[sel_row-2][0]=="header" else sel_row
        if top_row<scroll: scroll=top_row
        if sel_row+2>scroll+visible: scroll=sel_row+2-visible
        scroll=max(0,min(scroll,max(0,len(rows)-visible)))
        for r in range(scroll,min(len(rows),scroll+visible)):
            y=3+r-scroll; kind,val=rows[r]
            if kind=="header": safe_add(win,y,2,f"─ {val} ─",accent())
            elif kind=="setting":
                label,keyname=choices[val]; safe_add(win,y,4,f"{label:<26}: {values[keyname]}",2 if val==selected else 1)
            elif kind=="help": safe_add(win,y,6,SETTING_HELP.get(choices[val][1],""),accent())
        if scroll>0: safe_add(win,2,w-4,"▲",accent())
        if scroll+visible<len(rows): safe_add(win,3+visible,w-4,"▼",accent())
        safe_add(win,h-3,2,"↑↓ select | ←→ / Enter change | q return",5)
        if notice: safe_add(win,h-4,2,notice[0][:max(0,w-8)],notice[1])
        win.refresh(); key=timed_key(win)
        if key!=-1: notice=None
        if key in (ord("q"),27): return
        if key==curses.KEY_UP: selected=max(0,selected-1); continue
        if key==curses.KEY_DOWN: selected=min(len(choices)-1,selected+1); continue
        if key not in (curses.KEY_LEFT,curses.KEY_RIGHT,10,13,curses.KEY_ENTER): continue
        name=choices[selected][1]
        direction=-1 if key==curses.KEY_LEFT else 1
        if name=="theme":
            vals=list(THEMES); idx=vals.index(theme_name); theme_name=vals[(idx+direction)%len(vals)]; SETTINGS["theme"]=theme_name; refresh_theme_pairs()
        elif name=="time_format": SETTINGS["time_format"]="12h" if SETTINGS["time_format"]=="24h" else "24h"
        elif name=="date_format":
            vals=["%d.%m.%Y","%Y-%m-%d","%m/%d/%Y","%A, %d %B %Y"]; idx=vals.index(SETTINGS["date_format"]) if SETTINGS["date_format"] in vals else 0; SETTINGS["date_format"]=vals[(idx+direction)%len(vals)]
        elif name=="timezone":
            vals=["local","Europe/Kyiv","Europe/London","Europe/Paris","America/New_York","Asia/Tokyo","UTC"]; idx=vals.index(SETTINGS["timezone"]) if SETTINGS["timezone"] in vals else 0; SETTINGS["timezone"]=vals[(idx+direction)%len(vals)]; apply_timezone()
        elif name=="refresh_rate": SETTINGS["refresh_rate"]=0.5 if SETTINGS["refresh_rate"]>=2 else round(SETTINGS["refresh_rate"]+0.5,1)
        elif name=="show_seconds": SETTINGS["show_seconds"]=not SETTINGS.get("show_seconds",True)
        elif name=="confirm_external": SETTINGS["confirm_external"]=not SETTINGS.get("confirm_external",True)
        elif name=="dashboard_extra": SETTINGS["dashboard_extra"]=not SETTINGS.get("dashboard_extra",True)
        elif name=="clock_style": SETTINGS["clock_style"]="slashes" if SETTINGS.get("clock_style","blocks")=="blocks" else "blocks"
        elif name=="show_hidden": SETTINGS["show_hidden"]=not SETTINGS.get("show_hidden",False)
        elif name=="file_icons": SETTINGS["file_icons"]=not SETTINGS.get("file_icons",True)
        elif name=="process_sort":
            vals=["memory","cpu","pid"]; idx=vals.index(SETTINGS["process_sort"]) if SETTINGS.get("process_sort") in vals else 0; SETTINGS["process_sort"]=vals[(idx+direction)%len(vals)]
        elif name=="confirm_kill": SETTINGS["confirm_kill"]=not SETTINGS.get("confirm_kill",True)
        elif name=="week_start": SETTINGS["week_start"]="sunday" if SETTINGS.get("week_start","monday")=="monday" else "monday"
        elif name=="package_list":
            vals=[50,100,200,500]; idx=vals.index(SETTINGS["package_list"]) if SETTINGS.get("package_list") in vals else 1; SETTINGS["package_list"]=vals[(idx+direction)%len(vals)]
        elif name=="reset":
            if key in (10,13,curses.KEY_ENTER):
                safe_add(win,h-3,2," "*max(0,w-4),1); safe_add(win,h-2,2," "*max(0,w-4),1)
                if prompt(win,"Reset all settings to default? y/N: ").strip().lower()=="y":
                    SETTINGS.update(DEFAULT_SETTINGS); theme_name=SETTINGS["theme"]; refresh_theme_pairs(); apply_timezone()
        elif name=="lock_password":
            if key in (10,13,curses.KEY_ENTER): notice=manage_lock_password(win)
        elif name=="system_time":
            value=prompt(win,"System time YYYY-MM-DD HH:MM:SS (blank cancels): ").strip()
            if value: run_external(win,"sudo timedatectl set-time "+shlex.quote(value))
        save_settings()


def save_settings():
    SETTINGS["theme"]=theme_name; curses.init_pair(2,curses.COLOR_BLACK,THEMES[theme_name]["accent"])
    (CONFIG/"settings.json").write_text(json.dumps(SETTINGS,indent=2),encoding="utf-8")


def load_settings():
    global theme_name
    try:
        data=json.loads((CONFIG/"settings.json").read_text(encoding="utf-8"))
        if isinstance(data,dict): SETTINGS.update({k:v for k,v in data.items() if k in SETTINGS})
    except Exception:
        try:
            old=(CONFIG/"settings.txt").read_text().strip()
            if old in THEMES: SETTINGS["theme"]=old
        except Exception: pass
    if SETTINGS["theme"] not in THEMES: SETTINGS["theme"]="cyan"
    if SETTINGS["time_format"] not in ("12h","24h"): SETTINGS["time_format"]="24h"
    if SETTINGS.get("process_sort") not in ("memory","cpu","pid"): SETTINGS["process_sort"]="memory"
    if SETTINGS.get("week_start") not in ("monday","sunday"): SETTINGS["week_start"]="monday"
    if SETTINGS.get("clock_style") not in ("blocks","slashes"): SETTINGS["clock_style"]="blocks"
    if SETTINGS.get("package_list") not in (50,100,200,500): SETTINGS["package_list"]=100
    theme_name=SETTINGS["theme"]; refresh_theme_pairs(); apply_timezone()


# ─────────────────────────────────────────────
# System information
# ─────────────────────────────────────────────

def system_info(win):
    win.erase()
    h, w = win.getmaxyx()

    safe_add(win, 0, 2, " SYSTEM INFORMATION ", accent())

    information = [
        f"OS: {platform.system()} {platform.release()}",
        f"Distribution: {platform.platform()}",
        f"Hostname: {platform.node()}",
        f"Architecture: {platform.machine()}",
        f"Python: {platform.python_version()}",
        f"User: {os.getenv('USER', 'unknown')}",
        f"Shell: {os.getenv('SHELL', 'unknown')}",
        f"Terminal: {os.getenv('TERM', 'unknown')}",
        f"Current directory: {Path.cwd()}",
    ]

    if psutil:
        information.extend([
            f"CPU cores: {psutil.cpu_count(logical=False)} physical / "
            f"{psutil.cpu_count()} logical",
            f"RAM: {psutil.virtual_memory().total / 1024**3:.2f} GB",
        ])

    for i, line in enumerate(information):
        safe_add(win, 3 + i, 2, line, 1)

    wait_key(win)


# ─────────────────────────────────────────────
# Power menu
# ─────────────────────────────────────────────

def power_app(win):
    options=[("Return to menu",None),("Lock screen","lock"),("Exit VTOS","exit"),("Reboot Linux","reboot"),("Shut down Linux","poweroff")]
    selected=0
    while True:
        win.erase(); h,w=win.getmaxyx(); center(win,3,"POWER OPTIONS",accent())
        for i,(label,_) in enumerate(options): center(win,6+i,label,2 if i==selected else 1)
        center(win,h-3,"↑↓ select | Enter confirm | q return",5); win.refresh(); key=timed_key(win)
        if key in (ord("q"),27): return None
        elif key==curses.KEY_UP: selected=(selected-1)%len(options)
        elif key==curses.KEY_DOWN: selected=(selected+1)%len(options)
        elif key in (10,13,curses.KEY_ENTER):
            action=options[selected][1]
            if action is None: return None
            if action in ("exit","lock"): return action
            center(win,12,"Confirm? y/N",6); win.refresh(); win.timeout(-1); confirm=win.getch()  # blocking: stays until a key is pressed
            if confirm in (ord("y"),ord("Y")):
                curses.endwin(); os.system("sudo reboot" if action=="reboot" else "sudo poweroff"); return "exit_system"


# ─────────────────────────────────────────────
# Additional applications (2.0)
# ─────────────────────────────────────────────

def timer_app(win):
    try: win.keypad(True)
    except Exception: pass
    presets=[("1 minute",60),("5 minutes",300),("10 minutes",600),("15 minutes",900),("25 minutes (focus)",1500),("Custom (minutes)",None)]
    selected=0; state="idle"; total=0; left=0.0; end_at=0.0
    while True:
        now=time.monotonic()
        if state=="running":
            left=max(0.0,end_at-now)
            if left<=0:
                state="finished"
                try: curses.beep()
                except curses.error: pass
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," TIMER ",accent())
        if state=="idle":
            safe_add(win,2,2,"↑↓ select | ENTER start | q return",5)
            for i,(label,_) in enumerate(presets): pointer_line(win,4+i,3,label,i==selected)
        else:
            rem=int(left)+(1 if left>int(left) else 0)
            hh,rem=divmod(rem,3600); mm,ss=divmod(rem,60)
            center(win,4,f"{hh:02d}:{mm:02d}:{ss:02d}",accent())
            center(win,6,bar(total-left,total,30),accent())
            label,col={"running":("RUNNING",4),"paused":("PAUSED",5),"finished":("TIME IS UP!",6)}[state]
            center(win,8,label,col)
            hint="SPACE pause | r reset | q return" if state=="running" else ("SPACE resume | r reset | q return" if state=="paused" else "r / ENTER new timer | q return")
            center(win,11,hint,5)
        win.refresh()
        win.timeout(100 if state=="running" else max(250,int(1000*SETTINGS.get("refresh_rate",1))))
        try: k=win.getch()
        finally: win.timeout(-1)
        if k in (ord('q'),27): return
        if state=="idle":
            if k==curses.KEY_UP: selected=max(0,selected-1)
            elif k==curses.KEY_DOWN: selected=min(len(presets)-1,selected+1)
            elif k in (10,13,curses.KEY_ENTER):
                secs=presets[selected][1]
                if secs is None:
                    try: minutes=float(prompt(win,"Minutes (e.g. 7 or 2.5): ").strip().replace(",","."))
                    except ValueError: continue
                    if not (0<minutes<=1440): continue
                    secs=int(minutes*60)
                if secs<=0: continue
                total=secs; left=float(secs); end_at=time.monotonic()+secs; state="running"
        elif state=="running":
            if k==ord(' '): state="paused"
            elif k==ord('r'): state="idle"
        elif state=="paused":
            if k==ord(' '): end_at=time.monotonic()+left; state="running"
            elif k==ord('r'): state="idle"
        elif state=="finished":
            if k in (ord('r'),10,13,curses.KEY_ENTER): state="idle"


WORLD_ZONES=["UTC","Europe/Kyiv","Europe/London","Europe/Berlin","America/New_York","America/Chicago","America/Los_Angeles","Asia/Dubai","Asia/Kolkata","Asia/Shanghai","Asia/Tokyo","Australia/Sydney"]

def world_clock_app(win):
    try: win.keypad(True)
    except Exception: pass
    try: from zoneinfo import ZoneInfo
    except Exception: ZoneInfo=None
    offset=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," WORLD CLOCK ",accent())
        fmt=clock_format(); rows=[]
        try:
            local=datetime_module.datetime.now().astimezone()
            rows.append((f"{'Local (VTOS)':<22} {local.strftime(fmt):<12} UTC{local.strftime('%z')[:3]}:{local.strftime('%z')[3:]}  {local.strftime('%a %d.%m')}",accent()))
        except Exception: rows.append(("Local (VTOS)        unavailable",6))
        for zone in WORLD_ZONES:
            try:
                if ZoneInfo is None: raise RuntimeError
                now=datetime_module.datetime.now(ZoneInfo(zone)); z=now.strftime('%z')
                rows.append((f"{zone:<22} {now.strftime(fmt):<12} UTC{z[:3]}:{z[3:]}  {now.strftime('%a %d.%m')}",1))
            except Exception: rows.append((f"{zone:<22} n/a (tz data not found)",6))
        visible=max(1,h-6); offset=max(0,min(offset,max(0,len(rows)-visible)))
        for i,(line,col) in enumerate(rows[offset:offset+visible]): safe_add(win,2+i,2,line[:w-4],col)
        safe_add(win,h-2,2,"↑↓ scroll | q return",5); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: offset=max(0,offset-1)
        elif key==curses.KEY_DOWN: offset=min(max(0,len(rows)-visible),offset+1)


TODO_FILE=DATA/"todo.json"

def todo_app(win):
    try: win.keypad(True)
    except Exception: pass
    try:
        data=json.loads(TODO_FILE.read_text(encoding="utf-8"))
        tasks=[{"text":str(t.get("text","")),"done":bool(t.get("done",False))} for t in data if isinstance(t,dict)] if isinstance(data,list) else []
    except Exception: tasks=[]
    def save():
        try: TODO_FILE.write_text(json.dumps(tasks,indent=2,ensure_ascii=False),encoding="utf-8")
        except Exception: pass
    selected=0; offset=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," TO-DO ",accent())
        safe_add(win,1,2,"↑↓ select | a add | SPACE/ENTER done | d delete | c clear done | q return",5)
        visible=max(1,h-6); selected=max(0,min(selected,len(tasks)-1)) if tasks else 0
        if selected<offset: offset=selected
        if selected>=offset+visible: offset=selected-visible+1
        if not tasks: safe_add(win,3,3,"No tasks yet. Press a to add one.",1)
        for i,t in enumerate(tasks[offset:offset+visible]):
            idx=i+offset; mark="[x]" if t["done"] else "[ ]"
            pointer_line(win,3+i,2,f"{mark} {t['text']}"[:w-8],idx==selected,4 if t["done"] else 1)
        done=sum(1 for t in tasks if t["done"])
        safe_add(win,h-2,2,f"{done}/{len(tasks)} done",4); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: selected=max(0,selected-1)
        elif key==curses.KEY_DOWN: selected=min(max(0,len(tasks)-1),selected+1)
        elif key==ord('a'):
            text=prompt(win,"New task: ").strip()
            if text: tasks.append({"text":text,"done":False}); selected=len(tasks)-1; save()
        elif key in (ord(' '),10,13,curses.KEY_ENTER) and tasks:
            tasks[selected]["done"]=not tasks[selected]["done"]; save()
        elif key==ord('d') and tasks:
            if prompt(win,f"Delete '{tasks[selected]['text'][:30]}'? y/N: ").strip().lower()=="y":
                tasks.pop(selected); save()
        elif key==ord('c') and any(t["done"] for t in tasks):
            if prompt(win,"Remove all completed tasks? y/N: ").strip().lower()=="y":
                tasks[:]=[t for t in tasks if not t["done"]]; save()


UNIT_CATEGORIES={
    "Length":{"mm":0.001,"cm":0.01,"m":1.0,"km":1000.0,"in":0.0254,"ft":0.3048,"yd":0.9144,"mi":1609.344},
    "Mass":{"mg":1e-6,"g":0.001,"kg":1.0,"t":1000.0,"oz":0.028349523125,"lb":0.45359237},
    "Data":{"B":1.0,"KiB":1024.0,"MiB":1024.0**2,"GiB":1024.0**3,"TiB":1024.0**4},
    "Speed":{"m/s":1.0,"km/h":1/3.6,"mph":0.44704,"kn":1852/3600},
    "Time":{"s":1.0,"min":60.0,"h":3600.0,"day":86400.0,"week":604800.0},
    "Temperature":{"C":None,"F":None,"K":None},
}

def convert_units(category,value,unit,units):
    if category=="Temperature":
        celsius={"C":value,"F":(value-32)*5/9,"K":value-273.15}[unit]
        return {"C":celsius,"F":celsius*9/5+32,"K":celsius+273.15}
    base=value*units[unit]
    return {name:base/factor for name,factor in units.items()}

def converter_app(win):
    try: win.keypad(True)
    except Exception: pass
    cats=list(UNIT_CATEGORIES); selected=0
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," UNIT CONVERTER ",accent())
        safe_add(win,2,2,"↑↓ select category | ENTER open | q return",5)
        for i,c in enumerate(cats): pointer_line(win,4+i,3,c,i==selected)
        win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: selected=(selected-1)%len(cats)
        elif key==curses.KEY_DOWN: selected=(selected+1)%len(cats)
        elif key in (10,13,curses.KEY_ENTER):
            cat=cats[selected]; units=UNIT_CATEGORIES[cat]; lookup={u.lower():u for u in units}; results=[]; message=""
            while True:
                win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2,f" UNIT CONVERTER — {cat} ",accent())
                safe_add(win,2,2,"Units: "+", ".join(units),5); safe_add(win,3,2,"Enter a value and unit, e.g. 10 "+next(iter(units)),5)
                for i,line in enumerate(results[:max(0,h-9)]): safe_add(win,5+i,3,line,1)
                if message: safe_add(win,h-4,2,message,6)
                text=prompt(win,"Value and unit (q = back): ").strip()
                if text.lower()=="q": break
                if not text: continue
                parts=text.replace(",",".").split()
                try:
                    if len(parts)==2: raw,unit_text=parts
                    elif len(parts)==1:
                        raw=parts[0].rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ/"); unit_text=parts[0][len(raw):]
                    else: raise ValueError("Use: <value> <unit>")
                    value=float(raw)
                    if unit_text.lower() not in lookup: raise ValueError(f"Unknown unit '{unit_text}'")
                    unit=lookup[unit_text.lower()]
                    if cat=="Temperature" and unit=="K" and value<0: raise ValueError("Kelvin cannot be negative")
                    converted=convert_units(cat,value,unit,units)
                    results=[f"{value:g} {unit} ="]+[f"   {v:.8g} {name}" for name,v in converted.items() if name!=unit]; message=""
                except ValueError as e: message=str(e)[:w-4]

PASSWORD_SYMBOLS="!@#$%^&*()-_=+[]{};:,.?/"

def password_app(win):
    import secrets, string
    try: win.keypad(True)
    except Exception: pass
    length=16; opts={"lower":True,"upper":True,"digits":True,"symbols":True,"similar":False}
    labels=[("Length","length"),("Lowercase a-z","lower"),("Uppercase A-Z","upper"),("Digits 0-9","digits"),("Symbols","symbols"),("Exclude similar (0 O 1 l I)","similar")]
    selected=0; passwords=[]
    def generate():
        pools=[]
        for key,chars in (("lower",string.ascii_lowercase),("upper",string.ascii_uppercase),("digits",string.digits),("symbols",PASSWORD_SYMBOLS)):
            if opts[key]:
                if opts["similar"]: chars="".join(c for c in chars if c not in "0O1lI")
                pools.append(chars)
        rng=secrets.SystemRandom(); out=[]
        for _ in range(6):
            chars=[rng.choice(p) for p in pools]; allchars="".join(pools)
            chars+=[rng.choice(allchars) for _ in range(length-len(chars))]
            rng.shuffle(chars); out.append("".join(chars))
        return out
    while True:
        win.erase(); h,w=win.getmaxyx(); safe_add(win,0,2," PASSWORD GENERATOR ",accent())
        safe_add(win,2,2,"↑↓ select | ←→ change | g / ENTER generate | q return",5)
        for i,(label,key) in enumerate(labels):
            value=length if key=="length" else ("On" if opts[key] else "Off")
            safe_add(win,4+i,3,f"{label:<30}: {value}",2 if i==selected else 1)
        for i,p in enumerate(passwords): safe_add(win,12+i,3,p,accent())
        win.refresh(); k=timed_key(win)
        if k in (ord('q'),27): return
        elif k==curses.KEY_UP: selected=max(0,selected-1)
        elif k==curses.KEY_DOWN: selected=min(len(labels)-1,selected+1)
        elif k in (curses.KEY_LEFT,curses.KEY_RIGHT,ord(' ')):
            key=labels[selected][1]; direction=-1 if k==curses.KEY_LEFT else 1
            if key=="length": length=max(8,min(64,length+direction))
            else:
                opts[key]=not opts[key]
                if not any(opts[x] for x in ("lower","upper","digits","symbols")): opts["lower"]=True
        elif k in (ord('g'),10,13,curses.KEY_ENTER): passwords=generate()


def hex_viewer_app(win):
    try: win.keypad(True)
    except Exception: pass
    raw=prompt(win,"File path: ").strip()
    if not raw: return
    path=Path(raw).expanduser()
    if not path.is_absolute(): path=Path.cwd()/path
    limit=1024*1024
    try:
        with path.open("rb") as f: data=f.read(limit)
        size=path.stat().st_size
    except Exception as e:
        win.erase(); center(win,4,f"Cannot open: {e}",6); wait_key(win); return
    offset=0
    while True:
        win.erase(); h,w=win.getmaxyx(); per=16 if w>=82 else 8
        safe_add(win,0,2,f" HEX VIEWER — {path.name} ",accent())
        note=f"{size} bytes" + (f" (showing first {limit})" if size>limit else "")
        safe_add(win,1,2,note,5)
        total_rows=max(1,(len(data)+per-1)//per); visible=max(1,h-5); offset=max(0,min(offset,max(0,total_rows-visible)))
        for i in range(visible):
            r=offset+i
            if r>=total_rows: break
            chunk=data[r*per:(r+1)*per]
            hexpart=" ".join(f"{b:02x}" for b in chunk)
            ascii_part="".join(chr(b) if 32<=b<127 else "." for b in chunk)
            safe_add(win,3+i,2,f"{r*per:08x}  {hexpart:<{per*3-1}}  |{ascii_part}|",1)
        safe_add(win,h-1,2,"↑↓ scroll | PgUp/PgDn | Home/End | q return",5); win.refresh(); key=timed_key(win)
        if key in (ord('q'),27): return
        elif key==curses.KEY_UP: offset=max(0,offset-1)
        elif key==curses.KEY_DOWN: offset=min(max(0,total_rows-visible),offset+1)
        elif key==curses.KEY_NPAGE: offset=min(max(0,total_rows-visible),offset+visible)
        elif key==curses.KEY_PPAGE: offset=max(0,offset-visible)
        elif key==curses.KEY_HOME: offset=0
        elif key==curses.KEY_END: offset=max(0,total_rows-visible)


LOGO_ART = [
    '                           █████          █████          ',
    '                                                         ',
    '                           █████             █████       ',
    '                                                         ',
    '█████        █████  ██████████████████          █████    ',
    '                                                         ',
    '  █████     █████          █████                    █████',
    '                                                         ',
    '   █████  █████            █████                █████    ',
    '                                                         ',
    '     ████████              █████             █████       ',
    '                                                         ',
    '       █████                ██████████    █████          ',
]

# ─────────────────────────────────────────────
# Boot screen, lock screen, shutdown screen (2.0)
# ─────────────────────────────────────────────

LOCK_FILE = CONFIG / "lock.json"
LOCK_ITERATIONS = 200_000

def draw_logo(win, color=1):
    # System logo (same art as on Desktop), centered both ways. Returns the top row.
    h, w = win.getmaxyx()
    top = max(0, (h - len(LOGO_ART)) // 2)
    for row, art_line in enumerate(LOGO_ART):
        center(win, top + row, art_line, color)
    return top

def load_lock_record():
    # {"salt": ..., "hash": ...} or None when no (valid) password is set.
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("salt") and data.get("hash"):
            return data
    except Exception:
        pass
    return None

def lock_password_exists():
    return load_lock_record() is not None

def _lock_hash(password, salt_hex, iterations):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()

def set_lock_password(password):
    salt = secrets.token_hex(16)
    record = {"salt": salt, "iterations": LOCK_ITERATIONS, "hash": _lock_hash(password, salt, LOCK_ITERATIONS)}
    LOCK_FILE.write_text(json.dumps(record), encoding="utf-8")
    try: os.chmod(LOCK_FILE, 0o600)
    except OSError: pass

def check_lock_password(password, record=None):
    record = record or load_lock_record()
    if record is None: return True
    try:
        expected = _lock_hash(password, record["salt"], int(record.get("iterations", LOCK_ITERATIONS)))
        return hmac.compare_digest(expected, record["hash"])
    except Exception:
        return False

def remove_lock_password():
    try: LOCK_FILE.unlink()
    except FileNotFoundError: pass

def prompt_secret(win, message):
    # Reads a line without showing it (stars instead). Returns None if cancelled with Esc.
    win.timeout(-1)
    buffer = ""
    while True:
        h, w = win.getmaxyx()
        safe_add(win, h - 3, 2, " " * max(0, w - 4), 1)
        safe_add(win, h - 2, 2, " " * max(0, w - 4), 1)
        safe_add(win, h - 3, 2, message, 5)
        safe_add(win, h - 2, 2, "> " + "*" * len(buffer), 4)
        win.refresh()
        try: ch = win.get_wch()
        except curses.error: continue
        if ch in ("\n", "\r") or ch == curses.KEY_ENTER: return buffer
        if ch == "\x1b": return None
        if ch in ("\x7f", "\b") or ch == curses.KEY_BACKSPACE: buffer = buffer[:-1]
        elif isinstance(ch, str) and ch.isprintable() and len(buffer) < 64: buffer += ch

def manage_lock_password(win):
    # Settings → Lock password. Returns (message, color).
    if load_lock_record() is None:
        first = prompt_secret(win, "New password (Esc cancels):")
        if not first: return ("Cancelled: password not set", 5)
        second = prompt_secret(win, "Confirm password:")
        if second is None: return ("Cancelled: password not set", 5)
        if second != first: return ("Passwords do not match: password not set", 6)
        set_lock_password(first)
        return ("Password created", 4)
    current = prompt_secret(win, "Enter the current password to remove it (Esc cancels):")
    if current is None: return ("Cancelled: password kept", 5)
    if check_lock_password(current):
        remove_lock_password()
        return ("Password removed", 4)
    return ("Wrong password: password kept", 6)

def boot_sequence(win):
    # 1) white logo exactly 1 second, centered; settings are loaded while it is on screen.
    win.erase(); draw_logo(win, 1); win.refresh()
    started = time.monotonic()
    load_settings(); refresh_theme_pairs()
    remaining = 1.0 - (time.monotonic() - started)
    if remaining > 0: time.sleep(remaining)

    # 2) loading bar in the theme color under the logo. Real start-up work, no artificial delays:
    #    the bar advances as fast as the computer finishes each step.
    tasks = [
        apply_timezone,
        lambda: (platform.node(), platform.system(), platform.release(), platform.python_version(), platform.machine()),
        lambda: psutil and (psutil.cpu_percent(interval=None), psutil.virtual_memory(), psutil.boot_time()),
        lambda: psutil and psutil.sensors_battery(),
        lambda: (net_speed(), wifi_level(), ethernet_connected()),
        lambda: (shutil.disk_usage("/"), CONFIG.mkdir(parents=True, exist_ok=True), DATA.mkdir(parents=True, exist_ok=True)),
        lambda: (NOTES.exists(), APP_CONFIG.exists()),
        lock_password_exists,
    ]

    def frame(done):
        h, w = win.getmaxyx()
        win.erase()
        top = draw_logo(win, 1)
        width = max(10, min(len(LOGO_ART[0]), w - 4))
        center(win, top + len(LOGO_ART) + 2, bar(done, len(tasks), width), accent())
        win.refresh()

    frame(0)
    for index, task in enumerate(tasks, 1):
        try: task()
        except Exception: pass
        frame(index)
    try: curses.flushinp()   # drop keys typed during boot
    except curses.error: pass

def lock_screen(win):
    # Clock (same as the main menu, follows Settings), password field, "ENTER unlock".
    record = load_lock_record()
    typed = ""; wrong = False
    try: win.keypad(True)
    except Exception: pass
    while True:
        win.erase(); h, w = win.getmaxyx()
        clock_y = max(1, (h - 12) // 2 - 1)
        draw_big_clock(win, clock_y, max(0, (w - CLOCK_WIDTH) // 2))
        field_y = clock_y + CLOCK_HEIGHT + 3
        if record is not None:
            if wrong: center(win, field_y, "неверный пароль", 6)
            elif typed: center(win, field_y, "*" * len(typed), accent())
            else: center(win, field_y, "введи пароль", 1)
        center(win, field_y + 2, "ENTER unlock", 5)
        win.refresh()
        win.timeout(250)
        try: ch = win.get_wch()
        except curses.error: continue      # no key: just redraw (the clock keeps running)
        finally: win.timeout(-1)
        if ch in ("\n", "\r") or ch == curses.KEY_ENTER:
            if record is None or check_lock_password(typed, record): return
            wrong = True; typed = ""
        elif ch == "\x1b": typed = ""; wrong = False
        elif ch in ("\x7f", "\b") or ch == curses.KEY_BACKSPACE: typed = typed[:-1]; wrong = False
        elif isinstance(ch, str) and ch.isprintable() and len(typed) < 64: typed += ch; wrong = False

def shutdown_screen(win):
    # Centered white logo without a bar, then VTOS exits immediately (no delay).
    win.erase(); draw_logo(win, 1); win.refresh()


# ─────────────────────────────────────────────
# Main menu
# ─────────────────────────────────────────────

MENU_CATEGORIES = [
    ("SYSTEM", [
        ("⌂", "Desktop", dashboard),
        ("⏻", "Power", power_app),
        ("⚙", "Settings", settings_app),
    ]),
    ("SYSTEM TOOLS", [
        ("◉", "System Center", monitor_hub),
        ("◎", "Network", network_app),
        ("⌘", "Shell", shell_app),
        ("▶", "Applications", apps_app),
    ]),
    ("FILES", [
        ("▤", "File Manager", file_manager),
        ("⌕", "File Search", file_search),
        ("✎", "Text Editor", text_editor),
        ("▥", "Hex Viewer", hex_viewer_app),
    ]),
    ("PRODUCTIVITY", [
        ("✎", "Notes", notes_app),
        ("☑", "To-Do", todo_app),
        ("▦", "Calendar", calendar_app),
        ("∑", "Calculator", calculator),
        ("⇄", "Unit Converter", converter_app),
    ]),
    ("TIME", [
        ("◷", "Stopwatch", stopwatch_app),
        ("⏲", "Timer", timer_app),
        ("◴", "World Clock", world_clock_app),
    ]),
    ("EXTRAS", [
        ("🎮", "Games", games_app),
        ("⚿", "Password Gen", password_app),
    ]),
]

# Flat list (selection works on this) + display rows (category headers and items).
MENU = [entry for _, entries in MENU_CATEGORIES for entry in entries]
MENU_ROWS = []
for _category, _entries in MENU_CATEGORIES:
    if MENU_ROWS:
        MENU_ROWS.append(("blank", None))   # gap between the previous app and the next category
    MENU_ROWS.append(("header", _category))
    for _ in _entries:
        MENU_ROWS.append(("item", sum(1 for kind, _v in MENU_ROWS if kind == "item")))


def main(stdscr):
    global theme_name

    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    stdscr.timeout(-1)

    init_colors()
    boot_sequence(stdscr)     # logo (1 s) + loading bar; also loads the settings
    lock_screen(stdscr)       # password if one is set

    selected = 0
    menu_scroll = 0
    cpu_history=[]
    if psutil: psutil.cpu_percent(interval=None)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        if h < 28 or w < 70:
            center(stdscr, 2, "VTOS needs at least 70x28 terminal size", 6)
            center(stdscr, 4, "Resize your terminal and press any key", 5)
            stdscr.refresh()
            stdscr.getch()
            continue

        # Top bar appears only on the home screen (not inside launched applications).
        safe_add(stdscr, 0, 2, " Vibecoded Terminal Operating System ", accent())
        safe_add(stdscr, 0, 42, f"Version {VERSION}", accent())
        draw_top_datetime(stdscr, w, speed_text=format_speed(net_speed()), wifi="ETHERNET" if ethernet_connected() else wifi_text(wifi_level()))

        try:
            stdscr.hline(1, 1, curses.ACS_HLINE, w - 2)
        except curses.error:
            pass

        # Left menu
        menu_width = 29

        safe_add(stdscr, 2, 3, "APPLICATIONS", accent())

        visible_rows = max(3, h - 6)
        sel_row = next(r for r, (kind, val) in enumerate(MENU_ROWS) if kind == "item" and val == selected)
        top_row = sel_row - 1 if MENU_ROWS[sel_row - 1][0] == "header" else sel_row
        if top_row < menu_scroll: menu_scroll = top_row
        if sel_row >= menu_scroll + visible_rows: menu_scroll = sel_row - visible_rows + 1
        menu_scroll = max(0, min(menu_scroll, max(0, len(MENU_ROWS) - visible_rows)))

        for r in range(menu_scroll, min(len(MENU_ROWS), menu_scroll + visible_rows)):
            y = 4 + r - menu_scroll
            kind, val = MENU_ROWS[r]

            if kind == "blank":
                continue

            if kind == "header":
                safe_add(stdscr, y, 3, f"─ {val}", accent())
                continue

            icon, name, _ = MENU[val]
            text = f" {icon}  {name}"

            if val == selected:
                safe_add(stdscr, y, 2, "▶", accent())
                safe_add(stdscr, y, 4, text, 2)
            else:
                safe_add(stdscr, y, 4, text, 1)

        if menu_scroll > 0:
            safe_add(stdscr, 3, menu_width - 3, "▲", accent())
        if menu_scroll + visible_rows < len(MENU_ROWS):
            safe_add(stdscr, 4 + visible_rows, menu_width - 3, "▼", accent())

        try:
            stdscr.vline(2, menu_width, curses.ACS_VLINE, h - 4)
        except curses.error:
            pass

        # Right information panel
        panel_x = menu_width + 3

        safe_add(stdscr, 2, panel_x, "SYSTEM OVERVIEW", accent())

        overview = [f"USER      {os.getenv('USER', 'user')}",
                    f"HOST      {platform.node()}",
                    f"OS        {platform.system()}",
                    f"RELEASE   {platform.release()}",
                    f"PYTHON    {platform.python_version()}"]
        for i, line in enumerate(overview):
            safe_add(stdscr, 4 + i, panel_x, line, 1)

        # Big clock under the date/time (right side); hidden if it would overlap the overview text.
        clock_x = w - CLOCK_WIDTH - 2
        if clock_x >= panel_x + max(len(line) for line in overview) + 2:
            draw_big_clock(stdscr, 2, clock_x)

        # Quick Status rows are separated by one blank line when the terminal is tall enough.
        step = 2 if h >= 32 else 1
        qy = 10 + step

        safe_add(stdscr, 10, panel_x, "QUICK STATUS", accent())

        if psutil:
            cpu_now = psutil.cpu_percent(interval=None)
            cpu_history.append(cpu_now); cpu_history=cpu_history[-5:]
            cpu = sum(cpu_history)/len(cpu_history)
            mem = psutil.virtual_memory().percent

            safe_add(stdscr, qy, panel_x,
                     f"CPU   {bar(cpu, 100, 16)} {cpu:5.1f}%", 4)
            qy += step
            safe_add(stdscr, qy, panel_x,
                     f"RAM   {bar(mem, 100, 16)} {mem:5.1f}%", 3)
            qy += step

            try:
                battery=psutil.sensors_battery()
            except Exception:
                battery=None
            if battery:
                batt_pct=max(0,min(100,float(battery.percent)))
                batt_color=4 if batt_pct>50 else (5 if batt_pct>=20 else 6)
                plug=" AC" if battery.power_plugged else ""
                if battery_charging(battery): batt_color=8   # charging: BAT, bar and "NN% AC" are all blue
                bar_text=bar(batt_pct,100,16)
                safe_add(stdscr, qy, panel_x, "BAT   ", batt_color)
                safe_add(stdscr, qy, panel_x + 6, bar_text, batt_color)
                safe_add(stdscr, qy, panel_x + 6 + len(bar_text), f" {batt_pct:4.0f}%{plug}", batt_color)
            else:
                safe_add(stdscr, qy, panel_x, "BAT", 6)         # no battery: BAT in red
                safe_add(stdscr, qy, panel_x + 6, "no data", 6)
            qy += step

            try:
                disk=shutil.disk_usage('/')
                used_pct=disk.used/disk.total*100 if disk.total else 0
                safe_add(stdscr, qy, panel_x,
                         f"DISK  {bar(used_pct,100,16)} {used_pct:4.0f}%", 5)
                qy += step
            except Exception:
                pass

            try:
                uptime_s=max(0,int(time.time()-psutil.boot_time()))
                up_d, rem=divmod(uptime_s,86400)
                up_h, up_m=divmod(rem//60,60)
                uptime_text=(f"{up_d}d {up_h}h {up_m}m" if up_d else f"{up_h}h {up_m}m")
                safe_add(stdscr, qy, panel_x, f"UPTIME  {uptime_text}", 1)
                qy += step
                safe_add(stdscr, qy, panel_x, f"PROCESSES {len(psutil.pids())}", 1)
                qy += step
            except Exception:
                pass

        # Last line of Quick Status: selected theme, shown in its own color.
        safe_add(stdscr, qy, panel_x, "THEME   ", 1)
        safe_add(stdscr, qy, panel_x + 8, theme_name, accent())
        qy += step

        # SHORTCUTS: one blank line between the title and the list.
        safe_add(stdscr, qy, panel_x, "SHORTCUTS", accent())
        safe_add(stdscr, qy + 2, panel_x, "↑ ↓ / J K   Navigate", accent())
        safe_add(stdscr, qy + 3, panel_x, "ENTER       Launch", accent())
        safe_add(stdscr, qy + 4, panel_x, "POWER       Exit", accent())

        stdscr.refresh()
        key = timed_key(stdscr)

        if key == 27:
            continue
        elif key == ord("q"):
            continue

        elif key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(MENU)

        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(MENU)

        elif key in (10, 13, curses.KEY_ENTER):
            app = MENU[selected][2]

            result = app(stdscr)

            if result == "exit":
                shutdown_screen(stdscr)
                return
            elif result == "exit_system":
                return
            elif result == "lock":
                lock_screen(stdscr)



# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main_screen = curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"\nVTOS error: {error}")
        print("Check terminal compatibility and Python installation.")