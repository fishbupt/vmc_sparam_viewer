"""Reproduce a retained DUAL encoding for RF 10..15 / LO 20 / IF 10..5."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,time
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication,QMessageBox
from unittest.mock import patch
import vna_workbench.gui.main_window as main
import vna_workbench.gui.workflows.vmc.calibration as cal_gui
import vna_workbench.gui.workflows.vmc.simulation as sim_gui
from vna_workbench.simulation.mixer_characterization import SimulationOptions,generate_files
from vna_workbench.calibration.vmc.error_terms import calibrate
from vna_workbench.calibration.vmc.dut_correction import calibrate_mut

app=QApplication([]);errors=[]
QMessageBox.warning=lambda *args:errors.append(args[-1])
for source in ('manual','global_restore','legacy_migration'):
    with tempfile.TemporaryDirectory() as tmp:
        def settings(*args):return QSettings(str(Path(tmp)/(args[-1]+'.ini')),QSettings.Format.IniFormat)
        cfg=dict(rf_start_hz=10e9,rf_stop_hz=15e9,lo_hz=20e9,points=31,
            frequency_conversion='high_side',raw_axis='dual',z0=50,
            standard_sampling='cubic_ri',frequency_tolerance_hz=.001)
        if source=='global_restore':settings('MixerSParameterViewer').setValue('vmc_global/config',json.dumps(cfg))
        if source=='legacy_migration':
            old=settings('VMCFullCalibration')
            for k,v in cfg.items():old.setValue(k,v/1e9 if k in ('rf_start_hz','rf_stop_hz','lo_hz') else v)
        # Stale per-page settings must never override the shared worker configuration.
        old=settings('VMCDummySimulation');old.setValue('raw_axis','dual');old.setValue('rf_stop_hz',20)
        with patch.object(main,'QSettings',settings),patch.object(cal_gui,'QSettings',settings),patch.object(sim_gui,'QSettings',settings):
            w=main.Window();flow=w.workspace;flow.show_page(1);cal=flow.calibration
            if source=='manual':
                cal.spins['rf_stop_hz'].setValue(15);cal.points.setValue(31)
                cal.conversion.setCurrentIndex(cal.conversion.findData('high_side'))
            assert flow.vmc_session.values=={**cfg,'raw_axis':'rf'},(source,flow.vmc_session.values)
            assert cal.raw_axis.currentData()=='rf'
            assert not cal.raw_axis.model().item(cal.raw_axis.findData('dual')).isEnabled()
            flow.show_page(4);sim=flow.simulation
            o=asdict(sim.options())
            for k,v in flow.vmc_session.values.items():assert o[k]==v,(source,k,o[k],v)
            assert sim.raw_axis.currentData()=='rf'
            # Even a stale hidden control cannot alter the actual worker snapshot.
            sim.raw_axis.blockSignals(True);sim.raw_axis.setCurrentIndex(sim.raw_axis.findData('dual'));sim.raw_axis.blockSignals(False)
            assert sim.options().raw_axis=='rf'
            flow.vmc_session.apply_all()
            mixer=generate_files(None,tmp,SimulationOptions(rf_stop_hz=15e9,lo_hz=20e9,points=31,frequency_conversion='high_side'))
            sim.import_cal.setChecked(True);sim.file_fields['calibration_mixer'].setText(str(mixer.mixer_path))
            sim.definition_axis.setCurrentIndex(sim.definition_axis.findData('rf'));sim.directory.setText(tmp)
            sim.compute();deadline=time.monotonic()+20
            while sim.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
            assert sim.worker is None and not errors,errors
            assert sim.result and sim.result.simulation.options.raw_axis=='rf'
            assert '原始横轴 RF' in sim.log.toPlainText()
            result=sim.result
            solved=calibrate(result.calibration_inputs(),result.calibration_options())
            out=calibrate_mut(solved,result.mut_path)
            np.testing.assert_allclose(out.dataset.s['S21'],result.simulation.mut.s['S21'],atol=3e-14)
            w.close();app.processEvents()
            restored=main.Window();restored.workspace.show_page(4)
            assert restored.workspace.simulation.options().raw_axis=='rf'
            assert restored.workspace.vmc_session.values['rf_stop_hz']==15e9
            restored.close()
print('Manual edit, global restore and legacy migration all generate RF-indexed high-side SNP matching the global configuration.')
