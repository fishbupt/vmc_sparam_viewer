"""Independent single/A-B views, full-grid overlays, matching, exports and state retention."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys, tempfile, time, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
import main
from parser import Dataset, PARAMS
app = QApplication([])
app.setStyleSheet(main.STYLE)
if os.environ.get('VMC_GUI_FONT'):
    QFontDatabase.addApplicationFont(os.environ['VMC_GUI_FONT'])
errors = []
QMessageBox.warning = lambda *args: errors.append(args[2])
def wait(page):
    deadline = time.monotonic()+20
    while page.worker and time.monotonic() < deadline:
        app.processEvents(); time.sleep(.01)
    app.processEvents()
    assert page.worker is None and not errors, errors
with tempfile.TemporaryDirectory() as tmp:
    main.QSettings = lambda *args: QSettings(str(Path(tmp)/'settings.ini'), QSettings.Format.IniFormat)
    w = main.Window(); w.show(); app.processEvents()
    c = w.comparison_view
    assert w.analysis_tabs.currentIndex() == 0 and not c.run.isEnabled()
    def data(name, f, magnitude, segments):
        phase = np.array([170, -170, -150, 160])[:len(f)]
        z = magnitude*np.exp(1j*np.deg2rad(phase))
        return Dataset(name, 'S2P / test', {p:z.copy() for p in PARAMS},
            {'StimulusFreq': np.array(f, float), 'OutputFreq': np.array(f, float)+20e9}, np.array(segments))
    a = data('a.s2p', [10e9,11e9,12e9,13e9], .1, [0,0,1,1])
    b = data('b.s2p', [10e9,11e9,12e9], .2, [0,0,1])
    d = data('c.s2p', [10e9,11e9], .3, [0,0])
    w.add_dataset(a); assert not c.run.isEnabled()
    w.add_dataset(b); w.add_dataset(d)
    assert c.selection()[0] is a and c.selection()[1] is b
    assert len(w.axes[0].lines) == 1
    np.testing.assert_allclose(w.axes[0].lines[0].get_ydata(), 20*np.log10(.3))
    # All single-file parameters and imported files share one plain curve style.
    for row in range(w.files.count()):
        w.files.setCurrentRow(row)
        for ax in w.axes:
            for line in ax.lines:
                assert line.get_color() == '#2563eb' and line.get_linestyle() == '-'
                assert line.get_marker() == 'None'
    w.files.setCurrentRow(0); w.mode.setCurrentText('相位 (°)')
    w.axis.setCurrentIndex(w.axis.findData('OutputFreq')); w.set_y_limits('S21',(-180,180))
    w.compare_any_files(); assert w.analysis_tabs.currentIndex() == 1
    assert c.selection()[0] is a and c.selection()[1] is b
    assert not w.single_controls.isVisible()
    # Four A / three B raw points, including unmatched points, and no third file.
    lines = c.axes[0].lines
    assert len(lines) == 4
    assert lines[0].get_color() != lines[2].get_color()
    assert lines[0].get_linestyle() == '-' and lines[2].get_linestyle() == '--'
    assert sum(len(line.get_xdata()) for line in lines[:2]) == 4
    assert sum(len(line.get_xdata()) for line in lines[2:]) == 3
    c.metric.setCurrentText('相位叠加 (°)')
    c.set_y_limits('S21',(-200,200)); assert c.y_limits and w.y_limits
    c.left_axis.setCurrentText('OutputFreq'); c.axis.setCurrentText('OutputFreq')
    c.compute(); wait(c)
    result = c.result
    assert result.left_axis == 'OutputFreq' and len(result.i) == 3
    np.testing.assert_allclose(result.delta['S21']['幅度差 (dB)'], -20*np.log10(2))
    c.metric.setCurrentText('幅度差 (dB)')
    w.workspace.show_page(6)
    assert w.workspace.comparison is c and c.result is result
    w.analysis_tabs.setCurrentIndex(0)
    assert w.dataset is a and w.mode.currentText() == '相位 (°)'
    assert w.axis.currentData() == 'OutputFreq'
    np.testing.assert_allclose(w.axes[2].get_ylim(),(-180,180))
    w.files.setCurrentRow(2)
    assert c.result is result and c.selection()[0] is a
    # Appending unrelated data preserves selected pair, computed result and settings.
    extra = data('extra.s2p', [10e9,11e9], .4,[0,0]); w.add_dataset(extra)
    assert c.result is result and c.metric.currentText() == '幅度差 (dB)'
    c.swap_files(); assert c.selection()[0] is b and c.selection()[1] is a
    assert c.result is None and c.left_axis.currentText() == 'OutputFreq'
    c.left_segment.setCurrentIndex(c.left_segment.findData(1))
    c.right_segment.setCurrentIndex(c.right_segment.findData(1))
    c.compute(); wait(c); assert c.result.i.tolist() == [2] and c.result.j.tolist() == [2]
    np.testing.assert_allclose(c.result.delta['S11']['幅度差 (dB)'],20*np.log10(2))
    out = Path(tmp)/'difference.csv'
    QFileDialog.getSaveFileName = lambda *args: (str(out),'CSV (*.csv)')
    c.export(); wait(c)
    with out.open(encoding='utf-8-sig') as stream: rows=list(csv.DictReader(stream))
    assert rows[0]['S2P_Row']=='3' and float(rows[0]['S2P_OutputFreq_Hz'])==32e9
    png=Path(tmp)/'plot.png'; QFileDialog.getSaveFileName=lambda *args:(str(png),'PNG (*.png)')
    c.export_image(); assert png.stat().st_size > 1000
    try: c.set_y_limits('S11',(10,0))
    except ValueError: pass
    else: raise AssertionError('invalid limits accepted')
    # Removing an unrelated file preserves results; removing selected B clears stale output.
    previous=c.result; w.remove(); assert c.result is previous
    w.files.setCurrentRow(0); w.remove(); assert c.result is None and not c.save.isEnabled()
    c.right.setCurrentIndex(c.left.currentIndex()); assert not c.run.isEnabled()
    w.clear_files(); assert c.result is None and not c.pairs
    assert not c.run.isEnabled() and all(not ax.lines for ax in c.axes)
    # General A/B analysis also accepts data with no StimulusFreq axis.
    a.axes={'OutputFreq':a.axes['OutputFreq']}; b.axes={'OutputFreq':b.axes['OutputFreq']}
    w.add_dataset(a); w.add_dataset(b); c.compute(); wait(c)
    assert c.result.left_axis == 'OutputFreq' and len(c.result.i)==3
    w.analysis_tabs.setCurrentIndex(1)
    w.resize(1000,700); app.processEvents(); assert w.width()==1000
    assert w.analysis_tabs.width() <= w.workspace.stack.width()
    assert c.canvas.height() >= 260
    destination=os.environ.get('VMC_GUI_SCREENSHOT_DIR')
    if destination:
        target=Path(destination); target.mkdir(parents=True,exist_ok=True)
        w.grab().save(str(target/'two_file_comparison_1000.png'))
        for index,name in ((0,'single_view.png'),(1,'two_file_comparison.png')):
            w.analysis_tabs.setCurrentIndex(index); w.resize(1420,900); app.processEvents(); c.canvas.draw()
            w.grab().save(str(target/name))
    w.close(); app.processEvents()
print('Analysis UI passed: independent pages / full-grid overlays / two axes / segments / state / exports')
