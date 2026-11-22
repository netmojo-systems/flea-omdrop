#!/usr/bin/python3
"""Exercise the installed Flea and systemd user manager without using the radio."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MAC = 'aa:bb:cc:dd:ee:01'


def script(path, body):
    path.write_text(body)
    path.chmod(0o755)


def main(work):
    tools = work / 'bin'
    tools.mkdir()
    runtime = work / 'runtime'
    runtime.mkdir(mode=0o700)
    (runtime / 'systemd').symlink_to(Path(os.environ['XDG_RUNTIME_DIR']) / 'systemd')
    bus = os.environ.get('DBUS_SESSION_BUS_ADDRESS', 'unix:path=' + os.environ['XDG_RUNTIME_DIR'] + '/bus')
    env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(work / 'config'), XDG_CACHE_HOME=str(work / 'cache'),
               XDG_DATA_HOME=str(work / 'data'), XDG_STATE_HOME=str(work / 'state'),
               DBUS_SESSION_BUS_ADDRESS=bus)
    # Use the real manager but never contend with an active desktop discovery.
    script(tools / 'systemd-run', f'''#!/usr/bin/python3
import os, sys
args = [s.replace('--unit=flea-omdrop-discover.service', '--unit={work.name}-discover.service') for s in sys.argv[1:]]
os.execv('/usr/bin/systemd-run', ['systemd-run', *args])
''')
    script(tools / 'omdrop', f'''#!/usr/bin/python3
import json, sys, time
from pathlib import Path
work = Path({str(work)!r})
if sys.argv[1] == 'status':
    print(json.dumps(dict(receiving=True, visible=True, name='Fixture', visibility='contacts')))
elif sys.argv[1] == 'peers':
    assert '-n' in sys.argv and '--json' in sys.argv
    row = dict(mac={MAC!r}, name='Delayed receiver')
    print(json.dumps(row if '--stream' in sys.argv else [row]))
elif sys.argv[1] == 'send':
    (work / 'offer').write_text(json.dumps(sys.argv[2:]))
    time.sleep(35)
    (work / 'received').write_bytes(Path(sys.argv[-1]).read_bytes())
else:
    sys.exit(2)
''')
    script(tools / 'notify-send', f'#!/usr/bin/python3\nfrom pathlib import Path\nimport sys\nPath({str(work / "notice")!r}).write_text(repr(sys.argv))\n')
    src = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    for args in [('add', str(src)), ('enable', 'netmojo.omdrop')]:
        subprocess.run(['flea', 'plugin', *args], check=True, env=env)
    def call(req):
        wire = dict(c='plugins', op='runtime', id=1, plugin='netmojo.omdrop', request=req)
        with subprocess.Popen(['flea', '--backend'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, env=env) as host:
            host.stdin.write(json.dumps(wire) + '\n')
            host.stdin.flush()
            try:
                for line in host.stdout:
                    response = json.loads(line)
                    if response.get('t') == 'pluginruntime':
                        assert response['ok'], response
                        return response['message']
                raise AssertionError('Backend exited without a reply')
            finally:
                host.stdin.close()
    until = time.monotonic() + 20
    while not any(t['id'] == MAC for t in call({'op':'targets'})['targets']):
        if time.monotonic() > until:
            raise AssertionError('No fixture target appeared')
        time.sleep(.5)
    selection = work / '- selected $HOME %n.txt'
    selection.write_text('Flea delayed transfer test\n')
    start = time.monotonic()
    reply = call(dict(op='send', target=MAC, paths=[str(selection)]))
    queued = time.monotonic() - start
    assert reply['op'] == 'done' and queued < 30 and not (work / 'received').exists(), reply
    print(f'Flea returned after {queued:.2f}s; backend exited before simulated acceptance.', flush=True)
    while not (work / 'notice').exists() and time.monotonic() - start < 50:
        time.sleep(.2)
    assert json.loads((work / 'offer').read_text()) == [f'--to={MAC}', '--', str(selection)]
    assert (work / 'received').read_bytes() == selection.read_bytes()
    assert (work / 'notice').exists()
    print(f'Delivered after {time.monotonic()-start:.2f}s; exact file and target preserved.')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='flea-omdrop-test-') as directory:
        main(Path(directory))
