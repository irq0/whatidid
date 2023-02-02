#!/usr/bin/env python3
import json
import logging
import pathlib
import re

import click
import dateutil.parser
import rich.logging
import sqlite_utils
import tqdm

LOG = logging.getLogger("whatidid")


@click.group()
@click.version_option()
@click.option("--debug/--no-debug", default=False)
def cli(debug):
    "Save data from capture_what_i_do.py JSON to a SQLite database"
    loglevel = [logging.INFO, logging.DEBUG][int(debug)]
    logging.basicConfig(
        level=loglevel,
        format="%(message)s",
        datefmt="[%Y-%m-%d %H:%M:%S]",
        handlers=[rich.logging.RichHandler(rich_tracebacks=True)],
    )


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(
        file_okay=True, dir_okay=False, allow_dash=False, path_type=pathlib.Path
    ),
    required=True,
)
@click.argument(
    "files",
    type=click.Path(
        file_okay=True, dir_okay=False, allow_dash=False, path_type=pathlib.Path
    ),
    required=True,
    nargs=-1,
)
def convert(db_path: pathlib.Path, files: list[pathlib.Path]):
    db = sqlite_utils.Database(db_path)
    for file in files:
        filesize = file.stat().st_size
        with open(file) as fd:
            t = tqdm.tqdm(total=filesize, unit="B", unit_scale=True)
            for row in fd:
                t.update(len(row))
                data = json.loads(row)

                try:
                    screen = next(
                        screen
                        for screen in data["screens"]
                        if screen["id"] == data["mouse"]["screen"]
                    )
                    active_screen = {
                        "primary": screen["primary"],
                        "name": screen["name"],
                        "res_x": int(screen["res_x"]),
                        "res_y": int(screen["res_y"]),
                        "off_x": int(screen["off_x"]),
                        "off_y": int(screen["off_y"]),
                    }
                except StopIteration:
                    active_screen = {
                        "primary": False,
                        "name": "no screen connected",
                        "res_x": 0,
                        "res_y": 0,
                        "off_x": 0,
                        "off_y": 0,
                    }

                title: str = data["title"]
                command = data["comm"]
                thing = None
                file_name = None

                # correct flatpak weirdness
                if command == "kthreadd" and title.endswith("Slack"):
                    command = "slack"
                elif command == "kthreadd" and title.endswith("Microsoft Teams"):
                    command = "teams"
                elif command == "netns" and "Spotify" in title:
                    command = "spotify"

                # extract things from title
                if command == "emacs":
                    # correct bug ;)
                    title = title.replace("⋄'xb", "⋄")
                    try:
                        buffer, file_name = title.split("⋄")
                        if file_name.strip():
                            thing = file_name.strip()
                        else:
                            thing = buffer.strip()
                    except ValueError:
                        LOG.warning(f"emacs title not splittable: {title}")
                elif command == "slack":
                    try:
                        match = re.search(r"(.+)\s-\s(.+)\s-\sSlack", title)
                        if match:
                            groups = match.groups()
                            thing = groups[0].strip()
                    except AttributeError:
                        LOG.warning(f"slack title extract error: {title}")
                elif command in ("vivaldi-bin", "chrome"):
                    thing = title[: title.rfind("-")].strip()
                elif command == "firefox":
                    thing = title[: title.rfind("—")].strip()
                elif command == "okular":
                    thing = title[: title.rfind("—")].strip()

                motd = None
                active_task = None
                if data["motd"]:
                    motd = data["motd"]
                    try:
                        active_task = re.search(r"\((.+)\)", motd).group(1)
                    except Exception:
                        LOG.exception(f"motd extract error: {motd}")

                category = None
                if not thing:
                    pass
                elif (
                    (command == "emacs" and re.search(r"mu4e|home/seri/Mail", thing))
                    or command == "slack"
                    or (
                        command == "chrome"
                        and re.search(r"Outlook|Microsoft Teams", thing)
                        and "Calendar" not in thing
                    )
                ):
                    category = "communication"
                elif re.search(
                    r"GitHub|Stack Overflow|PyPI|WORKSPACE/|/compile/|magit",
                    thing,
                ):
                    category = "devel"

                try:
                    db["log"].insert(
                        {
                            "window_title": title,
                            "ts": dateutil.parser.isoparse(data["ts"]),
                            "command": command,
                            "thing": thing,
                            "motd": motd,
                            "category": category,
                            "active_task": active_task,
                            "desktop": int(data["desktop"] or -1),
                            "mouse_x": int(data["mouse"]["x"] or -1),
                            "mouse_y": int(data["mouse"]["y"] or -1),
                            "nscreens": len(data["screens"]),
                            "focus_screen": db["screens"].lookup(active_screen),
                            "locked": data["locked"],
                            "music_playing": data["music"]["playing"],
                            "music_app": data["music"]["app"],
                            "music_playback": data["music"]["playback"].strip() or None,
                            "music_extra": data["music"].get("extra", None),
                        },
                        pk="ts",
                    )
                except TypeError:
                    LOG.exception(f"insert failed:\nrow:\n{data}")
    for i in ("window_title", "command", "thing", "motd", "category", "active_task"):
        db["log"].create_index((i,))


if __name__ == "__main__":
    cli(obj={})
