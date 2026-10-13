"""Export calibrated MUT results without invoking the solver."""

import json
from vna_workbench.data.archives import csv_record, atomic_zip

def export_mut(result,path):
    data=result.dataset;f=data.axes['InputFreq'];iff=data.axes['OutputFreq']
    z0=result.manifest['calibration']['options']['z0']
    lines=['! VMC calibrated MUT; S21=VC21; RF axis; IF=see frequency_map.csv.',
        '! S12 is NOT calibrated; zero placeholder. Unilateral MUT model.',f'# Hz S RI R {z0:.17g}']
    for i,frequency in enumerate(f):
        row=[frequency]
        for p in ('S11','S21','S12','S22'):
            v=data.s[p][i];row.extend((v.real,v.imag))
        lines.append(' '.join(format(float(v),'.17g') for v in row))
    return atomic_zip(path,{'calibrated_mut.s2p':'\n'.join(lines)+'\n',
        'calibrated_mut.csv':csv_record({'RF_Hz':f,'IF_Hz':iff},{'S11':data.s['S11'],'VC21':data.s['S21'],'S22':data.s['S22']}),
        'raw_mut.csv':csv_record({'RF_Hz':f,'IF_Hz':iff},result.raw),
        'frequency_map.csv':csv_record({'RF_Hz':f,'IF_Hz':iff,'LO_Hz':data.axes['LO1Freq']},{}),
        'report.json':json.dumps(result.manifest,ensure_ascii=False,indent=2)})
