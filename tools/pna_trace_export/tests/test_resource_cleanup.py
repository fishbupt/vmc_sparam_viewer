"""不支持上下文管理器的 VISA 对象也必须正确关闭。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_window_traces as tool


class ResourceCleanupTests(unittest.TestCase):
    def run_export(self, failure=None):
        closed = []

        class Instrument:
            def query(self, command):
                if failure == 'query' and command == '*IDN?':
                    raise RuntimeError('query failed')
                return {'*IDN?': 'Fake PNA', 'SYST:ERR?': '0,"No error"',
                        'DISP:WIND2:CAT?': '12', 'FORM:DATA?': 'REAL,64',
                        'SYST:MEAS:CAT?': '6', 'SYST:MEAS6:WIND?': '2',
                        'SYST:MEAS6:TRAC?': '12', '*OPC?': '1',
                        'SYST:ACT:WIND?': '2'}[command]

            def write(self, command):
                pass

            def close(self):
                closed.append('instrument')

        class Manager:
            def open_resource(self, address):
                if failure == 'connect':
                    raise RuntimeError('connect failed')
                return Instrument()

            def close(self):
                closed.append('manager')

        visa = types.SimpleNamespace(ResourceManager=Manager,
                                     errors=types.SimpleNamespace(VisaIOError=OSError))
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(sys.modules, pyvisa=visa), \
                    patch.object(sys, 'argv', ['export', '--output', directory]), \
                    patch.object(tool, 'export_trace', return_value={'file': 'Tr6_S21.s1p', 'points': 2}), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = tool.main()
            report = json.loads(next(Path(directory).glob('*/manifest.json')).read_text())
        return code, closed, report

    def test_success_without_context_manager_protocol(self):
        code, closed, report = self.run_export()
        self.assertEqual(code, 0)
        self.assertEqual(closed, ['instrument', 'manager'])
        self.assertEqual(len(report['traces']), 1)

    def test_query_failure_closes_both_resources(self):
        code, closed, report = self.run_export('query')
        self.assertEqual(code, 1)
        self.assertEqual(closed, ['instrument', 'manager'])
        self.assertIn('query failed', report['errors'][0]['error'])

    def test_connection_failure_closes_manager(self):
        code, closed, report = self.run_export('connect')
        self.assertEqual(code, 1)
        self.assertEqual(closed, ['manager'])
        self.assertIn('connect failed', report['errors'][0]['error'])


if __name__ == '__main__':
    unittest.main()
