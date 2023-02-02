#!/usr/bin/env python3
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime


def exception_info(ex):
    if isinstance(ex, subprocess.CalledProcessError):
        return f"{ex}: {ex.output}"
    else:
        return str(ex)


def retry(exception_types, max_retries):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = Exception("max_retries < 1")
            for retry in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    last_exception = e
                    print(
                        (
                            f'Function "{func.__name__}" failed '
                            f"{retry+1}/{max_retries}: {exception_info(e)}"
                        ),
                        file=sys.stderr,
                    )
                    time.sleep(1 * retry)
            raise last_exception

        return wrapper

    return decorator


def get_screens():
    proc = subprocess.run(["xrandr", "--listmonitors"], capture_output=True, check=True)

    result = []
    for line in proc.stdout.decode("UTF-8").split("\n"):
        if re.match(r"\s+[0-9]+", line):
            match = re.search(
                r"(?P<id>\d+):\s+\+(?P<primary>\*?)(?P<name>[\w-]+)"
                r"\s+(?P<res_x>[0-9]+)/[0-9]+x(?P<res_y>[0-9]+)/"
                r"[0-9]+[+](?P<off_x>[0-9]+)[+](?P<off_y>[0-9]+)",
                line,
            )
            if match:
                group_dict = match.groupdict()
                group_dict["primary"] = group_dict["primary"] == "*"
                result.append(group_dict)

    return result


def get_session_info():
    proc = subprocess.run(
        ["loginctl", "show-session", "self"], capture_output=True, check=True
    )
    result = dict(
        match.groups()
        for line in proc.stdout.decode("UTF-8").split("\n")
        if line != "" and (match := re.match(r"(\w+)\=(.+)", line))
    )
    for k in result.keys():
        if result[k] in ("yes", "no"):
            result[k] = result[k] == "yes"

    return result


def get_comm_for_pid(pid):
    with contextlib.suppress(FileNotFoundError):
        return open(f"/proc/{pid}/comm").read().strip()


@retry((subprocess.CalledProcessError), 3)
def get_window_mouse_desktop():
    proc = subprocess.run(
        [
            "xdotool",
            "getwindowfocus",
            "getwindowname",
            "getwindowpid",
            "get_desktop",
            "getmouselocation",
        ],
        capture_output=True,
        check=True,
    )
    out = proc.stdout.decode("UTF-8").split("\n")
    result = {
        "title": out[0],
        "comm": get_comm_for_pid(out[1]),
        "desktop": out[2],
        "mouse": match.groupdict()
        if (
            match := re.match(
                r"x:(?P<x>\d+)\s+"
                r"y:(?P<y>\d+)\s+"
                r"screen:(?P<screen>\d+)\s+"
                r"window:(?P<window_id>\d+)",
                out[3],
            )
        )
        else {},
    }
    return result


def get_current_motd():
    with contextlib.suppress(FileNotFoundError):
        return open(os.path.expanduser("~/var/current-emacs-motd")).read().strip()


def get_current_music():
    proc = subprocess.run(
        ["currently_playing_music", "json"], capture_output=True, check=True
    )
    return json.loads(proc.stdout)


def main():
    screens = get_screens()
    session_info = get_session_info()
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        window_mouse_desktop = get_window_mouse_desktop()
    except subprocess.CalledProcessError:
        window_mouse_desktop = {
            "title": "UNKNOWN",
            "comm": "",
            "desktop": None,
            "mouse": {"x": None, "y": None, "screen": None, "window": None},
        }
    music = get_current_music()
    motd = get_current_motd()

    window_mouse_desktop.update(
        {
            "ts": now,
            "session_info": session_info,
            "locked": session_info[
                "LockedHint"
            ],  # alternative: xscreensaver-command -time
            "screens": screens,
            "music": music,
            "motd": motd,
        }
    )
    print(json.dumps(window_mouse_desktop))


main()
