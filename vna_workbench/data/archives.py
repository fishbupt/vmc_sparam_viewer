"""Shared CSV records and atomic ZIP output."""

from pathlib import Path
import csv, io, os, tempfile, zipfile

def csv_record(axes,values):
    out=io.StringIO();w=csv.writer(out);head=list(axes)
    for name in values: head.extend((name+'_real',name+'_imag'))
    w.writerow(head)
    for i in range(len(next(iter(axes.values())))):
        row=[v[i] for v in axes.values()]
        for v in values.values(): row.extend((v[i].real,v[i].imag))
        w.writerow(row)
    return out.getvalue()


def atomic_zip(path,payload):
    path=Path(path);temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.zip',delete=False) as stream: temp=stream.name
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for name,blob in payload.items(): z.writestr(name,blob)
        os.replace(temp,path);temp=None
    finally:
        if temp is not None: Path(temp).unlink(missing_ok=True)
    return str(path)
