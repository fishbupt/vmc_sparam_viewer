"""Viewer data columns and complete CSV export."""

import csv
from vna_workbench.data.models import PARAMS
from vna_workbench.analysis.transforms import values

def table_data(data):
    cols = {'SegIndex': data.segment, **{k + ' (Hz)': v for k, v in data.axes.items()}, **data.auxiliary}
    for p in PARAMS:
        z = data.s[p]
        cols[p + ' Real'] = z.real
        cols[p + ' Imag'] = z.imag
        cols[p + ' Mag (dB)'] = values(z, 'dB', data.segment)
        cols[p + ' Phase (Deg)'] = values(z, 'Phase', data.segment)
    return list(cols), list(cols.values())


def export_csv(data, path):
    headers, columns = table_data(data)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in zip(*columns):
            writer.writerow([format(float(x), '.17g') for x in row])
