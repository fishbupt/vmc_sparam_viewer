"""VMC raw-file generation UI; all physics and file I/O live in vmc_simulation."""
from pathlib import Path
import numpy as np
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,
    QGroupBox,QLabel,QLineEdit,QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,
    QScrollArea,QWidget,QFileDialog,QMessageBox,QPlainTextEdit,QProgressBar,QSplitter,QTabWidget,QSizePolicy)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from characterize_gui import Worker
from characterization import SAMPLING_METHODS
from frequency_mapping import CONVERSION_MODES, output_frequencies
from parser import Dataset
from vmc_calibration import AXIS_MODES
from vmc_simulation import VMCSimulationOptions,MixerModel,PortModel,generate_vmc_files,RAW_NAMES

class VMCSimulationDialog(QDialog):
    generated=pyqtSignal(object)

    def __init__(self,parent=None,embedded=False):
        super().__init__(parent)
        self.embedded=embedded
        self.workbench_owner=parent if embedded else None
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle('生成 VMC 原始测量 SNP · Dummy DUT')
        self.resize(1380,920);self.setMinimumSize(1000,700)
        self.settings=QSettings('VNAAlgorithmTools','VMCDummySimulation')
        self.worker=None;self.result=None;self.controls=[];self.parameters={};self.models={};self.file_fields={};self.file_buttons={}
        layout=QVBoxLayout(self)
        intro=QLabel('生成 OPEN / SHORT / LOAD / THRU / CalTHRU / MUT 六个原始 S2P，附标准定义、无噪声真值与误差项。\n'
            '默认 RF 10～20 GHz、LO 20 GHz、IF 30～40 GHz；理想 SOL + 零延迟 Flush Thru。MUT S12 真值为零。')
        intro.setWordWrap(True);layout.addWidget(intro)
        split=QSplitter(Qt.Orientation.Horizontal);split.setChildrenCollapsible(False);layout.addWidget(split,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(450)
        panel=QWidget();left=QVBoxLayout(panel);scroll.setWidget(panel);split.addWidget(scroll)
        defaults=VMCSimulationOptions()
        group=QGroupBox('VMC 配置');form=QFormLayout(group);left.addWidget(group)
        for key,label,factor,low,high in [('rf_start_hz','RF 起点 (GHz)',1e9,.000001,1000),
            ('rf_stop_hz','RF 终点 (GHz)',1e9,.000001,1000),('lo_hz','固定 LO (GHz)',1e9,.000001,1000),
            ('z0','参考阻抗 (Ω)',1,.001,10000),('frequency_tolerance_hz','频点容差 (Hz)',1,0,1e6)]:
            spin=self.number(key,getattr(defaults,key)/factor,low,high);self.parameters[key]=(spin,factor);form.addRow(label,spin)
        spin=self.integer('points',defaults.points,2,200001);self.parameters['points']=(spin,1);form.addRow('RF 扫频点数',spin)
        self.conversion=self.combo('frequency_conversion',CONVERSION_MODES,'up');form.addRow('变频方向',self.conversion)
        self.mapping=QLabel();self.mapping.setWordWrap(True);form.addRow('自动 IF',self.mapping)
        self.raw_axis=self.combo('raw_axis',AXIS_MODES,'dual');form.addRow('CalTHRU / MUT 横轴',self.raw_axis)
        self.sampling=self.combo('standard_sampling',SAMPLING_METHODS,'cubic_ri');form.addRow('定义插值（禁止外推）',self.sampling)
        group=QGroupBox('标准件定义：OPEN / SHORT / LOAD / THRU');form=QFormLayout(group);left.addWidget(group)
        self.import_sol=self.check('import_sol','导入三个实际 SOL S1P；否则理想 +1 / −1 / 0');form.addRow(self.import_sol)
        for k in ('open','short','load'):self.file_row(form,k,k.upper()+' S1P','S1P (*.s1p *.S1P)')
        self.import_thru=self.check('import_thru','导入 THRU S2P；否则零延迟 / 零损耗 Flush');form.addRow(self.import_thru)
        self.file_row(form,'thru','THRU S2P','S2P (*.s2p *.S2P)')
        note=QLabel('输出标准定义与本轮原始测量配套。Keysight 和自研校准均需使用这些定义，不能套用机械校准套默认偏移。')
        note.setWordWrap(True);form.addRow(note)
        group=QGroupBox('已表征的校准混频器');form=QFormLayout(group);left.addWidget(group)
        self.import_cal=self.check('import_cal','导入已表征 S2P；否则使用下面的互易模型');form.addRow(self.import_cal)
        self.file_row(form,'calibration_mixer','校准混频器 S2P','S2P (*.s2p *.S2P)')
        self.definition_axis=self.combo('mixer_definition_axis',{'rf':'RF 横轴','if':'IF 横轴'},'rf');form.addRow('导入表征横轴',self.definition_axis)
        tabs=QTabWidget();tabs.setUsesScrollButtons(True);left.addWidget(tabs)
        for name,label,model in [('calibration_mixer','校准混频器',defaults.calibration_mixer),('mut','MUT（S12=0）',defaults.mut),
                                 ('port1','Port1 误差盒',defaults.port1),('port2','Port2 误差盒',defaults.port1)]:
            page=QWidget();grid=QGridLayout(page);tabs.addTab(page,label);self.models[name]={}
            prefixes=('s11','s22','transmission') if isinstance(model,MixerModel) else ('edf','esf','tracking')
            for col,text in enumerate(('参数','幅度 dB','起点相位 °','时延 ps')):grid.addWidget(QLabel(text),0,col)
            for row,prefix in enumerate(prefixes,1):
                label={'transmission':'S21=S12' if name=='calibration_mixer' else 'VC21','tracking':'单程 t','edf':'EDF','esf':'ESF'}.get(prefix,prefix.upper())
                grid.addWidget(QLabel(label),row,0)
                for col,suffix in enumerate(('db','phase_deg','delay_ps'),1):
                    key=prefix+'_'+suffix;high=40 if prefix in ('transmission','tracking') else -.000001
                    lo,hi=(-300,high) if suffix=='db' else (-1e6,1e6)
                    spin=self.number('model/'+name+'/'+key,getattr(model,key),lo,hi)
                    spin.setMinimumWidth(90);spin.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
                    self.models[name][key]=spin;grid.addWidget(spin,row,col)
        self.separate_port2=self.check('separate_port2','Port2 使用独立误差盒；否则与 Port1 相同');left.addWidget(self.separate_port2)
        note=QLabel('混频器相位以 RF 起点为参考；端口误差盒以实际物理频率计算，参考频率同为 RF 起点。\n'
            '单程 t 对应 ERF=t²；校准混频器互易，MUT 固定单向模型。')
        note.setWordWrap(True);left.addWidget(note)
        group=QGroupBox('原始测量噪声');form=QFormLayout(group);left.addWidget(group)
        self.noise=self.check('noise_enabled','启用复高斯加性噪声；定义和真值不加噪声');form.addRow(self.noise)
        spin=self.number('noise_floor_db',defaults.noise_floor_db,-300,0);self.parameters['noise_floor_db']=(spin,1);form.addRow('复数 RMS (dB，参考 S=1)',spin)
        for key,label,low,high in [('noise_seed','随机种子',0,2**31-1),('noise_averages','等效平均次数',1,10000)]:
            spin=self.integer(key,getattr(defaults,key),low,high);self.parameters[key]=(spin,1);form.addRow(label,spin)
        note=QLabel('σ=10^(dB/20)/√N；各采集独立；双频段复制相同噪声数据。非 dBm / IFBW 模型。')
        note.setWordWrap(True);form.addRow(note)
        group=QGroupBox('输出父目录');form=QFormLayout(group);left.addWidget(group)
        self.directory=QLineEdit(str(self.settings.value('output_parent','')));self.directory.textChanged.connect(self.invalidate)
        btn=QPushButton('选择目录…');btn.clicked.connect(self.browse_output);row=QHBoxLayout();row.addWidget(self.directory);row.addWidget(btn);form.addRow(row);self.controls.extend((self.directory,btn))
        left.addStretch()
        right=QWidget();content=QVBoxLayout(right);split.addWidget(right);split.setSizes([600,780]);split.setStretchFactor(1,1)
        self.figure=Figure(layout='constrained',facecolor='white');self.canvas=FigureCanvasQTAgg(self.figure)
        content.addWidget(NavigationToolbar2QT(self.canvas,self));content.addWidget(self.canvas,1)
        self.summary=QLabel('设置参数和输出目录后生成。每次创建独立 vmc_dummy_… 子目录。');self.summary.setWordWrap(True);content.addWidget(self.summary)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(110);content.addWidget(self.log)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.run_btn=QPushButton('生成 VMC 原始测量 SNP');self.run_btn.setObjectName('primary');self.run_btn.clicked.connect(self.compute);actions.addWidget(self.run_btn)
        self.calibrate_btn=QPushButton('将本轮文件载入 VMC 校准窗口');self.calibrate_btn.clicked.connect(self.open_calibration);self.calibrate_btn.setEnabled(False);actions.addWidget(self.calibrate_btn)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();actions.addWidget(self.progress)
        close=QPushButton('关闭');close.clicked.connect(self.reject);actions.addWidget(close)
        if embedded:close.hide();self.setMinimumSize(0,0)
        for c in (self.import_sol,self.import_thru,self.import_cal,self.noise,self.separate_port2):c.toggled.connect(self.update_controls)
        self.update_mapping();self.update_controls()

    def number(self,key,default,lo,hi):
        spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(6 if key.startswith('model/') else 9);spin.setValue(float(self.settings.value(key,default)))
        spin.valueChanged.connect(self.invalidate);self.controls.append(spin);return spin

    def integer(self,key,default,lo,hi):
        spin=QSpinBox();spin.setRange(lo,hi);spin.setValue(int(self.settings.value(key,default)))
        spin.valueChanged.connect(self.invalidate);self.controls.append(spin);return spin

    def combo(self,key,choices,default):
        c=QComboBox()
        c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(12)
        for value,label in choices.items():c.addItem(label,value)
        c.setCurrentIndex(max(0,c.findData(self.settings.value(key,default))))
        c.currentIndexChanged.connect(self.invalidate);self.controls.append(c);return c

    def check(self,key,label):
        c=QCheckBox(label);c.setChecked(self.settings.value(key,False,type=bool));c.toggled.connect(self.invalidate);self.controls.append(c);return c

    def file_row(self,form,key,label,filter):
        field=QLineEdit(str(self.settings.value('path/'+key,'')));field.setMinimumWidth(100);field.textChanged.connect(self.invalidate)
        btn=QPushButton('浏览…');btn.clicked.connect(lambda checked=False:self.browse(field,filter))
        row=QHBoxLayout();row.addWidget(field);row.addWidget(btn);form.addRow(label,row)
        self.file_fields[key]=field;self.file_buttons[key]=btn;self.controls.extend((field,btn))

    def browse(self,field,filter):
        path,_=QFileDialog.getOpenFileName(self,'选择实际定义',self.settings.value('directory',''),filter)
        if path:self.settings.setValue('directory',str(Path(path).parent));field.setText(path)

    def browse_output(self):
        path=QFileDialog.getExistingDirectory(self,'选择输出父目录',self.directory.text())
        if path:self.directory.setText(path)

    def invalidate(self,*args):
        self.result=None
        if hasattr(self,'calibrate_btn'):
            self.calibrate_btn.setEnabled(False);self.summary.setText('配置已改变，请重新生成；已保存文件保留。')
            self.figure.clear();self.canvas.draw_idle()
        if hasattr(self,'mapping'):self.update_mapping()

    def update_mapping(self):
        try:
            rf=[self.parameters[k][0].value()*1e9 for k in ('rf_start_hz','rf_stop_hz')]
            iff=output_frequencies(rf,self.parameters['lo_hz'][0].value()*1e9,self.conversion.currentData())
            self.mapping.setText(f'IF {iff[0]/1e9:g}～{iff[-1]/1e9:g} GHz')
        except ValueError as e:self.mapping.setText(str(e))

    def update_controls(self,*args):
        if self.worker:return
        for k,active in [('open',self.import_sol.isChecked()),('short',self.import_sol.isChecked()),('load',self.import_sol.isChecked()),
                         ('thru',self.import_thru.isChecked()),('calibration_mixer',self.import_cal.isChecked())]:
            self.file_fields[k].setEnabled(active);self.file_buttons[k].setEnabled(active)
        self.definition_axis.setEnabled(self.import_cal.isChecked())
        for spin in self.models['calibration_mixer'].values():spin.setEnabled(not self.import_cal.isChecked())
        for spin in self.models['port2'].values():spin.setEnabled(self.separate_port2.isChecked())
        for key in ('noise_floor_db','noise_seed','noise_averages'):self.parameters[key][0].setEnabled(self.noise.isChecked())

    def options(self):
        v={k:spin.value()*factor for k,(spin,factor) in self.parameters.items()}
        for key in ('points','noise_seed','noise_averages'):v[key]=int(v[key])
        model=lambda name,cls:cls(**{k:s.value() for k,s in self.models[name].items()})
        return VMCSimulationOptions(**v,frequency_conversion=self.conversion.currentData(),raw_axis=self.raw_axis.currentData(),
            standard_sampling=self.sampling.currentData(),noise_enabled=self.noise.isChecked(),
            calibration_mixer=model('calibration_mixer',MixerModel),mut=model('mut',MixerModel),
            port1=model('port1',PortModel),port2=model('port2',PortModel) if self.separate_port2.isChecked() else None)

    def remember(self):
        for k,(spin,_) in self.parameters.items():self.settings.setValue(k,spin.value())
        for name,model in self.models.items():
            for k,s in model.items():self.settings.setValue('model/'+name+'/'+k,s.value())
        for k,e in self.file_fields.items():self.settings.setValue('path/'+k,e.text())
        for k,c in [('frequency_conversion',self.conversion),('raw_axis',self.raw_axis),('standard_sampling',self.sampling),('mixer_definition_axis',self.definition_axis)]:self.settings.setValue(k,c.currentData())
        for k,c in [('import_sol',self.import_sol),('import_thru',self.import_thru),('import_cal',self.import_cal),('separate_port2',self.separate_port2),('noise_enabled',self.noise)]:self.settings.setValue(k,c.isChecked())
        self.settings.setValue('output_parent',self.directory.text())

    def compute(self):
        if self.worker:return
        standard_paths=[self.file_fields[k].text().strip() for k in ('open','short','load')] if self.import_sol.isChecked() else None
        thru=self.file_fields['thru'].text().strip() if self.import_thru.isChecked() else None
        cal=self.file_fields['calibration_mixer'].text().strip() if self.import_cal.isChecked() else None
        if not self.directory.text().strip() or (standard_paths is not None and not all(standard_paths)) or (self.import_thru.isChecked() and not thru) or (self.import_cal.isChecked() and not cal):
            QMessageBox.warning(self,'缺少输入','请选择输出目录，并填写启用导入的所有标准定义。');return
        o=self.options();self.remember();self.invalidate()
        for c in self.controls:c.setEnabled(False)
        self.run_btn.setEnabled(False);self.progress.show();self.summary.setText('正在计算正向波量响应并生成文件…')
        self.worker=Worker(generate_vmc_files,(self.directory.text().strip(),o,standard_paths,thru,cal,self.definition_axis.currentData()),self)
        self.worker.done.connect(self.accept_result);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.finish);self.worker.start()

    def accept_result(self,result):
        self.result=result;s=result.simulation;o=s.options
        self.summary.setText(f'已生成六个原始 S2P，附 SOL / THRU 定义、校准混频器与 MUT 真值、21 个误差项和报告。\n'
            f'RF {s.frequency[0]/1e9:g}～{s.frequency[-1]/1e9:g} GHz → IF {s.if_frequency[0]/1e9:g}～{s.if_frequency[-1]/1e9:g} GHz；{o.points} 点。\n'
            f'THRU：'+('导入实际 S2P' if self.import_thru.isChecked() else '理想 Flush，零延迟 / 零损耗')+f'；输出：{result.directory}')
        self.log.appendPlainText(self.summary.text());self.log.appendPlainText('\n'.join(s.manifest['warnings']))
        self.figure.clear();axes=self.figure.subplots(2,1);f=s.frequency/1e9
        target=s.if_frequency if o.raw_axis=='if' else s.frequency
        idx=np.searchsorted(s.mixed_frequency,target);raw=s.raw['mut_raw.s2p'][idx,1,0];truth=s.mut.s['S21']
        for z,label,color in [(truth,'MUT truth VC21','#2563eb'),(raw,'MUT raw SM21','#d97706')]:
            axes[0].plot(f,20*np.log10(abs(z)),label=label,color=color)
            axes[1].plot(f,np.rad2deg(np.unwrap(np.angle(z))),label=label,color=color)
        axes[0].set_ylabel('Magnitude (dB)');axes[1].set_ylabel('Unwrapped phase (deg)')
        for ax in axes:ax.set_xlabel('RF (GHz)');ax.grid(alpha=.25);ax.legend(fontsize=9)
        self.canvas.draw_idle();self.generated.emit(s.mut)
        c=s.raw['mut_raw.s2p'][idx]
        self.generated.emit(Dataset('mut_raw.s2p','S2P / VMC simulated raw',
            {'S11':c[:,0,0].copy(),'S21':c[:,1,0].copy(),'S12':c[:,0,1].copy(),'S22':c[:,1,1].copy()},
            {k:v.copy() for k,v in s.mut.axes.items()},np.zeros(len(f),int),
            {'参考阻抗':f'{o.z0:g} Ω','频率轴':'RF（由生成配置映射）'},[]))

    def finish(self):
        self.worker.deleteLater();self.worker=None;self.progress.hide()
        for c in self.controls:c.setEnabled(True)
        self.run_btn.setEnabled(True);self.calibrate_btn.setEnabled(self.result is not None);self.update_controls()

    def failed(self,message,trace):
        self.log.appendPlainText(trace);self.summary.setText('生成失败：'+message);QMessageBox.warning(self,'生成未完成',message)

    def open_calibration(self):
        if not self.result or self.worker:return
        if self.embedded:
            self.workbench_owner.workspace.use_generated_files(self.result);return
        from vmc_calibration_gui import VMCCalibrationDialog
        dialog=VMCCalibrationDialog(self);dialog.set_generated_files(self.result);dialog.generated.connect(self.generated.emit);dialog.exec()

    def reject(self):
        if self.embedded:return
        if not self.worker:super().reject()
    def closeEvent(self,event):
        if self.worker:event.ignore()
        else:super().closeEvent(event)
