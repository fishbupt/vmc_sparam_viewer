from vna_workbench.calibration.vmc.models import ROLES
from pathlib import Path
import csv
import io
import json
import zipfile
import numpy as np

def s2p_text(result):
    d = result.dataset
    lines = ['! VMC calibration mixer + filter characterization',
             f'! Stimulus=RF; {result.manifest["if_relation"]}; reciprocal S21=S12',
             '! PhaseConvention='+result.manifest.get('phase_convention', 'legacy non-inverting'),
             f'! LO_Hz={result.manifest["lo_hz"]:.17g}',
             f'! SecondRound={result.manifest["second_round"]}; StandardSampling={result.manifest["standard_sampling"]}',
             f'! InterpolationCoordinates={result.manifest["interpolation_coordinates"]}',
             f'! SharedKit={result.manifest["standard_kit"]}; CubicBoundary={result.manifest["interpolation_boundary"]}; Extrapolation=False',
             f'! GlobalRootSign={result.manifest["root_sign"]}; absolute sign not identified by SOL reflection',
             f'# Hz S RI R {result.manifest["z0_ohm"]:.17g}']
    for i, freq in enumerate(d.axes['StimulusFreq']):
        row = [freq]
        for p in ('S11', 'S21', 'S12', 'S22'):
            z = d.s[p][i]; row.extend((z.real, z.imag))
        lines.append(' '.join(format(float(x), '.17g') for x in row))
    return '\n'.join(lines)+'\n'


def s2px_text(result):
    d = result.dataset
    out = io.StringIO()
    out.write('!CSV A.01.00\n!Source: Self-developed Mixer Characterization (not a Keysight-generated file)\n')
    out.write('!PhaseConvention: '+result.manifest.get('phase_convention','legacy non-inverting')+'\n')
    out.write(f'!Reference Impedance: {result.manifest["z0_ohm"]:.17g} ohm\n')
    writer = csv.writer(out)
    writer.writerow(['SegIndex', 'InputFreq', 'OutputFreq', 'LO1Freq']+
                    [h for p in ('S11', 'S21', 'S12', 'S22') for h in (f'{p} Mag (dB)', f'{p} Phase (Deg)')])
    for i in range(d.count):
        row = [0, d.axes['InputFreq'][i], d.axes['OutputFreq'][i], d.axes['LO1Freq'][i]]
        for p in ('S11', 'S21', 'S12', 'S22'):
            z = d.s[p][i]
            # RI S2P remains authoritative for zero magnitudes; DB cannot encode
            # a defined phase at zero. Avoid producing non-readable S2PX.
            if abs(z) == 0:
                raise ValueError('S2PX 幅相格式无法表示零幅度的有效相位；请仅导出 RI S2P。')
            row += [20*np.log10(abs(z)), np.rad2deg(np.angle(z))]
        writer.writerow([format(float(x), '.17g') for x in row])
    return out.getvalue()


def diagnostic_csv(result):
    columns = dict(result.dataset.axes)
    for key, z in result.terms.items():
        columns[key+'_Real'], columns[key+'_Imag'] = z.real, z.imag
    for i, role in enumerate(ROLES):
        z, m = result.evaluated_standards[:, i], result.measured[:, i]
        columns[role+'_Gamma_Real'], columns[role+'_Gamma_Imag'] = z.real, z.imag
        columns[role+'_S11_Real'], columns[role+'_S11_Imag'] = m.real, m.imag
    columns.update(result.diagnostics)
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(columns)
    writer.writerows([[format(float(x), '.17g') for x in row] for row in zip(*columns.values())])
    return '\ufeff'+out.getvalue()


def export_s2p(result, path):
    Path(path).write_text(s2p_text(result), encoding='ascii')


def export_bundle(result, path):
    """Complete reproducible record; S2P is authoritative, optional DB CSV."""
    manifest = dict(result.manifest)
    payloads = {'characterized_mixer.s2p': s2p_text(result), 'sol_diagnostics.csv': diagnostic_csv(result)}
    try:
        payloads['characterized_mixer.s2px'] = s2px_text(result)
    except ValueError as exc:
        manifest['s2px_export_note'] = str(exc)
    payloads['characterization_report.json'] = json.dumps(manifest, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            archive.writestr(name, content.encode('utf-8'))
