"""Simulation controls, threaded generation and preview; model lives in simulation.py."""
from pathlib import Path
from dataclasses import fields
import traceback
import numpy as np
from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,
    QGroupBox,QLabel,QLineEdit,QPushButton,QComboBox,QDoubleSpinBox,QSpinBox,
    QCheckBox,QScrollArea,QWidget,QFileDialog,QMessageBox,QPlainTextEdit,QProgressBar,QSplitter)
from PyQt6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from characterize_gui import Worker, CharacterizeDialog
from characterization import SAMPLING_METHODS
from simulation import SimulationOptions, generate_files
from frequency_mapping import CONVERSION_MODES

class SimulationDialog(QDialog):
    generated=pyqtSignal(object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('生成 SOL 仿真文件与 Mixer 真值 · v1.5')
        self.resize(1380,900)
        self.settings=QSettings('VNAAlgorithmTools','MixerSimulation')
        self.kit_settings=QSettings('VNAAlgorithmTools','MixerCharacterization')
        self.worker=None;self.result=None;self.controls=[];self.parameters={}
        layout=QVBoxLayout(self)
        intro=QLabel('基于共用 OPEN / SHORT / LOAD 定义生成六个原始测量 S2P 和无噪声 Mixer.s2p。\n'
            '固定 LO、可选 IF=RF−LO 下变频 / IF=RF+LO 上变频、互易模型；六个测量文件仅 S11 有效。相位参数以 RF 起点为参考。')
        intro.setWordWrap(True);layout.addWidget(intro)
        splitter=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(splitter,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(580)
        panel=QWidget();left=QVBoxLayout(panel);scroll.setWidget(panel);splitter.addWidget(scroll)
        kit=QGroupBox('共用校准套（实际标准定义 S1P）');grid=QGridLayout(kit);left.addWidget(kit)
        self.standards=[]
        for i,kind in enumerate(('OPEN','SHORT','LOAD')):
            field=QLineEdit(str(self.settings.value('kit/'+kind.lower(),self.kit_settings.value('kit/'+kind.lower(),''))))
            field.textChanged.connect(self.invalidate)
            btn=QPushButton('浏览…');btn.clicked.connect(lambda checked=False,e=field:self.browse_standard(e))
            grid.addWidget(QLabel(kind),i,0);grid.addWidget(field,i,1);grid.addWidget(btn,i,2)
            self.standards.append(field);self.controls.extend((field,btn))
        reuse=QPushButton('复用表征窗口最近使用的三个标准件');reuse.clicked.connect(self.reuse_kit)
        grid.addWidget(reuse,3,0,1,3);self.controls.append(reuse)
        defaults=SimulationOptions()
        sweep=QGroupBox('扫频与标准求值');form=QFormLayout(sweep);left.addWidget(sweep)
        for name,label,factor,low,high,dec in [
            ('rf_start_hz','RF 起点 (GHz)',1e9,.000001,1000,9),
            ('rf_stop_hz','RF 终点 (GHz)',1e9,.000001,1000,9),
            ('lo_hz','固定 LO (GHz)',1e9,.000001,1000,9),
            ('frequency_tolerance_hz','频率容差 (Hz)',1,0,1e6,6)]:
            box=self.number(name,getattr(defaults,name)/factor,low,high,dec)
            self.parameters[name]=(box,factor);form.addRow(label,box)
        points=self.integer('points',defaults.points,2,200001);self.parameters['points']=(points,1);form.addRow('线性扫频点数',points)
        self.conversion=QComboBox()
        for mode,label in CONVERSION_MODES.items():self.conversion.addItem(label,mode)
        self.conversion.setCurrentIndex(max(0,self.conversion.findData(self.settings.value('frequency_conversion','down'))))
        self.conversion.currentIndexChanged.connect(self.invalidate);self.controls.append(self.conversion)
        form.addRow('IF 相对 RF 的变频方向',self.conversion)
        self.sampling=QComboBox()
        for name,label in SAMPLING_METHODS.items():self.sampling.addItem(label,name)
        saved_sampling=self.settings.value('standard_sampling','cubic_ri')
        if saved_sampling not in SAMPLING_METHODS:saved_sampling='cubic_ri'
        self.sampling.setCurrentIndex(self.sampling.findData(saved_sampling))
        self.sampling.currentIndexChanged.connect(self.invalidate);self.controls.append(self.sampling)
        form.addRow('标准件插值（禁止外推）',self.sampling)
        model=QGroupBox('幅相模型：幅度固定，相位随频率按时延变化');grid=QGridLayout(model);left.addWidget(model)
        for c,label in enumerate(('参数','幅度 (dB)','起点相位 (°)','时延 (ps)')):grid.addWidget(QLabel(label),0,c)
        for row,(prefix,label) in enumerate([('s11','Mixer S11'),('s22','Mixer S22'),('transmission','Mixer S21=S12'),('edf','EDF 方向性'),('esf','ESF 源匹配'),('erf','ERF 反射跟踪')],1):
            grid.addWidget(QLabel(label),row,0)
            for column,(suffix,low,high,dec) in enumerate([('db',-300,-.000001 if prefix in ('s11','s22','edf','esf') else 40,6),('phase_deg',-36000,36000,6),('delay_ps',-1e6,1e6,6)],1):
                name=prefix+'_'+suffix;box=self.number(name,getattr(defaults,name),low,high,dec)
                self.parameters[name]=(box,1);grid.addWidget(box,row,column)
        note=QLabel('ERF 是复数反射跟踪误差项，不是误差盒的单程 S21。\nMixer.s2p 表示有效变频系数，普通 S2P 本身不执行频率转换。')
        note.setWordWrap(True);left.addWidget(note)
        noise=QGroupBox('基线噪声：各频点 / 各 SOL 状态独立');form=QFormLayout(noise);left.addWidget(noise)
        self.noise=QCheckBox('启用复高斯加性噪声（仅六个测量文件）')
        saved=self.settings.value('noise_enabled',False)
        self.noise.setChecked(saved is True or str(saved).lower()=='true')
        self.noise.toggled.connect(self.invalidate);self.noise.toggled.connect(self.update_noise_controls);self.controls.append(self.noise)
        form.addRow(self.noise)
        box=self.number('noise_floor_db',defaults.noise_floor_db,-300,0,6);self.parameters['noise_floor_db']=(box,1);form.addRow('复数 RMS 噪声底 (dB，参考 S=1)',box)
        box=self.integer('noise_seed',defaults.noise_seed,0,2**31-1);self.parameters['noise_seed']=(box,1);form.addRow('随机种子',box)
        box=self.integer('noise_averages',defaults.noise_averages,1,10000);self.parameters['noise_averages']=(box,1);form.addRow('等效复数平均次数',box)
        note=QLabel('σ=10^(噪声底/20)/√平均次数；I/Q 标准差各为 σ/√2。\n无 IFBW 或功率标定依赖，不代表仪器 dBm 噪声底。')
        note.setWordWrap(True);form.addRow(note)
        target=QGroupBox('输出目录');form=QFormLayout(target);left.addWidget(target)
        self.directory=QLineEdit(str(self.settings.value('output_parent','')));self.directory.textChanged.connect(self.invalidate)
        btn=QPushButton('选择目录…');btn.clicked.connect(self.browse_output)
        row=QHBoxLayout();row.addWidget(self.directory);row.addWidget(btn);form.addRow(row);self.controls.extend((self.directory,btn))
        note=QLabel('每次在所选目录创建独立 vmc_sim_… 子目录，保留七个 S2P、三个标准副本及真值/噪声记录。')
        note.setWordWrap(True);form.addRow(note);left.addStretch()
        right=QWidget();right_layout=QVBoxLayout(right);splitter.addWidget(right);splitter.setStretchFactor(1,1)
        self.figure=Figure(figsize=(8,6),layout='constrained');self.canvas=FigureCanvasQTAgg(self.figure)
        right_layout.addWidget(NavigationToolbar2QT(self.canvas,self));right_layout.addWidget(self.canvas,1)
        self.summary=QLabel('选择校准套、参数与输出目录，点击“生成文件”。');self.summary.setWordWrap(True);self.summary.setMinimumHeight(84);right_layout.addWidget(self.summary)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(130);right_layout.addWidget(self.log)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.run_btn=QPushButton('生成七个 S2P 文件');self.run_btn.setObjectName('primary');self.run_btn.clicked.connect(self.compute)
        self.characterize_btn=QPushButton('将本轮文件载入表征窗口');self.characterize_btn.clicked.connect(self.open_characterization);self.characterize_btn.setEnabled(False)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide()
        close=QPushButton('关闭');close.clicked.connect(self.reject)
        for widget in (self.run_btn,self.characterize_btn,self.progress,close):actions.addWidget(widget)
        self.update_noise_controls()

    def number(self,name,default,low,high,dec):
        box=QDoubleSpinBox();box.setRange(low,high);box.setDecimals(dec);box.setValue(float(self.settings.value(name,default)))
        box.valueChanged.connect(self.invalidate);self.controls.append(box);return box

    def integer(self,name,default,low,high):
        box=QSpinBox();box.setRange(low,high);box.setValue(int(self.settings.value(name,default)))
        box.valueChanged.connect(self.invalidate);self.controls.append(box);return box

    def invalidate(self,*args):
        self.result=None
        if hasattr(self,'characterize_btn'):
            self.characterize_btn.setEnabled(False)
            self.summary.setText('配置已改变，请重新生成；已保存的文件保留。')
            self.figure.clear();self.canvas.draw_idle()

    def update_noise_controls(self,*args):
        if self.worker:return
        for name in ('noise_floor_db','noise_seed','noise_averages'):
            if name in self.parameters:self.parameters[name][0].setEnabled(self.noise.isChecked())

    def browse_standard(self,field):
        path,_=QFileDialog.getOpenFileName(self,'选择标准件定义',self.settings.value('directory',''),'S1P (*.s1p *.S1P);;所有文件 (*)')
        if path:self.settings.setValue('directory',str(Path(path).parent));field.setText(path)

    def reuse_kit(self):
        for kind,field in zip(('open','short','load'),self.standards):field.setText(str(self.kit_settings.value('kit/'+kind,'')))

    def browse_output(self):
        path=QFileDialog.getExistingDirectory(self,'选择仿真输出父目录',self.directory.text())
        if path:self.directory.setText(path)

    def options(self):
        values={name:box.value()*factor for name,(box,factor) in self.parameters.items()}
        for name in ('points','noise_seed','noise_averages'):values[name]=int(values[name])
        return SimulationOptions(**values,standard_sampling=self.sampling.currentData(),noise_enabled=self.noise.isChecked(),frequency_conversion=self.conversion.currentData())

    def compute(self):
        if self.worker:return
        paths=[e.text().strip() for e in self.standards];parent=self.directory.text().strip()
        if not all(paths) or not parent:
            QMessageBox.warning(self,'缺少输入','请选择 OPEN、SHORT、LOAD 三个 S1P 和输出目录。');return
        self.invalidate();opts=self.options()
        for name,(box,factor) in self.parameters.items():self.settings.setValue(name,box.value())
        self.settings.setValue('standard_sampling',opts.standard_sampling);self.settings.setValue('noise_enabled',opts.noise_enabled)
        self.settings.setValue('frequency_conversion',opts.frequency_conversion)
        self.settings.setValue('output_parent',parent)
        for kind,path in zip(('open','short','load'),paths):self.settings.setValue('kit/'+kind,path)
        for c in self.controls:c.setEnabled(False)
        self.run_btn.setEnabled(False);self.progress.show();self.summary.setText('正在求标准值并生成正向响应、噪声和文件…')
        self.worker=Worker(generate_files,(paths,parent,opts),self)
        self.worker.done.connect(self.accept_result);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.finish);self.worker.start()

    def accept_result(self,result):
        self.result=result
        sim=result.simulation
        self.summary.setText(f'已生成 {sim.truth.count} 点、七个 S2P 文件。\n输出：{result.directory}\n'
            f'{CONVERSION_MODES[sim.manifest["frequency_conversion"]]}；IF {sim.truth.axes["OutputFreq"][0]/1e9:g}～{sim.truth.axes["OutputFreq"][-1]/1e9:g} GHz\n'
            f'实际复数噪声 RMS：{sim.manifest["noise"]["effective_complex_rms"]:.6g}；Mixer.s2p 保留无噪声真值。')
        self.log.appendPlainText(self.summary.text())
        self.log.appendPlainText('\n'.join(sim.manifest['warnings']))
        f=sim.frequency/1e9
        axes=self.figure.subplots(2,2)
        for name in ('S11','S21','S22'):
            z=sim.truth.s[name]
            axes[0,0].plot(f,20*np.log10(abs(z)),label=name)
            axes[0,1].plot(f,np.rad2deg(np.unwrap(np.angle(z))),label=name)
        axes[0,0].set_title('Mixer truth magnitude (S12 = S21)');axes[0,0].set_ylabel('dB')
        axes[0,1].set_title('Mixer truth unwrapped phase');axes[0,1].set_ylabel('Degree')
        for ax,offset,title in [(axes[1,0],0,'Input SOL measured / clean'),(axes[1,1],3,'Mixer SOL measured / clean')]:
            for j,(kind,color) in enumerate(zip(('Open','Short','Load'),('tab:red','tab:blue','tab:green'))):
                with np.errstate(divide='ignore'):
                    ax.plot(f,20*np.log10(abs(sim.measured[:,offset+j])),color=color,label=kind)
                    ax.plot(f,20*np.log10(abs(sim.clean[:,offset+j])),color=color,ls='--',alpha=.55)
            ax.set_title(title);ax.set_ylabel('S11 (dB)')
        for ax in axes.flat:ax.set_xlabel('RF (GHz)');ax.grid(alpha=.25);ax.legend(fontsize=8)
        self.canvas.draw_idle();self.generated.emit(sim.truth)

    def failed(self,message,trace):
        self.log.appendPlainText(trace);self.summary.setText('生成失败：'+message);QMessageBox.warning(self,'生成未完成',message)

    def finish(self):
        self.worker.deleteLater();self.worker=None;self.progress.hide()
        for c in self.controls:c.setEnabled(True)
        self.run_btn.setEnabled(True);self.characterize_btn.setEnabled(self.result is not None);self.update_noise_controls()

    def open_characterization(self):
        if self.result is None or self.worker:return
        result=self.result;dialog=CharacterizeDialog(self)
        for field,path in zip(dialog.measurements,result.measurement_paths):field.setText(str(path))
        for field,path in zip(dialog.standards,result.standard_paths):field.setText(str(path))
        dialog.lo.setValue(result.simulation.manifest['options']['lo_hz']/1e9)
        dialog.conversion.setCurrentIndex(dialog.conversion.findData(result.simulation.manifest['frequency_conversion']))
        dialog.sampling.setCurrentIndex(dialog.sampling.findData(result.simulation.manifest['standard_sampling']))
        dialog.tol.setValue(result.simulation.manifest['options']['frequency_tolerance_hz'])
        dialog.second.setCurrentIndex(dialog.second.findData('raw'))
        # Choose the known simulated truth's global sign, not a fit to measured data.
        dialog.sign.setCurrentIndex(dialog.sign.findData(result.simulation.manifest['truth_reference_root_sign']))
        dialog.generated.connect(self.generated.emit)
        dialog.exec()

    def reject(self):
        if not self.worker:super().reject()
    def closeEvent(self,event):
        if self.worker:event.ignore()
        else:super().closeEvent(event)
