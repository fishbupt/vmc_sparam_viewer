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

    def write(self, command):
        self.commands.append(command)


class TraceMappingTests(unittest.TestCase):
    def test_activates_window_and_trace_then_verifies_readback(self):
        inst = FakeInstrument({'*OPC?': '1', 'SYST:ACT:WIND?': '2'})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.activate_window(inst, 2, 12), 2)
        operations = [c for c in inst.commands if c != 'SYST:ERR?']
        self.assertEqual(operations, ['SYST:ACT:WIND 2', 'DISP:WIND2:TRAC12:SEL',
                                      '*OPC?', 'SYST:ACT:WIND?'])

    def test_rejects_window_activation_mismatch(self):
        inst = FakeInstrument({'*OPC?': '1', 'SYST:ACT:WIND?': '1'})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, '请求 2，回读 1'):
            tool.activate_window(inst, 2, 12)

    def test_channel_zero_never_sends_calc(self):
        inst = FakeInstrument({'SYST:MEAS2:CHAN?': '0', '*OPC?': '1',
                               'SYST:ACT:WIND?': '2', 'SYST:ACT:MEAS:NUMB?': '2'})
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, '无效通道 0'):
                tool.export_trace(inst, 2, 12, Path(directory))
        self.assertFalse(any(c.startswith('CALC') for c in inst.commands))

    def test_export_uses_explicit_channel_and_preserves_complex_data(self):
        inst = FakeInstrument({'SYST:MEAS6:CHAN?': '3',
                               '*OPC?': '1', 'SYST:ACT:WIND?': '2',
                               'SYST:ACT:MEAS:NUMB?': '6',
                               'CALC3:MEAS6:PAR?': '"a2/b2,1"',
                               'SENS3:SWE:TYPE?': 'LIN',
                               'CALC3:MEAS6:EQU:STAT?': '0',
                               'CALC3:MEAS6:DATA:X?': '18000000000,19000000000',
                               'CALC3:MEAS6:DATA:SDATA?': '0.1,-0.2,0.3,0.4'})
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            record = tool.export_trace(inst, 2, 3, Path(directory))
            self.assertEqual(record['file'], 'Tr6_a2_over_b2,1.s1p')
            text = (Path(directory) / record['file']).read_text()
            rows = [list(map(float, l.split())) for l in text.splitlines() if not l.startswith(('!', '#'))]
            self.assertEqual(rows, [[18e9, .1, -.2], [19e9, .3, .4]])
        self.assertIn('DISP:WIND2:TRAC3:SEL', inst.commands)
        self.assertFalse(any(c == 'SYST:MEAS:CAT?' or c.endswith(':WIND?')
                             and c.startswith('SYST:MEAS') for c in inst.commands))

    def test_invalid_active_measurement_never_queries_channel(self):
        inst = FakeInstrument({'*OPC?': '1', 'SYST:ACT:WIND?': '2',
                               'SYST:ACT:MEAS:NUMB?': '0'})
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, '有效测量编号'):
                tool.export_trace(inst, 2, 12, Path(directory))
        self.assertFalse(any(c.endswith(':CHAN?') for c in inst.commands))

    def test_query_failure_keeps_command_and_does_not_query_error_queue(self):
        inst = FakeInstrument({'CALC3:MEAS6:PAR?': TimeoutError('timeout')})
        with self.assertRaisesRegex(tool.ScpiTransportError, 'CALC3:MEAS6:PAR'):
            tool.query(inst, 'CALC3:MEAS6:PAR?')
        self.assertEqual(inst.commands, ['CALC3:MEAS6:PAR?'])


if __name__ == '__main__':
    unittest.main()
