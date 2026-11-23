"""Render Omdrop's byte counters without slowing the stderr reader."""

import html
import os
import re
import subprocess
import sys
import threading
import time


_STEP = re.compile(rb'\r([0-9]{1,20}) / ([0-9]{1,20}) bytes')


def amount(value):
    for unit, scale in [('GiB', 1 << 30), ('MiB', 1 << 20), ('KiB', 1 << 10)]:
        if value >= scale:
            return f'{value / scale:.1f} {unit}'
    return f'{value} B'


class Notification:
    def __init__(self, paths):
        self.label = os.path.basename(paths[0]) if len(paths) == 1 else f'{len(paths)} files'
        self.tail = b''
        self.id = 0
        self.latest = None
        self.closed = False
        self.condition = threading.Condition()
        self.thread = None

    def feed(self, block):
        data = self.tail + block
        step = None
        end = 0
        for match in _STEP.finditer(data):
            end = match.end()
            sent, total = map(int, match.groups())
            if 0 <= sent <= total and total:
                step = sent, total
        self.tail = data[max(end, len(data) - 64):]
        if step is None:
            return
        with self.condition:
            self.latest = step
            if self.thread is None:
                self.thread = threading.Thread(target=self._update)
                self.thread.start()
            self.condition.notify()

    def _show(self, title, body, options=()):
        try:
            reply = subprocess.run(['notify-send', '--app-name=Flea', '--print-id',
                                    f'--replace-id={self.id}', *options, '--', title, html.escape(body)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   text=True, timeout=3, check=True)
            self.id = int(reply.stdout.strip())
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f'Could not show Omdrop notification: {exc}', file=sys.stderr)

    def _update(self):
        next_update = 0
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.latest is not None)
                if self.closed:
                    return
                delay = next_update - time.monotonic()
                if delay > 0:
                    self.condition.wait_for(lambda: self.closed, timeout=delay)
                    if self.closed:
                        return
                sent, total = self.latest
                self.latest = None
            pct = sent * 100 // total
            bar = '▰' * (pct // 10) + '▱' * (10 - pct // 10)
            self._show('Omdrop · sending', f'{bar}  {pct}%\n{self.label} · {amount(sent)} of {amount(total)}',
                       ('--transient', '--expire-time=30000', f'--hint=int:value:{pct}'))
            next_update = time.monotonic() + 1

    def finish(self, title, body):
        with self.condition:
            self.closed = True
            self.condition.notify()
        if self.thread is not None:
            self.thread.join()
        self._show(title, body)
