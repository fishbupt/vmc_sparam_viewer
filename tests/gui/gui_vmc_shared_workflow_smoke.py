"""Complete five-step workflow with a shared configuration and independent P2 kit."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox
from unittest.mock import patch
from tests.vmc.test_independent_kits import make_kits
import vna_workbench.gui.main_window as main
import vna_workbench.gui.workflows.vmc.calibration as cal_gui
import vna_workbench.gui.workflows.vmc.simulation as sim_gui
import vna_workbench.gui.workflows.vmc.characterization_simulation as sol_gui
import vna_workbench.gui.workflows.vmc.mixer_characterization as char_gui

app=QApplication([]);app.setStyleSheet(main.STYLE);errors=[]
if os.environ.get('VMC_GUI_FONT'):
    from PyQt6.QtGui import QFontDatabase,QFont
    fontid=QFontDatabase.addApplicationFont(os.environ['VMC_GUI_FONT'])
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(fontid)[0],10))
QMessageBox.warning=lambda *args:errors.append(args[-1])
def wait(page):
    deadline=time.monotonic()+30
    while page.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    app.processEvents()
    assert page.worker is None and not errors,errors

with tempfile.TemporaryDirectory() as tmp:
    def settings(*args):return QSettings(str(Path(tmp)/(args[-1]+'.ini')),QSettings.Format.IniFormat)
    with patch.object(main,'QSettings',settings),patch.object(cal_gui,'QSettings',settings), \
         patch.object(sim_gui,'QSettings',settings),patch.object(sol_gui,'QSettings',settings), \
         patch.object(char_gui,'QSettings',settings):
        w=main.Window();w.show();flow=w.workspace
        assert flow.navigation.currentRow()==1 and flow.calibration is None
        flow.show_page(1);flow.high_side_preset();flow.calibration.spins['z0'].setValue(75)
        flow.calibration.points.setValue(31)
        config=dict(flow.vmc_session.values);paths=make_kits(tmp,75)
        flow.show_page(2);a=flow.sol_simulation;a.directory.setText(tmp)
        assert a.options().z0==75 and a.options().points==31 and a.options().lo_hz==20e9
        assert a.sweep_group.isHidden()
        a.synthetic_kit.setChecked(False);a.separate_kit.setChecked(True)
        for field,p in zip(a.standards+a.standards2,paths):field.setText(str(p))
        a.compute();wait(a);saved=a.result;a.open_characterization()
        b=flow.characterization
        assert flow.vmc_session.values==config and b.separate_kit.isChecked()
        assert [e.text() for e in b.standards+b.standards2]==list(map(str,saved.standard_paths))
        b.compute();wait(b)
        for k,v in saved.simulation.truth.s.items():np.testing.assert_allclose(b.result.dataset.s[k],v,atol=3e-14)
        b.use_characterization();wait(b)
        c=flow.simulation
        assert c.definition_axis.currentData()=='rf' and c.import_cal.isChecked() and c.separate_kit.isChecked()
        assert c.options().points==31 and c.options().z0==75 and c.sweep_group.isHidden()
        c.directory.setText(tmp);c.compute();wait(c);run=c.result;c.open_calibration()
        cal=flow.calibration
        assert flow.stack.currentWidget() is cal and cal.separate_std.isChecked()
        cal.compute();wait(cal);flow.show_page(6);cal.compute_mut();wait(cal)
        np.testing.assert_allclose(cal.mut_result.dataset.s['S21'],run.simulation.mut.s['S21'],atol=3e-14)
        # Unrelated navigation preserves results; changing shared RF invalidates all steps.
        flow.show_page(2);assert a.result is saved and cal.calibration is not None
        flow.show_page(1);cal.spins['rf_stop_hz'].setValue(14)
        assert flow.vmc_session.values['rf_stop_hz']==14e9
        assert a.result is None and b.result is None and c.result is None and cal.calibration is None
        assert a.options().rf_stop_hz==14e9 and c.options().rf_stop_hz==14e9
        for page in (1,2,3,4):
            flow.show_page(page);app.processEvents()
            w.grab().save(f'/tmp/vmc_shared_workflow_{page}.png')
        w.close();app.processEvents()
        restored=main.Window();restored.workspace.show_page(4)
        assert restored.workspace.simulation.options().rf_stop_hz==14e9
        assert restored.workspace.simulation.options().z0==75
        restored.close()
print('Shared VMC five-step workflow, independent port kits, invalidation and settings passed (offscreen).')
