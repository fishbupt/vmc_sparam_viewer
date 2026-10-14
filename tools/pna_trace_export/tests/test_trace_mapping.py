import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_window_traces as tool


class FakeInstrument:
    def __init__(self, responses):
        self.responses = responses
        self.commands = []

    def query(self, command):
        self.commands.append(command)
        if command == 'SYST:ERR?':
            return '0,"No error"'
        value = self.responses[command]
        if isinstance(value, Exception):
            raise value
        return value


class TraceMappingTests(unittest.TestCase):
    def test_mapping_ignores_front_panel_state_and_other_windows(self):
        inst = FakeInstrument({'SYST:MEAS:CAT?': '"2,6,9"',
                               'SYST:MEAS2:WIND?': '2', 'SYST:MEAS2:TRAC?': '12',
                               'SYST:MEAS6:WIND?': '2', 'SYST:MEAS6:TRAC?': '3',
                               'SYST:MEAS9:WIND?': '1'})
        self.assertEqual(tool.window_measurements(inst, 2), {12: 2, 3: 6})
        self.assertFalse(any('ACT:' in c for c in inst.commands))

    def test_channel_zero_never_sends_calc(self):
        inst = FakeInstrument({'SYST:MEAS2:CHAN?': '0'})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, '无效通道 0'):
                tool.export_trace(inst, 2, 12, Path(directory), measurement=2)
        self.assertFalse(any(c.startswith('CALC') for c in inst.commands))

    def test_export_uses_explicit_channel_and_preserves_complex_data(self):
        inst = FakeInstrument({'SYST:MEAS6:CHAN?': '3',
                               'CALC3:MEAS6:PAR?': '"a2/b2,1"',
                               'SENS3:SWE:TYPE?': 'LIN',
                               'CALC3:MEAS6:EQU:STAT?': '0',
                               'CALC3:MEAS6:DATA:X?': '18000000000,19000000000',
                               'CALC3:MEAS6:DATA:SDATA?': '0.1,-0.2,0.3,0.4'})
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            record = tool.export_trace(inst, 2, 3, Path(directory), measurement=6)
            self.assertEqual(record['file'], 'Tr6_a2_over_b2,1.s1p')
            text = (Path(directory) / record['file']).read_text()
            rows = [list(map(float, l.split())) for l in text.splitlines() if not l.startswith(('!', '#'))]
            self.assertEqual(rows, [[18e9, .1, -.2], [19e9, .3, .4]])

    def test_query_failure_keeps_command_and_does_not_query_error_queue(self):
        inst = FakeInstrument({'CALC3:MEAS6:PAR?': TimeoutError('timeout')})
        with self.assertRaisesRegex(tool.ScpiTransportError, 'CALC3:MEAS6:PAR'):
            tool.query(inst, 'CALC3:MEAS6:PAR?')
        self.assertEqual(inst.commands, ['CALC3:MEAS6:PAR?'])


if __name__ == '__main__':
    unittest.main()
