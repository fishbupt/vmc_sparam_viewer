import csv
import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frequency_mapping import output_frequencies
from simulation import SimulationOptions, simulate, generate_files
from characterization import (Options, characterize, load_standard, sample_standard,
                              export_s2p, export_bundle)
from parser import load_file, parse_text

ROOT = Path(__file__).resolve().parents[1]
KIT = [ROOT/'examples/keysight_validation'/n for n in
       ('open.s1p', 'short_validation_band.s1p', 'load.s1p')]


class FrequencyConversionTests(unittest.TestCase):
    def test_mapping_and_invalid_inputs(self):
        rf = np.array([10e9, 12e9, 15e9])
        np.testing.assert_array_equal(output_frequencies(rf, 5e9, 'down'), [5e9, 7e9, 10e9])
        np.testing.assert_array_equal(output_frequencies(rf, 5e9, 'up'), [15e9, 17e9, 20e9])
        # Sum product is valid even when LO is greater than RF.
        np.testing.assert_array_equal(output_frequencies([1e9, 2e9], 5e9, 'up'), [6e9, 7e9])
        for mode, axis, lo in [('bad', rf, 5e9), ('down', [5e9], 5e9),
                              ('down', [4e9], 5e9), ('up', rf, 0),
                              ('up', [np.nan], 5e9), ('up', [], 5e9),
                              ('up', [[1e9]], 5e9), ('up', [-1e9], 5e9)]:
            with self.subTest(mode=mode, axis=axis, lo=lo), self.assertRaises(ValueError):
                output_frequencies(axis, lo, mode)

    def test_both_directions_roundtrip_and_export_axes(self):
        for mode in ('down', 'up'):
            for method in ('linear_ri', 'cubic_ri'):
                with self.subTest(mode=mode, method=method), tempfile.TemporaryDirectory() as temp:
                    opts = SimulationOptions(rf_stop_hz=15e9, points=37,
                        frequency_conversion=mode, standard_sampling=method,
                        transmission_phase_deg=120)
                    saved = generate_files(KIT, temp, opts)
                    sim = saved.simulation
                    expected_if = sim.frequency + (5e9 if mode == 'up' else -5e9)
                    np.testing.assert_array_equal(sim.truth.axes['OutputFreq'], expected_if)
                    # Evaluate the output kit independently at the requested physical IF.
                    for i, path in enumerate(KIT):
                        expected_gamma, _ = sample_standard(load_standard(path), expected_if, method)
                        np.testing.assert_array_equal(sim.gamma[:, 3+i], expected_gamma)
                    result = characterize(saved.measurement_paths, saved.standard_paths,
                        Options(frequency_conversion=mode, standard_sampling=method,
                                root_sign=sim.manifest['truth_reference_root_sign']))
                    for name in sim.truth.s:
                        np.testing.assert_allclose(result.dataset.s[name], sim.truth.s[name], atol=2e-14)
                    np.testing.assert_array_equal(result.dataset.axes['OutputFreq'], expected_if)
                    report = json.loads((saved.directory/'simulation_report.json').read_text())
                    relation = 'IF=RF+LO' if mode == 'up' else 'IF=RF-LO'
                    self.assertEqual(report['frequency_conversion'], mode)
                    self.assertEqual(report['options']['frequency_conversion'], mode)
                    self.assertIn(relation, report['if_relation'])
                    self.assertEqual(result.manifest['frequency_conversion'], mode)
                    rows = list(csv.DictReader((saved.directory/'simulation_truth.csv').read_text(encoding='utf-8-sig').splitlines()))
                    np.testing.assert_array_equal([float(row['IF_Hz']) for row in rows], expected_if)
                    for path in [*saved.measurement_paths, saved.mixer_path]:
                        self.assertIn(relation, path.read_text())
                    output = Path(temp)/'extracted.s2p'
                    export_s2p(result, output)
                    self.assertIn(relation, output.read_text())
                    for name in sim.truth.s:
                        np.testing.assert_array_equal(load_file(output).s[name], result.dataset.s[name])
                    output = Path(temp)/'record.zip'
                    export_bundle(result, output)
                    import zipfile
                    with zipfile.ZipFile(output) as archive:
                        report = json.loads(archive.read('characterization_report.json'))
                        self.assertEqual(report['frequency_conversion'], mode)
                        data = parse_text(archive.read('characterized_mixer.s2px').decode(), 'own.s2px')
                        np.testing.assert_array_equal(data.axes['OutputFreq'], expected_if)

    def test_upconversion_with_lo_above_rf(self):
        # Neither rejecting LO>RF nor abs(RF-LO) is correct for the sum branch.
        opts = SimulationOptions(rf_start_hz=5e9, rf_stop_hz=7e9, lo_hz=10e9,
                                 frequency_conversion='up', points=23)
        with tempfile.TemporaryDirectory() as temp:
            saved = generate_files(KIT, temp, opts)
            result = characterize(saved.measurement_paths, saved.standard_paths,
                Options(lo_hz=10e9, frequency_conversion='up', standard_sampling='cubic_ri'))
            for name in result.dataset.s:
                np.testing.assert_allclose(result.dataset.s[name], saved.simulation.truth.s[name], atol=2e-14)

    def test_upconversion_independent_forward_wave_system(self):
        sim = simulate(KIT, SimulationOptions(rf_stop_hz=15e9, frequency_conversion='up', points=29))
        z = sim.truth.s
        d, s, r = [sim.terms[k] for k in ('EDF', 'ESF', 'ERF')]
        te = np.sqrt(r)
        for k in range(len(sim.frequency)):
            for j, g in enumerate(sim.gamma[k, 3:]):
                matrix = np.array([[1,0,-te[k],0], [0,1,-s[k],0],
                    [0,-z['S11'][k],1,-z['S12'][k]*g],
                    [0,-z['S21'][k],0,1-z['S22'][k]*g]], complex)
                expected = np.linalg.solve(matrix, [d[k], te[k], 0, 0])[0]
                self.assertLess(abs(sim.clean[k, 3+j]-expected), 1e-14)

    def test_upconversion_noise_and_corrected_second_round(self):
        opts = SimulationOptions(rf_stop_hz=15e9, frequency_conversion='up', points=103,
                                 noise_enabled=True, noise_floor_db=-80, noise_seed=45)
        sim = simulate(KIT, opts)
        np.testing.assert_array_equal(sim.measured, simulate(KIT, opts).measured)
        avg = simulate(KIT, replace(opts, noise_averages=4))
        np.testing.assert_allclose(avg.measured-avg.clean, (sim.measured-sim.clean)/2, atol=2e-16)
        with tempfile.TemporaryDirectory() as temp:
            saved = generate_files(KIT, temp, replace(opts, noise_enabled=False))
            z = saved.simulation.truth.s
            gamma = saved.simulation.gamma[:, 3:]
            corrected = z['S11'][:, None] + z['S12'][:, None]*z['S21'][:, None]*gamma/(1-z['S22'][:, None]*gamma)
            # Replace only second-round S11 with independently port-corrected observations.
            from test_characterization import write_s2p
            for i, path in enumerate(saved.measurement_paths[3:]):
                write_s2p(path, saved.simulation.frequency, corrected[:, i])
            result = characterize(saved.measurement_paths, saved.standard_paths,
                Options(frequency_conversion='up', standard_sampling='cubic_ri', second_round='corrected'))
            for name in z:
                np.testing.assert_allclose(result.dataset.s[name], z[name], atol=2e-14)

    def test_wrong_mapping_and_missing_output_band(self):
        with tempfile.TemporaryDirectory() as temp:
            # Up IF=15..25 GHz exceeds the provided short definition (5..20 GHz).
            with self.assertRaisesRegex(ValueError, '禁止外推'):
                generate_files(KIT, temp, SimulationOptions(frequency_conversion='up'))
            self.assertFalse(list(Path(temp).iterdir()))
            saved = generate_files(KIT, temp, SimulationOptions(rf_stop_hz=15e9, frequency_conversion='up'))
            wrong = characterize(saved.measurement_paths, saved.standard_paths, Options(standard_sampling='cubic_ri'))
            self.assertGreater(np.max(abs(wrong.dataset.s['S21']-saved.simulation.truth.s['S21'])), .01)


if __name__ == '__main__':
    unittest.main()
