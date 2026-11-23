#!/usr/bin/python3
"""Drive the real send worker with a split stderr record and a recording notifier."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / 'plugin.py'


class ProgressTest(unittest.TestCase):
    def run_send(self, exit_code):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            tools = {
                'notify-send': '''import json, os, sys
with open(os.environ['NOTICE'], 'a') as f:
    print(json.dumps(sys.argv[1:]), file=f)
print(73)
''',
                'omdrop': '''import os, sys, time
os.write(2, b'\\r1 / ')
time.sleep(.05)
os.write(2, b'4 bytes')
end = time.monotonic() + 5
while not os.path.exists(os.environ['NOTICE']) and time.monotonic() < end:
    time.sleep(.01)
os.write(2, b'\\r4 / 4 bytes\\n')
if os.environ['RC'] != '0':
    os.write(2, b'The transfer failed.\\n')
sys.exit(int(os.environ['RC']))
'''}
            for name, source in tools.items():
                item = root / name
                item.write_text('#!/usr/bin/python3\n' + source)
                item.chmod(0o755)
            log = root / 'notices'
            env = dict(os.environ, PATH=path + ':' + os.environ['PATH'], RC=str(exit_code), NOTICE=str(log))
            result = subprocess.run([PLUGIN, '--deliver', 'aa:bb:cc:dd:ee:ff', '/tmp/<photo>.png'],
                                    env=env, timeout=12, capture_output=True)
            self.assertEqual(result.returncode, exit_code, result.stderr)
            return [json.loads(line) for line in log.read_text().splitlines()]

    def test_progress_is_replaced_by_confirmed_delivery(self):
        first, *middle, last = self.run_send(0)
        self.assertIn('--hint=int:value:25', first)
        self.assertIn('&lt;photo&gt;.png · 1 B of 4 B', first[-1])
        self.assertIn('--replace-id=73', last)
        self.assertEqual(last[-2], 'Omdrop: sent')

    def test_full_byte_count_does_not_mask_failure(self):
        last = self.run_send(1)[-1]
        self.assertIn('--replace-id=73', last)
        self.assertEqual(last[-2], 'Omdrop: send failed')
        self.assertIn('The transfer failed.', last[-1])


if __name__ == '__main__':
    unittest.main()
