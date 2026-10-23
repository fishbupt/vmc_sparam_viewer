

"""Application navigation and persistent workflow pages; no calibration formulas."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QStackedWidget)
from vna_workbench.app.calibration_registry import CALIBRATION_TYPES

PAGES = (
    ('数据查看', '单文件查看与双文件比较独立设置，共用导入文件库。'),
    ('VMC 全局配置', 'RF / LO / IF、点数、参考阻抗与求值规则由全部步骤共享。'),
    ('1. 生成两轮 SOL', '第一轮按 RF、第二轮按 IF 求值；端口 2 标准可独立配置。'),
    ('2. 表征校准混频器', '由两轮 SOL 测量和各端口标准定义提取混频器表征。'),
    ('3. 生成 VMC 原始测量 SNP', '使用已表征混频器生成 SOL / THRU / CalTHRU / MUT。'),
    ('4. 校准求解', '关联输入并计算 VMC 误差项，可保存或载入校准包。'),
    ('5. 校准 MUT', '使用当前校准包校准 MUT，结果进入数据查看。'),
    ('验证报告', '复用差异曲线、误差统计与 CSV 导出。'),
)

# These are workflow choices, not a claim that their numerical engines exist.


class WorkbenchPages(QWidget):
    def __init__(self, owner, viewer):
        super().__init__(owner)
        self.owner = owner
        self.calibration = self.simulation = self.sol_simulation = self.characterization = None
        self._cascading=False
        from vna_workbench.gui.workflows.vmc.session import VMCSession
        self.vmc_session=VMCSession(self)
        self.comparison = owner.comparison_view
        self.primary_action = None
        self.workers = [self.comparison]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.navigation = QListWidget()
        self.navigation.setObjectName('workflowNavigation')
        self.navigation.setMinimumWidth(155)
        self.navigation.setMaximumWidth(250)
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
        self.placeholder = QWidget()
        empty_layout = QVBoxLayout(self.placeholder)
        self.placeholder_title = QLabel()
        self.placeholder_title.setStyleSheet('font-size: 16pt; color: #64748b;')
        self.placeholder_title.setWordWrap(True)
        self.placeholder_note = QLabel('此类型的校准页面暂未实现。')
        self.placeholder_note.setStyleSheet('color: #64748b;')
        empty_layout.addStretch()
        empty_layout.addWidget(self.placeholder_title, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.placeholder_note, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch()
        self.stack.addWidget(self.placeholder)
        box.addWidget(self.stack, 1)
        layout.addWidget(body, 1)
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.itemClicked.connect(self.clicked_navigation)
        self.show_page(0)

    def clicked_navigation(self,item):
        pass  # Each workflow step now has its own persistent navigation entry.

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
        if index == 6 and self.owner.calibration_type != 'vmc':
            self.heading.setText('校准 DUT')
        if index == 0:
            self.stack.setCurrentIndex(0)
            self.button('添加文件…', self.owner.open_files)
        elif index == 7:
            self.show_comparison()
        elif self.owner.calibration_type != 'vmc':
            label = CALIBRATION_TYPES[self.owner.calibration_type][0]
            self.description.setText(label + ' · 待实现')
            self.placeholder_title.setText(label)
            self.stack.setCurrentWidget(self.placeholder)
        else:
            self.ensure_calibration()
            if index in (1,5,6):
                self.calibration.set_workspace_section({1:'project',5:'solve',6:'mut'}[index])
                self.stack.setCurrentWidget(self.calibration)
            elif index==2:
                self.ensure_sol();self.stack.setCurrentWidget(self.sol_simulation)
            elif index==3:
                self.ensure_characterization();self.stack.setCurrentWidget(self.characterization_scroll)
            elif index==4:
                self.ensure_simulation();self.stack.setCurrentWidget(self.simulation)
            if index!=1:self.button('修改全局配置',lambda:self.show_page(1))
            if index==1:
                self.button('高边 LO 预设：RF 10～15 / LO 20 GHz',self.high_side_preset)
            if index==5:
                self.primary_action=self.button('计算 VMC 校准误差项',self.calibration.compute)
                self.primary_action.setObjectName('primary')

    def high_side_preset(self):
        self.vmc_session.update(dict(rf_start_hz=10e9,rf_stop_hz=15e9,lo_hz=20e9,
            points=201,frequency_conversion='high_side',raw_axis='rf'))


    def wire(self, page):
        self.workers.append(page)
        if hasattr(page, 'generated'):
            page.generated.connect(self.owner.add_dataset)
        if hasattr(page, 'log'):
            self.owner.merge_page_log(page)
            page.log.hide()

    def ensure_calibration(self):
        if self.calibration is None:
            from dataclasses import asdict
            from vna_workbench.gui.workflows.vmc.calibration import VMCCalibrationDialog
            self.calibration=VMCCalibrationDialog(self.owner,embedded=True)
            self.wire(self.calibration);self.stack.addWidget(self.calibration)
            if not self.vmc_session.restored:
                self.vmc_session.update(asdict(self.calibration.options()),force=True)
                self.vmc_session.restored=True
            fields={k:(v,1e9 if k.endswith('_hz') and k!='frequency_tolerance_hz' else 1) for k,v in self.calibration.spins.items()}
            fields.update(points=(self.calibration.points,1),frequency_conversion=(self.calibration.conversion,1),
                standard_sampling=(self.calibration.sampling,1),raw_axis=(self.calibration.raw_axis,1))
            self.vmc_session.attach(self.calibration,fields,editor=True)

    def ensure_sol(self):
        if self.sol_simulation is None:
            from vna_workbench.gui.workflows.vmc.characterization_simulation import SimulationDialog
            from vna_workbench.gui.workflows.vmc.session import generator_fields
            self.sol_simulation=SimulationDialog(self.owner,embedded=True)
            self.wire(self.sol_simulation);self.stack.addWidget(self.sol_simulation)
            self.vmc_session.attach(self.sol_simulation,generator_fields(self.sol_simulation))
            self.sol_simulation.invalidated.connect(lambda:self.invalidate_after(1))

    def ensure_characterization(self):
        if self.characterization is None:
            from PyQt6.QtWidgets import QScrollArea
            from vna_workbench.gui.workflows.vmc.mixer_characterization import CharacterizeDialog
            self.characterization=CharacterizeDialog(self.owner,embedded=True)
            self.wire(self.characterization)
            self.characterization_scroll=QScrollArea();self.characterization_scroll.setWidgetResizable(True)
            self.characterization_scroll.setWidget(self.characterization);self.stack.addWidget(self.characterization_scroll)
            self.vmc_session.attach(self.characterization,{
                'lo_hz':(self.characterization.lo,1e9),'frequency_conversion':(self.characterization.conversion,1),
                'standard_sampling':(self.characterization.sampling,1),'frequency_tolerance_hz':(self.characterization.tol,1)})
            self.characterization.invalidated.connect(lambda:self.invalidate_after(2))

    def ensure_simulation(self):
        if self.simulation is None:
            from vna_workbench.gui.workflows.vmc.simulation import VMCSimulationDialog
            from vna_workbench.gui.workflows.vmc.session import generator_fields
            self.simulation=VMCSimulationDialog(self.owner,embedded=True)
            self.wire(self.simulation);self.stack.addWidget(self.simulation)
            self.vmc_session.attach(self.simulation,generator_fields(self.simulation,True))
            self.simulation.invalidated.connect(lambda:self.invalidate_after(3))

    def show_simulation(self):
        if self.owner.choose_calibration_type('vmc'):self.show_page(4)

    def show_sol(self):
        if self.owner.choose_calibration_type('vmc'):self.show_page(2)

    def show_characterization(self):
        if self.owner.choose_calibration_type('vmc'):self.show_page(3)

    def use_sol_files(self,saved):
        if self.busy():return
        self.ensure_characterization()
        self.characterization.set_generated_files(saved)
        self.show_page(3)

    def use_characterized_file(self,path,standards):
        # Called from the exporting worker's done signal. Inputs are a fixed snapshot.
        self.ensure_simulation();sim=self.simulation
        sim.synthetic_sol.setChecked(False);sim.import_sol.setChecked(True)
        sim.separate_kit.setChecked(len(standards)==6)
        for key,value in zip(('open','short','load','p2_open','p2_short','p2_load'),standards):
            sim.file_fields[key].setText(str(value))
        sim.import_cal.setChecked(True);sim.file_fields['calibration_mixer'].setText(str(path))
        sim.definition_axis.setCurrentIndex(sim.definition_axis.findData('rf'))
        self.show_page(4)

    def invalidate_after(self,stage):
        if self._cascading:return
        self._cascading=True
        try:
            if stage<2 and self.characterization:self.characterization.invalidate()
            if stage<3 and self.simulation:self.simulation.invalidate()
            if self.calibration:self.calibration.invalidate_cal()
        finally:self._cascading=False

    def use_generated_files(self, saved):
        if not self.owner.choose_calibration_type('vmc'):
            return
        self.ensure_calibration()
        if self.calibration.worker:
            self.owner.statusBar().showMessage('校准正在执行，请完成后再载入生成文件。')
            return
        self.calibration.set_generated_files(saved)
        self.show_page(5)

    def show_comparison(self):
        # A report opens the same comparison instance and keeps its results/settings.
        self.stack.setCurrentIndex(0)
        self.owner.analysis_tabs.setCurrentIndex(1)

    def busy(self):
        return any(page.worker is not None for page in self.workers)

    def refresh_actions(self):
        busy=self.owner.busy()
        for page in self.workers:
            if page is self.comparison:continue
            page.setEnabled(not busy or page.worker is not None)
        for i in range(self.actions.count()):
            widget=self.actions.itemAt(i).widget()
            if widget:widget.setEnabled(not busy)

    def calibration_type_changed(self):
        self.navigation.item(8).setText('5. 校准 MUT' if self.owner.calibration_type == 'vmc' else '校准 DUT')
        self.navigate(self.navigation.currentRow())

    def remember(self):
        import json
        self.owner.settings.setValue('vmc_global/config',json.dumps(self.vmc_session.values))
        if self.calibration is not None:
            self.calibration.remember()
        if self.simulation is not None:
            self.simulation.remember()
