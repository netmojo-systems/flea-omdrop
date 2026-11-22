"""Hand off Flea sends to the user manager and report the actual Omdrop result."""

import fcntl
import html
import os
from pathlib import Path
import select
import subprocess
import sys
import uuid


_STDERR_LIMIT = 8192


def _run(argv, *, own_session=False):
    """Keep a bounded stderr tail without waiting on pipes inherited by grandchildren."""
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, start_new_session=own_session) as child:
        fd = child.stderr.fileno()
        tail = bytearray()
        pidfd = os.pidfd_open(child.pid)
        try:
            events = select.poll()
            events.register(fd, select.POLLIN)
            events.register(pidfd, select.POLLIN)
            while True:
                ready = dict(events.poll())
                if pidfd in ready:
                    # The command has exited. Collect only what is already buffered;
                    # a still-running helper may have inherited the write end.
                    os.set_blocking(fd, False)
                    try:
                        tail.extend(os.read(fd, fcntl.fcntl(fd, fcntl.F_GETPIPE_SZ))[-_STDERR_LIMIT:])
                    except BlockingIOError:
                        pass
                    break
                block = os.read(fd, _STDERR_LIMIT)
                if not block:
                    break
                tail.extend(block)
                del tail[:-_STDERR_LIMIT]
        finally:
            os.close(pidfd)
        return child.wait(), tail[-_STDERR_LIMIT:].decode('utf-8', errors='replace')


def _reason(stderr):
    for line in reversed(stderr.splitlines()):
        line = ''.join(c if c.isprintable() else ' ' for c in line).strip()
        if line and line != 'Cancelled.':
            return line[:400]
    return ''


def enqueue(mac, paths):
    """Return after systemd confirms exec, not after a transfer finishes."""
    argv = [
        'systemd-run', '--user', '--quiet', '--collect', '--no-ask-password',
        '--service-type=exec', '--expand-environment=no',
        '--setenv=PATH', '--setenv=XDG_RUNTIME_DIR',
        f'--unit=flea-omdrop-send-{uuid.uuid4().hex}', '--description=Flea Omdrop send',
        '--property=StandardOutput=journal', '--property=StandardError=journal',
        # systemd-run sends an argv vector via D-Bus, not an ExecStart= text
        # directive: % is already literal. The option above keeps $ literal too.
        '--', os.path.abspath(sys.executable), str(Path(__file__).resolve().with_name('plugin.py')),
        '--deliver', mac, *paths,
    ]
    code, stderr = _run(argv)
    if code:
        raise RuntimeError('Could not start the Omdrop send: ' +
                           (_reason(stderr) or f'systemd-run exited with status {code}.'))


def deliver(mac, paths):
    """Run as the service's main process. Notification failures never change its verdict."""
    count = len(paths)
    try:
        # When sending turns Omdrop on, the 1Password identity prompt needs
        # a live session leader. Let the CLI lead its own session until it exits.
        code, stderr = _run(['omdrop', 'send', f'--to={mac}', '--', *paths], own_session=True)
    except OSError as error:
        code, stderr = 1, str(error)
    if code == 0:
        title = 'Omdrop: sent'
        body = f'Sent {count} file{"" if count == 1 else "s"} to {mac}.'
    elif any(line.strip() == 'They declined it.' for line in stderr.splitlines()):
        title, body = 'Omdrop: declined', f'{mac} declined the transfer.'
    else:
        title = 'Omdrop: send failed'
        body = f'Could not send to {mac}: ' + (_reason(stderr) or f'omdrop exited with status {code}.')
    print(f'{title}: {body}', flush=True)
    try:
        subprocess.run(['notify-send', '--app-name=Flea', '--', title, html.escape(body)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        print(f'Could not show the Omdrop notification: {error}', file=sys.stderr)
    return int(code != 0)
