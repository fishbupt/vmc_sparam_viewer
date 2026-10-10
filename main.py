"""Run directly: python main.py [file.s2p|file.s2px]."""
from __future__ import annotations
import sys
import traceback
from pathlib import Path
import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QSettings
from PyQt6.QtGui import QAction, QActionGroup, QCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QListWidget, QComboBox, QLabel, QSplitter, QTabWidget,
    QTextEdit, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
    QTableView, QProgressBar, QGroupBox, QLineEdit, QMenu)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from parser import PARAMS, load_file, parse_text, table_data, export_csv, values, runs

MODES = {'幅度 (dB)': 'dB', '线性幅度': 'Magnitude', '相位 (°)': 'Phase',
         '解缠绕相位 (°)': 'Unwrapped', '实部': 'Real', '虚部': 'Imag'}
COLORS = {'S11': '#2563eb', 'S12': '#d97706', 'S21': '#059669', 'S22': '#7c3aed'}
STYLE = '''
QMainWindow, QDialog { background: #f3f6fa; }
QWidget { font-family: "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"; font-size: 10pt; color: #24344a; }
QGroupBox { background: white; border: 1px solid #dce3ec; border-radius: 7px; margin-top: 12px; padding: 12px 8px 8px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; }
QListWidget,QTableView,QTextEdit,QPlainTextEdit { background: white; border: 1px solid #dce3ec; border-radius: 4px; selection-background-color: #dbeafe; selection-color: #143e78; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 5px; padding: 7px 12px; }
QPushButton:hover { background: #eaf2fd; }
QPushButton:disabled { color: #94a3b8; background: #eef2f6; }
QPushButton#primary { background: #2563eb; color: white; border-color: #2563eb; }
QComboBox,QLineEdit { background: white; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px; }
QComboBox QAbstractItemView { background: white; color: #24344a; selection-background-color: #dbeafe; }
QTabWidget::pane { background: white; border: 1px solid #dce3ec; }
QTabBar::tab { padding: 9px 16px; background: #e9eef5; }
QTabBar::tab:selected { background: white; color: #2563eb; }
QMenuBar, QMenu { background: white; color: #24344a; }
QMenu::item:selected { background: #dbeafe; }
QHeaderView::section { background: #edf2f8; padding: 6px; border: 0; border-right: 1px solid #dce3ec; }
'''

class Task(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:
            self.failed.emit(str(e), traceback.format_exc())

class DataModel(QAbstractTableModel):
    def __init__(self, dataset):
        super().__init__()
        self.headers, self.columns = table_data(dataset)
        self.n = dataset.count
    def rowCount(self, parent=None):
        return self.n
    def columnCount(self, parent=None):
        return len(self.headers)
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            return f'{self.columns[index.column()][index.row()]:.12g}'
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section] if orientation == Qt.Orientation.Horizontal else str(section + 1)

class PasteDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('粘贴 S2P / S2PX 文本')
        self.resize(860, 620)
        box = QVBoxLayout(self)
        box.addWidget(QLabel('粘贴完整头部与数据正文。按内容识别格式，不依赖文件扩展名。'))
        self.name = QLineEdit('粘贴数据')
        self.name.setPlaceholderText('数据名称')
        box.addWidget(self.name)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('# Hz S DB R 50\n...\n或 SegIndex,InputFreq,OutputFreq,...')
        box.addWidget(self.editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

class YAxisDialog(QDialog):
    """Choose automatic or finite, increasing limits in the current display units."""
    def __init__(self, parent, param=None):
        super().__init__(parent)
        self.setWindowTitle('Y 轴范围 · ' + parent.mode.currentText())
        form = QFormLayout(self)
        self.target = QComboBox()
        self.target.addItem('全部 S 参数', None)
        for p in PARAMS:
            self.target.addItem(p, p)
        self.target.setCurrentIndex(self.target.findData(param))
        form.addRow('应用到', self.target)
        self.scale = QComboBox()
        self.scale.addItems(['AutoScale（自动缩放）', '手动范围'])
        form.addRow('缩放方式', self.scale)
        self.minimum = QLineEdit()
        self.maximum = QLineEdit()
        form.addRow('最小值', self.minimum)
        form.addRow('最大值', self.maximum)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #b91c1c;')
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        self.owner = parent
        self.target.currentIndexChanged.connect(self.refresh)
        self.scale.currentIndexChanged.connect(self.toggle)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.refresh()

    def refresh(self):
        p = self.target.currentData() or PARAMS[0]
        limits = self.owner.y_limits.get((MODES[self.owner.mode.currentText()], p))
        shown = limits or self.owner.axes[PARAMS.index(p)].get_ylim()
        self.minimum.setText(f'{shown[0]:.12g}')
        self.maximum.setText(f'{shown[1]:.12g}')
        self.scale.setCurrentIndex(1 if limits else 0)
        self.toggle()

    def toggle(self):
        manual = self.scale.currentIndex() == 1
        self.minimum.setEnabled(manual)
        self.maximum.setEnabled(manual)
        self.error.clear()

    def accept(self):
        limits = None
        if self.scale.currentIndex() == 1:
            try:
                limits = (float(self.minimum.text()), float(self.maximum.text()))
                if not all(np.isfinite(limits)) or limits[0] >= limits[1]:
                    raise ValueError
            except ValueError:
                self.error.setText('请输入有限数值，并确保最小值小于最大值。')
                return
        self.owner.set_y_limits(self.target.currentData(), limits)
        super().accept()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        # Keep the existing settings namespace so recent paths/preferences survive the rename.
        self.settings = QSettings('VNAAlgorithmTools', 'MixerSParameterViewer')
        self.datasets = []
        self.dataset = None
        self.task = None
        self.pending = []
        self.y_limits = {}
        self.setWindowTitle('VMC Calibration Workbench · VMC 校准与验证工作台')
        self.resize(1420, 900)
        self.setMinimumSize(1000, 700)
        self.setAcceptDrops(True)
        self.build()
        geometry = self.settings.value('geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)

    def build(self):
        menu = self.menuBar().addMenu('文件')
        for title, shortcut, slot in [('打开文件…', 'Ctrl+O', self.open_files), ('粘贴文本…', 'Ctrl+Shift+V', self.paste), ('导出 CSV…', 'Ctrl+E', self.export)]:
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel('MIXER  /  S-PARAMETER VIEWER')
        title.setStyleSheet('font-size: 19pt; font-weight: bold; padding: 5px;')
        layout.addWidget(title)
        subtitle = QLabel('校准混频器表征文件  ·  S2P / S2PX  ·  复数数据与频率映射')
        subtitle.setStyleSheet('color: #64748b; padding: 0 5px 8px;')
        layout.addWidget(subtitle)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        left = QWidget()
        left.setMinimumWidth(250)
        left.setMaximumWidth(440)
        side = QVBoxLayout(left)
        side.setContentsMargins(0, 0, 10, 0)
        self.open_btn = QPushButton('打开 S2P / S2PX')
        self.open_btn.setObjectName('primary')
        self.open_btn.clicked.connect(self.open_files)
        self.paste_btn = QPushButton('粘贴文件内容')
        self.paste_btn.clicked.connect(self.paste)
        compare_btn = QPushButton('比较同名 S2P / S2PX')
        compare_btn.clicked.connect(self.compare_files)
        side.addWidget(self.open_btn)
        side.addWidget(self.paste_btn)
        side.addWidget(compare_btn)
        any_compare = QPushButton('比较任意两份表征文件')
        any_compare.clicked.connect(self.compare_any_files)
        side.addWidget(any_compare)
        characterize_btn = QPushButton('两轮 SOL → 校准混频器表征')
        characterize_btn.setObjectName('primary')
        characterize_btn.clicked.connect(self.characterize_mixer)
        side.addWidget(characterize_btn)
        simulation_btn = QPushButton('生成 SOL 仿真文件 / Mixer 真值')
        simulation_btn.clicked.connect(self.simulate_sol)
        side.addWidget(simulation_btn)
        vmc_btn = QPushButton('VMC 校准误差项 / 校准 MUT')
        vmc_btn.clicked.connect(self.calibrate_vmc)
        side.addWidget(vmc_btn)
        self.files = QListWidget()
        self.files.currentRowChanged.connect(self.select)
        side.addWidget(self.files, 1)
        remove = QPushButton('移除选中文件')
        remove.clicked.connect(self.remove)
        side.addWidget(remove)
        group = QGroupBox('绘图设置')
        form = QFormLayout(group)
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        saved_mode = self.settings.value('mode', '幅度 (dB)')
        self.mode.setCurrentText('解缠绕相位 (°)' if saved_mode == '展开相位 (°)' else saved_mode)
        self.axis = QComboBox()
        self.unit = QComboBox()
        self.unit.addItems(['GHz', 'MHz', 'kHz', 'Hz'])
        self.segment = QComboBox()
        self.segment.addItem('全部')
        for label, box in [('显示', self.mode), ('横轴', self.axis), ('频率单位', self.unit), ('分段', self.segment)]:
            form.addRow(label, box)
            box.currentIndexChanged.connect(self.plot)
        y_axis_btn = QPushButton('Y 轴设置…')
        y_axis_btn.clicked.connect(lambda: self.edit_y_limits())
        form.addRow(y_axis_btn)
        side.addWidget(group)
        self.export_btn = QPushButton('导出完整数据 CSV')
        self.export_btn.clicked.connect(self.export)
        self.export_btn.setEnabled(False)
        side.addWidget(self.export_btn)
        note = QLabel('保留原始点序；不插值、不补点。\n解缠绕相位按连续分段分别计算。\n右键曲线切换显示 / 设置 Y 轴。')
        note.setWordWrap(True)
        note.setStyleSheet('color: #64748b; padding: 8px 0;')
        side.addWidget(note)
        splitter.addWidget(left)
        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel('打开文件或粘贴数据开始查看')
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet('background: white; border: 1px solid #dce3ec; padding: 12px; font-weight: bold;')
        content.addWidget(self.summary)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet('background: #fff7e6; color: #92400e; padding: 8px;')
        self.warning.hide()
        content.addWidget(self.warning)
        self.tabs = QTabWidget()
        content.addWidget(self.tabs, 1)
        page = QWidget()
        chart = QVBoxLayout(page)
        self.figure = Figure(figsize=(9, 6), layout='constrained', facecolor='white')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.subplots(2, 2).ravel()
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        chart.addWidget(self.toolbar)
        chart.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('motion_notify_event', self.hover)
        self.canvas.mpl_connect('button_press_event', self.plot_context_menu)
        self.tabs.addTab(page, 'S 参数 · 2 × 2')
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.tabs.addTab(self.table, '数据表')
        self.meta = QPlainTextEdit()
        self.meta.setReadOnly(True)
        self.tabs.addTab(self.meta, '文件信息 / Mixer 配置')
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.tabs.addTab(self.raw, '原始文本')
        splitter.addWidget(main)
        splitter.setSizes([280, 1100])
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        self.log.setPlaceholderText('读取记录与详细错误')
        layout.addWidget(self.log)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage('就绪 · 支持拖入文件')
        self.plot()

    def compare_files(self):
        if self.busy():
            return
        from compare_gui import CompareDialog
        dialog = CompareDialog(self.datasets, self)
        dialog.exec()

    def compare_any_files(self):
        if self.busy():
            return
        from compare_gui import CompareDialog
        CompareDialog(self.datasets, self, general=True).exec()

    def calibrate_vmc(self):
        from vmc_calibration_gui import VMCCalibrationDialog
        dialog = VMCCalibrationDialog(self)
        dialog.generated.connect(self.add_dataset)
        dialog.exec()

    def simulate_sol(self):
        if self.busy():
            return
        from simulate_gui import SimulationDialog
        dialog = SimulationDialog(self)
        dialog.generated.connect(self.add_dataset)
        dialog.exec()

    def characterize_mixer(self):
        if self.busy():
            return
        from characterize_gui import CharacterizeDialog
        dialog = CharacterizeDialog(self)
        dialog.generated.connect(self.add_dataset)
        dialog.exec()

    def busy(self):
        return self.task is not None

    def start_task(self, fn, args, callback):
        if self.busy():
            return False
        self.progress.show()
        self.open_btn.setEnabled(False)
        self.paste_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.task = Task(fn, *args)
        self.task.done.connect(callback)
        self.task.failed.connect(self.error)
        self.task.finished.connect(self.finished)
        self.task.start()
        return True

    def finished(self):
        self.task.deleteLater()
        self.task = None
        self.progress.hide()
        self.open_btn.setEnabled(True)
        self.paste_btn.setEnabled(True)
        self.export_btn.setEnabled(self.dataset is not None)
        if self.pending:
            self.read_next()

    def error(self, message, trace):
        self.log.appendPlainText(trace)
        QMessageBox.warning(self, '操作未完成', message)

    def open_files(self):
        if self.busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, '打开混频器表征文件', self.settings.value('directory', ''),
                    'Mixer 文件 (*.s2p *.S2P *.s2px *.S2PX *.csv);;所有文件 (*)')
        self.load_paths(paths)

    def load_paths(self, paths):
        if not paths:
            return
        self.pending.extend(paths)
        if not self.busy():
            self.read_next()

    def read_next(self):
        path = self.pending.pop(0)
        self.settings.setValue('directory', str(Path(path).parent))
        self.statusBar().showMessage(f'正在读取 {Path(path).name}')
        self.start_task(load_file, (path,), self.add_dataset)

    def paste(self):
        if self.busy():
            return
        dialog = PasteDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.start_task(parse_text, (dialog.editor.toPlainText(), dialog.name.text() or '粘贴数据'), self.add_dataset)

    def add_dataset(self, data):
        self.datasets.append(data)
        self.files.addItem(Path(data.name).name)
        self.files.item(self.files.count() - 1).setToolTip(data.name)
        self.files.setCurrentRow(len(self.datasets) - 1)
        self.log.appendPlainText(f'已读取 {data.name} | {data.kind} | {data.count} 点')
        for warning in data.warnings:
            self.log.appendPlainText('提示：' + warning)
        self.statusBar().showMessage('读取完成')

    def select(self, index):
        self.dataset = self.datasets[index] if 0 <= index < len(self.datasets) else None
        self.axis.blockSignals(True)
        self.segment.blockSignals(True)
        self.axis.clear()
        self.segment.clear()
        self.segment.addItem('全部', None)
        d = self.dataset
        if d:
            for key in d.axes:
                self.axis.addItem(key, key)
            self.axis.addItem('点序号', 'Index')
            for seg in dict.fromkeys(d.segment.tolist()):
                self.segment.addItem(str(seg), seg)
            primary = next(iter(d.axes.values()))
            self.summary.setText(f'{Path(d.name).name}  |  {d.kind}  |  {d.count} 点\n'
                                 f'{next(iter(d.axes))}: {primary.min()/1e9:.9g} – {primary.max()/1e9:.9g} GHz'
                                 f'  |  Z₀: {d.metadata.get("参考阻抗", "未声明")}')
            self.warning.setText('\n'.join(d.warnings))
            self.warning.setVisible(bool(d.warnings))
            self.table.setModel(DataModel(d))
            self.table.horizontalHeader().setDefaultSectionSize(145)
            self.meta.setPlainText('\n'.join(f'{k}: {v}' for k, v in d.metadata.items()))
            limit = 2_000_000
            self.raw.setPlainText(d.raw_text[:limit] + ('\n[预览已截断；解析与导出使用完整数据]' if len(d.raw_text) > limit else ''))
        else:
            self.summary.setText('打开文件或粘贴数据开始查看')
            self.warning.hide()
            self.table.setModel(None)
            self.meta.clear()
            self.raw.clear()
        self.axis.blockSignals(False)
        self.segment.blockSignals(False)
        self.export_btn.setEnabled(d is not None and not self.busy())
        self.plot()

    def remove(self):
        if self.busy():
            return
        row = self.files.currentRow()
        if row >= 0:
            self.files.blockSignals(True)
            self.datasets.pop(row)
            self.files.takeItem(row)
            self.files.blockSignals(False)
            self.files.setCurrentRow(min(row, len(self.datasets) - 1))
            self.select(self.files.currentRow())

    def set_y_limits(self, param, limits):
        mode = MODES[self.mode.currentText()]
        if limits is not None:
            if not all(np.isfinite(limits)) or limits[0] >= limits[1]:
                raise ValueError('Y 轴最小值必须小于最大值，且均为有限数值。')
        for p in PARAMS if param is None else [param]:
            if limits is None:
                self.y_limits.pop((mode, p), None)
            else:
                self.y_limits[(mode, p)] = tuple(limits)
        self.plot()

    def edit_y_limits(self, param=None):
        YAxisDialog(self, param).exec()

    def make_plot_menu(self, param):
        menu = QMenu(self)
        display = menu.addMenu('显示（全部 S 参数）')
        group = QActionGroup(display)
        group.setExclusive(True)
        for label in MODES:
            action = display.addAction(label)
            action.setCheckable(True)
            action.setChecked(label == self.mode.currentText())
            group.addAction(action)
            action.triggered.connect(lambda checked=False, text=label: self.mode.setCurrentText(text))
        menu.addSeparator()
        auto = menu.addAction(f'{param} Y 轴 AutoScale')
        auto.triggered.connect(lambda: self.set_y_limits(param, None))
        manual = menu.addAction(f'{param} Y 轴手动范围…')
        manual.triggered.connect(lambda: self.edit_y_limits(param))
        menu.addAction('全部 Y 轴 AutoScale', lambda: self.set_y_limits(None, None))
        return menu

    def plot_context_menu(self, event):
        if event.button != 3 or event.inaxes not in self.axes:
            return
        p = PARAMS[list(self.axes).index(event.inaxes)]
        menu = self.make_plot_menu(p)
        menu.exec(QCursor.pos())
        menu.deleteLater()

    def plotting_arrays(self, param):
        d = self.dataset
        key = self.axis.currentData()
        scale = {'GHz': 1e9, 'MHz': 1e6, 'kHz': 1e3, 'Hz': 1}[self.unit.currentText()]
        x = np.arange(1, d.count + 1) if key == 'Index' else d.axes[key] / scale
        y = values(d.s[param], MODES[self.mode.currentText()], d.segment)
        chosen = self.segment.currentData()
        mask = np.ones(d.count, dtype=bool) if chosen is None else d.segment == chosen
        return x, y, mask

    def plot(self):
        for ax, p in zip(self.axes, PARAMS):
            ax.clear()
            ax.set_title(p, loc='left', color=COLORS[p], fontsize=13, fontweight='bold')
            ax.grid(True, color='#e7ecf3', linewidth=.7)
            ax.tick_params(labelsize=9, colors='#52647b')
            for spine in ax.spines.values():
                spine.set_color('#dbe3ed')
            if self.dataset and self.axis.currentData():
                x, y, mask = self.plotting_arrays(p)
                for run in runs(self.dataset.segment):
                    indices = run[mask[run]]
                    if len(indices):
                        yp = y[indices].copy()
                        yp[~np.isfinite(yp)] = np.nan
                        ax.plot(x[indices], yp, color=COLORS[p], linewidth=1.6,
                                marker='o' if len(indices) <= 100 else None, markersize=4)
                key = self.axis.currentData()
                ax.set_xlabel('Point index' if key == 'Index' else f'{key} ({self.unit.currentText()})', fontsize=9)
                mode = MODES[self.mode.currentText()]
                ax.set_ylabel({'dB': 'Magnitude (dB)', 'Magnitude': 'Magnitude (linear)', 'Phase': 'Phase (deg)',
                               'Unwrapped': 'Unwrapped phase (deg)', 'Real': 'Real', 'Imag': 'Imaginary'}[mode], fontsize=9)
                ax.margins(x=.05)
            else:
                ax.text(.5, .5, 'Open or paste S2P / S2PX', ha='center', va='center', transform=ax.transAxes, color='#94a3b8')
            limits = self.y_limits.get((MODES[self.mode.currentText()], p))
            if limits is not None:
                ax.set_ylim(*limits)
        self.toolbar.update()
        self.canvas.draw_idle()

    def hover(self, event):
        if not self.dataset or event.inaxes not in self.axes or event.xdata is None:
            return
        p = PARAMS[list(self.axes).index(event.inaxes)]
        x, y, mask = self.plotting_arrays(p)
        idx = np.flatnonzero(mask)
        if len(idx):
            k = idx[np.argmin(np.abs(x[idx] - event.xdata))]
            self.statusBar().showMessage(f'{p} | 点 {k+1} | {self.axis.currentText()}={x[k]:.12g} '
                                         f'| 值={y[k]:.12g} | 段={self.dataset.segment[k]}')

    def export(self):
        if self.dataset is None or self.busy():
            return
        default = str(Path(self.settings.value('directory', '') or '.') / (Path(self.dataset.name).stem + '_export.csv'))
        path, _ = QFileDialog.getSaveFileName(self, '导出完整数据（不受分段筛选影响）', default, 'CSV (*.csv)')
        if path:
            if not path.lower().endswith('.csv'):
                path += '.csv'
            self.start_task(export_csv, (self.dataset, path), lambda _: self.log.appendPlainText(f'已导出：{path}'))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.load_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy():
            self.statusBar().showMessage('正在处理数据，请完成后再关闭。')
            event.ignore()
            return
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('mode', self.mode.currentText())
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1:
        window.load_paths(sys.argv[1:])
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
