"""Offscreen UI workflow including background compute, reload and invalidation."""
import os,sys,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox,QPushButton
import vmc_calibration_gui
from vmc_calibration_gui import VMCCalibrationDialog
from vmc_calibration import save_calibration,load_calibration,export_mut
from test_vmc_calibration import fixture
from main import Window,STYLE
import numpy as np

app=QApplication([])
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);screenshots=Path(os.environ.get('VMC_GUI_SCREENSHOT_DIR',tmp));screenshots.mkdir(parents=True,exist_ok=True)
    settings=QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)
    vmc_calibration_gui.QSettings=lambda *a:settings
    errors=[];QMessageBox.warning=lambda *a:errors.append(a[2])
    main=Window();dialog=VMCCalibrationDialog(main);dialog.generated.connect(main.add_dataset)
    inp,opts,mut,truth=fixture(root)
    assert any('VMC 校准误差项' in b.text() for b in main.findChildren(QPushButton))
    assert dialog.tabs.count()==2 and dialog.tabs.tabText(1)=='校准 MUT'
    assert dialog.sampling.count()==2
    assert dialog.config_panel.isAncestorOf(dialog.spins['rf_start_hz'])
    assert dialog.config_panel.isAncestorOf(dialog.mut_axis)
    assert dialog.standard_group.isAncestorOf(dialog.fields['std_P1_OPEN'])
    assert dialog.standard_group.isAncestorOf(dialog.fields['definition_thru_RF'])
    for key in ['sol_shared_OPEN','thru_RF','cal_raw']:
        assert dialog.measurement_group.isAncestorOf(dialog.fields[key])
    assert dialog.mixer_group.isAncestorOf(dialog.fields['cal_mixer'])
    assert dialog.if_start.text()=='30' and dialog.if_stop.text()=='40'
    for kind,path in zip(['OPEN','SHORT','LOAD'],inp.standards['P1']):dialog.fields['std_P1_'+kind].setText(path)
    for kind,path in zip(['OPEN','SHORT','LOAD'],inp.sol['P1_RF']):dialog.fields['sol_shared_'+kind].setText(path)
    dialog.fields['thru_RF'].setText(inp.thru_raw['RF'])
    dialog.fields['cal_mixer'].setText(inp.calibration_mixer);dialog.fields['cal_raw'].setText(inp.cal_mixer_raw)
    dialog.points.setValue(opts.points);dialog.fields['mut_raw'].setText(mut)
    def wait():
        deadline=time.monotonic()+15
        while dialog.worker and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        assert dialog.worker is None,'worker did not finish'
        assert not errors,errors
    dialog.show();dialog.compute();assert not dialog.compute_btn.isEnabled();wait()
    assert dialog.calibration and dialog.mut_btn.isEnabled() and dialog.save_btn.isEnabled()
    dialog.show_term();assert len(main.datasets)==1
    dialog.compute_mut();wait();assert dialog.mut_result and dialog.export_btn.isEnabled()
    assert len(main.datasets)==3
    np.testing.assert_allclose(main.datasets[-1].s['S21'],truth[:,1,0],atol=2e-14,rtol=0)
    bundle=root/'calibration.zip'
    dialog.begin(save_calibration,(dialog.calibration,bundle),lambda _:None);wait()
    dialog.fields['mut_raw'].setText(str(root/'new.s2p'))
    assert dialog.calibration and dialog.mut_result is None and not dialog.export_btn.isEnabled()
    dialog.fields['cal_raw'].setText('changed.s2p');assert dialog.calibration is None and not dialog.mut_btn.isEnabled()
    dialog.begin(load_calibration,(bundle,),dialog.accept_loaded);wait()
    assert dialog.calibration and dialog.points.value()==41 and dialog.separate_sol.isChecked()
    dialog.fields['mut_raw'].setText(mut);dialog.compute_mut();wait()
    dialog.begin(export_mut,(dialog.mut_result,root/'result.zip'),lambda _:None);wait()
    assert (root/'result.zip').is_file()
    dialog.tabs.setCurrentIndex(0);app.processEvents()
    assert dialog.grab().save(str(screenshots/'vmc_calibration_split_advanced.png'))
    # Inspect the default shared-files view and resizing independently of reload mapping.
    dialog.separate_sol.setChecked(False);app.processEvents()
    assert dialog.shared_sol.isVisible() and not dialog.sol_groups.isVisible()
    assert dialog.grab().save(str(screenshots/'vmc_calibration_split_shared.png'))
    dialog.resize(1000,700);app.processEvents()
    assert dialog.config_scroll.geometry().right()<dialog.tabs.geometry().left()
    dialog.resize(1320,940);app.processEvents()
    dialog.tabs.setCurrentIndex(1);app.processEvents()
    assert dialog.grab().save(str(screenshots/'vmc_calibration_split_mut.png'))
    dialog.reject();again=VMCCalibrationDialog(main)
    assert again.points.value()==41 and again.fields['mut_raw'].text()==mut
    assert again.calibration is None and not again.mut_btn.isEnabled()
    again.reject();main.close()
print('VMC Qt offscreen workflow passed: compute / MUT / main view / save / reload / export / invalidation / settings.')
