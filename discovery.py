"""Serve recent Flea targets; only the transient worker talks to Omdrop."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time


UNIT = "flea-omdrop-discover.service"
PLUGIN = Path(__file__).resolve().with_name("plugin.py")
REFRESH_AFTER = 15
EXPIRE_AFTER = 120
MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")
# Bound both the row count and the UTF-8 size of Flea's single 64 KiB reply.
MAX_PEERS = 64
MAX_NAME_CHARS = 96
MESSAGES = {
    "scanning": "Looking for Omdrop devices. Reopen this menu in a moment.",
    "empty": "No named devices nearby. Open AirDrop on the recipient, then reopen this menu.",
    "off": "Omdrop is off. Run 'omdrop on', then reopen this menu.",
    "radio": "Omdrop's radio is unavailable. Check 'omdrop status'.",
    "missing": "Omdrop was not found. Install it to discover devices.",
    "failed": "Omdrop discovery failed. Check 'journalctl --user -u flea-omdrop-discover'.",
    "timeout": "Omdrop discovery timed out. Reopen this menu to try again.",
    "launcher": "Cannot start Omdrop discovery. Check the systemd user session.",
    "runtime": "Omdrop discovery needs a private XDG_RUNTIME_DIR.",
}


def _private(directory):
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise OSError("Not a private runtime directory")


def _cache_path():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    if not runtime.is_absolute():
        raise OSError("Missing absolute XDG_RUNTIME_DIR")
    _private(runtime)
    directory = runtime / "flea-omdrop"
    directory.mkdir(mode=0o700, exist_ok=True)
    _private(directory)
    return directory / "peers.json"


def _now():
    # An address seen just before suspending must expire during sleep too.
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def _peers(records):
    if not isinstance(records, list):
        raise ValueError("Expected Omdrop's peer array")
    peers = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        mac, name = rec.get("mac"), rec.get("name")
        if not isinstance(mac, str) or not MAC.fullmatch(mac) or not isinstance(name, str):
            continue
        name = "".join(c if c.isprintable() else " " for c in name[:MAX_NAME_CHARS]).strip()
        if name:
            peers.setdefault(mac.lower(), name)
            if len(peers) == MAX_PEERS:
                break
    return peers


def _read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return None
            data = json.loads(file.read(65537))
        if not isinstance(data, dict) or type(data.get("at")) not in (int, float):
            return None
        age = _now() - data["at"]
        if not 0 <= age <= EXPIRE_AFTER:
            return None
        state, peers = data["state"], _peers(data["peers"])
        if state == "ready" and peers or state in MESSAGES and not peers:
            return age, state, peers
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        pass
    return None


def _store(path, state, peers):
    data = {"at": _now(), "state": state,
            "peers": [{"mac": mac, "name": name} for mac, name in peers.items()]}
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as tmp:
        try:
            json.dump(data, tmp, ensure_ascii=False, separators=(",", ":"))
            tmp.flush()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


def _lookup():
    status = subprocess.run(["omdrop", "status", "--json"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, check=True, timeout=15)
    status = json.loads(status.stdout)
    if not isinstance(status, dict) or type(status.get("visible")) is not bool:
        return "radio", {}
    if not status["visible"]:
        return "off", {}
    listing = subprocess.run(["omdrop", "peers", "-n", "--json"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, timeout=120)
    # With the radio on, Omdrop also uses exit 1 with [] for an empty room.
    if listing.returncode == 1 and listing.stdout.strip() == b"[]":
        return "empty", {}
    listing.check_returncode()
    peers = _peers(json.loads(listing.stdout))
    return ("ready" if peers else "empty"), peers


def discover():
    path = _cache_path()
    try:
        state, peers = _lookup()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        state, peers = "missing", {}
    except subprocess.TimeoutExpired as exc:
        print(exc, file=sys.stderr)
        state, peers = "timeout", {}
    except (OSError, subprocess.CalledProcessError, ValueError, RecursionError) as exc:
        print(exc, file=sys.stderr)
        state, peers = "failed", {}
    _store(path, state, peers)
    return int(state in ("failed", "timeout", "missing", "radio"))


def _start():
    args = ["systemd-run", "--user", "--quiet", "--no-ask-password", "--no-block", "--collect",
            "--unit=" + UNIT, "--expand-environment=no", "--setenv=PATH", "--setenv=XDG_RUNTIME_DIR",
            "--property=RuntimeMaxSec=150s", "--property=StandardOutput=journal",
            "--property=StandardError=journal", "--", sys.executable, str(PLUGIN), "--discover"]
    try:
        child = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, env={**os.environ, "LC_ALL": "C"}, timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(exc, file=sys.stderr)
        return False
    # systemd serializes this fixed unit across all windows and plugin processes.
    if child.returncode == 0 or (UNIT.encode() in child.stderr and b"already" in child.stderr):
        return True
    sys.stderr.buffer.write(child.stderr)
    return False


def _offline(state):
    return [{"id": "omdrop-status", "label": MESSAGES[state], "state": "offline"}]


def targets():
    try:
        snapshot = _read(_cache_path())
    except OSError:
        return _offline("runtime")
    if (snapshot is None or snapshot[0] >= REFRESH_AFTER) and not _start():
        return _offline("launcher")
    if snapshot is None:
        return _offline("scanning")
    _, state, peers = snapshot
    if state != "ready":
        return _offline(state)
    return [{"id": mac, "label": f"{name} ({mac})", "state": "ready"}
            for mac, name in sorted(peers.items(), key=lambda item: (item[1].casefold(), item[0]))]


def known_target(address):
    if not isinstance(address, str) or not MAC.fullmatch(address):
        return False
    try:
        snapshot = _read(_cache_path())
    except OSError:
        return False
    return snapshot is not None and address in snapshot[2]
