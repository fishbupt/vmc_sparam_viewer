"""Offscreen high-side presets, worker generation and workflow handoff."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox
from unittest.mock import patch
import vna_workbench.gui.workflows.vmc.simulation as full
import vna_workbench.gui.workflows.vmc.characterization_simulation as char
import vna_workbench.gui.workflows.vmc.mixer_characterization as extract
import vna_workbench.gui.workflows.vmc.calibration as cal

app=QApplication([])
errors=[]
QMessageBox.warning=lambda *args:errors.append(args[-1])

def wait(dialog):
    deadline=time.monotonic()+30
    while dialog.worker and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert dialog.worker is None,'worker timed out'
    assert not errors,errors

with tempfile.TemporaryDirectory() as tmp:
    def settings(name):return QSettings(str(Path(tmp)/(name+'.ini')),QSettings.Format.IniFormat)
    with patch.object(full,'QSettings',lambda *args:settings('full')), \
         patch.object(char,'QSettings',lambda *args:settings('char')), \
         patch.object(extract,'QSettings',lambda *args:settings('extract')), \
         patch.object(cal,'QSettings',lambda *args:settings('cal')):
        a=char.SimulationDialog();a.high_side_btn.click();a.directory.setText(tmp)
        assert a.conversion.currentData()=='high_side' and a.synthetic_kit.isChecked()
        a.compute();wait(a);assert a.result and a.characterize_btn.isEnabled()
        assert a.result.simulation.truth.axes['OutputFreq'][-1]==5e9
        def check_characterization(d):
            assert d.conversion.currentData()=='high_side'
            d.compute();wait(d)
            for k in a.result.simulation.truth.s:
                np.testing.assert_allclose(d.result.dataset.s[k],a.result.simulation.truth.s[k],atol=3e-14)
            return 0
        with patch.object(extract.CharacterizeDialog,'exec',check_characterization):
            a.open_characterization()
        b=full.VMCSimulationDialog();b.high_side_btn.click();b.directory.setText(tmp)
        assert b.raw_axis.currentData()=='rf' and b.synthetic_sol.isChecked()
        assert '10～5' in b.mapping.text()
        b.compute();wait(b);assert b.result
        def check_calibration(d):
            assert d.conversion.currentData()=='high_side'
            assert d.if_start.text()=='10' and d.if_stop.text()=='5'
            d.compute();wait(d);d.compute_mut();wait(d)
            np.testing.assert_allclose(d.mut_result.dataset.s['S21'],b.result.simulation.mut.s['S21'],atol=3e-14)
            return 0
        with patch.object(cal.VMCCalibrationDialog,'exec',check_calibration):b.open_calibration()
        b2=full.VMCSimulationDialog()
        assert b2.conversion.currentData()=='high_side' and b2.synthetic_sol.isChecked()
        b.conversion.setCurrentIndex(b.conversion.findData('up'))
        assert b.result is None and not b.calibrate_btn.isEnabled()
        for d in (a,b,b2):d.close()
print('High-side GUI presets, generation, characterization and MUT handoff OK (offscreen).')
