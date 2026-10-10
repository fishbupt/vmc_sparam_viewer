"""Persistent page state, multi-file rendering and embedded background workflow."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import time
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QMessageBox
import main, vmc_calibration_gui, vmc_simulation_gui
from parser import Dataset, PARAMS

app = QApplication([])
app.setStyleSheet(main.STYLE)
if os.environ.get('VMC_GUI_FONT'):
    QFontDatabase.addApplicationFont(os.environ['VMC_GUI_FONT'])
errors = []
QMessageBox.warning = lambda *args: errors.append(args[2])

def wait(page):
    deadline = time.monotonic() + 25
    while getattr(page, 'worker', None) is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    assert getattr(page, 'worker', None) is None, 'worker timeout'
    assert not errors, errors

with tempfile.TemporaryDirectory() as tmp:
    def settings(*args):
        return QSettings(str(Path(tmp) / (args[-1] + '.ini')), QSettings.Format.IniFormat)
    for module in (main, vmc_calibration_gui, vmc_simulation_gui):
        module.QSettings = settings
    window = main.Window()
    window.show()
    app.processEvents()
    assert window.workspace.navigation.currentRow() == 1
    assert window.workspace.stack.currentIndex() == 0
    assert window.workspace.calibration is None  # No project is required at startup.
    assert not window.log.isVisible()
    f = np.array([10e9, 11e9, 12e9])
    for n, value in enumerate((.1, .2, .3)):
        window.add_dataset(Dataset(f'file{n}.s2p', 'S2P / test',
            {p: np.full(3, value, complex) for p in PARAMS},
            {'StimulusFreq': f.copy(), 'OutputFreq': f + 20e9}, np.zeros(3, int)))
    assert all(len(ax.lines) == 3 for ax in window.axes)
    original_color = window.axes[0].lines[1].get_color()
    window.files.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert all(len(ax.lines) == 2 for ax in window.axes)
    window.files.setCurrentRow(1)
    window.axis.setCurrentIndex(window.axis.findData('OutputFreq'))
    window.files.setCurrentRow(2)
    window.files.setCurrentRow(1)
    assert window.axis.currentData() == 'OutputFreq'
    window.remove()
    assert all(len(ax.lines) == 1 for ax in window.axes)
    assert window.axes[0].lines[0].get_color() != original_color
    window.files.item(0).setCheckState(Qt.CheckState.Checked)
    assert len(window.axes[0].lines) == 2
    window.set_y_limits('S21', (-50, 0))
    window.overlay.setCurrentIndex(1)
    assert len(window.axes[0].lines) == 1
    np.testing.assert_allclose(window.axes[2].get_ylim(), [-50, 0])
    window.workspace.show_page(6)
    comparison = window.workspace.comparison
    assert comparison.pairs
    comparison.compute()
    wait(comparison)
    assert comparison.result is not None
    window.workspace.show_page(1)
    cal = window.workspace.calibration
    cal.spins['lo_hz'].setValue(19)
    for page in (2, 3, 4, 5):
        window.workspace.show_page(page)
        assert window.workspace.calibration is cal
        assert cal.spins['lo_hz'].value() == 19
    assert cal.tabs.currentIndex() == 1
    # Complete the real embedded generator -> shared solver -> MUT handoff.
    window.simulate_vmc()
    sim = window.workspace.simulation
    window.workspace.clicked_navigation(window.workspace.navigation.currentItem())
    assert window.workspace.stack.currentWidget() is cal
    window.simulate_vmc()
    assert window.workspace.simulation is sim
    sim.directory.setText(tmp)
    sim.parameters['points'][0].setValue(11)
    sim.compute()
    assert window.busy()
    window.close()
    assert window.isVisible()  # Never destroy a page while its thread runs.
    wait(sim)
    sim.open_calibration()
    assert window.workspace.calibration is cal
    assert window.workspace.stack.currentWidget() is cal
    assert cal.points.value() == 11
    assert cal.fields['mut_raw'].text() == str(sim.result.mut_path)
    cal.compute()
    # Queued file import must not consume a path while a page is busy.
    queued = Path(tmp) / 'queued.s2p'
    queued.write_text('# Hz S RI R 50\n10000000000 0.1 0 0.2 0 0 0 0.1 0\n')
    window.load_paths([str(queued)])
    window.read_next()
    assert window.pending == [str(queued)]
    wait(cal)
    deadline = time.monotonic() + 10
    while (window.pending or window.task) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.pending and window.task is None
    assert any(data.name == str(queued) for data in window.datasets)
    package = cal.calibration
    assert package is not None
    window.workspace.show_page(5)
    assert cal.calibration is package
    cal.compute_mut()
    wait(cal)
    assert cal.mut_result is not None
    np.testing.assert_allclose(cal.mut_result.dataset.s['S21'], sim.result.simulation.mut.s['S21'], atol=2e-14)
    assert window.workspace.stack.currentIndex() == 0
    assert window.datasets[-1] is cal.mut_result.dataset
    assert '已校准 MUT' in window.log.toPlainText()
    window.log_toggle.setChecked(True)
    assert window.log.isVisible()
    window.log_toggle.setChecked(False)
    # Rebuild statistics after imported results change the dataset list.
    window.workspace.show_page(6)
    assert window.workspace.comparison is not comparison
    for page in (0, 1, 2, 3, 4, 5, 6):
        window.workspace.show_page(page)
        window.resize(1000, 700)
        app.processEvents()
        assert window.width() == 1000, (page, window.width())
        assert window.workspace.stack.width() > 300
    window.workspace.show_page(0)
    window.clear_files()
    assert not window.datasets and all(not ax.lines for ax in window.axes)
    # Optional review screenshots contain real program widgets, not a mockup.
    destination = os.environ.get('VMC_GUI_SCREENSHOT_DIR')
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        for size in ((1420, 900), (1000, 700)):
            window.resize(*size)
            window.add_dataset(Dataset('MUT_truth.s2p', 'S2P / review',
                {p: np.full(3, .1, complex) for p in PARAMS}, {'StimulusFreq': f}, np.zeros(3, int)))
            app.processEvents()
            window.canvas.draw()
            window.grab().save(str(target / f'workbench_{size[0]}.png'))
        window.workspace.show_page(4)
        window.resize(1420, 900)
        app.processEvents()
        window.grab().save(str(target / 'workbench_solver.png'))
    window.close()
print('Workbench UI passed: default / overlay / axes / shared state / threaded handoff / close guard / statistics / layout')
