import os,sys,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathlib import Path
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox,QPushButton
from simulate_gui import SimulationDialog
import simulate_gui,characterize_gui
from main import Window
from characterization import characterize,Options
import numpy as np
app=QApplication([])
with tempfile.TemporaryDirectory() as tmp:
 settings=QSettings(tmp+'/gui.ini',QSettings.Format.IniFormat)
 settings.setValue('standard_sampling','linear_mag_unwrapped_phase')
 simulate_gui.QSettings=lambda *a:settings
 characterize_gui.QSettings=lambda *a:QSettings(tmp+'/characterize.ini',QSettings.Format.IniFormat)
 errors=[];QMessageBox.warning=lambda *a:errors.append(a[2])
 main=Window();dialog=SimulationDialog(main);dialog.generated.connect(main.add_dataset)
 assert any('生成 SOL' in b.text() for b in main.findChildren(QPushButton))
 kit=Path(__file__).resolve().parents[1]/'examples/keysight_validation'
 for e,n in zip(dialog.standards,['open.s1p','short_validation_band.s1p','load.s1p']):e.setText(str(kit/n))
 dialog.directory.setText(tmp);dialog.show();dialog.compute()
 deadline=time.monotonic()+10
 while dialog.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
 assert not errors,errors
 assert dialog.result is not None and dialog.characterize_btn.isEnabled()
 assert len(main.datasets)==1
 assert len(list(dialog.result.directory.glob('*.s2p')))==7
 # Inspect automatic characterization mapping without running a nested modal loop.
 captured=[]
 original=characterize_gui.CharacterizeDialog.exec
 def inspect(child):
  captured.append(child)
  assert [e.text() for e in child.measurements]==[str(p) for p in dialog.result.measurement_paths]
  assert [e.text() for e in child.standards]==[str(p) for p in dialog.result.standard_paths]
  assert child.sampling.currentData()=='cubic_ri'
  assert child.second.currentData()=='raw'
  assert child.sampling.count()==2
  assert child.conversion.currentData()==dialog.result.simulation.manifest['frequency_conversion']
  return 0
 characterize_gui.CharacterizeDialog.exec=inspect
 dialog.open_characterization();assert len(captured)==1
 characterize_gui.CharacterizeDialog.exec=original
 first=dialog.result
 recovered=characterize(first.measurement_paths,first.standard_paths,Options(standard_sampling='cubic_ri'))
 print('GUI no-noise recovery max complex:',max(max(abs(recovered.dataset.s[k]-first.simulation.truth.s[k])) for k in recovered.dataset.s))
 # Verify direction changes invalidate results; then generate a sum-branch run.
 assert dialog.sampling.count()==2 and dialog.sampling.currentData()=='cubic_ri'
 dialog.conversion.setCurrentIndex(dialog.conversion.findData('up'))
 assert dialog.result is None and not dialog.characterize_btn.isEnabled()
 dialog.parameters['rf_stop_hz'][0].setValue(15)
 dialog.compute()
 deadline=time.monotonic()+10
 while dialog.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
 assert not errors,errors
 assert dialog.result.simulation.manifest['frequency_conversion']=='up'
 np.testing.assert_array_equal(dialog.result.simulation.truth.axes['OutputFreq'],dialog.result.simulation.frequency+5e9)
 characterize_gui.CharacterizeDialog.exec=inspect
 dialog.open_characterization();assert len(captured)==2
 characterize_gui.CharacterizeDialog.exec=original
 child=captured[-1];child.result=object();child.save_btn.setEnabled(True)
 child.conversion.setCurrentIndex(child.conversion.findData('down'))
 assert child.result is None and not child.save_btn.isEnabled()
 child.demo();assert child.conversion.currentData()=='down'
 child.grab().save(tmp+'/characterization_check.png')
 first=dialog.result
 dialog.noise.setChecked(True);dialog.parameters['noise_floor_db'][0].setValue(-70)
 assert dialog.result is None and not dialog.characterize_btn.isEnabled()
 assert dialog.parameters['noise_seed'][0].isEnabled()
 dialog.compute()
 deadline=time.monotonic()+10
 while dialog.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
 assert dialog.result.simulation.manifest['noise']['enabled']
 assert not errors,errors
 assert dialog.result.directory!=first.directory
 assert len(main.datasets)==3
 dialog.grab().save(tmp+'/gui_check.png')
 again=SimulationDialog(main)
 assert again.conversion.currentData()=='up' and again.sampling.count()==2
 assert '解缠绕相位' in again.sampling.itemText(again.sampling.findData('linear_ri'))
 assert '解缠绕相位' in captured[-1].sampling.itemText(captured[-1].sampling.findData('linear_ri'))
 assert '解缠绕相位' in again.sampling.itemText(again.sampling.findData('cubic_ri'))
 assert '解缠绕相位' in captured[-1].sampling.itemText(captured[-1].sampling.findData('cubic_ri'))
 assert again.noise.isChecked() and again.parameters['noise_floor_db'][0].value()==-70
 again.close();dialog.close();main.close()
 print('GUI: generation, preview, truth delivery, transfer to characterization, noise, settings and invalidation OK')
