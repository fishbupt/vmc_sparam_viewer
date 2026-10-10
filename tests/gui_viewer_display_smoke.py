"""Offscreen checks of main-view display actions and real plotted Y limits."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QDialog
import main
from parser import Dataset, PARAMS

app = QApplication([])
app.setStyleSheet(main.STYLE)
with tempfile.TemporaryDirectory() as tmp:
    settings = QSettings(str(Path(tmp)/'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('mode', '展开相位 (°)')
    main.QSettings = lambda *args: settings
    window = main.Window()
    assert window.mode.currentText() == '解缠绕相位 (°)'
    phase = np.array([170, -170, 0, -170, 170, 170, -170.])
    z = .1*np.exp(1j*np.deg2rad(phase)); z[2] = 0
    data = Dataset('display.s2p', 'S2P / test', {p:z.copy() for p in PARAMS},
                   {'StimulusFreq': np.arange(7.)*1e9+10e9}, np.array([0,0,0,0,0,1,1]))
    window.add_dataset(data)
    window.show(); app.processEvents(); window.canvas.draw()
    expected = [170,190,np.nan,-170,-190,170,190]
    plotted = np.concatenate([line.get_ydata() for line in window.axes[0].lines])
    np.testing.assert_allclose(plotted, expected, equal_nan=True)
    menu = window.make_plot_menu('S21')
    actions = {a.text(): a for a in menu.actions()[0].menu().actions()}
    actions['幅度 (dB)'].trigger()
    assert window.mode.currentText() == '幅度 (dB)'
    np.testing.assert_allclose(window.axes[0].lines[0].get_ydata()[[0,1,3,4]], -20)
    window.set_y_limits('S21', (-50,0))
    np.testing.assert_allclose(window.axes[2].get_ylim(), [-50,0])
    assert not np.allclose(window.axes[0].get_ylim(), [-50,0])
    actions['相位 (°)'].trigger()
    np.testing.assert_allclose(window.axes[0].lines[0].get_ydata(), [170,-170,np.nan,-170,170], equal_nan=True)
    assert not np.allclose(window.axes[2].get_ylim(), [-50,0])
    actions['幅度 (dB)'].trigger()
    np.testing.assert_allclose(window.axes[2].get_ylim(), [-50,0])
    dialog = main.YAxisDialog(window, 'S21')
    for lo,hi in [('nan','0'), ('-inf','1'), ('10','10'), ('20','10'), ('abc','1')]:
        dialog.minimum.setText(lo); dialog.maximum.setText(hi); dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted and dialog.error.text()
        np.testing.assert_allclose(window.axes[2].get_ylim(), [-50,0])
    dialog.minimum.setText('-35.5'); dialog.maximum.setText('-5'); dialog.accept()
    np.testing.assert_allclose(window.axes[2].get_ylim(), [-35.5,-5])
    window.segment.setCurrentIndex(1)
    window.add_dataset(data)
    np.testing.assert_allclose(window.axes[2].get_ylim(), [-35.5,-5])
    for action in menu.actions():
        if action.text() == 'S21 Y 轴 AutoScale': action.trigger()
    assert window.axes[2].get_autoscaley_on()
    assert not np.allclose(window.axes[2].get_ylim(), [-35.5,-5])
    dialog = main.YAxisDialog(window)
    dialog.scale.setCurrentIndex(1); dialog.minimum.setText('-80'); dialog.maximum.setText('5'); dialog.accept()
    for ax in window.axes: np.testing.assert_allclose(ax.get_ylim(), [-80,5])
    for action in menu.actions():
        if action.text() == '全部 Y 轴 AutoScale': action.trigger()
    assert all(ax.get_autoscaley_on() for ax in window.axes)
    window.resize(1000,700); app.processEvents(); window.canvas.draw()
    assert window.centralWidget().width() <= 1000
    window.close()
print('Main display / Y-axis UI checks passed')
