#!/usr/bin/python3
import json
import os
import sys

import delivery
import discovery


MAX_LINE = 65536


def dispatch(request):
    op = request.get("op")
    if op == "targets":
        return {"op": "targets", "targets": discovery.targets()}
    if op == "send":
        target, paths = request.get("target"), request.get("paths")
        if not isinstance(target, str) or not discovery.known_target(target):
            raise ValueError("This device is no longer listed. Reopen the file menu to refresh.")
        if (not isinstance(paths, list) or not 1 <= len(paths) <= 512 or
                not all(isinstance(p, str) and os.path.isabs(p) and '\0' not in p for p in paths)):
            raise ValueError("Select one or more local files.")
        delivery.enqueue(target, paths)
        return {"op": "done", "message": "Queued for Omdrop. A notification will report the result."}
    if op == "settings":
        return {"op": "done"}
    raise ValueError("Unsupported plugin operation.")


def serve():
    ready = False
    while line := sys.stdin.buffer.readline(MAX_LINE + 1):
        if len(line) > MAX_LINE:
            return 1
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("Expected a request object.")
            if req.get("op") == "cancel":
                return 0
            if not ready:
                if req.get("op") != "hello" or req.get("protocolVersion") != 1:
                    return 1
                reply = {"op": "ready", "protocolVersion": 1}
                ready = True
            else:
                reply = dispatch(req)
        except (ValueError, OSError, RuntimeError) as exc:
            reply = {"op": "error", "message": str(exc)[:512] or "Omdrop request failed."}
        print(json.dumps(reply, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(serve())
    if args == ["--discover"]:
        sys.exit(discovery.discover())
    if len(args) >= 3 and args[0] == "--deliver":
        sys.exit(delivery.deliver(args[1], args[2:]))
    sys.exit("Unexpected arguments.")
