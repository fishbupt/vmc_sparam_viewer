"""Forward generator regression, independent closed forms and calibration integration."""
from dataclasses import replace
from pathlib import Path
import hashlib,json,tempfile,unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from parser import load_file,PARAMS
from characterization import parse_s1p
from simulation import _s2p
from vmc_simulation import (VMCSimulationOptions,MixerModel,PortModel,simulate_vmc,
                            generate_vmc_files,forward_wave,RAW_NAMES)
from vmc_calibration import calibrate,calibrate_mut

class VMCSimulationTests(unittest.TestCase):
    def test_default_independent_closed_forms(self):
        s=simulate_vmc();f=s.physical_frequency;rf=s.frequency;iff=s.if_frequency
        np.testing.assert_allclose(f,np.linspace(10e9,40e9,601),rtol=0,atol=0)
        # Independent expressions, including physical IF phase and single-pass tracking.
        def terms(f):
            x=f-10e9
            return (.01778279410038923*np.exp(1j*(np.pi/6-2*np.pi*x*5e-12)),
                    .05623413251903491*np.exp(1j*(-np.pi/9-2*np.pi*x*10e-12)),
                    .9440608762859234*np.exp(1j*(np.pi/24-2*np.pi*x*20e-12)))
        d,e,t=terms(f)
        for name,g in zip(RAW_NAMES[:3],(1,-1,0)):
            m=s.raw[name];expected=d+t*t*g/(1-e*g)
            np.testing.assert_allclose(m[:,0,0],expected,atol=3e-16)
            np.testing.assert_array_equal(m[:,0,0],m[:,1,1]);np.testing.assert_array_equal(m[:,0,1],0)
        np.testing.assert_allclose(s.raw['thru_raw.s2p'][:,1,0],t*t/(1-e*e),atol=3e-16)
        np.testing.assert_allclose(s.raw['thru_raw.s2p'][:,0,0],d+t*t*e/(1-e*e),atol=3e-16)
        _,er,tr=terms(rf);_,ei,ti=terms(iff)
        for name,c in [('cal_mixer_raw.s2p',s.calibration_mixer.s),('mut_raw.s2p',s.mut.s)]:
            den=(1-er*c['S11'])*(1-ei*c['S22'])-er*ei*c['S12']*c['S21']
            expected=tr*ti*c['S21']/den
            np.testing.assert_allclose(s.raw[name][:201,1,0],expected,atol=4e-16)
            np.testing.assert_array_equal(s.raw[name][:201],s.raw[name][400:])
        np.testing.assert_allclose(s.expected_terms['VMC_ETF'],tr*ti,atol=2e-16)
        np.testing.assert_allclose(abs(s.mut.s['S21']),10**(-9/20));np.testing.assert_array_equal(s.mut.s['S12'],0)
        np.testing.assert_array_equal(s.thru['S21'],1);np.testing.assert_array_equal(s.thru['S11'],0)

    def test_up_down_axes_asymmetric_boxes_closed_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            for direction,lo in [('up',20e9),('down',18e9)]:
                for axis in ('rf','if','dual'):
                    with self.subTest(direction=direction,axis=axis):
                        o=replace(VMCSimulationOptions(),rf_start_hz=20e9 if direction=='down' else 10e9,
                                  rf_stop_hz=30e9 if direction=='down' else 20e9,points=41,frequency_conversion=direction,lo_hz=lo,raw_axis=axis,
                                  port2=PortModel(-39,53,7,-29,-47,9,-.9,23,27))
                        saved=generate_vmc_files(tmp,o);cal=calibrate(saved.calibration_inputs(),saved.calibration_options())
                        for name,z in saved.simulation.expected_terms.items():np.testing.assert_allclose(cal.terms[name],z,atol=3e-14,rtol=0)
                        out=calibrate_mut(cal,saved.mut_path).dataset
                        for p in ('S11','S21','S22'):np.testing.assert_allclose(out.s[p],saved.simulation.mut.s[p],atol=3e-14,rtol=0)

    def test_actual_sol_thru_and_imported_if_mixer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);o=replace(VMCSimulationOptions(),points=21);base=simulate_vmc(o);f=base.physical_frequency
            paths=[]
            for k,z in [('open',.97*np.exp(.12j)),('short',-.96*np.exp(-.08j)),('load',.015+.01j)]:
                p=root/(k+'.s1p');p.write_text('# Hz S RI R 50\n'+'\n'.join(f'{x:.17g} {z.real:.17g} {z.imag:.17g}' for x in f));paths.append(p)
            vals={'S11':np.full(len(f),.04+.02j),'S22':np.full(len(f),-.03+.01j),
                  'S21':.9*np.exp(-2j*np.pi*(f-f[0])*12e-12),'S12':.87*np.exp(-2j*np.pi*(f-f[0])*15e-12)}
            thru=root/'thru.s2p';thru.write_text(_s2p(f,vals,50,['Nonideal asymmetric Thru.']))
            calfile=root/'cal_if.s2p';calfile.write_text(_s2p(base.if_frequency,base.calibration_mixer.s,50,['IF stimulus.']))
            for method in ('linear_ri','cubic_ri'):
                saved=generate_vmc_files(root,replace(o,standard_sampling=method),paths,thru,calfile,'if')
                cal=calibrate(saved.calibration_inputs(),saved.calibration_options());out=calibrate_mut(cal,saved.mut_path).dataset
                for p in ('S11','S21','S22'):np.testing.assert_allclose(out.s[p],saved.simulation.mut.s[p],atol=3e-14,rtol=0)
                np.testing.assert_allclose(load_file(saved.directory/'calibration_mixer.s2p').s['S21'],base.calibration_mixer.s['S21'])
                report=json.loads((saved.directory/'simulation_report.json').read_text())
                for source in report['source_inputs']:
                    copied=saved.directory/source['copied_path']
                    self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(),source['sha256'])

    def test_definition_interpolation_polar_and_no_extrapolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);o=replace(VMCSimulationOptions(),points=9,standard_sampling='linear_ri')
            # Smooth 170 -> 190 deg crossing, knots span the physical acquisition grid.
            f=np.array([10e9,20e9,30e9,40e9]);paths=[]
            for name,mag,phase in [('open',.98,170),('short',.95,-20),('load',0,0)]:
                g=mag*np.exp(1j*np.deg2rad(phase+(f-10e9)/1e9*2));p=root/(name+'.s1p')
                p.write_text('# Hz S RI R 50\n'+'\n'.join(f'{x} {z.real:.17g} {z.imag:.17g}' for x,z in zip(f,g)));paths.append(p)
            s=simulate_vmc(o,paths)
            np.testing.assert_allclose(s.standards['open'],.98*np.exp(1j*np.deg2rad(170+(s.physical_frequency-10e9)/1e9*2)),atol=1e-15)
            self.assertGreater(s.manifest['interpolated_points'][str(paths[0].resolve())],0)
            paths[0].write_text('# Hz S RI R 50\n1e10 1 0\n2e10 1 0')
            with self.assertRaises(ValueError):generate_vmc_files(root,o,paths)
            self.assertFalse(list(root.glob('vmc_dummy_*')))

    def test_noise_reproducibility_averaging_dual_and_clean_truth(self):
        o=replace(VMCSimulationOptions(),points=41,noise_enabled=True,noise_floor_db=-40,noise_seed=1234)
        s=simulate_vmc(o);same=simulate_vmc(o);avg=simulate_vmc(replace(o,noise_averages=4));clean=simulate_vmc(replace(o,noise_enabled=False))
        for k in RAW_NAMES:
            np.testing.assert_array_equal(s.raw[k],same.raw[k]);np.testing.assert_allclose(avg.raw[k]-avg.clean[k],(s.raw[k]-s.clean[k])/2,atol=2e-16)
        for k in RAW_NAMES[4:]:
            np.testing.assert_array_equal(s.raw[k][:41],s.raw[k][-41:])
        for p in PARAMS:np.testing.assert_array_equal(s.mut.s[p],clean.mut.s[p])
        self.assertFalse(np.array_equal(s.raw['open_raw.s2p'][:,0,0],s.raw['short_raw.s2p'][:,0,0]))
        np.testing.assert_array_equal(s.raw['open_raw.s2p'][:,0,1],0)

    def test_arbitrary_shift_and_overlap_single_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            for direction,lo in [('up',20.123e9),('up',1.123e9),('down',1.123e9)]:
                for axis in (('rf','if','dual') if lo==20.123e9 else ('rf','if')):
                    o=replace(VMCSimulationOptions(),points=17,lo_hz=lo,frequency_conversion=direction,raw_axis=axis)
                    saved=generate_vmc_files(tmp,o);cal=calibrate(saved.calibration_inputs(),saved.calibration_options())
                    np.testing.assert_allclose(calibrate_mut(cal,saved.mut_path).dataset.s['S21'],saved.simulation.mut.s['S21'],atol=2e-14)

    def test_files_unique_hashes_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            o=replace(VMCSimulationOptions(),points=11);a=generate_vmc_files(tmp,o);b=generate_vmc_files(tmp,o)
            self.assertNotEqual(a.directory,b.directory)
            report=json.loads((a.directory/'simulation_report.json').read_text())
            for name,digest in report['output_sha256'].items():self.assertEqual(hashlib.sha256((a.directory/name).read_bytes()).hexdigest(),digest)
            for k in RAW_NAMES:self.assertTrue(np.isfinite(np.array(list(load_file(a.directory/k).s.values()))).all())
            d=load_file(a.directory/'thru_definition.s2p');np.testing.assert_array_equal(d.s['S21'],1)
            with np.load(a.directory/'forward_observations.npz',allow_pickle=False) as pack:self.assertIn('clean_cal_mixer_raw',pack.files)
            with patch('vmc_simulation._s2p',side_effect=OSError('failed write')):
                with self.assertRaises(OSError):generate_vmc_files(tmp,o)
            self.assertEqual(len(list(Path(tmp).iterdir())),2)

    def test_invalid_inputs_and_impedance(self):
        bad=[{'points':1},{'points':True},{'points':float('nan')},{'z0':0},{'lo_hz':float('inf')},
             {'lo_hz':20e9,'frequency_conversion':'down'},{'lo_hz':1e9,'raw_axis':'dual'},
             {'raw_axis':'unknown'},{'standard_sampling':'unknown'},{'noise_averages':0},
             {'noise_seed':-1},{'frequency_tolerance_hz':1e9},{'mut':MixerModel(s11_db=0)}]
        for change in bad:
            with self.subTest(change=change),self.assertRaises(ValueError):simulate_vmc(replace(VMCSimulationOptions(),**change))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.s1p';path.write_text('# Hz S RI R 75\n1e10 1 0\n4e10 1 0')
            with self.assertRaisesRegex(ValueError,'阻抗'):simulate_vmc(standard_paths=[path]*3)
        # Direct singular forward model must fail before a file is published.
        c=np.ones((1,2,2),complex)/2;box=(np.zeros(1),np.ones(1),np.ones(1))
        with self.assertRaises(ValueError):forward_wave(c,box,box)

if __name__=='__main__':unittest.main()
