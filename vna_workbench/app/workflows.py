"""Explicit file/configuration handoff; simulation never invokes calibration math."""
def vmc_calibration_inputs(saved):
    from vna_workbench.calibration.vmc.input_reader import shared_inputs
    from vna_workbench.simulation.vmc import RAW_NAMES
    p=saved.directory
    return shared_inputs([str(p/f'standard_{k}.s1p') for k in ('open','short','load')],
        [str(p/n) for n in RAW_NAMES[:3]],str(p/'thru_raw.s2p'),
        str(p/'calibration_mixer.s2p'),str(p/'cal_mixer_raw.s2p'),str(p/'thru_definition.s2p'))

def vmc_calibration_options(saved):
    from vna_workbench.calibration.vmc.models import CalibrationOptions
    o=saved.simulation.options
    return CalibrationOptions(**{k:getattr(o,k) for k in
        ('rf_start_hz','rf_stop_hz','points','lo_hz','frequency_conversion','z0',
         'raw_axis','standard_sampling','frequency_tolerance_hz')},mixer_definition_axis='rf')
