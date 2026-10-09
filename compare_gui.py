from pathlib import Path
import traceback
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QDoubleSpinBox,
 QPushButton,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QTabWidget,QWidget,QAbstractItemView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from comparison import compare,stats,export_comparison
from parser import PARAMS

METRICS=['幅度差 (dB)','相位差 (°)','复数差模值','实部差','虚部差','幅度叠加 (dB)']
YLABELS=['Delta magnitude (dB)','Wrapped delta phase (deg)','Abs(A - B)','Delta real','Delta imaginary','Magnitude (dB)']
class Work(QThread):
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
    def __init__(self,fn,*args):
        super().__init__(); self.fn=fn; self.args=args
    def run(self):
        try: self.done.emit(self.fn(*self.args))
        except Exception: self.failed.emit(traceback.format_exc())

class CompareDialog(QDialog):
    def __init__(self,datasets,parent=None,general=False):
        super().__init__(parent)
        self.setWindowTitle('任意表征文件比较 · A − B' if general else '同名 S2P / S2PX 比较')
        self.resize(1250,900)
        self.result=None; self.worker=None
        self.pairs=[]
        for a in datasets:
            if not a.kind.startswith('S2P /'): continue
            for b in datasets:
                if a is b: continue
                if general:
                    if b.kind.startswith(('S2P /', 'S2PX')): self.pairs.append((a,b))
                elif b.kind.startswith('S2PX') and Path(a.name).stem.casefold()==Path(b.name).stem.casefold():
                    self.pairs.append((a,b))
        box=QVBoxLayout(self)
        box.addWidget(QLabel('差值 = A − B（A 为左侧 S2P，B 为右侧文件）；相位差归一到 [−180°, 180°)。仅比较唯一匹配频点，不插值。'))
        self.pair=QComboBox()
        for a,b in self.pairs: self.pair.addItem(f'A: {a.name}  →  B: {b.name}')
        box.addWidget(self.pair)
        options=QHBoxLayout(); box.addLayout(options)
        options.addWidget(QLabel('S2P Stimulus 对齐到'))
        self.axis=QComboBox(); options.addWidget(self.axis)
        options.addWidget(QLabel('绝对容差 (Hz)'))
        self.tol=QDoubleSpinBox(); self.tol.setDecimals(6); self.tol.setRange(0,1e9); self.tol.setValue(.001)
        options.addWidget(self.tol)
        self.run=QPushButton('计算差异'); options.addWidget(self.run)
        self.metric=QComboBox(); self.metric.addItems(METRICS); options.addWidget(self.metric)
        self.save=QPushButton('导出差异 CSV'); self.save.setEnabled(False); options.addWidget(self.save)
        self.summary=QLabel('选择频率轴后计算。请确认 A 的 RF/Stimulus 与 B 所选频率轴具有相同物理含义。')
        self.summary.setWordWrap(True); box.addWidget(self.summary)
        self.tabs=QTabWidget(); box.addWidget(self.tabs,1)
        chart=QWidget(); layout=QVBoxLayout(chart)
        self.fig=Figure(layout='constrained',facecolor='white'); self.axes=self.fig.subplots(2,2).ravel()
        self.canvas=FigureCanvasQTAgg(self.fig); self.toolbar=NavigationToolbar2QT(self.canvas,self)
        layout.addWidget(self.toolbar); layout.addWidget(self.canvas)
        self.tabs.addTab(chart,'差异曲线 / 叠加')
        self.table=QTableWidget(4,10)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(['参数','max |ΔdB|','RMS ΔdB','max |Δφ| (°)','RMS Δφ (°)','max |Δcomplex|','RMS |Δcomplex|','max |ΔRe|','max |ΔIm|','有效幅相点'])
        self.tabs.addTab(self.table,'误差统计')
        self.pair.currentIndexChanged.connect(self.set_pair)
        self.axis.currentIndexChanged.connect(self.invalidate)
        self.tol.valueChanged.connect(self.invalidate)
        self.run.clicked.connect(self.compute)
        self.metric.currentIndexChanged.connect(self.plot)
        self.save.clicked.connect(self.export)
        self.set_pair()

    def set_pair(self,*args):
        self.axis.blockSignals(True); self.axis.clear()
        if self.pairs:
            for key in self.pairs[self.pair.currentIndex()][1].axes: self.axis.addItem(key)
        self.axis.blockSignals(False)
        self.invalidate()
        self.run.setEnabled(bool(self.pairs))
        if not self.pairs: self.summary.setText('没有可比较的文件对。请先在主界面打开两份文件（A须为S2P）；同名模式需S2P/S2PX主名相同。')

    def invalidate(self,*args):
        self.result=None; self.save.setEnabled(False)
        self.table.clearContents()
        self.summary.setText('设置已改变，请点击“计算差异”。请确认所选频率轴对应 A 的 RF/Stimulus。')
        self.plot()

    def begin(self,fn,args,callback):
        if self.worker: return
        for w in (self.run,self.pair,self.axis,self.tol,self.save): w.setEnabled(False)
        self.worker=Work(fn,*args)
        self.worker.done.connect(callback)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finish)
        self.worker.start()

    def failed(self,msg):
        self.summary.setText('操作失败，请检查频率轴与容差。')
        QMessageBox.warning(self,'操作失败',msg)

    def finish(self):
        self.worker.deleteLater(); self.worker=None
        for w in (self.run,self.pair,self.axis,self.tol): w.setEnabled(True)
        self.save.setEnabled(self.result is not None)

    def compute(self):
        if not self.pairs: return
        a,b=self.pairs[self.pair.currentIndex()]
        self.invalidate()
        self.summary.setText('正在对齐并计算…')
        self.begin(compare,(a,b,self.axis.currentText(),self.tol.value()),self.accept_result)

    def accept_result(self,r):
        self.result=r
        self.summary.setText(f'匹配 {len(r.i)} 点 / A {r.left.count} 点 / B {r.right.count} 点；'
            f'未参与比较：S2P {r.left.count-len(r.i)} 点，B {r.right.count-len(r.j)} 点；'
            f'A 歧义点 {r.ambiguous}。最大频率偏差 {np.max(np.abs(r.left.axes["StimulusFreq"][r.i]-r.right.axes[r.axis][r.j])):.6g} Hz。\n'
            '零幅度的 dB/相位差记为 NaN 并从对应统计排除；不自动判定通过/失败，不作重归一化。')
        for row,p in enumerate(PARAMS):
            d=r.delta[p]; db=stats(d[METRICS[0]]); ph=stats(d[METRICS[1]]); co=stats(d[METRICS[2]])
            cells=[p,db[0],db[1],ph[0],ph[1],co[0],co[1],stats(d[METRICS[3]])[0],stats(d[METRICS[4]])[0],db[2]]
            for col,v in enumerate(cells):
                self.table.setItem(row,col,QTableWidgetItem(v if isinstance(v,str) else f'{v:.9g}'))
        self.table.resizeColumnsToContents(); self.plot()

    def plot(self,*args):
        for ax,p in zip(self.axes,PARAMS):
            ax.clear(); ax.set_title(p,loc='left',fontweight='bold'); ax.grid(True,alpha=.2)
            ax.set_xlabel('S2P Stimulus (GHz)')
            ax.set_ylabel(YLABELS[self.metric.currentIndex()])
            if self.result:
                r=self.result; x=r.left.axes['StimulusFreq'][r.i]/1e9
                # Break at gaps, segment changes or frequency direction changes; never reorder samples.
                breaks=(np.diff(r.i)!=1)|(np.diff(r.j)!=1)|(np.diff(r.right.segment[r.j])!=0)|(np.diff(x)<=0)
                groups=np.split(np.arange(len(x)),np.flatnonzero(breaks)+1)
                if self.metric.currentIndex()==5:
                    with np.errstate(divide='ignore'):
                        ys=[20*np.log10(np.abs(r.left.s[p][r.i])),20*np.log10(np.abs(r.right.s[p][r.j]))]
                    for y,color,label,style in zip(ys,['#2563eb','#d97706'],['A','B'],['-','--']):
                        for n,g in enumerate(groups):
                            ax.plot(x[g],y[g],style,color=color,marker='o',markersize=3,label=label if n==0 else None)
                    ax.legend(fontsize=8)
                else:
                    y=r.delta[p][self.metric.currentText()]
                    for g in groups: ax.plot(x[g],y[g],color='#2563eb',marker='o',markersize=3)
                    ax.axhline(0,color='#94a3b8',linewidth=.8)
                ax.ticklabel_format(axis='y',style='sci',scilimits=(-3,3),useOffset=False)
        self.toolbar.update(); self.canvas.draw_idle()

    def export(self):
        if not self.result: return
        path,_=QFileDialog.getSaveFileName(self,'导出匹配点及差异',Path(self.result.left.name).stem+'_difference.csv','CSV (*.csv)')
        if path:
            if not path.lower().endswith('.csv'): path+='.csv'
            self.begin(export_comparison,(self.result,path),lambda _: self.summary.setText('差异已导出：'+path))

    def reject(self):
        if not self.worker: super().reject()
    def closeEvent(self,event):
        if self.worker: event.ignore()
        else: super().closeEvent(event)
