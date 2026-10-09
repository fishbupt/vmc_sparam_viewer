from pathlib import Path
from dataclasses import replace
import sys,tempfile,unittest,json
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simulation import simulate,generate_files,SimulationOptions,MEASUREMENT_NAMES
from characterization import characterize,Options
from parser import load_file

ROOT=Path(__file__).resolve().parents[1]
KIT=[ROOT/'examples/keysight_validation'/name for name in ['open.s1p','short_validation_band.s1p','load.s1p']]

class SimulationTests(unittest.TestCase):
    def test_forward_matches_independent_wave_system(self):
        sim=simulate(KIT,SimulationOptions(points=41))
        z=sim.truth.s;d,s,r=[sim.terms[k] for k in ['EDF','ESF','ERF']]
        te=np.sqrt(r)
        for k in range(len(sim.frequency)):
            for i,g in enumerate(sim.gamma[k]):
                if i<3:
                    mat=np.array([[1,-te[k]*g],[0,1-s[k]*g]],complex)
                    expected=np.linalg.solve(mat,[d[k],te[k]])[0]
                else:
                    mat=np.array([[1,0,-te[k],0],[0,1,-s[k],0],
                        [0,-z['S11'][k],1,-z['S12'][k]*g],
                        [0,-z['S21'][k],0,1-z['S22'][k]*g]],complex)
                    expected=np.linalg.solve(mat,[d[k],te[k],0,0])[0]
                self.assertLess(abs(expected-sim.clean[k,i]),1e-14)

    def test_nonideal_kit_roundtrip_and_full_export(self):
        with tempfile.TemporaryDirectory() as temp:
            saved=generate_files(KIT,temp)
            self.assertEqual({p.name for p in saved.directory.glob('*.s2p')},set(MEASUREMENT_NAMES)|{'Mixer.s2p'})
            result=characterize(saved.measurement_paths,saved.standard_paths,Options(standard_sampling='cubic_ri'))
            truth=load_file(saved.mixer_path)
            for name in truth.s:np.testing.assert_allclose(result.dataset.s[name],truth.s[name],atol=2e-14,rtol=1e-13)
            # Actual nonideal standards are not silently replaced by +/-1/0.
            self.assertGreater(abs(saved.simulation.gamma[0,0]-1),.1)
            for p,b in zip(saved.standard_paths,saved.simulation.standard_bytes):self.assertEqual(p.read_bytes(),b)
            report=json.loads((saved.directory/'simulation_report.json').read_text())
            self.assertFalse(report['noise']['enabled'])
            self.assertEqual(len(report['output_sha256']),11)
            for p in saved.measurement_paths:
                ds=load_file(p)
                for name in ['S21','S12','S22']:np.testing.assert_array_equal(ds.s[name],0)
            again=generate_files(KIT,temp)
            self.assertNotEqual(saved.directory,again.directory)
            self.assertEqual(saved.mixer_path.read_bytes(),again.mixer_path.read_bytes())

    def test_noise_seed_rms_independence_and_averaging(self):
        opts=SimulationOptions(points=5001,noise_enabled=True,noise_floor_db=-60,noise_seed=77)
        a=simulate(KIT,opts);b=simulate(KIT,opts)
        np.testing.assert_array_equal(a.measured,b.measured)
        delta=a.measured-a.clean
        self.assertAlmostEqual(float(np.sqrt(np.mean(abs(delta)**2))),.001,delta=.00002)
        self.assertLess(abs(np.corrcoef(delta[:,0].real,delta[:,1].real)[0,1]),.06)
        avg=simulate(KIT,replace(opts,noise_averages=4))
        np.testing.assert_allclose(avg.measured-avg.clean,delta/2,atol=2e-16)
        c=simulate(KIT,replace(opts,noise_seed=78))
        self.assertGreater(max(abs(a.measured[:,0]-c.measured[:,0])),.001)
        for name in a.truth.s:np.testing.assert_array_equal(a.truth.s[name],c.truth.s[name])
        self.assertEqual(a.manifest['noise']['effective_complex_rms'],.001)

    def test_invalid_frequency_kit_and_options_leave_no_partial_output(self):
        for changes in [dict(lo_hz=11e9),dict(points=1),dict(points=2.5),dict(noise_seed=-1),
                        dict(noise_averages=0),dict(standard_sampling='bad'),dict(s11_db=1),dict(erf_db=1000)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):simulate(KIT,replace(SimulationOptions(),**changes))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'禁止外推'):
                generate_files(KIT,temp,SimulationOptions(rf_stop_hz=25e9))
            self.assertFalse(list(Path(temp).iterdir()))
        with self.assertRaisesRegex(ValueError,'三个'):simulate(KIT[:2])

    def test_mixer_phase_reference_and_known_sign_ambiguity(self):
        opts=SimulationOptions(points=41,transmission_phase_deg=120,transmission_delay_ps=80)
        with tempfile.TemporaryDirectory() as temp:
            saved=generate_files(KIT,temp,opts)
            recovered=characterize(saved.measurement_paths,saved.standard_paths,Options(standard_sampling='cubic_ri',root_sign=-1))
            np.testing.assert_allclose(recovered.dataset.s['S21'],saved.simulation.truth.s['S21'],atol=1e-14)
            self.assertAlmostEqual(np.rad2deg(np.angle(saved.simulation.truth.s['S21'][0])),120,places=10)

    def test_alias_warning_and_reference_impedance(self):
        a=simulate(KIT,SimulationOptions(points=11,transmission_delay_ps=1000))
        self.assertTrue(any('alias' in w for w in a.manifest['warnings']))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'load75.s1p';p.write_text(KIT[2].read_text().replace('R 50','R 75'))
            with self.assertRaisesRegex(ValueError,'阻抗'):simulate([*KIT[:2],p])

if __name__=='__main__':unittest.main()
