import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_window_traces as tool


class FakeInstrument:
    def __init__(self, responses):
        self.responses = responses
        self.commands = []

    def query(self, command):
        self.commands.append(command)
        value = self.responses[command]
        if isinstance(value, Exception):
            raise value
        return value

    def write(self, command):
        self.commands.append(command)


class TraceExportTests(unittest.TestCase):
    def test_minimal_export_uses_channel_one_and_preserves_complex_data(self):
        inst = FakeInstrument({'SYST:ACT:MEAS:NUMB?': '6',
                               'CALC1:MEAS6:DATA:X?': '18000000000,19000000000',
                               'CALC1:MEAS6:DATA:SDATA?': '0.1,-0.2,0.3,0.4'})
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            record = tool.export_trace(inst, 2, 3, Path(directory))
            self.assertEqual(record['file'], 'Tr6.s1p')
            self.assertIsNone(record['parameter'])
            self.assertEqual(record['channel'], 1)
            text = (Path(directory) / record['file']).read_text()
            rows = [list(map(float, line.split())) for line in text.splitlines()
                    if not line.startswith(('!', '#'))]
            self.assertEqual(rows, [[18e9, .1, -.2], [19e9, .3, .4]])
        self.assertEqual(inst.commands, ['DISP:WIND2:TRAC3:SEL',
                                        'SYST:ACT:MEAS:NUMB?',
                                        'CALC1:MEAS6:DATA:X?', 'CALC1:MEAS6:DATA:SDATA?'])

    def test_query_failure_keeps_command(self):
        inst = FakeInstrument({'CALC1:MEAS6:DATA:X?': TimeoutError('timeout')})
        with self.assertRaisesRegex(tool.ScpiTransportError, 'CALC1:MEAS6:DATA:X'):
            tool.query(inst, 'CALC1:MEAS6:DATA:X?')
        self.assertEqual(inst.commands, ['CALC1:MEAS6:DATA:X?'])


if __name__ == '__main__':
    unittest.main()
