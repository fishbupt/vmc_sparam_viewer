"""Persistent A/B analysis page; overlay uses raw samples, differences use unique matches."""
from pathlib import Path
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QDoubleSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QFileDialog, QMessageBox, QDialogButtonBox,
    QFormLayout, QLineEdit, QMenu, QSizePolicy)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from parser import PARAMS, values, runs
from comparison import compare, stats, export_comparison
from compare_gui import Work, METRICS, YLABELS

OVERLAYS = {'幅度叠加 (dB)': 'dB', '线性幅度叠加': 'Magnitude',
    '相位叠加 (°)': 'Phase', '解缠绕相位叠加 (°)': 'Unwrapped',
    '实部叠加': 'Real', '虚部叠加': 'Imag'}


class ComparisonPage(QDialog):
    def __init__(self, datasets, parent=None):
        super().__init__(parent)
        self.workbench_owner = parent
        self.worker = self.result = None
        self.datasets = []
        self.options = {}
        self.y_limits = {}
        self._selected = (None, None)
        box = QVBoxLayout(self)
        grid = QGridLayout()
        box.addLayout(grid)
        self.left = QComboBox(); self.right = QComboBox()
        self.left_axis = QComboBox(); self.axis = QComboBox()
        self.left_segment = QComboBox(); self.right_segment = QComboBox()
        for row, (name, file, axis, segment) in enumerate((
                ('A', self.left, self.left_axis, self.left_segment),
                ('B', self.right, self.axis, self.right_segment))):
            grid.addWidget(QLabel(name), row, 0)
            grid.addWidget(file, row, 1)
            grid.addWidget(QLabel('横轴'), row, 2)
            grid.addWidget(axis, row, 3)
            grid.addWidget(QLabel('分段'), row, 4)
            grid.addWidget(segment, row, 5)
            file.currentIndexChanged.connect(self.set_pair)
            axis.currentIndexChanged.connect(self.settings_changed)
            segment.currentIndexChanged.connect(self.settings_changed)
        grid.setColumnStretch(1, 2); grid.setColumnStretch(3, 1)
        self.swap = QPushButton('交换 A/B'); grid.addWidget(self.swap, 0, 6, 2, 1)
        self.swap.clicked.connect(self.swap_files)
        row = QHBoxLayout(); box.addLayout(row)
        self.metric = QComboBox(); self.metric.addItems([*OVERLAYS, *METRICS[:5]])
        row.addWidget(QLabel('显示')); row.addWidget(self.metric)
        self.unit = QComboBox(); self.unit.addItems(['GHz', 'MHz', 'kHz', 'Hz'])
        row.addWidget(self.unit)
        self.y_auto = QPushButton('Y AutoScale'); row.addWidget(self.y_auto)
        self.y_manual = QPushButton('Y 范围…'); row.addWidget(self.y_manual)
        row.addStretch()
        row = QHBoxLayout(); box.addLayout(row)
        row.addWidget(QLabel('唯一频点匹配容差 (Hz)'))
        self.tol = QDoubleSpinBox(); self.tol.setDecimals(6); self.tol.setRange(0, 1e9); self.tol.setValue(.001)
        row.addWidget(self.tol)
        self.run = QPushButton('计算差异 / 统计'); row.addWidget(self.run)
        self.save = QPushButton('导出差异 CSV'); row.addWidget(self.save)
        self.image = QPushButton('导出曲线图片'); row.addWidget(self.image)
        row.addStretch()
        self.summary = QLabel(); self.summary.setWordWrap(True); box.addWidget(self.summary)
        self.tabs = QTabWidget(); box.addWidget(self.tabs, 1)
        chart = QWidget(); layout = QVBoxLayout(chart)
        self.fig = Figure(layout='constrained', facecolor='white')
        self.axes = self.fig.subplots(2, 2).ravel()[[0, 2, 1, 3]]
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(260)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar); layout.addWidget(self.canvas, 1)
        self.tabs.addTab(chart, '叠加 / 差异曲线')
        self.table = QTableWidget(4, 10)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(['参数', 'max |ΔdB|', 'RMS ΔdB', 'max |Δφ| (°)',
            'RMS Δφ (°)', 'max |Δcomplex|', 'RMS |Δcomplex|', 'max |ΔRe|', 'max |ΔIm|', '有效幅相点'])
        self.tabs.addTab(self.table, '误差统计')
        self.metric.currentIndexChanged.connect(self.plot)
        self.unit.currentIndexChanged.connect(self.plot)
        self.tol.valueChanged.connect(self.invalidate)
        self.run.clicked.connect(self.compute); self.save.clicked.connect(self.export)
        self.image.clicked.connect(self.export_image)
        self.y_auto.clicked.connect(lambda: self.set_y_limits(None, None))
        self.y_manual.clicked.connect(lambda: self.edit_y_limits())
        self.canvas.mpl_connect('button_press_event', self.context_menu)
        self.set_datasets(datasets)

    def selection(self):
        return self.left.currentData(), self.right.currentData()

    @property
    def pairs(self):
        a, b = self.selection()
        return [(a, b)] if a is not None and b is not None and a is not b else []

    def remember_options(self):
        for side, data, axis, segment in zip(('A', 'B'), self._selected,
                (self.left_axis, self.axis), (self.left_segment, self.right_segment)):
            if data is not None:
                self.options[(side, id(data))] = (axis.currentText(), segment.currentData())

    def set_datasets(self, datasets):
        self.remember_options()
        previous = self.selection()
        if len(self.datasets) < 2:
            previous = (previous[0], None)
        self.datasets = list(datasets)
        for combo, old, default in ((self.left, previous[0], 0), (self.right, previous[1], 1)):
            combo.blockSignals(True); combo.clear()
            for n, d in enumerate(self.datasets):
                combo.addItem(f'{n+1}: {Path(d.name).name}', d)
                combo.setItemData(n, d.name, Qt.ItemDataRole.ToolTipRole)
            index = next((n for n, d in enumerate(self.datasets) if d is old), min(default, len(self.datasets)-1))
            combo.setCurrentIndex(index); combo.blockSignals(False)
        valid_ids = {id(d) for d in self.datasets}
        self.options = {k: v for k, v in self.options.items() if k[1] in valid_ids}
        current = self.selection()
        # Appending an unrelated file must preserve an existing comparison result.
        if all(a is b for a, b in zip(previous, current)) and self.datasets:
            self.update_enabled()
            return
        self.set_pair()

    def set_pair(self, *args):
        self.remember_options()
        self._selected = self.selection()
        for side, d, axis, segment in zip(('A', 'B'), self._selected,
                (self.left_axis, self.axis), (self.left_segment, self.right_segment)):
            axis.blockSignals(True); segment.blockSignals(True)
            axis.clear(); segment.clear(); segment.addItem('全部', None)
            if d is not None:
                axis.addItems(list(d.axes))
                for key in dict.fromkeys(d.segment.tolist()): segment.addItem(str(key), key)
                key, seg = self.options.get((side, id(d)), (next(iter(d.axes)), None))
                axis.setCurrentIndex(max(0, axis.findText(key)))
                segment.setCurrentIndex(max(0, segment.findData(seg)))
            axis.blockSignals(False); segment.blockSignals(False)
        self.invalidate()

    def select_left(self, dataset):
        if self.worker: return
        index = next((n for n, d in enumerate(self.datasets) if d is dataset), -1)
        if index < 0: return
        self.left.setCurrentIndex(index)
        if self.right.currentData() is dataset:
            other = next((n for n, d in enumerate(self.datasets) if d is not dataset), -1)
            if other >= 0: self.right.setCurrentIndex(other)

    def swap_files(self):
        if self.worker: return
        self.remember_options()
        a, b = self.selection()
        if a is None or b is None: return
        aopt = (self.left_axis.currentText(), self.left_segment.currentData())
        bopt = (self.axis.currentText(), self.right_segment.currentData())
        self.options[('A', id(b))] = bopt; self.options[('B', id(a))] = aopt
        i, j = self.left.currentIndex(), self.right.currentIndex()
        self.left.blockSignals(True); self.right.blockSignals(True)
        self.left.setCurrentIndex(j); self.right.setCurrentIndex(i)
        self.left.blockSignals(False); self.right.blockSignals(False)
        self._selected = (None, None)  # Do not overwrite the swapped settings.
        self.set_pair()

    def settings_changed(self, *args):
        self.remember_options(); self.invalidate()

    def other_busy(self):
        owner = self.workbench_owner
        return self.worker is None and owner is not None and hasattr(owner, 'workspace') and owner.busy()

    def update_enabled(self):
        valid = bool(self.pairs)
        idle = self.worker is None and not self.other_busy()
        for w in (self.left, self.right, self.left_axis, self.axis,
                  self.left_segment, self.right_segment, self.tol, self.swap):
            w.setEnabled(idle)
        self.run.setEnabled(valid and idle)
        self.save.setEnabled(self.result is not None and idle)

    def invalidate(self, *args):
        self.result = None; self.table.clearContents()
        self.summary.setText('请选择两份不同文件。' if not self.pairs else
            '叠加使用各自原始频点；差异 = A − B，仅匹配容差内唯一频点，不插值。请确认两侧 RF / IF 物理含义一致，点击计算获得统计。')
        self.update_enabled(); self.plot()

    def begin(self, fn, args, callback):
        if self.worker: return
        self.worker = Work(fn, *args); self.update_enabled()
        self.worker.done.connect(callback)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finish); self.worker.start()

    def failed(self, msg):
        self.summary.setText('操作失败：请检查频率轴、分段与容差。')
        QMessageBox.warning(self, '操作失败', msg)

    def finish(self):
        self.worker.deleteLater(); self.worker = None; self.update_enabled()

    def compute(self):
        if not self.pairs or self.worker or self.other_busy(): return
        a, b = self.selection(); self.invalidate()
        self.summary.setText('正在进行唯一频点匹配与差异统计…')
        self.begin(compare, (a, b, self.axis.currentText(), self.tol.value(),
            self.left_axis.currentText(), self.left_segment.currentData(), self.right_segment.currentData()), self.accept_result)

    def accept_result(self, r):
        self.result = r
        ac = r.left.count if r.left_segment is None else np.count_nonzero(r.left.segment == r.left_segment)
        bc = r.right.count if r.right_segment is None else np.count_nonzero(r.right.segment == r.right_segment)
        deviation = np.max(np.abs(r.left.axes[r.left_axis][r.i] - r.right.axes[r.axis][r.j]))
        self.summary.setText(f'匹配 {len(r.i)} 点；所选分段 A {ac} / B {bc} 点，未匹配 A {ac-len(r.i)} / B {bc-len(r.j)}；'
            f'A 歧义 {r.ambiguous} 点；最大频率偏差 {deviation:.6g} Hz。零幅度的幅相差不参与统计；不自动判定通过 / 失败。')
        for row, p in enumerate(PARAMS):
            d = r.delta[p]; db = stats(d[METRICS[0]]); ph = stats(d[METRICS[1]]); co = stats(d[METRICS[2]])
            cells = [p, db[0], db[1], ph[0], ph[1], co[0], co[1], stats(d[METRICS[3]])[0], stats(d[METRICS[4]])[0], db[2]]
            for col, v in enumerate(cells): self.table.setItem(row, col, QTableWidgetItem(v if isinstance(v, str) else f'{v:.9g}'))
        self.table.resizeColumnsToContents(); self.plot()

    def plot(self, *args):
        metric = self.metric.currentText(); overlay = metric in OVERLAYS
        scale = {'GHz': 1e9, 'MHz': 1e6, 'kHz': 1e3, 'Hz': 1}[self.unit.currentText()]
        for ax, p in zip(self.axes, PARAMS):
            ax.clear(); ax.set_title(p, loc='left', fontsize=11, fontweight='bold'); ax.tick_params(labelsize=8); ax.grid(True, alpha=.2)
            axes = list(dict.fromkeys((self.left_axis.currentText(), self.axis.currentText())))
            ax.set_xlabel(f'{" / ".join(axes)} ({self.unit.currentText()})', fontsize=8)
            labels = {'dB': 'Magnitude (dB)', 'Magnitude': 'Magnitude (linear)',
                'Phase': 'Phase (deg)', 'Unwrapped': 'Unwrapped phase (deg)', 'Real': 'Real', 'Imag': 'Imaginary'}
            ax.set_ylabel(labels[OVERLAYS[metric]] if overlay else YLABELS[METRICS.index(metric)], fontsize=8)
            if self.pairs and overlay:
                for label, d, axis, seg, color, style in zip(('A', 'B'), self.selection(),
                    (self.left_axis.currentText(), self.axis.currentText()),
                    (self.left_segment.currentData(), self.right_segment.currentData()), ('#2563eb', '#d97706'), ('-', '--')):
                    x = d.axes[axis] / scale; y = values(d.s[p], OVERLAYS[metric], d.segment)
                    mask = np.ones(d.count, bool) if seg is None else d.segment == seg
                    labeled = False
                    for run in runs(d.segment):
                        indices = run[mask[run]]
                        if len(indices):
                            ax.plot(x[indices], y[indices], style, color=color, label=f'{label}: {Path(d.name).name}' if not labeled else None)
                            labeled = True
                ax.legend(fontsize=8)
            elif self.result and not overlay:
                r = self.result; x = r.left.axes[r.left_axis][r.i] / scale
                breaks = (np.diff(r.i) != 1) | (np.diff(r.j) != 1) | (np.diff(r.left.segment[r.i]) != 0) | (np.diff(r.right.segment[r.j]) != 0) | (np.diff(x) <= 0)
                for group in np.split(np.arange(len(x)), np.flatnonzero(breaks)+1):
                    ax.plot(x[group], r.delta[p][metric][group], color='#2563eb', marker='o', markersize=3)
                ax.axhline(0, color='#94a3b8', linewidth=.8)
            elif not overlay:
                ax.text(.5, .5, 'Compute differences first', ha='center', transform=ax.transAxes)
            limits = self.y_limits.get((metric, p))
            if limits is not None: ax.set_ylim(*limits)
        self.toolbar.update(); self.canvas.draw_idle()

    def set_y_limits(self, param, limits):
        if limits is not None and (not np.all(np.isfinite(limits)) or limits[0] >= limits[1]):
            raise ValueError('Y 范围必须是有限数且最小值小于最大值。')
        for p in PARAMS if param is None else (param,):
            key = (self.metric.currentText(), p)
            if limits is None: self.y_limits.pop(key, None)
            else: self.y_limits[key] = limits
        self.plot()

    def edit_y_limits(self, param=None):
        dialog = QDialog(self); dialog.setWindowTitle('比较页 Y 轴范围')
        form = QFormLayout(dialog); target = QComboBox(); target.addItem('全部 S 参数', None)
        for p in PARAMS: target.addItem(p, p)
        target.setCurrentIndex(target.findData(param)); form.addRow('应用到', target)
        lo = QLineEdit(); hi = QLineEdit(); form.addRow('最小值', lo); form.addRow('最大值', hi)
        error = QLabel(); form.addRow(error)
        def refresh():
            p = target.currentData() or PARAMS[0]
            limits = self.y_limits.get((self.metric.currentText(), p), self.axes[PARAMS.index(p)].get_ylim())
            lo.setText(f'{limits[0]:.12g}'); hi.setText(f'{limits[1]:.12g}')
        target.currentIndexChanged.connect(refresh); refresh()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons); buttons.rejected.connect(dialog.reject)
        def accept():
            try: self.set_y_limits(target.currentData(), (float(lo.text()), float(hi.text())))
            except ValueError: error.setText('请输入有限数值，并确保最小值小于最大值。'); return
            dialog.accept()
        buttons.accepted.connect(accept); dialog.exec()

    def context_menu(self, event):
        if event.button != 3 or event.inaxes not in self.axes: return
        p = PARAMS[list(self.axes).index(event.inaxes)]
        menu = QMenu(self)
        for label in [*OVERLAYS, *METRICS[:5]]:
            action = menu.addAction(label); action.setCheckable(True); action.setChecked(label == self.metric.currentText())
            action.triggered.connect(lambda checked=False, key=label: self.metric.setCurrentText(key))
        menu.addSeparator()
        menu.addAction('Y AutoScale', lambda: self.set_y_limits(p, None))
        menu.addAction('Y 手动范围…', lambda: self.edit_y_limits(p))
        menu.exec(self.canvas.mapToGlobal(self.canvas.rect().center()))

    def export(self):
        if not self.result or self.worker or self.other_busy(): return
        path, _ = QFileDialog.getSaveFileName(self, '导出匹配点及差异', Path(self.result.left.name).stem+'_difference.csv', 'CSV (*.csv)')
        if path:
            if not path.lower().endswith('.csv'): path += '.csv'
            self.begin(export_comparison, (self.result, path), lambda _: self.summary.setText('差异已导出：'+path))

    def export_image(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出比较曲线', 'comparison.png', 'PNG (*.png);;SVG (*.svg)')
        if path:
            if not Path(path).suffix: path += '.png'
            try: self.fig.savefig(path, dpi=180)
            except Exception as exc: QMessageBox.warning(self, '图片导出失败', str(exc))

    def reject(self):
        if self.windowType() != Qt.WindowType.Widget and not self.worker: super().reject()

    def closeEvent(self, event):
        if self.worker: event.ignore()
        else: super().closeEvent(event)
