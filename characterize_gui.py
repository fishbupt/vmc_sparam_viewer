"""Explicit six-state input mapping for mixer characterization."""
from pathlib import Path
import traceback
from PyQt6.QtCore import QThread, pyqtSignal, QSettings
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
 QLineEdit, QPushButton, QComboBox, QDoubleSpinBox, QFileDialog, QMessageBox,
 QPlainTextEdit, QProgressBar, QGroupBox)
from frequency_mapping import CONVERSION_MODES
from characterization import LABELS, Options, characterize, export_s2p, export_bundle, SAMPLING_METHODS

class Worker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    def __init__(self, fn, args, parent=None):
        super().__init__(parent); self.fn, self.args = fn, args
    def run(self):
        try: self.done.emit(self.fn(*self.args))
        except Exception as e: self.failed.emit(str(e), traceback.format_exc())

class CharacterizeDialog(QDialog):
    generated = pyqtSignal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('校准混频器表征 · 两轮 SOL')
        self.resize(1180, 800)
        self.settings = QSettings('VNAAlgorithmTools', 'MixerCharacterization')
        self.worker = None; self.result = None
        layout = QVBoxLayout(self)
        intro = QLabel('两轮采集均读取 S2P 的 S11（RF 横轴）。第一轮标准定义取 RF；第二轮取 IF=RF−LO（下变频）或 RF+LO（上变频）。\n'
                       '先解 SOL，再消除输入误差；传输采用互易假设，输出高精度 RI S2P。')
        intro.setWordWrap(True); layout.addWidget(intro)
        group = QGroupBox('两轮 SOL 的六个测量文件（S2P）')
        grid = QGridLayout(group)
        grid.addWidget(QLabel('校准连接状态'), 0, 0)
        grid.addWidget(QLabel('仿真测量 S2P'), 0, 1)
        self.measurements = []; self.standards = []; self.input_controls = []
        for i, label in enumerate(LABELS):
            grid.addWidget(QLabel(label), i+1, 0)
            field = QLineEdit(str(self.settings.value(f's2p/{i}', '')))
            field.setPlaceholderText('选择 S2P 文件')
            field.textChanged.connect(self.invalidate)
            button = QPushButton('浏览…')
            button.clicked.connect(lambda checked=False, e=field: self.browse(e, 's2p'))
            grid.addWidget(field, i+1, 1); grid.addWidget(button, i+1, 2)
            self.measurements.append(field); self.input_controls.extend((field, button))
        grid.setColumnStretch(1, 1)
        layout.addWidget(group)
        kit = QGroupBox('共用标准件定义（S1P）：两轮使用同一套 OPEN / SHORT / LOAD')
        kit_grid = QGridLayout(kit)
        for i, kind in enumerate(('OPEN', 'SHORT', 'LOAD')):
            kit_grid.addWidget(QLabel(kind), i, 0)
            # Migrate the first-round v1.2 entries to one shared kit.
            field = QLineEdit(str(self.settings.value(f'kit/{kind.lower()}', self.settings.value(f's1p/{i}', ''))))
            field.setPlaceholderText('同一文件需覆盖第一轮 RF 和第二轮 IF 频段')
            field.textChanged.connect(self.invalidate)
            button = QPushButton('浏览…')
            button.clicked.connect(lambda checked=False, e=field: self.browse(e, 's1p'))
            kit_grid.addWidget(field, i, 1); kit_grid.addWidget(button, i, 2)
            self.standards.append(field); self.input_controls.extend((field, button))
        kit_grid.setColumnStretch(1, 1); layout.addWidget(kit)
        shortcuts = QHBoxLayout(); layout.addLayout(shortcuts)
        demo = QPushButton('载入理想 SOL 演示（非真实标准件）')
        demo.clicked.connect(self.demo)
        shortcuts.addWidget(demo); shortcuts.addStretch()
        self.input_controls.append(demo)
        options = QHBoxLayout(); layout.addLayout(options)
        options.addWidget(QLabel('固定 LO (GHz)'))
        self.lo = QDoubleSpinBox(); self.lo.setDecimals(9); self.lo.setRange(.000000001, 1000)
        self.lo.setValue(float(self.settings.value('lo_ghz', 5)))
        options.addWidget(self.lo)
        self.sampling = QComboBox()
        for method, label in SAMPLING_METHODS.items():
            self.sampling.addItem(label, method)
        saved_sampling = self.settings.value('standard_sampling', 'cubic_ri')
        if saved_sampling not in SAMPLING_METHODS: saved_sampling = 'cubic_ri'
        self.sampling.setCurrentIndex(max(0, self.sampling.findData(saved_sampling)))
        self.sampling.setToolTip('线性和三次样条均对线性幅度与解缠绕相位分别插值；样条采用 not-a-knot 边界。精确节点优先，禁止外推；样条负幅度报错。')
        options.addWidget(self.sampling)
        options.addWidget(QLabel('频率容差 (Hz)'))
        self.tol = QDoubleSpinBox(); self.tol.setDecimals(6); self.tol.setRange(0, 1e6); self.tol.setValue(.001)
        options.addWidget(self.tol)
        mapping = QHBoxLayout(); layout.addLayout(mapping)
        mapping.addWidget(QLabel('IF 相对 RF 的变频方向'))
        self.conversion = QComboBox()
        for mode, label in CONVERSION_MODES.items(): self.conversion.addItem(label, mode)
        self.conversion.setCurrentIndex(max(0, self.conversion.findData(self.settings.value('frequency_conversion', 'down'))))
        mapping.addWidget(self.conversion); mapping.addStretch()
        options2 = QHBoxLayout(); layout.addLayout(options2)
        self.second = QComboBox()
        self.second.addItem('第二轮：原始 S11（包含输入误差盒）', 'raw')
        self.second.addItem('第二轮：已经第一轮校准修正的 S11', 'corrected')
        options2.addWidget(self.second)
        options2.addWidget(QLabel('传输整体开方分支'))
        self.sign = QComboBox(); self.sign.addItem('+（首点乘积主值开方，后续连续）', 1)
        self.sign.addItem('−（全频段 S21/S12 同时反号）', -1)
        options2.addWidget(self.sign)
        for c in (self.lo, self.tol): c.valueChanged.connect(self.invalidate)
        for c in (self.sampling, self.second, self.sign, self.conversion): c.currentIndexChanged.connect(self.invalidate)
        self.input_controls.extend((self.lo, self.tol, self.sampling, self.second, self.sign, self.conversion))
        actions = QHBoxLayout(); layout.addLayout(actions)
        self.run_btn = QPushButton('计算并载入主界面'); self.run_btn.setObjectName('primary')
        self.run_btn.clicked.connect(self.compute); actions.addWidget(self.run_btn)
        self.save_btn = QPushButton('保存表征 S2P…'); self.save_btn.clicked.connect(self.save_s2p)
        self.bundle_btn = QPushButton('导出 S2P / S2PX / SOL 诊断包…'); self.bundle_btn.clicked.connect(self.save_bundle)
        actions.addWidget(self.save_btn); actions.addWidget(self.bundle_btn)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.hide()
        actions.addWidget(self.progress)
        self.summary = QLabel('请指定六个测量 S2P 和三个共用标准 S1P；标准定义必须覆盖 RF/IF。')
        self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); layout.addWidget(self.log, 1)
        note = QLabel('SOL 回代与两路径一致性属于数值自检，不能替代独立 Keysight 对照。\n'
                      '生成后在主界面打开 Keysight 的 S2P/S2PX，使用“比较任意两份表征文件”；差值为 A−B。')
        note.setWordWrap(True); layout.addWidget(note)
        close = QPushButton('关闭'); close.clicked.connect(self.reject); layout.addWidget(close)
        self.invalidate()

    def invalidate(self, *args):
        self.result = None
        if hasattr(self, 'save_btn'):
            self.save_btn.setEnabled(False); self.bundle_btn.setEnabled(False)
            self.summary.setText('输入或设置已改变，请重新计算；此前主界面结果作为独立快照保留。')

    def browse(self, field, suffix):
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', self.settings.value('directory', ''),
                     f'Touchstone (*.{suffix} *.{suffix.upper()});;所有文件 (*)')
        if path:
            self.settings.setValue('directory', str(Path(path).parent)); field.setText(path)

    def demo(self):
        directory = Path(__file__).parent/'examples'/'characterization_demo'
        for i, field in enumerate(self.measurements):
            round_no, kind = (1 if i < 3 else 2), ('Open', 'Short', 'Load')[i % 3]
            prefix = 'Input' if i < 3 else 'Mixer'
            field.setText(str(directory/f'{round_no:02d}_{prefix}_SOL_{kind}.s2p'))
        for field, kind in zip(self.standards, ('Open', 'Short', 'Load')):
            field.setText(str(directory/f'Standard_{kind}.s1p'))
        self.conversion.setCurrentIndex(self.conversion.findData('down'))
        self.lo.setValue(5); self.second.setCurrentIndex(0); self.sign.setCurrentIndex(0)
        self.summary.setText('已载入理想 SOL 演示。实际标准带寄生/偏置时，请替换三个标准 S1P。')

    def begin(self, fn, args, callback):
        if self.worker: return
        for c in (*self.input_controls, self.run_btn, self.save_btn, self.bundle_btn): c.setEnabled(False)
        self.progress.show()
        self.worker = Worker(fn, args, self)
        self.worker.done.connect(callback); self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finish); self.worker.start()

    def finish(self):
        self.worker.deleteLater(); self.worker = None; self.progress.hide()
        for c in (*self.input_controls, self.run_btn): c.setEnabled(True)
        self.save_btn.setEnabled(self.result is not None); self.bundle_btn.setEnabled(self.result is not None)

    def failed(self, message, trace):
        self.log.appendPlainText(trace); self.summary.setText('操作未完成：'+message)
        QMessageBox.warning(self, '表征未完成', message)

    def compute(self):
        measurements = [e.text().strip() for e in self.measurements]
        standards = [e.text().strip() for e in self.standards]
        if not all(measurements+standards):
            QMessageBox.warning(self, '缺少输入', '请指定六个测量 S2P，以及 OPEN、SHORT、LOAD 三个共用标准 S1P。'); return
        self.invalidate()
        opts = Options(lo_hz=self.lo.value()*1e9, standard_sampling=self.sampling.currentData(),
                       frequency_tolerance_hz=self.tol.value(), second_round=self.second.currentData(),
                       root_sign=self.sign.currentData(), frequency_conversion=self.conversion.currentData())
        for i, p in enumerate(measurements): self.settings.setValue(f's2p/{i}', p)
        for kind, p in zip(('open', 'short', 'load'), standards): self.settings.setValue(f'kit/{kind}', p)
        self.settings.setValue('standard_sampling', self.sampling.currentData())
        self.settings.setValue('lo_ghz', self.lo.value())
        self.settings.setValue('frequency_conversion', self.conversion.currentData())
        self.summary.setText('正在读取文件并执行两轮 SOL…')
        self.begin(characterize, (measurements, standards, opts), self.accept_result)

    def accept_result(self, result):
        self.result = result
        m = result.manifest
        self.summary.setText(f'已生成 {result.dataset.count} 点表征。两路径最大复数差 '
                             f'{m["max_diagnostics"]["Two_path_complex_difference"]:.6g}；'
                             f'SOL 最大条件数 {max(m["max_diagnostics"]["SOL1_condition"], m["max_diagnostics"]["SOL2_condition"]):.6g}。')
        self.log.appendPlainText(self.summary.text())
        self.log.appendPlainText(CONVERSION_MODES[m['frequency_conversion']])
        self.log.appendPlainText('标准求值：'+SAMPLING_METHODS[m['standard_sampling']]+'；两轮共用 OPEN/SHORT/LOAD。')
        for role, count in m['interpolated_points_per_standard'].items():
            self.log.appendPlainText(f'{role}: 插值 {count} 点')
        self.log.appendPlainText('\n'.join(result.dataset.warnings))
        self.generated.emit(result.dataset)

    def save_s2p(self):
        if self.result is None: return
        path, _ = QFileDialog.getSaveFileName(self, '保存自研表征（RF 横轴）', 'characterized_mixer.s2p', 'S2P (*.s2p)')
        if path:
            if not path.lower().endswith('.s2p'): path += '.s2p'
            self.begin(export_s2p, (self.result, path), lambda _: self.log.appendPlainText('已保存 '+path))

    def save_bundle(self):
        if self.result is None: return
        path, _ = QFileDialog.getSaveFileName(self, '保存表征与两轮系数诊断', 'characterized_mixer_validation.zip', 'ZIP (*.zip)')
        if path:
            if not path.lower().endswith('.zip'): path += '.zip'
            self.begin(export_bundle, (self.result, path), lambda _: self.log.appendPlainText('已保存 '+path))

    def reject(self):
        if not self.worker: super().reject()
    def closeEvent(self, event):
        if self.worker: event.ignore()
        else: super().closeEvent(event)
