#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
from typing import Literal, TypedDict

from colorama import Fore, init

init(autoreset=True)

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

TaskType = Literal["delete_file", "delete_registry"]

def task_cn(task: TaskType) -> str:
    return "delete files" if task == "delete_file" else "delete registry"


_SEP = "─" * 60
_SEP_THICK = "═" * 60


class TaskItem(TypedDict):
    task: TaskType
    kind: str
    path: str


def header(title: str, count: int) -> None:
    print()
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")
    print(f"{Fore.YELLOW}  {title}    {count} items")
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")


def item_line(index: int, task_tag: str, path: str) -> None:
    print(f"  [{index:>3}]  {task_tag:<16} {path}")


def _url_launcher(path: str) -> str | None:
    """Classify a .url file by URL scheme: 'steam' for steam://, 'epic' for
    com.epicgames.launcher://"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    txt: str | None = None
    for enc in ("utf-8-sig", "utf-16-le", "gbk"):
        try:
            txt = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if txt is None:
        txt = raw.decode("utf-8", errors="replace")
    for line in txt.splitlines():
        line = line.strip()
        if line.lower().startswith("url="):
            url = line[4:].strip()
            if "steam://" in url:
                return "steam"
            if "com.epicgames.launcher://" in url:
                return "epic"
            return None
    return None


def _scan_win_url_shortcuts(dirs: list[str], scheme: str) -> list[TaskItem]:
    items: list[TaskItem] = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".url"):
                continue
            info = _url_launcher(d + "\\" + fn)
            if info != scheme:
                continue
            items.append(
                {
                    "task": "delete_file",
                    "kind": "shortcut",
                    "path": d + "\\" + fn,
                }
            )
    return items


def _scan_win_uninstalls() -> list[TaskItem]:
    import winreg

    items: list[TaskItem] = []
    path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if not name.startswith("Steam App "):
                    continue
                items.append(
                    {
                        "task": "delete_registry",
                        "kind": "uninstall",
                        "path": f"{path}\\{name}",
                    }
                )
    except OSError:
        pass
    return items


def scan_windows() -> list[TaskItem]:
    items: list[TaskItem] = []
    desktops = [os.path.expanduser("~/Desktop")]
    appdata = os.environ.get("APPDATA", "")
    start_menu = [appdata + r"\Microsoft\Windows\Start Menu\Programs\Steam"]
    # Steam writes game shortcuts to the per-user desktop and Start Menu;
    # Epic writes only to the desktop (com.epicgames.launcher://).
    items += _scan_win_url_shortcuts(desktops, "steam")
    items += _scan_win_url_shortcuts(start_menu, "steam")
    items += _scan_win_url_shortcuts(desktops, "epic")
    items += _scan_win_uninstalls()
    return items


def _desktop_dir() -> str:
    """Resolve the desktop directory per the XDG spec (user-dirs.dirs)"""
    cfg = (
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        + "/user-dirs.dirs"
    )
    home = os.path.expanduser("~")
    try:
        with open(cfg, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("XDG_DESKTOP_DIR="):
                    v = line.split("=", 1)[1].strip().strip('"')
                    if not v:
                        break
                    return os.path.expanduser(v.replace("$HOME", home))
    except OSError:
        pass
    return home + "/Desktop"


def _desktop_entry(path: str) -> tuple[str, str]:
    """Read the Exec and Icon fields of a .desktop file."""
    exec_line, icon = "", ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Exec=") and not exec_line:
                    exec_line = line[5:].strip()
                elif line.startswith("Icon=") and not icon:
                    icon = line[5:].strip()
                if exec_line and icon:
                    break
    except OSError:
        pass
    return exec_line, icon


def _is_steam_exec(exec_line: str) -> bool:
    """Whether the .desktop Exec line launches a game via Steam (steam -applaunch / steam://rungameid)."""
    if re.search(r"steam\s+-applaunch\s+\d+", exec_line):
        return True
    if re.search(r"steam://rungameid/\d+", exec_line):
        return True
    return bool(re.search(r"steam\s+steam://rungameid/\d+", exec_line))


def _scan_icons(icon_names: list[str], data_home: str) -> list[TaskItem]:
    """Find icon-theme files whose basename matches the given icon names (steam_icon_<appid> etc.)."""
    icon_root = data_home + "/icons"
    names = sorted({n for n in icon_names if n})
    if not names or not os.path.isdir(icon_root):
        return []
    items: list[TaskItem] = []
    seen: set[str] = set()
    for dirpath, _dirs, filenames in os.walk(icon_root):
        for fn in filenames:
            base = os.path.splitext(fn)[0]
            if base not in names:
                continue
            path = dirpath + "/" + fn
            if path in seen:
                continue
            seen.add(path)
            items.append(
                {
                    "task": "delete_file",
                    "kind": "icon",
                    "path": path,
                }
            )
    return items


def scan_linux() -> list[TaskItem]:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    scan_dirs = [
        data_home + "/applications",
        _desktop_dir(),
    ]
    items: list[TaskItem] = []
    icon_names: list[str] = []
    for d in scan_dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".desktop"):
                continue
            path = d + "/" + fn
            exec_line, icon = _desktop_entry(path)
            if not _is_steam_exec(exec_line):
                continue
            if icon:
                icon_names.append(icon)
            items.append(
                {
                    "task": "delete_file",
                    "kind": "desktop",
                    "path": path,
                }
            )
    items += _scan_icons(icon_names, data_home)
    return items


def scan_macos() -> list[TaskItem]:
    apps_dir = os.path.expanduser("~/Applications")
    items: list[TaskItem] = []
    if not os.path.isdir(apps_dir):
        return items
    for name in sorted(os.listdir(apps_dir)):
        if not name.endswith(".app"):
            continue
        app = apps_dir + "/" + name
        if not os.path.isdir(app):
            continue
        runsh = app + "/Contents/MacOS/run.sh"
        if not os.path.isfile(runsh):
            continue
        try:
            with open(runsh, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        if "steam://" not in content:
            continue
        items.append(
            {
                "task": "delete_file",
                "kind": "app",
                "path": app,
            }
        )
    return items


def _delete_path(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _delete_reg_tree(path: str) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_ALL_ACCESS
    ) as key:
        while True:
            try:
                sub = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_reg_tree(path + "\\" + sub)
    winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, path)


def execute_tasks(selected: list[TaskItem]) -> dict[str, int | list[str]]:
    deleted_files = 0
    deleted_registry = 0
    failed: list[str] = []

    for it in selected:
        try:
            if it["task"] == "delete_registry":
                _delete_reg_tree(it["path"])
                deleted_registry += 1
                tag = task_cn("delete_registry")
            else:
                _delete_path(it["path"])
                deleted_files += 1
                tag = task_cn("delete_file")
            print(f"  [executed {tag}] {it['path']}")
        except OSError:
            failed.append(it["path"])

    if IS_LINUX and any(it["kind"] == "desktop" for it in selected):
        apps_dir = (
            os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        ) + "/applications"
        _ = subprocess.run(
            ["update-desktop-database", apps_dir], capture_output=True, check=False
        )

    return {
        "deleted": deleted_files + deleted_registry,
        "delete_file": deleted_files,
        "delete_registry": deleted_registry,
        "failed": failed,
    }


# ---------- main ----------
def main() -> None:
    if not (IS_WINDOWS or IS_MACOS or IS_LINUX):
        print(f"{Fore.RED}Unsupported OS: {sys.platform}")
        sys.exit(2)

    print()
    print(f"{Fore.CYAN}{_SEP_THICK}")
    print(f"{Fore.CYAN}  steam-ungarbage — cross-platform Steam link garbage cleaner")
    print(f"{Fore.CYAN}  platform: {sys.platform}")
    print(f"{Fore.CYAN}{_SEP_THICK}")

    print()
    if IS_WINDOWS:
        print(
            f"{Fore.YELLOW}Warning: deleting the HKLM uninstall entries requires administrator rights; "
            + "re-run as administrator if registry cleanup should succeed."
        )
        print()
    try:
        _ = input("Press Enter to start scanning (Ctrl+C to exit)")
    except (EOFError, KeyboardInterrupt):
        print("\nExited.")
        sys.exit(0)
    print()
    print(f"{Fore.CYAN}Scanning...")

    try:
        if IS_WINDOWS:
            items = scan_windows()
        elif IS_LINUX:
            items = scan_linux()
        else:
            items = scan_macos()
    except RuntimeError as e:
        print(f"{Fore.RED}Scan failed: {e}")
        sys.exit(1)

    print(f"{Fore.GREEN}Scan complete.")
    groups: dict[str, list[TaskItem]] = {}
    for it in items:
        groups.setdefault(it["task"], []).append(it)

    for task in ("delete_file", "delete_registry"):
        glist = groups.get(task, [])
        header(task_cn(task), len(glist))
        for i, it in enumerate(glist, 1):
            item_line(i, task_cn(task), it["path"])

    if not items:
        print()
        print(f"{Fore.GREEN}No Steam garbage found; nothing to clean.")
        return

    print()
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")
    print(
        f"{Fore.MAGENTA}  Found {len(items)} items: "
        + " + ".join(
            f"{len(groups[t])}x{task_cn(t)}"
            for t in ("delete_file", "delete_registry")
            if t in groups
        )
    )
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")

    try:
        confirm = input(f"Confirm cleaning (all {len(items)} items)? [y/N] ").strip()
    except (EOFError, KeyboardInterrupt):
        confirm = ""
    if not confirm.lower().startswith("y"):
        print("Cancelled; nothing was modified.")
        return

    print()
    print(f"{Fore.CYAN}{_SEP_THICK}")
    print(f"{Fore.CYAN}  Cleaning")
    print(f"{Fore.CYAN}{_SEP_THICK}")

    result = execute_tasks(items)

    print()
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")
    print(f"{Fore.GREEN}  Done: deleted {result['deleted']} items.")
    print(f"{Fore.MAGENTA}    {task_cn('delete_file')}: {result['delete_file']} items")
    print(
        f"{Fore.MAGENTA}    {task_cn('delete_registry')}: {result['delete_registry']} items"
    )
    failed_items = result["failed"]
    assert isinstance(failed_items, list)
    for f in failed_items:
        print(f"{Fore.RED}  Delete failed: {f}")
    print(f"{Fore.LIGHTBLACK_EX}{_SEP}")


if __name__ == "__main__":
    main()
