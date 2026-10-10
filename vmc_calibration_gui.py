"""VMC calibration / calibrate MUT dialog. No independent comparison page."""
from pathlib import Path
import numpy as np
from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QGroupBox,
    QLabel,QLineEdit,QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,
    QTabWidget,QWidget,QScrollArea,QPlainTextEdit,QProgressBar,QFileDialog,QMessageBox)
from characterize_gui import Worker
from characterization import SAMPLING_METHODS
from frequency_mapping import CONVERSION_MODES, output_frequencies
from parser import Dataset
from vmc_calibration import (GROUPS,KINDS,AXIS_MODES,CalibrationOptions,CalibrationInputs,
    calibrate,calibrate_mut,save_calibration,load_calibration,export_mut,term_dataset)

class VMCCalibrationDialog(QDialog):
    generated=pyqtSignal(object)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('VMC 全量校准 · 计算误差项 / 校准 MUT');self.resize(1100,850)
        self.settings=QSettings('VNAAlgorithmTools','VMCFullCalibration')
        self.worker=None;self.calibration=None;self.mut_result=None
        self.fields={};self.controls=[];self.cal_inputs=[];self.mut_inputs=[]
        layout=QVBoxLayout(self)
        intro=QLabel('机械 SOLT：两个端口分别做 RF / IF SOL，普通 Thru 求负载匹配，校准混频器求变频 ETF。\n'
                     '校准 MUT 使用单向 / 忽略反向耦合公式；展示与比较复用主界面。')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        page=QWidget();page_layout=QVBoxLayout(page);scroll=QScrollArea();scroll.setWidgetResizable(True)
        body=QWidget();body_layout=QVBoxLayout(body);scroll.setWidget(body);page_layout.addWidget(scroll)
        self.tabs.addTab(page,'计算 VMC 校准误差项')
        group=QGroupBox('频率与标准件求值');form=QFormLayout(group);body_layout.addWidget(group)
        self.spins={}
        for key,label,default,lo,hi in [
                ('rf_start_hz','RF 起点 (GHz)',10,.000000001,1000),
                ('rf_stop_hz','RF 终点 (GHz)',20,.000000001,1000),
                ('lo_hz','固定 LO (GHz)',20,.000000001,1000),
                ('z0','参考阻抗 (Ω)',50,.001,10000),
                ('frequency_tolerance_hz','频点容差 (Hz)',.001,0,1e6)]:
            s=QDoubleSpinBox();s.setDecimals(9);s.setRange(lo,hi)
            s.setValue(float(self.settings.value(key,default)));form.addRow(label,s)
            s.valueChanged.connect(self.invalidate_cal);self.spins[key]=s;self.controls.append(s)
        self.points=QSpinBox();self.points.setRange(2,200001);self.points.setValue(int(self.settings.value('points',201)))
        self.points.valueChanged.connect(self.invalidate_cal);form.addRow('扫频点数',self.points);self.controls.append(self.points)
        self.conversion=self.combo(form,'IF 变频方向',CONVERSION_MODES,'frequency_conversion','up')
        self.sampling=self.combo(form,'标准定义插值',SAMPLING_METHODS,'standard_sampling','cubic_ri')
        self.raw_axis=self.combo(form,'变频原始文件横轴',AXIS_MODES,'raw_axis','dual')
        self.definition_axis=self.combo(form,'校准混频器表征横轴',{'rf':'RF 横轴','if':'IF 横轴'},'mixer_definition_axis','rf')
        self.mapping_label=QLabel();self.mapping_label.setWordWrap(True);form.addRow('频率映射',self.mapping_label)
        self.update_mapping()
        group=QGroupBox('标准件定义：OPEN / SHORT / LOAD（S1P）');form=QFormLayout(group);body_layout.addWidget(group)
        for kind in KINDS: self.path_field(form,'std_P1_'+kind,'Port1 / 共用 '+kind)
        self.separate_std=self.check(form,'Port2 使用独立标准件定义','separate_std')
        self.std2_group=QGroupBox('Port2 标准件定义');sub=QFormLayout(self.std2_group);body_layout.addWidget(self.std2_group)
        for kind in KINDS: self.path_field(sub,'std_P2_'+kind,'Port2 '+kind)
        self.separate_std.toggled.connect(self.std2_group.setVisible);self.std2_group.setVisible(self.separate_std.isChecked())
        group=QGroupBox('SOL 原始测量');form=QFormLayout(group);body_layout.addWidget(group)
        self.separate_sol=self.check(form,'逐项导入 12 组 SOL（S1P 或 S2P）','separate_sol')
        self.shared_sol=QGroupBox('共用三个 S2P：P1 读取 S11、P2 读取 S22，分别匹配 RF / IF');sub=QFormLayout(self.shared_sol)
        for kind in KINDS: self.path_field(sub,'sol_shared_'+kind,kind)
        body_layout.addWidget(self.shared_sol)
        self.sol_groups=QGroupBox('四组独立 SOL');sub=QFormLayout(self.sol_groups)
        for g in GROUPS:
            for kind in KINDS:self.path_field(sub,'sol_'+g+'_'+kind,g+' '+kind)
        body_layout.addWidget(self.sol_groups)
        self.separate_sol.toggled.connect(self.toggle_sol);self.toggle_sol(self.separate_sol.isChecked())
        group=QGroupBox('普通 Thru / Flush 与校准混频器');form=QFormLayout(group);body_layout.addWidget(group)
        self.path_field(form,'thru_RF','Thru 原始测量 RF / 共用（S2P）')
        self.path_field(form,'thru_IF','Thru 原始测量 IF（空则共用 RF 文件）')
        self.defined_thru=self.check(form,'使用已定义 Thru；不勾选为理想 Flush','defined_thru')
        self.path_field(form,'definition_thru_RF','Thru 定义 RF / 共用（S2P）')
        self.path_field(form,'definition_thru_IF','Thru 定义 IF（空则共用 RF 定义）')
        self.path_field(form,'cal_mixer','已表征校准混频器（S2P）')
        self.path_field(form,'cal_raw','校准混频器变频 Thru 原始测量（S2P）')
        self.defined_thru.toggled.connect(self.toggle_thru);self.toggle_thru(self.defined_thru.isChecked())
        actions=QHBoxLayout();page_layout.addLayout(actions)
        self.compute_btn=QPushButton('计算 VMC 校准误差项');self.compute_btn.setObjectName('primary');self.compute_btn.clicked.connect(self.compute)
        self.save_btn=QPushButton('保存校准包…');self.save_btn.clicked.connect(self.save)
        self.load_btn=QPushButton('载入校准包…');self.load_btn.clicked.connect(self.load)
        for b in [self.compute_btn,self.save_btn,self.load_btn]:actions.addWidget(b)
        row=QHBoxLayout();page_layout.addLayout(row)
        self.terms=QComboBox();self.terms.addItems(['尚无校准误差项']);row.addWidget(self.terms,1)
        self.show_term_btn=QPushButton('载入选中误差项到主界面');self.show_term_btn.clicked.connect(self.show_term);row.addWidget(self.show_term_btn)
        mut=QWidget();ml=QVBoxLayout(mut);self.tabs.addTab(mut,'校准 MUT')
        info=QLabel('使用刚计算或载入的校准包。原始 MUT 与校准结果同时载入主界面；S21 显示 VC21。\n'
                    'S12 未校准；导出文件中的 S12=0 为明确标记的占位，不能作为反向结果。')
        info.setWordWrap(True);ml.addWidget(info)
        self.cal_state=QLabel('尚无校准包，请先计算或载入。');self.cal_state.setWordWrap(True);ml.addWidget(self.cal_state)
        form=QFormLayout();ml.addLayout(form)
        self.path_field(form,'mut_raw','MUT 原始测量（S2P）',mut=True)
        self.mut_axis=QComboBox()
        for key,label in AXIS_MODES.items():self.mut_axis.addItem(label,key)
        self.mut_axis.setCurrentIndex(max(0,self.mut_axis.findData(self.settings.value('mut_axis','dual'))))
        self.mut_axis.currentIndexChanged.connect(self.invalidate_mut);form.addRow('MUT 原始文件横轴',self.mut_axis);self.controls.append(self.mut_axis)
        actions=QHBoxLayout();ml.addLayout(actions)
        self.mut_btn=QPushButton('校准 MUT 并载入主界面');self.mut_btn.setObjectName('primary');self.mut_btn.clicked.connect(self.compute_mut)
        self.export_btn=QPushButton('导出校准 MUT 结果包…');self.export_btn.clicked.connect(self.export)
        actions.addWidget(self.mut_btn);actions.addWidget(self.export_btn);ml.addStretch()
        self.summary=QLabel('请配置四组 SOL、普通 Thru 和校准混频器，或载入已有校准包。');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();layout.addWidget(self.progress)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        close=QPushButton('关闭');close.clicked.connect(self.reject);layout.addWidget(close)
        self.refresh_buttons()

    def path_field(self,form,key,label,mut=False):
        row=QHBoxLayout();field=QLineEdit(str(self.settings.value('path/'+key,'')));button=QPushButton('浏览…')
        row.addWidget(field,1);row.addWidget(button);form.addRow(label,row)
        button.clicked.connect(lambda checked=False,e=field:self.browse(e))
        field.textChanged.connect(self.invalidate_mut if mut else self.invalidate_cal)
        self.fields[key]=field;self.controls.extend([field,button])
        return field

    def combo(self,form,label,choices,key,default):
        c=QComboBox()
        for value,title in choices.items():c.addItem(title,value)
        c.setCurrentIndex(max(0,c.findData(self.settings.value(key,default))))
        c.currentIndexChanged.connect(self.invalidate_cal);form.addRow(label,c);self.controls.append(c);return c

    def check(self,form,label,key):
        c=QCheckBox(label);c.setChecked(self.settings.value(key,False,type=bool));form.addRow(c)
        c.toggled.connect(self.invalidate_cal);self.controls.append(c);return c

    def toggle_sol(self,independent):
        self.shared_sol.setVisible(not independent);self.sol_groups.setVisible(independent)

    def toggle_thru(self,enabled):
        for key in ['definition_thru_RF','definition_thru_IF']:self.fields[key].setEnabled(enabled)

    def invalidate_cal(self,*args):
        self.calibration=None;self.mut_result=None
        if hasattr(self,'mapping_label'):self.update_mapping()
        if hasattr(self,'summary'):self.summary.setText('校准输入已改变，请重新计算或载入校准包。');self.refresh_buttons()

    def invalidate_mut(self,*args):
        self.mut_result=None
        if hasattr(self,'summary'):self.refresh_buttons()

    def refresh_buttons(self):
        busy=self.worker is not None;cal=self.calibration is not None
        self.save_btn.setEnabled(cal and not busy);self.show_term_btn.setEnabled(cal and not busy)
        self.mut_btn.setEnabled(cal and not busy);self.export_btn.setEnabled(self.mut_result is not None and not busy)
        self.compute_btn.setEnabled(not busy);self.load_btn.setEnabled(not busy)
        if hasattr(self,'cal_state'):
            if cal:
                c=self.calibration
                self.cal_state.setText(f'当前校准：RF {c.frequency[0]/1e9:g}～{c.frequency[-1]/1e9:g} GHz；'
                    f'IF {c.if_frequency[0]/1e9:g}～{c.if_frequency[-1]/1e9:g} GHz；'
                    f'{len(c.frequency)} 点，{len(c.terms)} 项，{c.manifest["options"]["z0"]:g} Ω。')
            else:self.cal_state.setText('尚无有效校准包，请先计算或载入。')

    def update_mapping(self):
        try:
            rf=np.array([self.spins['rf_start_hz'].value(),self.spins['rf_stop_hz'].value()])*1e9
            iff=output_frequencies(rf,self.spins['lo_hz'].value()*1e9,self.conversion.currentData())
            self.mapping_label.setText(f'RF {rf[0]/1e9:g}～{rf[1]/1e9:g} GHz → IF {iff[0]/1e9:g}～{iff[1]/1e9:g} GHz；'
                f'{self.points.value()} 个配对点。导出报告保留逐点映射。')
        except ValueError as e:self.mapping_label.setText(str(e))

    def browse(self,field):
        path,_=QFileDialog.getOpenFileName(self,'选择原始测量或标准定义',self.settings.value('directory',''),'Touchstone (*.s1p *.s2p *.S1P *.S2P);;所有文件 (*)')
        if path:self.settings.setValue('directory',str(Path(path).parent));field.setText(path)

    def options(self):
        v={k:s.value()*(1e9 if k.endswith('_hz') and k!='frequency_tolerance_hz' else 1) for k,s in self.spins.items()}
        return CalibrationOptions(**v,points=self.points.value(),frequency_conversion=self.conversion.currentData(),
            standard_sampling=self.sampling.currentData(),raw_axis=self.raw_axis.currentData(),mixer_definition_axis=self.definition_axis.currentData())

    def inputs(self):
        f={k:e.text().strip() for k,e in self.fields.items()}
        s1=[f['std_P1_'+k] for k in KINDS];s2=[f['std_P2_'+k] for k in KINDS] if self.separate_std.isChecked() else s1
        sol={g:[f['sol_'+g+'_'+k] if self.separate_sol.isChecked() else f['sol_shared_'+k] for k in KINDS] for g in GROUPS}
        definitions={'RF':f['definition_thru_RF'],'IF':f['definition_thru_IF'] or f['definition_thru_RF']} if self.defined_thru.isChecked() else None
        inputs=CalibrationInputs({'P1':s1,'P2':s2},sol,{'RF':f['thru_RF'],'IF':f['thru_IF'] or f['thru_RF']},f['cal_mixer'],f['cal_raw'],definitions)
        required=s1+s2+[p for paths in sol.values() for p in paths]+list(inputs.thru_raw.values())+[inputs.calibration_mixer,inputs.cal_mixer_raw]
        if definitions:required+=list(definitions.values())
        if not all(required):raise ValueError('缺少标准定义、SOL、Thru 或校准混频器文件。')
        return inputs

    def remember(self):
        for k,e in self.fields.items():self.settings.setValue('path/'+k,e.text())
        for k,s in self.spins.items():self.settings.setValue(k,s.value())
        self.settings.setValue('points',self.points.value())
        for k,c in [('frequency_conversion',self.conversion),('standard_sampling',self.sampling),('raw_axis',self.raw_axis),('mixer_definition_axis',self.definition_axis),('mut_axis',self.mut_axis)]:self.settings.setValue(k,c.currentData())
        for k,c in [('separate_sol',self.separate_sol),('separate_std',self.separate_std),('defined_thru',self.defined_thru)]:self.settings.setValue(k,c.isChecked())

    def begin(self,fn,args,callback):
        if self.worker:return
        self.remember();self.worker=Worker(fn,args,self)
        for c in self.controls:c.setEnabled(False)
        self.refresh_buttons();self.progress.show()
        self.worker.done.connect(callback);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.finish);self.worker.start()

    def finish(self):
        self.worker.deleteLater();self.worker=None;self.progress.hide()
        for c in self.controls:c.setEnabled(True)
        self.toggle_thru(self.defined_thru.isChecked());self.refresh_buttons()

    def failed(self,message,trace):
        self.log.appendPlainText(trace);self.summary.setText('操作未完成：'+message);QMessageBox.warning(self,'VMC 校准未完成',message)

    def compute(self):
        try:inputs=self.inputs();options=self.options()
        except Exception as e:QMessageBox.warning(self,'检查输入',str(e));return
        self.invalidate_cal();self.summary.setText('正在求解 RF / IF 四组 SOL、普通 Thru 和变频 ETF…')
        self.begin(calibrate,(inputs,options),self.accept_calibration)

    def accept_calibration(self,cal):
        self.calibration=cal;self.mut_result=None;self.terms.clear();self.terms.addItems(cal.terms)
        self.terms.setCurrentText('VMC_ETF')
        self.summary.setText(f'校准完成：{len(cal.frequency)} 个 RF / IF 配对点，{len(cal.terms)} 个误差项。可校准 MUT 或保存校准包。')
        self.log.appendPlainText(self.summary.text())
        for group,d in cal.manifest['diagnostics'].items():self.log.appendPlainText(f'{group}: SOL 最大条件数 {d["max_condition"]:.6g}；残差 {d["max_SOL_residual"]:.6g}')
        self.log.appendPlainText('限制：未采集隔离 / 开关项；MUT 采用单向公式，Keysight 现场对照待验证。')
        self.refresh_buttons()

    def show_term(self):
        if self.calibration:self.generated.emit(term_dataset(self.calibration,self.terms.currentText()))

    def compute_mut(self):
        if not self.calibration:return
        path=self.fields['mut_raw'].text().strip()
        if not path:QMessageBox.warning(self,'缺少输入','请选择 MUT 原始 S2P。');return
        self.invalidate_mut();self.summary.setText('正在校准 MUT 的 S11 / S22 / VC21…')
        self.begin(calibrate_mut,(self.calibration,path,self.mut_axis.currentData()),self.accept_mut)

    def accept_mut(self,result):
        self.mut_result=result;d=result.dataset
        raw=Dataset('MUT_raw_paired','VMC raw MUT',{k:v.copy() for k,v in result.raw.items()},
            {k:v.copy() for k,v in d.axes.items()},np.zeros(d.count,int),{'S21':'未校准 SM21'},[])
        self.generated.emit(raw);self.generated.emit(d)
        self.summary.setText(f'已校准 MUT：{d.count} 点；原始响应与校准结果已载入主界面。S21 为 VC21，S12 未校准。')
        self.log.appendPlainText(self.summary.text());self.refresh_buttons()

    def save(self):
        if not self.calibration:return
        path,_=QFileDialog.getSaveFileName(self,'保存 VMC 校准包','vmc_calibration.zip','ZIP (*.zip)')
        if path:self.begin(save_calibration,(self.calibration,self.suffix(path)),lambda p:self.log.appendPlainText('已保存：'+p))

    def load(self):
        path,_=QFileDialog.getOpenFileName(self,'载入 VMC 校准包',self.settings.value('directory',''),'ZIP (*.zip)')
        if path:
            self.invalidate_cal();self.begin(load_calibration,(path,),self.accept_loaded)

    def accept_loaded(self,cal):
        o=cal.manifest['options']
        for k,s in self.spins.items():s.setValue(o[k]/(1e9 if k.endswith('_hz') and k!='frequency_tolerance_hz' else 1))
        self.points.setValue(o['points'])
        for key,c in [('frequency_conversion',self.conversion),('standard_sampling',self.sampling),('raw_axis',self.raw_axis),('mixer_definition_axis',self.definition_axis)]:c.setCurrentIndex(c.findData(o[key]))
        self.mut_axis.setCurrentIndex(self.mut_axis.findData(o['raw_axis']))
        m=cal.manifest['input_mapping']
        for port in ['P1','P2']:
            for kind,path in zip(KINDS,m['standards'][port]):self.fields['std_'+port+'_'+kind].setText(path)
        self.separate_std.setChecked(m['standards']['P1']!=m['standards']['P2'])
        self.separate_sol.setChecked(True)
        for group in GROUPS:
            for kind,path in zip(KINDS,m['sol'][group]):self.fields['sol_'+group+'_'+kind].setText(path)
        for band in ['RF','IF']:
            self.fields['thru_'+band].setText(m['thru_raw'][band])
            self.fields['definition_thru_'+band].setText((m['thru_definition'] or {}).get(band,'') or '')
        self.defined_thru.setChecked(bool(m['thru_definition']))
        self.fields['cal_mixer'].setText(m['calibration_mixer']);self.fields['cal_raw'].setText(m['cal_mixer_raw'])
        self.accept_calibration(cal);self.remember()

    def export(self):
        if not self.mut_result:return
        path,_=QFileDialog.getSaveFileName(self,'导出校准 MUT','calibrated_mut.zip','ZIP (*.zip)')
        if path:self.begin(export_mut,(self.mut_result,self.suffix(path)),lambda p:self.log.appendPlainText('已导出：'+p))

    @staticmethod
    def suffix(path):return path if path.lower().endswith('.zip') else path+'.zip'

    def reject(self):
        if self.worker:return
        self.remember();super().reject()

    def closeEvent(self,event):
        if self.worker:event.ignore()
        else:self.remember();event.accept()
