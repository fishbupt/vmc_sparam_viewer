

"""S-parameter viewer layout, kept separate from parsing and plotting behavior."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QListWidget, QComboBox, QLabel, QSplitter, QTabWidget,
    QPlainTextEdit, QTableView, QGroupBox, QScrollArea)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from pathlib import Path
import numpy as np
from PyQt6.QtGui import QActionGroup, QCursor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QComboBox, QLabel, QPlainTextEdit, QFileDialog, QMenu, QListWidgetItem
from vna_workbench.data.models import PARAMS
from vna_workbench.analysis.csv_exports import export_csv
from vna_workbench.analysis.transforms import values, runs
from vna_workbench.gui.display_modes import MODES
from vna_workbench.gui.dialogs.data_view import YAxisDialog
from vna_workbench.gui.models import DataModel

def build_viewer(owner, modes):
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMinimumWidth(250)
    scroll.setMaximumWidth(390)
    panel = QWidget()
    panel.setObjectName('viewerSidebar')
    side = QVBoxLayout(panel)
    scroll.setWidget(panel)
    splitter.addWidget(scroll)
    actions = QHBoxLayout()
    owner.open_btn = QPushButton('打开 SNP / S2PX')
    owner.open_btn.setObjectName('primary')
    owner.open_btn.clicked.connect(owner.open_files)
    owner.paste_btn = QPushButton('粘贴')
    owner.paste_btn.clicked.connect(owner.paste)
    actions.addWidget(owner.open_btn)
    actions.addWidget(owner.paste_btn)
    side.addLayout(actions)
    side.addWidget(QLabel('共享文件库 · 选中查看单个文件'))
    owner.files = QListWidget()
    owner.files.setMinimumHeight(140)
    owner.files.currentRowChanged.connect(owner.select)
    side.addWidget(owner.files, 1)
    row = QHBoxLayout()
    for title, slot in [('移除选中', owner.remove), ('清空', owner.clear_files)]:
        button = QPushButton(title)
        button.clicked.connect(slot)
        row.addWidget(button)
    side.addLayout(row)
    group = QGroupBox('单文件频率设置')
    owner.single_controls = group
    form = QFormLayout(group)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    owner.axis = QComboBox()
    owner.unit = QComboBox()
    owner.unit.addItems(['GHz', 'MHz', 'kHz', 'Hz'])
    owner.segment = QComboBox()
    owner.segment.addItem('全部')
    for label, widget in [('当前文件横轴', owner.axis),
                          ('频率单位', owner.unit), ('当前文件分段', owner.segment)]:
        form.addRow(label, widget)
        widget.currentIndexChanged.connect(owner.plot)
    button = QPushButton('与另一文件比较…')
    button.clicked.connect(owner.compare_any_files)
    form.addRow(button)
    side.addWidget(group)
    owner.export_btn = QPushButton('导出当前文件完整 CSV')
    owner.export_btn.clicked.connect(owner.export)
    owner.export_btn.setEnabled(False)
    side.addWidget(owner.export_btn)
    main = QWidget()
    outer = QVBoxLayout(main)
    outer.setContentsMargins(0, 0, 0, 0)
    owner.analysis_tabs = QTabWidget()
    outer.addWidget(owner.analysis_tabs)
    single = QWidget()
    owner.analysis_tabs.addTab(single, '单文件查看')
    content = QVBoxLayout(single)
    content.setContentsMargins(0, 0, 0, 0)
    owner.summary = QLabel('打开文件或粘贴数据开始查看；无需创建校准项目。')
    owner.summary.setWordWrap(True)
    owner.summary.setStyleSheet('background: white; border: 1px solid #dce3ec; padding: 10px;')
    content.addWidget(owner.summary)
    owner.warning = QLabel()
    owner.warning.setWordWrap(True)
    owner.warning.setStyleSheet('background: #fff7e6; color: #92400e; padding: 8px;')
    owner.warning.hide()
    content.addWidget(owner.warning)
    owner.tabs = QTabWidget()
    content.addWidget(owner.tabs, 1)
    page = QWidget()
    chart = QVBoxLayout(page)
    settings = QHBoxLayout()
    settings.addWidget(QLabel('显示'))
    owner.mode = QComboBox()
    owner.mode.addItems(modes)
    saved = owner.settings.value('mode', '幅度 (dB)')
    owner.mode.setCurrentText('解缠绕相位 (°)' if saved == '展开相位 (°)' else saved)
    owner.mode.currentIndexChanged.connect(owner.plot)
    settings.addWidget(owner.mode)
    owner.y_scale = QComboBox()
    owner.y_scale.addItems(['Y 轴 AutoScale', '手动范围…'])
    owner.y_scale.activated.connect(owner.change_y_scale)
    settings.addWidget(owner.y_scale)
    button = QPushButton('Y 轴设置…')
    button.clicked.connect(lambda: owner.edit_y_limits())
    settings.addWidget(button)
    settings.addStretch()
    chart.addLayout(settings)
    owner.figure = Figure(figsize=(9, 6), layout='constrained', facecolor='white')
    owner.canvas = FigureCanvasQTAgg(owner.figure)
    # Preserve PARAMS indexing while placing transmission at the top right.
    owner.axes = owner.figure.subplots(2, 2).ravel()[[0, 2, 1, 3]]
    owner.toolbar = NavigationToolbar2QT(owner.canvas, owner)
    chart.addWidget(owner.toolbar)
    chart.addWidget(owner.canvas, 1)
    owner.canvas.mpl_connect('motion_notify_event', owner.hover)
    owner.canvas.mpl_connect('button_press_event', owner.plot_context_menu)
    owner.tabs.addTab(page, '曲线 · 2 × 2')
    owner.table = QTableView()
    owner.table.setAlternatingRowColors(True)
    owner.tabs.addTab(owner.table, '数据表')
    owner.meta = QPlainTextEdit()
    owner.meta.setReadOnly(True)
    owner.tabs.addTab(owner.meta, '元数据 / Mixer 配置')
    owner.raw = QPlainTextEdit()
    owner.raw.setReadOnly(True)
    owner.tabs.addTab(owner.raw, '原始文本')
    from vna_workbench.gui.pages.sparameter_comparison import ComparisonPage
    owner.comparison_view = ComparisonPage([], owner)
    owner.comparison_view.setWindowFlags(Qt.WindowType.Widget)
    owner.comparison_view.setMinimumSize(0, 0)
    compare_scroll = QScrollArea()
    compare_scroll.setWidgetResizable(True)
    compare_scroll.setWidget(owner.comparison_view)
    owner.analysis_tabs.addTab(compare_scroll, '双文件比较')
    owner.analysis_tabs.currentChanged.connect(
        lambda index: (group.setVisible(index == 0), owner.export_btn.setVisible(index == 0)))
    splitter.addWidget(main)
    splitter.setSizes([290, 1040])
    return splitter



class SParameterViewerController:
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
