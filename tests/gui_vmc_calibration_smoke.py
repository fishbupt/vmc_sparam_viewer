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
from main import Window
import numpy as np

app=QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);settings=QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)
    vmc_calibration_gui.QSettings=lambda *a:settings
    errors=[];QMessageBox.warning=lambda *a:errors.append(a[2])
    main=Window();dialog=VMCCalibrationDialog(main);dialog.generated.connect(main.add_dataset)
    inp,opts,mut,truth=fixture(root)
    assert any('VMC 校准误差项' in b.text() for b in main.findChildren(QPushButton))
    assert dialog.tabs.count()==2 and dialog.tabs.tabText(1)=='校准 MUT'
    assert dialog.sampling.count()==2
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
    dialog.grab().save('/workspace/scratch/81ccd9fb0d9c/vmc_calibration_v160_gui.png')
    dialog.tabs.setCurrentIndex(1);app.processEvents()
    dialog.grab().save('/workspace/scratch/81ccd9fb0d9c/vmc_mut_v160_gui.png')
    dialog.reject();again=VMCCalibrationDialog(main)
    assert again.points.value()==41 and again.fields['mut_raw'].text()==mut
    assert again.calibration is None and not again.mut_btn.isEnabled()
    again.reject();main.close()
print('VMC Qt offscreen workflow passed: compute / MUT / main view / save / reload / export / invalidation / settings.')
