"""Run directly: python main.py [file.s2p|file.s2px]."""
from __future__ import annotations
import sys
import traceback
from pathlib import Path
import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QSettings, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QComboBox, QLabel, QPlainTextEdit, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QProgressBar, QLineEdit, QMenu, QListWidgetItem)
from parser import PARAMS, load_file, parse_text, table_data, export_csv, values, runs

MODES = {'幅度 (dB)': 'dB', '线性幅度': 'Magnitude', '相位 (°)': 'Phase',
         '解缠绕相位 (°)': 'Unwrapped', '实部': 'Real', '虚部': 'Imag'}
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
QListWidget#workflowNavigation, QWidget#viewerSidebar { background: white; border: 1px solid #dce3ec; }
QListWidget#workflowNavigation::item { padding: 12px 8px; }
QListWidget#workflowNavigation::item:selected { background: #e7effd; color: #2563eb; }
QListWidget#workflowNavigation::item:disabled { color: #64748b; padding-top: 15px; font-size: 9pt; }
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
        self.file_serial = 0
        self.view_options = {}
        self.setWindowTitle('VNA Calibration Workbench · VNA 校准与验证工作台')
        self.resize(1420, 900)
        self.setMinimumSize(1000, 700)
        self.setAcceptDrops(True)
        self.build()
        geometry = self.settings.value('geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)

    def build(self):
        menu = self.menuBar().addMenu('文件')
        for title, shortcut, slot in [('打开文件…', 'Ctrl+O', self.open_files),
                                     ('粘贴文本…', 'Ctrl+Shift+V', self.paste),
                                     ('导出当前文件 CSV…', 'Ctrl+E', self.export)]:
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
        view_menu = self.menuBar().addMenu('视图')
        view_menu.addAction('查看与比较', lambda: self.workspace.show_page(0))
        tools = self.menuBar().addMenu('工具')
        tools.addAction('两轮 SOL 表征…', self.characterize_mixer)
        tools.addAction('生成两轮 SOL 仿真…', self.simulate_sol)
        tools.addAction('生成 VMC 原始测量 SNP', self.simulate_vmc)
        from workbench_gui import WorkbenchPages, CALIBRATION_TYPES
        saved_type = str(self.settings.value('calibration_type', 'vmc'))
        self.calibration_type = saved_type if saved_type in CALIBRATION_TYPES else 'vmc'
        self.type_menu = self.menuBar().addMenu('校准类型')
        type_group = QActionGroup(self.type_menu)
        type_group.setExclusive(True)
        self.type_actions = {}
        groups = {}
        for key, (label, category) in CALIBRATION_TYPES.items():
            if category not in groups:
                groups[category] = self.type_menu.addMenu(category)
            action = groups[category].addAction(label + ('（待实现）' if key != 'vmc' else ''))
            action.setCheckable(True)
            action.setChecked(key == self.calibration_type)
            type_group.addAction(action)
            action.triggered.connect(lambda checked=False, name=key: self.choose_calibration_type(name))
            self.type_actions[key] = action
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel('VNA Calibration Workbench · VNA 校准与验证工作台')
        title.setStyleSheet('font-size: 18pt; font-weight: bold; padding: 5px;')
        layout.addWidget(title)
        context_row = QHBoxLayout()
        context = QLabel('S 参数查看与比较 · 无需创建项目')
        context.setStyleSheet('color: #64748b; padding: 0 5px 8px;')
        context_row.addWidget(context)
        context_row.addStretch()
        context_row.addWidget(QLabel('校准类型'))
        self.type_selector = QComboBox()
        self.type_selector.setMinimumContentsLength(22)
        for key, (label, _) in CALIBRATION_TYPES.items():
            self.type_selector.addItem(label + ('（待实现）' if key != 'vmc' else ''), key)
        self.type_selector.setCurrentIndex(self.type_selector.findData(self.calibration_type))
        self.type_selector.currentIndexChanged.connect(self.select_calibration_type)
        context_row.addWidget(self.type_selector)
        layout.addLayout(context_row)
        from viewer_gui import build_viewer
        self.workspace = WorkbenchPages(self, build_viewer(self, MODES))
        self.workspace.calibration_type_changed()
        layout.addWidget(self.workspace, 1)
        self.log_toggle = QPushButton('日志与数据诊断 ▸')
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self.toggle_log)
        layout.addWidget(self.log_toggle)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setPlaceholderText('读取记录与详细错误')
        self.log.hide()
        layout.addWidget(self.log)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage('就绪 · 支持拖入文件 · 启动默认显示单文件查看')
        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self.refresh_activity)
        self.activity_timer.start(150)
        self.plot()

    def refresh_activity(self):
        active = self.busy()
        self.progress.setVisible(active)
        self.open_btn.setEnabled(not active)
        self.paste_btn.setEnabled(not active)
        self.export_btn.setEnabled(self.dataset is not None and not active)
        self.workspace.refresh_actions()
        self.comparison_view.update_enabled()
        self.type_selector.setEnabled(not active)
        self.type_menu.setEnabled(not active)
        if self.pending and not active:
            self.read_next()

    def choose_calibration_type(self, key):
        """Menu and explicit VMC tools use the same visible selection."""
        index = self.type_selector.findData(key)
        if index < 0:
            return False
        if self.busy() and key != self.calibration_type:
            self.type_actions[self.calibration_type].setChecked(True)
            self.statusBar().showMessage('后台任务运行中，请完成后再切换校准类型。')
            return False
        self.type_selector.setCurrentIndex(index)
        return self.calibration_type == key

    def select_calibration_type(self, index):
        key = self.type_selector.itemData(index)
        if key is None:
            return
        if self.busy():
            self.type_selector.blockSignals(True)
            self.type_selector.setCurrentIndex(self.type_selector.findData(self.calibration_type))
            self.type_selector.blockSignals(False)
            self.type_actions[self.calibration_type].setChecked(True)
            return
        self.calibration_type = key
        self.type_actions[key].setChecked(True)
        self.settings.setValue('calibration_type', key)
        self.workspace.calibration_type_changed()

    def toggle_log(self, visible):
        self.log.setVisible(visible)
        self.log_toggle.setText('日志与数据诊断 ▾' if visible else '日志与数据诊断 ▸')

    def merge_page_log(self, page):
        previous = ['']
        def changed():
            current = page.log.toPlainText()
            extra = current[len(previous[0]):] if current.startswith(previous[0]) else current
            previous[0] = current
            if extra.strip():
                self.log.appendPlainText(f'[{page.windowTitle()}] ' + extra.strip())
        page.log.textChanged.connect(changed)

    def change_y_scale(self, index):
        if index == 0:
            self.set_y_limits(None, None)
        else:
            self.edit_y_limits()
        self.update_y_scale()

    def update_y_scale(self):
        mode = MODES[self.mode.currentText()]
        manual = any((mode, p) in self.y_limits for p in PARAMS)
        self.y_scale.setCurrentIndex(1 if manual else 0)

    def compare_files(self):
        if self.busy():
            return
        from compare_gui import CompareDialog
        dialog = CompareDialog(self.datasets, self)
        dialog.exec()

    def compare_any_files(self):
        if self.busy():
            return
        self.workspace.show_page(0)
        self.analysis_tabs.setCurrentIndex(1)
        if self.dataset is not None:
            self.comparison_view.select_left(self.dataset)

    def calibrate_vmc(self):
        if not self.choose_calibration_type('vmc'):
            return
        self.workspace.show_page(4)

    def simulate_vmc(self):
        self.workspace.show_simulation()

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
        return self.task is not None or (hasattr(self, "workspace") and self.workspace.busy())

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
        self.log_toggle.setChecked(True)
        QMessageBox.warning(self, '操作未完成', message)

    def open_files(self):
        if self.busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, '打开 S 参数 / 混频器表征文件', self.settings.value('directory', ''),
                    'Mixer 文件 (*.s2p *.S2P *.s2px *.S2PX *.csv);;所有文件 (*)')
        self.load_paths(paths)

    def load_paths(self, paths):
        if not paths:
            return
        self.pending.extend(paths)
        if not self.busy():
            self.read_next()

    def read_next(self):
        if not self.pending or self.busy():
            return
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
        self.comparison_view.set_datasets(self.datasets)
        item = QListWidgetItem(Path(data.name).name)
        item.setToolTip(data.name)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.ItemDataRole.UserRole, self.file_serial)
        self.file_serial += 1
        self.files.addItem(item)
        self.files.setCurrentRow(len(self.datasets) - 1)
        self.workspace.show_page(0)
        self.analysis_tabs.setCurrentIndex(0)
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
            serial = self.files.currentItem().data(Qt.ItemDataRole.UserRole)
            key, chosen = self.view_options.get(serial, (next(iter(d.axes)), None))
            self.axis.setCurrentIndex(max(0, self.axis.findData(key)))
            self.segment.setCurrentIndex(max(0, self.segment.findData(chosen)))
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
            self.comparison_view.set_datasets(self.datasets)
            item = self.files.takeItem(row)
            self.view_options.pop(item.data(Qt.ItemDataRole.UserRole), None)
            self.files.blockSignals(False)
            self.files.setCurrentRow(min(row, len(self.datasets) - 1))
            self.select(self.files.currentRow())

    def clear_files(self):
        if self.busy():
            return
        self.files.blockSignals(True)
        self.files.clear()
        self.datasets.clear()
        self.comparison_view.set_datasets(self.datasets)
        self.view_options.clear()
        self.files.blockSignals(False)
        self.select(-1)

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

    def plotting_arrays(self, param, dataset=None, option=None):
        d = self.dataset if dataset is None else dataset
        key, chosen = option or (self.axis.currentData(), self.segment.currentData())
        scale = {'GHz': 1e9, 'MHz': 1e6, 'kHz': 1e3, 'Hz': 1}[self.unit.currentText()]
        x = np.arange(1, d.count + 1) if key == 'Index' else d.axes[key] / scale
        y = values(d.s[param], MODES[self.mode.currentText()], d.segment)
        mask = np.ones(d.count, dtype=bool) if chosen is None else d.segment == chosen
        return x, y, mask

    def plot_entries(self):
        current = self.files.currentItem()
        if current is not None and self.dataset is not None:
            self.view_options[current.data(Qt.ItemDataRole.UserRole)] = (
                self.axis.currentData(), self.segment.currentData())
        entries = []
        if current is not None and self.dataset is not None:
            serial = current.data(Qt.ItemDataRole.UserRole)
            option = self.view_options[serial]
            entries.append((self.files.currentRow(), self.dataset, serial, option))
        return entries

    def plot(self):
        entries = self.plot_entries()
        for ax, p in zip(self.axes, PARAMS):
            ax.clear()
            title = p
            if p == 'S21' and any('VC21' in data.auxiliary or 'VC21' in data.metadata.get('S21', '')
                                  for _, data, _, _ in entries):
                title = 'S21 / VC21'
            ax.set_title(title, loc='left', color='#24344a', fontsize=13, fontweight='bold')
            ax.grid(True, color='#e7ecf3', linewidth=.7)
            ax.tick_params(labelsize=9, colors='#52647b')
            for spine in ax.spines.values():
                spine.set_color('#dbe3ed')
            if entries:
                for row, data, serial, option in entries:
                    x, y, mask = self.plotting_arrays(p, data, option)
                    labeled = False
                    for run in runs(data.segment):
                        indices = run[mask[run]]
                        if len(indices):
                            yp = y[indices].copy()
                            yp[~np.isfinite(yp)] = np.nan
                            ax.plot(x[indices], yp, color='#2563eb', linewidth=1.6,
                                    linestyle='-',
                                    label=f'{row + 1}: {Path(data.name).name}' if not labeled else None,
                                    marker=None)
                            labeled = True
                if len(entries) > 1:
                    ax.legend(fontsize=8, loc='best')
                key = self.axis.currentData()
                keys = list(dict.fromkeys(entry[3][0] for entry in entries))
                ax.set_xlabel('Point index' if key == 'Index' else f'{" / ".join(keys)} ({self.unit.currentText()})', fontsize=9)
                mode = MODES[self.mode.currentText()]
                ax.set_ylabel({'dB': 'Magnitude (dB)', 'Magnitude': 'Magnitude (linear)', 'Phase': 'Phase (deg)',
                               'Unwrapped': 'Unwrapped phase (deg)', 'Real': 'Real', 'Imag': 'Imaginary'}[mode], fontsize=9)
                ax.margins(x=.05)
            else:
                ax.text(.5, .5, 'Select datasets to plot' if self.datasets else 'Open or paste S2P / S2PX',
                        ha='center', va='center', transform=ax.transAxes, color='#94a3b8')
            limits = self.y_limits.get((MODES[self.mode.currentText()], p))
            if limits is not None:
                ax.set_ylim(*limits)
        self.toolbar.update()
        self.update_y_scale()
        self.canvas.draw_idle()

    def hover(self, event):
        if not self.dataset or event.inaxes not in self.axes or event.xdata is None:
            return
        p = PARAMS[list(self.axes).index(event.inaxes)]
        if not any(data is self.dataset for _, data, _, _ in self.plot_entries()):
            return
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
        self.workspace.remember()
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
