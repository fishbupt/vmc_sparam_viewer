from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QProgressBar
from vna_workbench.data.touchstone import load_file, parse_text
from vna_workbench.gui.display_modes import MODES
from vna_workbench.gui.theme import STYLE
from vna_workbench.gui.workers import Task
from vna_workbench.gui.dialogs.data_view import PasteDialog, YAxisDialog
from vna_workbench.gui.pages.sparameter_viewer import SParameterViewerController

class Window(SParameterViewerController, QMainWindow):
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
        from vna_workbench.gui.workspace import WorkbenchPages
        from vna_workbench.app.calibration_registry import CALIBRATION_TYPES
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
        from vna_workbench.gui.pages.sparameter_viewer import build_viewer
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



    def compare_files(self):
        if self.busy():
            return
        from vna_workbench.gui.dialogs.same_name_comparison import CompareDialog
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
        self.workspace.show_page(5)

    def simulate_vmc(self):
        self.workspace.show_simulation()

    def simulate_sol(self):
        if not self.busy():self.workspace.show_sol()

    def characterize_mixer(self):
        if not self.busy():self.workspace.show_characterization()

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
