"""Forward simulation using a physical kit; no inverse extraction formulas."""
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from datetime import datetime
import csv
import hashlib
import io
import json
import tempfile
import shutil
import uuid
import numpy as np
from characterization import load_standard, sample_standard, SAMPLING_METHODS, INTERPOLATION_COORDINATES
from parser import Dataset
from frequency_mapping import output_frequencies, frequency_relation

MEASUREMENT_NAMES = tuple(f'{r:02d}_{prefix}_SOL_{kind}.s2p'
    for r, prefix in [(1, 'Input'), (2, 'Mixer')] for kind in ['Open', 'Short', 'Load'])

@dataclass(frozen=True)
class SimulationOptions:
    rf_start_hz: float = 10e9
    rf_stop_hz: float = 20e9
    points: int = 201
    lo_hz: float = 5e9
    standard_sampling: str = 'cubic_ri'
    frequency_tolerance_hz: float = .001
    s11_db: float = -18
    s11_phase_deg: float = -20
    s11_delay_ps: float = 20
    s22_db: float = -20
    s22_phase_deg: float = 30
    s22_delay_ps: float = 15
    transmission_db: float = -6
    transmission_phase_deg: float = -30
    transmission_delay_ps: float = 80
    edf_db: float = -35
    edf_phase_deg: float = 30
    edf_delay_ps: float = 5
    esf_db: float = -25
    esf_phase_deg: float = -20
    esf_delay_ps: float = 10
    erf_db: float = -1
    erf_phase_deg: float = 15
    erf_delay_ps: float = 40
    noise_enabled: bool = False
    noise_floor_db: float = -90
    noise_seed: int = 20261009
    noise_averages: int = 1
    frequency_conversion: str = 'down'

@dataclass
class Simulation:
    truth: Dataset
    frequency: np.ndarray
    gamma: np.ndarray
    clean: np.ndarray
    measured: np.ndarray
    terms: dict
    standard_bytes: list
    manifest: dict

@dataclass
class SavedSimulation:
    directory: Path
    measurement_paths: list
    standard_paths: list
    mixer_path: Path
    simulation: Simulation


def _validate(o):
    for f in fields(o):
        if f.name not in ('standard_sampling', 'noise_enabled', 'frequency_conversion'):
            value = getattr(o, f.name)
            if not np.isfinite(value):
                raise ValueError(f'{f.name}: 参数必须是有限数。')
    if (isinstance(o.points, bool) or int(o.points) != o.points or not 2 <= o.points <= 200001):
        raise ValueError('扫频点数必须为 2～200001 的整数。')
    if not 0 < o.rf_start_hz < o.rf_stop_hz:
        raise ValueError('需要 0 < RF起点 < RF终点。')
    output_frequencies([o.rf_start_hz, o.rf_stop_hz], o.lo_hz, o.frequency_conversion)
    if o.standard_sampling not in SAMPLING_METHODS:
        raise ValueError('未知标准件求值方式。')
    if o.frequency_tolerance_hz < 0:
        raise ValueError('频率容差必须非负。')
    for name in ('s11_db', 's22_db', 'edf_db', 'esf_db'):
        if not -300 <= getattr(o, name) < 0:
            raise ValueError(f'{name}: 需在 −300～0 dB 范围且小于 0。')
    for name in ('transmission_db', 'erf_db'):
        if not -300 <= getattr(o, name) <= 40:
            raise ValueError(f'{name}: 需在 −300～40 dB 范围。')
    if not -300 <= o.noise_floor_db <= 0:
        raise ValueError('噪声底需在 −300～0 dB 范围。')
    if isinstance(o.noise_seed, bool) or int(o.noise_seed) != o.noise_seed or not 0 <= o.noise_seed <= 2**32-1:
        raise ValueError('随机种子必须为 0～2³²−1 的整数。')
    if isinstance(o.noise_averages, bool) or int(o.noise_averages) != o.noise_averages or not 1 <= o.noise_averages <= 10000:
        raise ValueError('噪声平均次数必须为 1～10000 的整数。')


def simulate(standard_paths, options=SimulationOptions()):
    _validate(options)
    if len(standard_paths) != 3:
        raise ValueError('请选择共用 OPEN、SHORT、LOAD 三个 S1P。')
    # Read each file once: copied bytes, hashes and evaluated values share one snapshot.
    from characterization import parse_s1p
    blobs = [Path(p).read_bytes() for p in standard_paths]
    standards = []
    for p, blob in zip(standard_paths, blobs):
        for enc in ('utf-8-sig', 'gb18030', 'cp1252'):
            try:
                text = blob.decode(enc); break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError(f'{p}: 无法解码标准文件。')
        standards.append(parse_s1p(text, str(p)))
    z0 = standards[0].z0
    if not np.allclose([s.z0 for s in standards], z0, rtol=1e-12, atol=0):
        raise ValueError('三个标准件参考阻抗必须一致，不自动重归一化。')
    f = np.linspace(options.rf_start_hz, options.rf_stop_hz, int(options.points))
    ifreq = output_frequencies(f, options.lo_hz, options.frequency_conversion)
    relation = frequency_relation(options.frequency_conversion)
    df = f-f[0]
    def response(db, phase, delay):
        return 10**(db/20)*np.exp(1j*(np.deg2rad(phase)-2*np.pi*df*delay*1e-12))
    o = options
    c11=response(o.s11_db,o.s11_phase_deg,o.s11_delay_ps)
    c22=response(o.s22_db,o.s22_phase_deg,o.s22_delay_ps)
    t=response(o.transmission_db,o.transmission_phase_deg,o.transmission_delay_ps)
    d=response(o.edf_db,o.edf_phase_deg,o.edf_delay_ps)
    s=response(o.esf_db,o.esf_phase_deg,o.esf_delay_ps)
    r=response(o.erf_db,o.erf_phase_deg,o.erf_delay_ps)
    gamma=[];counts=[]
    for axis in (f, ifreq):
        for std in standards:
            g,n=sample_standard(std,axis,o.standard_sampling,o.frequency_tolerance_hz)
            gamma.append(g);counts.append(n)
    gamma=np.column_stack(gamma)
    def reflect(a,b,c,g):
        denom=1-c[:,None]*g
        if np.any(np.abs(denom)<1e-10):
            raise ValueError('正向模型分母接近零，请调整标准件或模型参数。')
        return a[:,None]+b[:,None]*g/denom
    first=reflect(d,r,s,gamma[:,:3])
    mixer_reflection=reflect(c11,t*t,c22,gamma[:,3:])
    second=reflect(d,r,s,mixer_reflection)
    clean=np.column_stack((first,second))
    sigma=10**(o.noise_floor_db/20)/np.sqrt(o.noise_averages) if o.noise_enabled else 0.
    if sigma:
        rng=np.random.Generator(np.random.PCG64(int(o.noise_seed)))
        noise=(rng.normal(size=clean.shape)+1j*rng.normal(size=clean.shape))*(sigma/np.sqrt(2))
        measured=clean+noise
    else:
        measured=clean.copy()
    if not np.all(np.isfinite(measured)):
        raise ValueError('仿真产生非有限值，未生成文件。')
    truth=Dataset('Mixer.s2p','S2P / Simulated truth',
        {'S11':c11,'S21':t,'S12':t.copy(),'S22':c22},
        {'StimulusFreq':f,'InputFreq':f,'OutputFreq':ifreq,'LO1Freq':np.full(len(f),o.lo_hz)},
        np.zeros(len(f),int),{'参考阻抗':f'{z0:g} Ω','数据格式':'RI','频率映射':relation,
        '说明':'无噪声混频器真值；不是可自行变频的 DummyDUT 模型'},[])
    matrix=np.stack((np.stack((c11,t),axis=-1),np.stack((t,c22),axis=-1)),axis=-2)
    max_sv=float(np.max(np.linalg.svd(matrix,compute_uv=False)))
    manifest={'version':'1.5.2','options':asdict(o),'z0_ohm':z0,'frequency_conversion':o.frequency_conversion,'if_relation':relation+' (non-inverting)',
        'phase_reference':'Phases are at RF start; phase slope is -2*pi*(RF-RF_start)*delay',
        'model':'m=D+R*Gamma/(1-S*Gamma); output reflection=C11+C12*C21*Gamma/(1-C22*Gamma)',
        'truth_reference_root_sign':1 if abs(np.sqrt(t[0]*t[0])-t[0]) <= abs(np.sqrt(t[0]*t[0])+t[0]) else -1,
        'reciprocal_assumption':True,'measurement_columns':'Only S11 is meaningful; S21/S12/S22 are zero placeholders',
        'mixer_truth_noise_free':True,'standard_sampling':o.standard_sampling,
        'interpolation_coordinates':INTERPOLATION_COORDINATES[o.standard_sampling],
        'interpolation_boundary':'not-a-knot' if o.standard_sampling.startswith('cubic_') else None,
        'extrapolation':False,'interpolated_points':counts,
        'noise':{'enabled':o.noise_enabled,'model':'IID circular complex Gaussian added AFTER input error map, independently for each frequency and SOL state',
            'db_reference':'20*log10(complex RMS relative to dimensionless S=1); NOT dBm or dBm/Hz',
            'effective_complex_rms':float(sigma),'iq_component_std':float(sigma/np.sqrt(2)),
            'seed':int(o.noise_seed),'generator':'NumPy PCG64','numpy_version':np.__version__,
            'averaging':'Gaussian-equivalent complex averaging: RMS scales as 1/sqrt(N)'},
        'standard_inputs':[{'kind':k,'source_path':str(p),'sha256':hashlib.sha256(b).hexdigest()}
            for k,p,b in zip(('OPEN','SHORT','LOAD'),standard_paths,blobs)],
        'max_effective_singular_value':max_sv,
        'warnings':['Mixer.s2p uses RF stimulus axis and frequency-translating effective coefficients; ordinary S2P does not itself implement frequency conversion.']}
    if max_sv>1+1e-10:
        manifest['warnings'].append('Effective S matrix singular value exceeds 1; this synthetic configuration is not constrained to passive behavior.')
    if abs(o.transmission_delay_ps)*(f[1]-f[0]) >= .25e12:
        manifest['warnings'].append('Transmission product phase changes by >=180 degrees per sample; reflection-only phase unwrapping may alias.')
    return Simulation(truth,f,gamma,clean,measured,{'EDF':d,'ESF':s,'ERF':r,'S12_times_S21':t*t},blobs,manifest)


def _s2p(f, values, z0, comments):
    lines=['! '+c for c in comments]+[f'# Hz S RI R {z0:.17g}']
    for i,frequency in enumerate(f):
        row=[frequency]
        for name in ('S11','S21','S12','S22'):
            z=values[name][i];row.extend((z.real,z.imag))
        lines.append(' '.join(format(float(v),'.17g') for v in row))
    return '\n'.join(lines)+'\n'


def generate_files(standard_paths, output_parent, options=SimulationOptions()):
    """Create a unique subfolder atomically; never overwrite an existing run."""
    result=simulate(standard_paths,options)
    parent=Path(output_parent)
    if not parent.is_dir():
        raise ValueError('输出父目录不存在，请选择现有目录。')
    folder=parent/('vmc_sim_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    stage=Path(tempfile.mkdtemp(prefix='.vmc_staging_',dir=parent))
    try:
        z0=result.manifest['z0_ohm'];f=result.frequency;zeros=np.zeros(len(f),complex)
        common=[f'RF_Hz={f[0]:.17g}..{f[-1]:.17g}; LO_Hz={options.lo_hz:.17g}; {frequency_relation(options.frequency_conversion)}',
                'StandardSampling='+options.standard_sampling+'; InterpolationCoordinates='+result.manifest['interpolation_coordinates'],
                f'NoiseEnabled={options.noise_enabled}; ComplexNoiseRMS={result.manifest["noise"]["effective_complex_rms"]:.17g}']
        for i,name in enumerate(MEASUREMENT_NAMES):
            values={'S11':result.measured[:,i],'S21':zeros,'S12':zeros,'S22':zeros}
            text=_s2p(f,values,z0,['SYNTHETIC SOL ACQUISITION: only S11 is meaningful; remaining S are zero placeholders.']+common)
            (stage/name).write_text(text,encoding='utf-8')
        text=_s2p(f,result.truth.s,z0,['SYNTHETIC MIXER TRUTH: reciprocal, noise-free; RF stimulus axis.',
                    'Effective frequency-translating coefficients; not a frequency-converting DummyDUT S2P.']+common[:2])
        (stage/'Mixer.s2p').write_text(text,encoding='utf-8');result.truth.raw_text=text
        for kind,blob in zip(('Open','Short','Load'),result.standard_bytes):
            (stage/f'Standard_{kind}.s1p').write_bytes(blob)
        # Full clean observations, applied noise, evaluated Gamma and error terms.
        stream=io.StringIO();writer=csv.writer(stream)
        labels=['RF_Hz','IF_Hz']
        arrays=[f,result.truth.axes['OutputFreq']]
        for name,values in {**result.terms,**result.truth.s}.items():
            labels.extend((name+'_Real',name+'_Imag'));arrays.extend((values.real,values.imag))
        for i,name in enumerate(MEASUREMENT_NAMES):
            for label,values in [('Gamma',result.gamma[:,i]),('Clean',result.clean[:,i]),('Measured',result.measured[:,i]),('Noise',result.measured[:,i]-result.clean[:,i])]:
                labels.extend((f'{name}_{label}_Real',f'{name}_{label}_Imag'));arrays.extend((values.real,values.imag))
        writer.writerow(labels);writer.writerows(zip(*arrays))
        (stage/'simulation_truth.csv').write_text(stream.getvalue(),encoding='utf-8-sig')
        result.manifest['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir()}
        (stage/'simulation_report.json').write_text(json.dumps(result.manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        stage.rename(folder)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise
    return SavedSimulation(folder,[folder/n for n in MEASUREMENT_NAMES],
        [folder/f'Standard_{k}.s1p' for k in ('Open','Short','Load')],folder/'Mixer.s2p',result)
