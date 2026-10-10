"""Application navigation and persistent workflow pages; no calibration formulas."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QStackedWidget)


PAGES = (
    ('查看与比较', '独立查看 SNP / S2PX；勾选文件叠加，或计算频率匹配后的差异。'),
    ('项目配置', 'VMC 频率规划与端口配置；当前仅开放已实现的算法。'),
    ('标准件定义', 'OPEN / SHORT / LOAD / THRU，以及已表征的校准混频器。'),
    ('原始测量', '导入 OPEN / SHORT / LOAD / THRU / CalTHRU；或生成配套仿真数据。'),
    ('校准求解', '关联全部输入，计算 VMC 误差项，保存或载入校准包。'),
    ('校准 MUT', '使用同一份校准包校准 MUT；原始响应与结果进入数据查看。'),
    ('验证报告', '复用差异曲线、误差统计与 CSV 导出；不自动判定容差通过。'),
)


class WorkbenchPages(QWidget):
    def __init__(self, owner, viewer):
        super().__init__(owner)
        self.owner = owner
        self.calibration = self.simulation = self.comparison = None
        self.comparison_signature = None
        self.primary_action = None
        self.workers = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.navigation = QListWidget()
        self.navigation.setObjectName('workflowNavigation')
        self.navigation.setMinimumWidth(155)
        self.navigation.setMaximumWidth(210)
        self.navigation.setSpacing(4)
        for title in ['数据分析', PAGES[0][0], '校准工作流程', *[p[0] for p in PAGES[1:]]]:
            item = QListWidgetItem(title)
            if title in ('数据分析', '校准工作流程'):
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.navigation.addItem(item)
        layout.addWidget(self.navigation)
        body = QWidget()
        box = QVBoxLayout(body)
        box.setContentsMargins(10, 0, 0, 0)
        head = QHBoxLayout()
        info = QVBoxLayout()
        self.heading = QLabel()
        self.heading.setStyleSheet('font-size: 17pt; font-weight: bold;')
        self.description = QLabel()
        self.description.setWordWrap(True)
        info.addWidget(self.heading)
        info.addWidget(self.description)
        head.addLayout(info, 1)
        self.actions = QHBoxLayout()
        head.addLayout(self.actions)
        box.addLayout(head)
        self.stack = QStackedWidget()
        self.stack.addWidget(viewer)
        box.addWidget(self.stack, 1)
        layout.addWidget(body, 1)
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.itemClicked.connect(self.clicked_navigation)
        self.show_page(0)

    def clicked_navigation(self, item):
        # Clicking the selected Raw Measurements entry leaves its generator subpage.
        if self.simulation is not None and self.stack.currentWidget() is self.simulation:
            if self.navigation.row(item) == 5:
                self.navigate(5)

    def button(self, text, fn):
        button = QPushButton(text)
        button.clicked.connect(fn)
        self.actions.addWidget(button)
        return button

    def show_page(self, index):
        self.navigation.setCurrentRow(1 if index == 0 else index + 2)

    def navigate(self, row):
        if row in (0, 2):
            return
        index = 0 if row == 1 else row - 2
        self.primary_action = None
        while self.actions.count():
            widget = self.actions.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.heading.setText(PAGES[index][0])
        self.description.setText(PAGES[index][1])
        if index == 0:
            self.stack.setCurrentIndex(0)
            self.button('添加文件…', self.owner.open_files)
        elif index == 6:
            self.show_comparison()
        else:
            self.ensure_calibration()
            self.calibration.set_workspace_section(
                {1: 'project', 2: 'standards', 3: 'raw', 4: 'solve', 5: 'mut'}[index])
            self.stack.setCurrentWidget(self.calibration)
            if index == 2:
                self.button('两轮 SOL 表征…', self.owner.characterize_mixer)
            if index == 3:
                self.button('生成 VMC 原始测量 SNP', self.show_simulation)
                self.button('生成两轮 SOL…', self.owner.simulate_sol)
            if index == 4:
                self.primary_action = self.button('计算 VMC 校准误差项', self.calibration.compute)
                self.primary_action.setObjectName('primary')

    def wire(self, page):
        self.workers.append(page)
        if hasattr(page, 'generated'):
            page.generated.connect(self.owner.add_dataset)
        if hasattr(page, 'log'):
            self.owner.merge_page_log(page)
            page.log.hide()

    def ensure_calibration(self):
        if self.calibration is None:
            from vmc_calibration_gui import VMCCalibrationDialog
            self.calibration = VMCCalibrationDialog(self.owner, embedded=True)
            self.wire(self.calibration)
            self.stack.addWidget(self.calibration)

    def show_simulation(self):
        if self.navigation.currentRow() == 5:
            self.navigate(5)
        else:
            self.show_page(3)
        if self.simulation is None:
            from vmc_simulation_gui import VMCSimulationDialog
            self.simulation = VMCSimulationDialog(self.owner, embedded=True)
            self.wire(self.simulation)
            self.stack.addWidget(self.simulation)
        self.stack.setCurrentWidget(self.simulation)
        self.heading.setText('原始测量 · VMC 仿真生成')
        self.description.setText('独立正向模型生成原始文件、标准定义和真值；生成后可载入同一校准流程。')
        self.button('返回测量导入', lambda: self.navigate(5))

    def use_generated_files(self, saved):
        self.ensure_calibration()
        if self.calibration.worker:
            self.owner.statusBar().showMessage('校准正在执行，请完成后再载入生成文件。')
            return
        self.calibration.set_generated_files(saved)
        self.show_page(4)

    def show_comparison(self):
        signature = tuple(id(d) for d in self.owner.datasets)
        if self.comparison is None or (signature != self.comparison_signature and not self.comparison.worker):
            if self.comparison is not None:
                self.stack.removeWidget(self.comparison)
                self.workers.remove(self.comparison)
                self.comparison.deleteLater()
            from compare_gui import CompareDialog
            self.comparison = CompareDialog(self.owner.datasets, self.owner, general=True)
            self.comparison.setWindowFlags(Qt.WindowType.Widget)
            self.comparison.setMinimumSize(0, 0)
            self.stack.addWidget(self.comparison)
            self.wire(self.comparison)
            self.comparison_signature = signature
        self.stack.setCurrentWidget(self.comparison)

    def busy(self):
        return any(page.worker is not None for page in self.workers)

    def refresh_actions(self):
        if self.primary_action is not None:
            self.primary_action.setEnabled(not self.owner.busy())

    def remember(self):
        if self.calibration is not None:
            self.calibration.remember()
        if self.simulation is not None:
            self.simulation.remember()
