"""One VMC configuration per workbench, with explicit UI bindings and invalidation."""
from dataclasses import asdict
import json
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QComboBox, QLabel
from vna_workbench.calibration.vmc.models import CalibrationOptions, AXIS_MODES
from vna_workbench.core.frequency_conversion import output_frequencies, CONVERSION_MODES, bands_overlap
from vna_workbench.core.standard_sampling import SAMPLING_METHODS

KEYS=('rf_start_hz','rf_stop_hz','points','lo_hz','frequency_conversion','z0',
      'standard_sampling','frequency_tolerance_hz','raw_axis')


class VMCSession(QObject):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace=workspace
        self.values={k:v for k,v in asdict(CalibrationOptions()).items() if k in KEYS}
        self.bindings=[];self.applying=False;self.restored=False
        self.axis_notice=''
        try:
            saved=json.loads(workspace.owner.settings.value('vmc_global/config','{}'))
            if isinstance(saved,dict) and saved:
                candidate={**self.values,**{k:v for k,v in saved.items() if k in KEYS}}
                candidate=self.compatible_axis(candidate)
                # Invalid old settings must not poison all pages at startup.
                from vna_workbench.calibration.vmc.input_reader import validate_axes
                validate_axes(CalibrationOptions(**candidate))
                self.values=candidate;self.restored=True
                workspace.owner.settings.setValue('vmc_global/config',json.dumps(self.values))
        except (TypeError,ValueError,KeyError,OverflowError):pass

    def attach(self,page,fields,editor=False):
        page.vmc_session=self
        summary=QLabel();summary.setWordWrap(True);summary.setObjectName('summaryCard')
        page.layout().insertWidget(0,summary)
        self.bindings.append((page,fields,summary,editor))
        for key,(control,factor) in fields.items():
            signal=control.currentIndexChanged if isinstance(control,QComboBox) else control.valueChanged
            signal.connect(lambda *_,k=key,c=control,f=factor:self.edit(k,c,f))
            if not editor:
                control.setToolTip('共享 VMC 配置；请到“VMC 全局配置”修改。')
        self.apply(page,fields,summary)

    def edit(self,key,control,factor):
        if self.applying:return
        value=control.currentData() if isinstance(control,QComboBox) else control.value()*factor
        self.update({key:int(value) if key=='points' else value})

    def update(self,values,force=False):
        patch={k:v for k,v in values.items() if k in KEYS}
        if self.workspace.owner.busy() and not force:
            self.apply_all();return False
        candidate=self.compatible_axis({**self.values,**patch})
        changed=candidate!=self.values
        if not changed:
            self.apply_all()  # Restore a rejected dual selection in every bound selector.
            return True
        self.values=candidate
        self.apply_all()
        for page,_,_,_ in self.bindings:
            (page.invalidate_cal if hasattr(page,'invalidate_cal') else page.invalidate)()
        self.workspace.owner.settings.setValue('vmc_global/config',json.dumps(self.values))
        return True

    def compatible_axis(self,values):
        """Keep one usable global encoding when physical bands touch or overlap.

        This selects RF-indexed files; the core dual encoding stays strict.
        Incomplete intermediate frequency edits remain visible for correction.
        """
        values=dict(values)
        try:
            rf=[values['rf_start_hz'],values['rf_stop_hz']]
            iff=output_frequencies(rf,values['lo_hz'],values['frequency_conversion'])
            overlap=bands_overlap(rf,iff)
            if not overlap or values['raw_axis']=='if':self.axis_notice=''
            if values['raw_axis']=='dual' and overlap:
                values['raw_axis']='rf'
                self.axis_notice='RF/IF 频段相接或重叠，已统一改用 RF 横轴生成原始文件。'
        except (ValueError,TypeError):pass
        return values

    def apply(self,page,fields,summary):
        self.applying=True
        try:
            for key,(control,factor) in fields.items():
                old=control.blockSignals(True)
                if isinstance(control,QComboBox):control.setCurrentIndex(control.findData(self.values[key]))
                else:control.setValue(int(self.values[key]) if key=='points' else self.values[key]/factor)
                control.blockSignals(old)
                if key=='raw_axis':
                    try:
                        v=self.values
                        rf=[v['rf_start_hz'],v['rf_stop_hz']]
                        iff=output_frequencies(rf,v['lo_hz'],v['frequency_conversion'])
                        item=control.model().item(control.findData('dual'))
                        if item is not None:item.setEnabled(not bands_overlap(rf,iff))
                    except (ValueError,TypeError):pass
            summary.setText(self.description())
            if hasattr(page,'update_mapping'):page.update_mapping()
        finally:self.applying=False

    def apply_all(self):
        for page,fields,summary,_ in self.bindings:self.apply(page,fields,summary)

    def description(self):
        v=self.values
        try:
            iff=output_frequencies([v['rf_start_hz'],v['rf_stop_hz']],v['lo_hz'],v['frequency_conversion'])
            output=f'IF {iff[0]/1e9:g} → {iff[-1]/1e9:g} GHz'
        except ValueError as e:output=str(e)
        return (f"全局 VMC：RF {v['rf_start_hz']/1e9:g}～{v['rf_stop_hz']/1e9:g} GHz · "
                f"LO {v['lo_hz']/1e9:g} GHz · {output} · {v['points']} 点 · {v['z0']:g} Ω\n"
                f"原始文件横轴：{AXIS_MODES[v['raw_axis']]}\n"
                f"{CONVERSION_MODES[v['frequency_conversion']]} · {SAMPLING_METHODS[v['standard_sampling']]} · "
                '在“VMC 全局配置”统一修改；两轮 SOL 测量文件固定 RF 横轴。'
                + ('\n'+self.axis_notice if self.axis_notice else ''))


def generator_fields(page,full=False):
    fields={k:pair for k,pair in page.parameters.items() if k in KEYS}
    fields.update(frequency_conversion=(page.conversion,1),standard_sampling=(page.sampling,1))
    if full:fields['raw_axis']=(page.raw_axis,1)
    return fields
