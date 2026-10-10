"""Independent wave-equation fixtures; no dependence on ignored personal examples."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from vmc_calibration import (CalibrationOptions,calibrate,calibrate_mut,shared_inputs,
    save_calibration,load_calibration,export_mut,term_dataset)

def write_s2p(path,f,c,z0=50):
    lines=[f'# Hz S RI R {z0}']
    for freq,s in zip(f,c):
        row=[freq]
        for v in [s[0,0],s[1,0],s[0,1],s[1,1]]:row.extend([v.real,v.imag])
        lines.append(' '.join(format(float(v),'.17g') for v in row))
    path.write_text('\n'.join(lines)+'\n');return str(path)

def box(f,port):
    x=(f-10e9)/1e9
    d=(.014+port*.003)*np.exp(1j*(.2-.018*x))
    e=(.042+port*.005)*np.exp(1j*(-.3-.025*x))
    t=(.94-port*.02)*np.exp(1j*(.12-.09*x))
    return d,e,t

def forward(c,f1,f2):
    d1,e1,t1=box(f1,1);d2,e2,t2=box(f2,2);out=[]
    for i,ci in enumerate(c):
        # Explicit four unknown internal waves, independently for each excitation.
        equations=np.array([[1,0,-e1[i],0],[0,1,0,-e2[i]],
            [-ci[0,0],-ci[0,1],1,0],[-ci[1,0],-ci[1,1],0,1]],complex)
        incident=np.array([[t1[i],0],[0,t2[i]],[0,0],[0,0]],complex)
        solution=np.linalg.solve(equations,incident)
        out.append(np.diag([d1[i],d2[i]])+np.diag([t1[i],t2[i]])@solution[2:])
    return np.array(out)

def fixture(root,axis='dual',direction='up',defined=False):
    rf=np.linspace(10e9,20e9,41) if direction=='up' else np.linspace(25e9,35e9,41)
    lo=20e9;iff=rf+lo if direction=='up' else rf-lo
    f=np.sort(np.concatenate([rf,iff]));n=len(rf)
    o=CalibrationOptions(rf_start_hz=rf[0],rf_stop_hz=rf[-1],points=n,
        lo_hz=lo,frequency_conversion=direction,raw_axis=axis)
    standards=[];sol=[]
    for kind,index in [('open',0),('short',1),('load',2)]:
        gamma=[.98*np.exp(-1j*(f-10e9)*2e-12),-.96*np.exp(-1j*(f-10e9)*3e-12),
               .01*np.exp(1j*(f-10e9)*1e-12)][index]
        path=root/(kind+'.s1p');path.write_text('# Hz S RI R 50\n'+''.join(
            f'{fr:.17g} {v.real:.17g} {v.imag:.17g}\n' for fr,v in zip(f,gamma)))
        standards.append(str(path))
        c=np.zeros((len(f),2,2),complex)
        for p in [1,2]:
            d,e,t=box(f,p);c[:,p-1,p-1]=d+t*t*gamma/(1-e*gamma)
        sol.append(write_s2p(root/(kind+'_raw.s2p'),f,c))
    thru=np.zeros((len(f),2,2),complex);thru[:,1,0]=1;thru[:,0,1]=1
    if defined:
        thru[:,0,0]=.05;thru[:,1,1]=-.04j
        thru[:,1,0]=.8*np.exp(-1j*(f-10e9)*5e-12);thru[:,0,1]=.7*np.exp(-1j*(f-10e9)*4e-12)
    definition=write_s2p(root/'thru_definition.s2p',f,thru) if defined else None
    thru_path=write_s2p(root/'thru_raw.s2p',f,forward(thru,f,f))
    c=np.zeros((n,2,2),complex);x=(rf-rf[0])/1e9
    c[:,0,0]=.12*np.exp(1j*(.2-.05*x));c[:,1,1]=.09*np.exp(1j*(-.1-.04*x))
    c[:,1,0]=.5*np.exp(1j*(-.5-.4*x));c[:,0,1]=.35*np.exp(1j*(-.7-.3*x))
    cal_path=write_s2p(root/'calibration_mixer.s2p',rf,c)
    mut=c.copy();mut[:,0,0]*=1.4;mut[:,1,1]*=.8;mut[:,1,0]*=.65;mut[:,0,1]=0
    def mixed_path(name,raw):
        if axis=='dual':return write_s2p(root/name,f,np.array([raw[np.argmin(abs((rf if v in rf else iff)-v))] for v in f]))
        return write_s2p(root/name,rf if axis=='rf' else iff,raw)
    cal_raw=mixed_path('cal_raw.s2p',forward(c,rf,iff));mut_path=mixed_path('mut_raw.s2p',forward(mut,rf,iff))
    inputs=shared_inputs(standards,sol,thru_path,cal_path,cal_raw,definition)
    return inputs,o,mut_path,mut

class VMCCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_independent_forward_wave_up_down_all_axes_and_defined_thru(self):
        for direction in ['up','down']:
            for axis in ['rf','if','dual']:
                for defined in [False,True]:
                    with self.subTest(direction=direction,axis=axis,defined=defined):
                        inp,o,path,truth=fixture(self.root,axis,direction,defined)
                        cal=calibrate(inp,o);result=calibrate_mut(cal,path)
                        for key,actual in [('S11',truth[:,0,0]),('S22',truth[:,1,1]),('S21',truth[:,1,0])]:
                            np.testing.assert_allclose(result.dataset.s[key],actual,atol=2e-14,rtol=0)
                        for band,f in [('RF',cal.frequency),('IF',cal.if_frequency)]:
                            for p in [1,2]:
                                d,e,t=box(f,p)
                                for name,actual in [('EDF',d),('ESF',e),('ERF',t*t)]:
                                    np.testing.assert_allclose(cal.terms[f'P{p}_{band}_{name}'],actual,atol=2e-14,rtol=0)
                            np.testing.assert_allclose(cal.terms[band+'_ELF'],box(f,2)[1],atol=2e-14,rtol=0)
                            np.testing.assert_allclose(cal.terms[band+'_ELR'],box(f,1)[1],atol=2e-14,rtol=0)
                            np.testing.assert_allclose(cal.terms[band+'_ETF'],box(f,1)[2]*box(f,2)[2],atol=2e-14,rtol=0)
                        np.testing.assert_allclose(cal.terms['VMC_ETF'],box(cal.frequency,1)[2]*box(cal.if_frequency,2)[2],atol=2e-14,rtol=0)

    def test_twelve_s1p_raw_inputs_and_separate_port_standards(self):
        from parser import load_file
        inp,o,path,truth=fixture(self.root)
        for group in inp.sol:
            axis=np.linspace(o.rf_start_hz,o.rf_stop_hz,o.points)
            if group.endswith('IF'):axis+=o.lo_hz
            param='S11' if group.startswith('P1') else 'S22'
            for i,old in enumerate(inp.sol[group]):
                data=load_file(old);indices=np.searchsorted(data.axes['StimulusFreq'],axis);values=data.s[param][indices]
                new=self.root/(group+str(i)+'.s1p');new.write_text('# Hz S RI R 50\n'+''.join(f'{f:.17g} {v.real:.17g} {v.imag:.17g}\n' for f,v in zip(axis,values)))
                inp.sol[group][i]=str(new)
        # Separate filenames preserve independent definitions; values need not differ.
        inp.standards['P2']=[]
        for old in inp.standards['P1']:
            new=self.root/('P2_'+Path(old).name);new.write_bytes(Path(old).read_bytes());inp.standards['P2'].append(str(new))
        result=calibrate_mut(calibrate(inp,o),path)
        np.testing.assert_allclose(result.dataset.s['S21'],truth[:,1,0],atol=2e-14,rtol=0)

    def test_pack_reload_and_export_with_no_source_files(self):
        inp,o,path,_=fixture(self.root);cal=calibrate(inp,o)
        bundle=self.root/'cal.zip';save_calibration(cal,bundle);loaded=load_calibration(bundle)
        for k in cal.terms:np.testing.assert_array_equal(loaded.terms[k],cal.terms[k])
        for p in inp.standards['P1']:Path(p).unlink()
        result=calibrate_mut(loaded,path);out=self.root/'mut.zip';export_mut(result,out)
        with zipfile.ZipFile(out) as z:
            self.assertIn('frequency_map.csv',z.namelist());report=json.loads(z.read('report.json'))
            self.assertFalse(report['reverse_calibrated']);self.assertIn('NOT calibrated',z.read('calibrated_mut.s2p').decode())
        self.assertTrue(np.all(result.dataset.s['S12']==0))

    def test_corrupted_pack_rejected(self):
        inp,o,_,_=fixture(self.root);path=self.root/'pack.zip';save_calibration(calibrate(inp,o),path)
        with zipfile.ZipFile(path) as z:payload={n:z.read(n) for n in z.namelist()}
        payload['arrays.npz']=payload['arrays.npz'][:-5]+b'wrong'
        with zipfile.ZipFile(path,'w') as z:
            for k,v in payload.items():z.writestr(k,v)
        with self.assertRaisesRegex(ValueError,'校验失败'):load_calibration(path)

    def test_missing_measurement_node_not_interpolated(self):
        inp,o,_,_=fixture(self.root)
        p=Path(inp.sol['P1_RF'][0]);lines=p.read_text().splitlines();p.write_text('\n'.join(lines[:2]+lines[3:]))
        with self.assertRaisesRegex(ValueError,'不插值'):calibrate(inp,o)

    def test_z0_mismatch_rejected(self):
        inp,o,_,_=fixture(self.root);p=Path(inp.calibration_mixer)
        p.write_text(p.read_text().replace('R 50','R 75'))
        with self.assertRaisesRegex(ValueError,'参考阻抗'):calibrate(inp,o)

    def test_dual_axis_conflict_rejected(self):
        inp,o,path,_=fixture(self.root);p=Path(path);lines=p.read_text().splitlines();v=lines[-1].split();v[3]=str(float(v[3])+.1);lines[-1]=' '.join(v);p.write_text('\n'.join(lines))
        cal=calibrate(inp,o)
        with self.assertRaisesRegex(ValueError,'不一致'):calibrate_mut(cal,path)

    def test_overlap_dual_axis_rejected(self):
        inp,o,_,_=fixture(self.root)
        with self.assertRaisesRegex(ValueError,'不重叠'):calibrate(inp,CalibrationOptions(lo_hz=5e9))

    def test_zero_cal_mixer_transmission_rejected(self):
        inp,o,_,_=fixture(self.root);p=Path(inp.calibration_mixer);lines=p.read_text().splitlines()
        for i in range(1,len(lines)):
            row=lines[i].split();row[3:5]=['0','0'];lines[i]=' '.join(row)
        p.write_text('\n'.join(lines))
        with self.assertRaisesRegex(ValueError,'校准混频器 S21'):calibrate(inp,o)

    def test_standard_interpolation_both_modes_and_provenance(self):
        inp,o,_,_=fixture(self.root)
        for p in inp.standards['P1']:
            lines=Path(p).read_text().splitlines();Path(p).write_text('\n'.join([lines[0]]+lines[1::2]+[lines[-1]]))
            # Last node is already retained for odd point count; remove exact duplicate.
            rows=Path(p).read_text().splitlines()
            if rows[-1]==rows[-2]:rows.pop()
            Path(p).write_text('\n'.join(rows))
        for sampling in ['linear_ri','cubic_ri']:
            opts=CalibrationOptions(**{**o.__dict__,'standard_sampling':sampling})
            cal=calibrate(inp,opts)
            self.assertTrue(any(v>0 for v in cal.manifest['interpolated_points'].values()))
            self.assertTrue(all(len(s['sha256'])==64 for s in cal.manifest['sources']))

    def test_term_dataset_and_mut_axis_override(self):
        inp,o,path,_=fixture(self.root);cal=calibrate(inp,o)
        data=term_dataset(cal,'VMC_ETF');np.testing.assert_array_equal(data.s['S21'],cal.terms['VMC_ETF'])
        np.testing.assert_array_equal(term_dataset(cal,'IF_ELF').axes['StimulusFreq'],cal.if_frequency)
        first=calibrate_mut(cal,path);second=calibrate_mut(cal,path,'rf')
        np.testing.assert_array_equal(first.dataset.s['S21'],second.dataset.s['S21'])

    def test_dc_node_allowed_in_standard_definitions(self):
        inp,o,_,_=fixture(self.root)
        for p in inp.standards['P1']:
            path=Path(p);lines=path.read_text().splitlines();first=lines[1].split()
            path.write_text('\n'.join([lines[0],'0 '+first[1]+' '+first[2]]+lines[1:]))
        self.assertEqual(len(calibrate(inp,o).frequency),o.points)

    def test_different_port2_standard_values(self):
        from parser import load_file
        from characterization import load_standard
        inp,o,path,truth=fixture(self.root);p2=[]
        for definition,raw_path in zip(inp.standards['P1'],inp.sol['P2_RF']):
            std=load_standard(definition);gamma=std.gamma*.9
            new=self.root/('port2_'+Path(definition).name)
            new.write_text('# Hz S RI R 50\n'+''.join(f'{f:.17g} {v.real:.17g} {v.imag:.17g}\n' for f,v in zip(std.frequency,gamma)));p2.append(str(new))
            raw=load_file(raw_path);f=raw.axes['StimulusFreq'];d,e,t=box(f,2)
            c=np.zeros((len(f),2,2),complex);c[:,0,0]=raw.s['S11'];c[:,1,1]=d+t*t*gamma/(1-e*gamma)
            write_s2p(Path(raw_path),f,c)
        inp.standards['P2']=p2
        result=calibrate_mut(calibrate(inp,o),path)
        np.testing.assert_allclose(result.dataset.s['S21'],truth[:,1,0],atol=2e-14,rtol=0)

    def test_cal_mixer_requires_four_parameter_definition(self):
        inp,o,_,_=fixture(self.root);inp.calibration_mixer=inp.standards['P1'][0]
        with self.assertRaisesRegex(ValueError,'四参数'):calibrate(inp,o)

    def test_nonfinite_raw_data_rejected(self):
        inp,o,_,_=fixture(self.root);p=Path(inp.cal_mixer_raw)
        lines=p.read_text().splitlines();row=lines[1].split();row[3]='nan';lines[1]=' '.join(row);p.write_text('\n'.join(lines))
        with self.assertRaisesRegex(ValueError,'有限数'):calibrate(inp,o)

if __name__=='__main__':unittest.main()
