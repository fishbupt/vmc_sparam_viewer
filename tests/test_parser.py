import csv
import io
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from parser import parse_text, load_file, values, export_csv
ROOT = Path(__file__).resolve().parents[1]

class ParserTests(unittest.TestCase):
    def test_user_samples(self):
        a = load_file(ROOT / 'examples/pna_excerpt.s2p')
        b = load_file(ROOT / 'examples/pna_excerpt.s2px')
        self.assertEqual(a.count, 2)
        self.assertEqual(b.count, 1)
        self.assertEqual(list(a.axes), ['StimulusFreq'])
        self.assertEqual(b.axes['OutputFreq'][0], 5e9)
        self.assertTrue(any('21' in w and '2' in w for w in a.warnings))
        self.assertFalse(any(k.startswith('0/') for k in a.metadata))
        for p in a.s:
            # S2PX export rounds to six decimal places; not bit-identical.
            self.assertAlmostEqual(values(a.s[p], 'dB', a.segment)[0], values(b.s[p], 'dB', b.segment)[0], places=5)
            self.assertAlmostEqual(values(a.s[p], 'Phase', a.segment)[0], values(b.s[p], 'Phase', b.segment)[0], places=5)
    def test_asymmetric_order_and_wrapping(self):
        d = parse_text('# MHz S RI R 75\n1000 1 2 3 4\n5 6 7 8 ! end\n')
        self.assertEqual(d.s['S12'][0], 5+6j)
        self.assertEqual(d.s['S21'][0], 3+4j)
        self.assertEqual(d.axes['StimulusFreq'][0], 1e9)
    def test_ma(self):
        d = parse_text('# Hz S MA R 50\n1D9 2 90 3 0 4 -90 5 180')
        self.assertAlmostEqual(d.s['S11'][0].imag, 2)
        self.assertAlmostEqual(d.s['S22'][0].real, -5)
    def test_csv_column_reordering(self):
        text = (ROOT / 'examples/pna_excerpt.s2px').read_text()
        rows = list(csv.reader(l for l in text.splitlines() if not l.startswith('!')))
        # Keep InputFreq discoverable; reverse actual header/data layout.
        reordered = '\n'.join(','.join(reversed(row)) for row in rows)
        d = parse_text(reordered)
        self.assertEqual(d.axes['InputFreq'][0], 1e10)
        self.assertAlmostEqual(values(d.s['S22'], 'dB', d.segment)[0], 2.011589)
    def test_unwrap_segments_and_zero(self):
        z = np.exp(1j*np.deg2rad([170,-170,-170,170]))
        np.testing.assert_allclose(values(z,'Unwrapped',np.array([0,0,1,1])),[170,190,-170,-190])
        self.assertTrue(np.isnan(values(np.array([0j]),'Phase',np.array([0]))[0]))
    def test_bad_data(self):
        for text in ['# Hz S RI R 50\n1 2 3', '# Hz S RI R 50\n1 nan 0 1 0 1 0 1 0', '[Version] 2.0', '# Hz Y RI R 50\n1 1 0 1 0 1 0 1 0']:
            with self.assertRaises(ValueError):
                parse_text(text)
    def test_export(self):
        d = load_file(ROOT / 'examples/pna_excerpt.s2px')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.csv'
            export_csv(d,path)
            with path.open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(float(rows[0]['InputFreq (Hz)']),1e10)
            self.assertAlmostEqual(float(rows[0]['S21 Mag (dB)']),-.331859)

if __name__ == '__main__':
    unittest.main()
