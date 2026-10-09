from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from characterization import Standard, sample_standard, characterize, Options, SAMPLING_METHODS
from parser import load_file

ROOT=Path(__file__).resolve().parents[1]

class SharedKitSamplingTests(unittest.TestCase):
    def test_shared_kit_two_frequency_axes_and_legacy_equivalence(self):
        d=ROOT/'examples/characterization_demo'
        measurements=[d/f'{r:02d}_{prefix}_SOL_{kind}.s2p' for r,prefix in [(1,'Input'),(2,'Mixer')] for kind in ['Open','Short','Load']]
        kit=[d/f'Standard_{kind}.s1p' for kind in ['Open','Short','Load']]
        for method in SAMPLING_METHODS:
            with self.subTest(method=method):
                result=characterize(measurements,kit,Options(standard_sampling=method))
                old=characterize(measurements,kit*2,Options(standard_sampling=method))
                for name in result.dataset.s:np.testing.assert_array_equal(result.dataset.s[name],old.dataset.s[name])
                self.assertEqual(result.manifest['standard_kit'],'shared_open_short_load')
                self.assertEqual(len(result.manifest['inputs']),6)
                self.assertEqual(result.manifest['inputs'][0]['standard_sha256'],result.manifest['inputs'][3]['standard_sha256'])
                np.testing.assert_array_equal(result.dataset.axes['OutputFreq'],result.dataset.axes['InputFreq']-5e9)

    def test_cubic_ri_recovers_polynomial_preserves_exact_nodes(self):
        f=np.array([0.,1.,2.,3.,4.]);g=(.1+.01*f**3)+1j*(.2-.02*f**2)
        std=Standard('polynomial',f,g,50)
        target=np.array([0, .5, 2+1e-5, 3.5, 4])
        actual,count=sample_standard(std,target,'cubic_ri',tolerance=1e-4)
        expected=(.1+.01*target**3)+1j*(.2-.02*target**2)
        expected[2]=g[2]
        np.testing.assert_allclose(actual,expected,atol=1e-14)
        self.assertEqual(count,2)
        for method in SAMPLING_METHODS:
            with self.assertRaisesRegex(ValueError,'禁止外推|精确'):
                sample_standard(std,np.array([4.5]),method)

    def test_only_linear_and_cubic_are_available(self):
        self.assertEqual(set(SAMPLING_METHODS), {'linear_ri', 'cubic_ri'})
        std=Standard('mixed',np.arange(4.),np.array([1,0,1j,-1],complex),50)
        for method in ['exact','linear_mag_unwrapped_phase','linear_db_unwrapped_phase','cubic_mag_unwrapped_phase','bad']:
            # Reject removed methods even when all requested points are exact.
            with self.assertRaisesRegex(ValueError,'未知'):
                sample_standard(std,np.array([0.]),method)
        with self.assertRaisesRegex(ValueError,'零幅度'):
            sample_standard(std,np.array([.5,1.5]),'linear_ri')

    def test_zero_load_and_mixed_zero_phase_rejection(self):
        f=np.array([0.,1.,2.,3.])
        for method in SAMPLING_METHODS:
            actual,_=sample_standard(Standard('Load',f,np.zeros(4,complex),50),np.array([.5,1.5]),method)
            np.testing.assert_array_equal(actual,[0j,0j])
            std=Standard('mixed',f,np.array([1,0,1j,-1],complex),50)
            actual,count=sample_standard(std,np.array([1.]),method)
            self.assertEqual(actual[0],0j);self.assertEqual(count,0)
            if method=='linear_ri':
                with self.assertRaisesRegex(ValueError,'零幅度'):
                    sample_standard(std,np.array([.5,1.,2.5]),method)
            else:
                actual,count=sample_standard(std,np.array([.5,1.,2.5]),method)
                self.assertTrue(np.all(np.isfinite(actual)))
                self.assertEqual(actual[1],0j);self.assertEqual(count,2)

    def test_linear_magnitude_and_phase_unwrap_across_multiple_turns(self):
        f=np.arange(5.)
        target=np.array([3.5,.5,1.5,2.5])  # Target order must be preserved.
        magnitude=.2+.1*f
        for slope in (90.,-90.):
            with self.subTest(slope=slope):
                phase=np.deg2rad(170+slope*f)
                std=Standard('phase_turns',f,magnitude*np.exp(1j*phase),50)
                actual,count=sample_standard(std,target,'linear_ri')
                expected=(.2+.1*target)*np.exp(1j*np.deg2rad(170+slope*target))
                np.testing.assert_allclose(actual,expected,atol=1e-15)
                np.testing.assert_allclose(abs(actual),.2+.1*target,atol=1e-15)
                self.assertEqual(count,4)

    def test_linear_uses_magnitude_not_db_or_complex_cartesian_average(self):
        gamma=np.array([.2*np.exp(1j*np.deg2rad(170)),
                        .8*np.exp(1j*np.deg2rad(-170))])
        std=Standard('wrap',np.array([0.,10.]),gamma,50)
        actual,count=sample_standard(std,np.array([5.]),'linear_ri')
        self.assertAlmostEqual(actual[0],-.5+0j)
        self.assertEqual(count,1)
        self.assertGreater(abs(actual[0]-(gamma[0]+gamma[1])/2),.01)
        # A dB-domain average would have magnitude sqrt(.2*.8)=.4.
        self.assertAlmostEqual(abs(actual[0]),.5)

    def test_linear_preserves_exact_nodes_and_tolerance_before_phase_conversion(self):
        f=np.array([0.,1.,2.,3.])
        g=np.array([.3+.4j,-.7+.2j,-.2-.5j,.2-.3j])
        std=Standard('exact',f,g,50)
        actual,count=sample_standard(std,f+1e-5,'linear_ri',tolerance=1e-4)
        np.testing.assert_array_equal(actual,g)
        self.assertEqual(count,0)
        for target in (np.array([-.1]),np.array([3.1])):
            with self.assertRaisesRegex(ValueError,'禁止外推'):
                sample_standard(std,target,'linear_ri')

    def test_current_keysight_regression_201_points(self):
        d=ROOT/'examples/keysight_validation'
        measurements=[d/f'{r:02d}_{prefix}_SOL_{kind}.s2p' for r,prefix in [(1,'Input'),(2,'Mixer')] for kind in ['Open','Short','Load']]
        kit=[d/'open.s1p',d/'short_validation_band.s1p',d/'load.s1p']
        result=characterize(measurements,kit,Options(standard_sampling='cubic_ri'))
        reference=load_file(d/'keysight_current.s2p')
        self.assertEqual(result.dataset.count,201)
        for name in reference.s:
            self.assertLess(float(max(abs(result.dataset.s[name]-reference.s[name]))),3e-7)
        self.assertIn('三次', '\n'.join(result.dataset.warnings))
        self.assertEqual(result.manifest['interpolation_boundary'],'not-a-knot')

if __name__=='__main__':unittest.main()
