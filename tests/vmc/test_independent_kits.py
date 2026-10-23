"""Independent port standards must survive generation, extraction and VMC handoff."""
from pathlib import Path
from dataclasses import replace
import tempfile, unittest
import numpy as np
from vna_workbench.simulation.verification_kit import verification_gamma
from vna_workbench.simulation.mixer_characterization import SimulationOptions, generate_files
from vna_workbench.calibration.vmc.mixer_characterization import Options, characterize
from vna_workbench.simulation.vmc import VMCSimulationOptions, generate_vmc_files
from vna_workbench.calibration.vmc.error_terms import calibrate
from vna_workbench.calibration.vmc.dut_correction import calibrate_mut


def make_kits(root,z0=50):
    f=np.linspace(5e9,40e9,701);paths=[]
    for port in (1,2):
        for name,g in zip(('open','short','load'),verification_gamma(f)):
            if port==2:g=g*.93*np.exp(.13j)
            p=Path(root)/f'p{port}_{name}.s1p'
            p.write_text(f'# Hz S RI R {z0}\n'+'\n'.join(f'{x:.17g} {v.real:.17g} {v.imag:.17g}' for x,v in zip(f,g)))
            paths.append(p)
    return paths


class IndependentKitTests(unittest.TestCase):
    def test_two_rounds_and_vmc_use_both_actual_kits(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=make_kits(tmp,75)
            for mode,lo in [('up',20e9),('down',5e9),('high_side',20e9)]:
                opts=SimulationOptions(rf_stop_hz=15e9,points=31,lo_hz=lo,frequency_conversion=mode,z0=75)
                saved=generate_files(paths,tmp,opts)
                self.assertEqual(len(saved.standard_paths),6)
                out=characterize(saved.measurement_paths,saved.standard_paths,Options(lo_hz=lo,frequency_conversion=mode,standard_sampling='cubic_ri'))
                for k,v in saved.simulation.truth.s.items():np.testing.assert_allclose(out.dataset.s[k],v,atol=3e-14)
                o=VMCSimulationOptions(rf_stop_hz=15e9,points=31,lo_hz=lo,frequency_conversion=mode,z0=75,raw_axis='rf')
                run=generate_vmc_files(tmp,o,paths,calibration_mixer_path=saved.mixer_path)
                inp=run.calibration_inputs()
                self.assertNotEqual(inp.standards['P1'],inp.standards['P2'])
                self.assertGreater(np.max(abs(run.simulation.raw['open_raw.s2p'][:,0,0]-run.simulation.raw['open_raw.s2p'][:,1,1])),.01)
                cal=calibrate(inp,run.calibration_options());mut=calibrate_mut(cal,run.mut_path)
                for k,v in run.simulation.mut.s.items():np.testing.assert_allclose(mut.dataset.s[k],v,atol=3e-14)

    def test_mixer_range_error_identifies_axis_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=make_kits(tmp)
            saved=generate_files(paths,tmp,SimulationOptions(rf_stop_hz=15e9,points=31,lo_hz=20e9,frequency_conversion='high_side'))
            o=VMCSimulationOptions(rf_stop_hz=15e9,points=31,lo_hz=20e9,frequency_conversion='high_side',raw_axis='rf')
            with self.assertRaisesRegex(ValueError,'IF 横轴读取.*文件频段 10～15 GHz.*所需频段 5～10 GHz.*另一横轴'):
                generate_vmc_files(tmp,o,calibration_mixer_path=saved.mixer_path,mixer_definition_axis='if')
            with self.assertRaisesRegex(ValueError,'RF 横轴读取.*所需频段 10～16 GHz'):
                generate_vmc_files(tmp,replace(o,rf_stop_hz=16e9),calibration_mixer_path=saved.mixer_path)


if __name__=='__main__':unittest.main()
