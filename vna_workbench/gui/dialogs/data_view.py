from __future__ import annotations
import numpy as np
from PyQt6.QtWidgets import QVBoxLayout, QFormLayout, QComboBox, QLabel, QPlainTextEdit, QDialog, QDialogButtonBox, QLineEdit
from vna_workbench.data.models import PARAMS
from vna_workbench.gui.display_modes import MODES

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
