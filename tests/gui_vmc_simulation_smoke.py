"""Threaded VMC raw generation -> matching calibration -> MUT integration."""
import os,sys,tempfile,time
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox,QPushButton,QScrollArea
import main,vmc_simulation_gui,vmc_calibration_gui
from vmc_simulation_gui import VMCSimulationDialog
from vmc_calibration_gui import VMCCalibrationDialog

app=QApplication([]);app.setStyleSheet(main.STYLE)
with tempfile.TemporaryDirectory() as tmp:
    settings=QSettings(str(Path(tmp)/'simulation.ini'),QSettings.Format.IniFormat)
    vmc_simulation_gui.QSettings=lambda *args:settings
    vmc_calibration_gui.QSettings=lambda *args:QSettings(str(Path(tmp)/'cal.ini'),QSettings.Format.IniFormat)
    main.QSettings=lambda *args:QSettings(str(Path(tmp)/'main.ini'),QSettings.Format.IniFormat)
    errors=[];QMessageBox.warning=lambda *args:errors.append(args[2])
    window=main.Window();dialog=VMCSimulationDialog(window);dialog.generated.connect(window.add_dataset)
    window.workspace.show_page(3)
    assert any(b.text()=='生成 VMC 原始测量 SNP' for b in window.findChildren(QPushButton))
    assert dialog.sampling.count()==2 and dialog.conversion.currentData()=='up'
    assert dialog.parameters['lo_hz'][0].value()==20 and '30～40' in dialog.mapping.text()
    assert not dialog.file_fields['open'].isEnabled() and not dialog.models['port2']['edf_db'].isEnabled()
    dialog.import_sol.setChecked(True);assert dialog.file_fields['open'].isEnabled();dialog.import_sol.setChecked(False)
    dialog.directory.setText(tmp);dialog.parameters['points'][0].setValue(41);dialog.show();dialog.compute()
    assert not dialog.run_btn.isEnabled() and not dialog.directory.isEnabled()
    def wait(d):
        deadline=time.monotonic()+20
        while d.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert d.worker is None,'worker timeout'
        assert not errors,errors
    wait(dialog);assert dialog.result and dialog.calibrate_btn.isEnabled()
    first=dialog.result;assert len(window.datasets)==2
    np.testing.assert_array_equal(window.datasets[0].s['S12'],0)
    assert len(dialog.figure.axes)==2
    # Actual handoff opens the configured dialog; inspect/compute without a nested modal loop.
    captured=[];original=VMCCalibrationDialog.exec
    def inspect(child):
        captured.append(child)
        assert child.points.value()==41 and child.if_start.text()=='30' and child.if_stop.text()=='40'
        assert child.defined_thru.isChecked() and not child.separate_sol.isChecked()
        assert child.fields['cal_raw'].text()==str(first.directory/'cal_mixer_raw.s2p')
        assert child.fields['cal_mixer'].text()==str(first.directory/'calibration_mixer.s2p')
        assert child.fields['mut_raw'].text()==str(first.mut_path)
        assert child.raw_axis.currentData()=='dual' and child.mut_axis.currentData()=='dual'
        child.compute();wait(child);assert child.calibration
        child.compute_mut();wait(child);assert child.mut_result
        np.testing.assert_allclose(child.mut_result.dataset.s['S21'],first.simulation.mut.s['S21'],atol=2e-14)
        return 0
    VMCCalibrationDialog.exec=inspect
    try:dialog.open_calibration()
    finally:VMCCalibrationDialog.exec=original
    assert len(captured)==1 and len(window.datasets)==4
    for size in [(1380,920),(1000,700)]:
        dialog.resize(*size);app.processEvents();dialog.canvas.draw()
        assert dialog.width()==size[0]
        if size[0]==1380:assert dialog.findChild(QScrollArea).horizontalScrollBar().maximum()==0
        assert dialog.run_btn.isVisible() and dialog.calibrate_btn.isVisible()
    dialog.conversion.setCurrentIndex(dialog.conversion.findData('down'));assert dialog.result is None and not dialog.calibrate_btn.isEnabled()
    dialog.parameters['rf_start_hz'][0].setValue(20);dialog.parameters['rf_stop_hz'][0].setValue(30)
    dialog.parameters['lo_hz'][0].setValue(18);dialog.raw_axis.setCurrentIndex(dialog.raw_axis.findData('if'))
    dialog.separate_port2.setChecked(True);assert dialog.models['port2']['tracking_db'].isEnabled()
    dialog.models['port2']['tracking_db'].setValue(-.8)
    dialog.noise.setChecked(True);dialog.parameters['noise_floor_db'][0].setValue(-65)
    assert dialog.parameters['noise_seed'][0].isEnabled()
    dialog.compute();wait(dialog);assert dialog.result and dialog.result.directory!=first.directory
    second=dialog.result
    imported=VMCSimulationDialog(window)
    assert imported.conversion.currentData()=='down' and imported.separate_port2.isChecked() and imported.noise.isChecked()
    imported.import_sol.setChecked(True);imported.import_thru.setChecked(True);imported.import_cal.setChecked(True)
    assert not imported.models['calibration_mixer']['transmission_db'].isEnabled()
    for k in ('open','short','load'):imported.file_fields[k].setText(str(second.directory/f'standard_{k}.s1p'))
    imported.file_fields['thru'].setText(str(second.directory/'thru_definition.s2p'))
    imported.file_fields['calibration_mixer'].setText(str(second.directory/'calibration_mixer.s2p'))
    imported.compute();wait(imported);assert imported.result
    assert imported.result.simulation.manifest['source_inputs']
    # Invalid overlap should fail visibly, publish no run, and restore controls.
    before=len(list(Path(tmp).glob('vmc_dummy_*')))
    imported.parameters['lo_hz'][0].setValue(1);imported.raw_axis.setCurrentIndex(imported.raw_axis.findData('dual'))
    imported.compute()
    deadline=time.monotonic()+20
    while imported.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert imported.worker is None and errors and imported.result is None and imported.run_btn.isEnabled()
    assert len(list(Path(tmp).glob('vmc_dummy_*')))==before
    imported.close();dialog.close();window.close()
print('VMC generation UI passed: defaults / background / handoff / recovery / axes / settings / imports / invalidation / errors')
