"""High-side LO regression against independently derived physical equations."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import numpy as np

from vna_workbench.core.frequency_conversion import output_frequencies
from vna_workbench.core.sol import solve_sol
from vna_workbench.data.touchstone import load_file, s2p_text
from vna_workbench.simulation.mixer_characterization import SimulationOptions, simulate, generate_files
from vna_workbench.calibration.vmc.mixer_characterization import Options, characterize, continuous_root
from vna_workbench.simulation.vmc import VMCSimulationOptions, PortModel, simulate_vmc, generate_vmc_files
from vna_workbench.calibration.vmc.error_terms import calibrate
from vna_workbench.calibration.vmc.dut_correction import calibrate_mut
from vna_workbench.calibration.vmc.package_io import save_calibration, load_calibration, validate_calibration


class HighSideTests(unittest.TestCase):
    def test_product_mapping(self):
        np.testing.assert_array_equal(output_frequencies([10e9,12.5e9,15e9],20e9,'high_side'),[10e9,7.5e9,5e9])
        np.testing.assert_array_equal(output_frequencies([10e9,15e9],20e9,'up'),[30e9,35e9])
        for rf in ([20e9], [21e9]):
            with self.assertRaises(ValueError): output_frequencies(rf,20e9,'high_side')

    def test_characterization_independent_formula_and_negative_control(self):
        o=SimulationOptions(rf_stop_hz=15e9,lo_hz=20e9,frequency_conversion='high_side')
        s=simulate(None,o);c=s.truth.s;g=s.gamma[:,3:]
        # Physical loaded input reflection, derived without the real-linear solver.
        loaded=c['S11'][:,None]+(c['S12']*c['S21'])[:,None]*g.conj()/(1-c['S22'].conj()[:,None]*g.conj())
        d,e,r=[s.terms[k][:,None] for k in ('EDF','ESF','ERF')]
        np.testing.assert_allclose(s.clean[:,3:],d+r*loaded/(1-e*loaded),atol=8e-16,rtol=0)
        wrong=continuous_root(solve_sol(loaded,g,1e12)[0][2])
        self.assertGreater(np.max(abs(np.angle(wrong/c['S21'],deg=True))),10)

    def test_characterization_raw_corrected_interpolation_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for method in ('linear_ri','cubic_ri'):
                # Sparse, complex kit forces interpolation at descending IF points.
                kit=generate_files(None,root,SimulationOptions(rf_stop_hz=15e9,lo_hz=20e9,points=31,frequency_conversion='high_side'))
                o=SimulationOptions(rf_stop_hz=15e9,lo_hz=20e9,points=101,frequency_conversion='high_side',standard_sampling=method)
                saved=generate_files(kit.standard_paths,root,o);s=saved.simulation
                opts=Options(lo_hz=o.lo_hz,frequency_conversion='high_side',standard_sampling=method)
                out=characterize(saved.measurement_paths,saved.standard_paths,opts)
                for k in s.truth.s: np.testing.assert_allclose(out.dataset.s[k],s.truth.s[k],atol=5e-14,rtol=0)
                np.testing.assert_allclose(out.evaluated_standards[:,3:],s.gamma[:,3:].conj(),atol=1e-15)
                self.assertIn('high_side_input_equivalent_v1',out.dataset.raw_text)
                self.assertTrue(np.all(np.diff(out.dataset.axes['OutputFreq'])<0))
                d,e,r=[s.terms[k][:,None] for k in ('EDF','ESF','ERF')]
                delta=s.clean[:,3:]-d;corrected=delta/(r+e*delta)
                for j,p in enumerate(saved.measurement_paths[3:]):
                    values={k:np.zeros(len(s.frequency),complex) for k in s.truth.s}
                    values['S11']=corrected[:,j]
                    p.write_text(s2p_text(s.frequency,values,50,[]))
                out2=characterize(saved.measurement_paths,saved.standard_paths,replace(opts,second_round='corrected'))
                for k in s.truth.s:np.testing.assert_allclose(out2.dataset.s[k],s.truth.s[k],atol=5e-14,rtol=0)

    def test_vmc_physical_transmission_closed_form(self):
        o=VMCSimulationOptions(rf_start_hz=10e9,rf_stop_hz=15e9,lo_hz=20e9,frequency_conversion='high_side',raw_axis='rf')
        s=simulate_vmc(o)
        es=s.expected_terms['P1_RF_ESF'];el=s.expected_terms['IF_ELF'];et=s.expected_terms['VMC_ETF']
        for name,c in [('cal_mixer_raw.s2p',s.calibration_mixer.s),('mut_raw.s2p',s.mut.s)]:
            den=(1-c['S11']*es)*(1-c['S22'].conj()*el.conj())-c['S12']*c['S21']*es*el.conj()
            expected=(et*c['S21']/den).conj()
            np.testing.assert_allclose(s.raw[name][:,1,0],expected,atol=8e-16,rtol=0)

    def test_vmc_axes_calibration_package_and_imported_mixer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for axis in ('rf','if','dual'):
                o=VMCSimulationOptions(rf_start_hz=11e9,rf_stop_hz=15e9,lo_hz=20e9,points=51,
                    frequency_conversion='high_side',raw_axis=axis,synthetic_sol=True,
                    port2=PortModel(-39,53,7,-29,-47,9,-.9,23,27))
                base=simulate_vmc(o)
                # User definition is IF-indexed and must be written with all columns sorted together.
                order=np.argsort(base.if_frequency);p=root/'cal_if.s2p'
                p.write_text(s2p_text(base.if_frequency[order],{k:v[order] for k,v in base.calibration_mixer.s.items()},50,[]))
                saved=generate_vmc_files(root,o,calibration_mixer_path=p,mixer_definition_axis='if')
                cal=calibrate(saved.calibration_inputs(),saved.calibration_options())
                for k,v in base.expected_terms.items():np.testing.assert_allclose(cal.terms[k],v,atol=4e-14,rtol=0)
                package=root/'cal.zip';save_calibration(cal,package);restored=load_calibration(package)
                mut=calibrate_mut(restored,saved.mut_path)
                for k,v in base.mut.s.items():np.testing.assert_allclose(mut.dataset.s[k],v,atol=4e-14,rtol=0)
                raw=load_file(saved.mut_path);self.assertTrue(np.all(np.diff(raw.axes['StimulusFreq'])>0))
                self.assertTrue((saved.directory/'high_side_phase_reference.csv').exists())
                cal.manifest.pop('phase_convention')
                with self.assertRaises(ValueError):validate_calibration(cal)

    def test_overlap_endpoint_noise_and_dual_copy(self):
        base=VMCSimulationOptions(rf_start_hz=10e9,rf_stop_hz=15e9,lo_hz=20e9,frequency_conversion='high_side',raw_axis='rf')
        simulate_vmc(base)  # Shared 10 GHz endpoint is valid with an RF-indexed file.
        with self.assertRaises(ValueError):simulate_vmc(replace(base,raw_axis='dual'))
        s=simulate_vmc(replace(base,rf_start_hz=11e9,raw_axis='dual',noise_enabled=True))
        a=np.searchsorted(s.mixed_frequency,s.frequency);b=np.searchsorted(s.mixed_frequency,s.if_frequency)
        for name in ('cal_mixer_raw.s2p','mut_raw.s2p'):
            np.testing.assert_array_equal(s.raw[name][a],s.raw[name][b])
        again=simulate_vmc(s.options)
        np.testing.assert_array_equal(s.raw['mut_raw.s2p'],again.raw['mut_raw.s2p'])


if __name__=='__main__':unittest.main()
