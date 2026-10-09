import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from characterization import (Options, characterize, parse_s1p, sample_standard,
                               export_s2p, export_bundle, s2px_text)
from parser import load_file, parse_text
from comparison import compare


def write_s1p(path, f, g, z0=50):
    path.write_text(f'# Hz S RI R {z0}\n'+''.join(f'{a:.17g} {z.real:.17g} {z.imag:.17g}\n' for a,z in zip(f,g)))

def write_s2p(path, f, m, z0=50):
    path.write_text(f'# Hz S RI R {z0}\n'+''.join(f'{a:.17g} {z.real:.17g} {z.imag:.17g} 0 0 0 0 0 0\n' for a,z in zip(f,m)))

class CharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.f = np.linspace(10e9, 20e9, 41); self.fi = self.f-5e9
        x=(self.f-10e9)/1e10
        self.d=.05*np.exp(1j*(.3+.6*x)); self.s=.08*np.exp(1j*(-.4+.7*x))
        self.t=.9*np.exp(-2j*np.pi*(self.f-1e10)*20e-12)
        self.c11=.12*np.exp(1j*(.4+.9*x));self.c22=.1*np.exp(1j*(-.7+1.1*x))
        self.c21=10**(-6/20)*np.exp(-2j*np.pi*(self.f-1e10)*80e-12)
        self.mp=[self.root/f'm{i}.s2p' for i in range(6)]
        self.sp=[self.root/f'g{i}.s1p' for i in range(6)]
        self.build()
    def tearDown(self): self.tmp.cleanup()
    def build(self, ideal=False, corrected=False):
        for i in range(6):
            freq=self.f if i<3 else self.fi
            if ideal:g=np.full(41,[1,-1,0][i%3],complex)
            elif i%3==0:g=.99*np.exp(-2j*np.pi*freq*18e-12)
            elif i%3==1:g=-.98*np.exp(-2j*np.pi*freq*16e-12)
            else:g=.02*np.exp(1j*(.2+freq/2e10))
            write_s1p(self.sp[i],freq,g)
            measured=[]
            # Independent forward wave-system solve; not inverse formulas.
            for k,gk in enumerate(g):
                if i<3:
                    mat=np.array([[1,-self.t[k]*gk],[0,1-self.s[k]*gk]],complex)
                    m=np.linalg.solve(mat,[self.d[k],self.t[k]])[0]
                elif corrected:
                    mat=np.array([[1,-self.c21[k]*gk],[0,1-self.c22[k]*gk]],complex)
                    m=np.linalg.solve(mat,[self.c11[k],self.c21[k]])[0]
                else:
                    mat=np.array([[1,0,-self.t[k],0],[0,1,-self.s[k],0],
                                  [0,-self.c11[k],1,-self.c21[k]*gk],
                                  [0,-self.c21[k],0,1-self.c22[k]*gk]],complex)
                    m=np.linalg.solve(mat,[self.d[k],self.t[k],0,0])[0]
                measured.append(m)
            write_s2p(self.mp[i],self.f,measured)
    def solve(self,**kwargs):return characterize(self.mp,self.sp,Options(**kwargs))
    def check_truth(self,r):
        for p,z in [('S11',self.c11),('S22',self.c22),('S21',self.c21),('S12',self.c21)]:
            np.testing.assert_allclose(r.dataset.s[p],z,rtol=1e-12,atol=1e-13)
        self.assertLess(max(r.diagnostics['Two_path_complex_difference']),1e-13)
    def test_nonideal_two_frequency_axes(self):
        r=self.solve(standard_sampling='linear_ri');self.check_truth(r)
        np.testing.assert_allclose(r.terms['D1'],self.d,atol=1e-14)
        np.testing.assert_allclose(r.terms['R1'],self.t**2,atol=1e-14)
    def test_ideal_and_continuous_root(self):
        self.build(ideal=True);r=self.solve();self.check_truth(r)
        phase=np.rad2deg(np.unwrap(np.angle(r.dataset.s['S21'])))
        self.assertAlmostEqual(phase[-1],-288,places=10)
    def test_corrected_second_round_no_double_correction(self):
        self.build(corrected=True);r=self.solve(second_round='corrected');self.check_truth(r)
        wrong=self.solve(second_round='raw')
        self.assertGreater(max(abs(wrong.dataset.s['S11']-self.c11)),.01)
    def test_global_sign_preserves_product(self):
        r=self.solve(root_sign=-1)
        np.testing.assert_allclose(r.dataset.s['S21'],-self.c21,atol=1e-13)
        np.testing.assert_allclose(r.dataset.s['S12']*r.dataset.s['S21'],self.c21**2,atol=1e-13)
    def test_export_roundtrip_and_comparison(self):
        r=self.solve();p=self.root/'own.s2p';export_s2p(r,p);d=load_file(p)
        comparison=compare(r.dataset,d,axis='StimulusFreq')
        self.assertEqual(len(comparison.i),41)
        self.assertLess(max(comparison.delta['S11']['复数差模值']),1e-15)
        x=parse_text(s2px_text(r),'own.s2px')
        np.testing.assert_allclose(x.axes['OutputFreq'],self.fi)
        self.assertLess(max(compare(d,x).delta['S21']['复数差模值']),1e-14)
        p=self.root/'record.zip';export_bundle(r,p)
        with zipfile.ZipFile(p) as z:
            manifest=json.loads(z.read('characterization_report.json'))
            self.assertEqual(manifest['second_round'],'raw')
            self.assertEqual(len(manifest['inputs']),6)
            rows=list(csv.DictReader(z.read('sol_diagnostics.csv').decode('utf-8-sig').splitlines()))
            self.assertEqual(len(rows),41)
            self.assertIn('output_open_Gamma_Real',rows[0])
    def test_wrong_output_standard_frequency_is_rejected(self):
        # Using RF definitions alone leaves required low IF frequencies out of band.
        self.sp[3]=self.sp[0]
        with self.assertRaisesRegex(ValueError,'禁止外推'):self.solve()
    def test_frequency_grid_mismatch(self):
        d=load_file(self.mp[5]);write_s2p(self.mp[5],self.f+1,d.s['S11'])
        with self.assertRaisesRegex(ValueError,'网格必须一致'):self.solve()
    def test_reference_impedance_mismatch(self):
        p=self.sp[1];p.write_text(p.read_text().replace('R 50','R 75'))
        with self.assertRaisesRegex(ValueError,'参考阻抗不一致'):self.solve()
    def test_degenerate_standards(self):
        write_s1p(self.sp[1],self.f,parse_s1p(self.sp[0].read_text()).gamma)
        with self.assertRaisesRegex(ValueError,'退化/病态'):self.solve()
    def test_invalid_options(self):
        with self.assertRaises(ValueError):self.solve(lo_hz=11e9)
        with self.assertRaises(ValueError):self.solve(root_sign=0)
    def test_standard_formats_interpolation_and_boundaries(self):
        for text,expected in [('# GHz S DB R 50\n5 -6 90\n',1j*10**(-6/20)),
                              ('# MHz S MA R 50\n5000 .5 -90\n',-.5j),
                              ('# Hz S RI R 50\n5D9 .1 -.2\n',.1-.2j)]:
            self.assertAlmostEqual(parse_s1p(text).gamma[0],expected)
        s=parse_s1p('# Hz S RI R 50\n0 1 0\n10 0 1\n')
        v,n=sample_standard(s,np.array([0,5,10]),tolerance=.001)
        np.testing.assert_allclose(v,[1,.5+.5j,1j]);self.assertEqual(n,1)
        with self.assertRaisesRegex(ValueError,'未知'):sample_standard(s,np.array([5]),method='exact')
        with self.assertRaisesRegex(ValueError,'禁止外推'):sample_standard(s,np.array([11]))
        with self.assertRaisesRegex(ValueError,'重复频点'):parse_s1p('# Hz S RI R 50\n1 1 0\n1 0 1\n')
        with self.assertRaisesRegex(ValueError,'多个'):sample_standard(s,np.array([5]),tolerance=6)

if __name__=='__main__':unittest.main()
