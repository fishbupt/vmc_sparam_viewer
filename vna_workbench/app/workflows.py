"""Explicit file/configuration handoff; simulation never invokes calibration math."""
def vmc_calibration_inputs(saved):
    from vna_workbench.calibration.vmc.input_reader import shared_inputs
    from vna_workbench.simulation.vmc import RAW_NAMES
    p=saved.directory
    result=shared_inputs([str(p/f'standard_{k}.s1p') for k in ('open','short','load')],
        [str(p/n) for n in RAW_NAMES[:3]],str(p/'thru_raw.s2p'),
        str(p/'calibration_mixer.s2p'),str(p/'cal_mixer_raw.s2p'),str(p/'thru_definition.s2p'))
    if saved.simulation.manifest.get('independent_port_standards'):
        result.standards['P2']=[str(p/f'standard_p2_{k}.s1p') for k in ('open','short','load')]
    return result

def vmc_calibration_options(saved):
    from vna_workbench.calibration.vmc.models import CalibrationOptions
    o=saved.simulation.options
    return CalibrationOptions(**{k:getattr(o,k) for k in
        ('rf_start_hz','rf_stop_hz','points','lo_hz','frequency_conversion','z0',
         'raw_axis','standard_sampling','frequency_tolerance_hz')},mixer_definition_axis='rf')


def characterize_with_config(measurements, standards, options, config):
    """Enforce the shared RF grid/reference impedance without changing extraction."""
    import numpy as np
    from vna_workbench.calibration.vmc.mixer_characterization import characterize
    result=characterize(measurements,standards,options)
    expected=np.linspace(config['rf_start_hz'],config['rf_stop_hz'],int(config['points']))
    actual=result.dataset.axes['InputFreq']
    if actual.shape!=expected.shape or not np.all(abs(actual-expected)<=config['frequency_tolerance_hz']):
        raise ValueError('两轮 SOL 的 RF 网格与 VMC 全局配置不一致；请修改全局配置或重新生成。')
    if not np.isclose(result.manifest['z0_ohm'],config['z0'],rtol=1e-12,atol=0):
        raise ValueError('标准/测量参考阻抗与 VMC 全局配置不一致。')
    return result
