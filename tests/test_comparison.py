import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from parser import Dataset,PARAMS,load_file
from comparison import compare,export_comparison
import tempfile,csv
ROOT=Path(__file__).resolve().parents[1]
def dataset(freq,phase=0,kind='left'):
 z=np.exp(1j*np.deg2rad(np.full(len(freq),phase)))
 return Dataset(kind,kind,{p:z.copy() for p in PARAMS},{'StimulusFreq' if kind=='left' else 'InputFreq':np.array(freq,dtype=float)},np.zeros(len(freq)))
class CompareTests(unittest.TestCase):
 def test_samples(self):
  a=load_file(ROOT/'examples/pna_excerpt.s2p');b=load_file(ROOT/'examples/pna_excerpt.s2px')
  r=compare(a,b)
  self.assertEqual(r.i.tolist(),[0]);self.assertEqual(r.j.tolist(),[0])
  self.assertAlmostEqual(r.delta['S21']['幅度差 (dB)'][0],.0000006414,places=12)
 def test_phase_wrap(self):
  r=compare(dataset([1],179),dataset([1],-179,'right'))
  self.assertAlmostEqual(r.delta['S11']['相位差 (°)'][0],-2)
 def test_sorted_matching_and_tolerance(self):
  r=compare(dataset([3,1,2]),dataset([1.0001,3],kind='right'),tolerance=.001)
  self.assertEqual(r.i.tolist(),[0,1]);self.assertEqual(r.j.tolist(),[1,0])
 def test_duplicates_not_paired(self):
  r=compare(dataset([1,1,2,3]),dataset([1,2,3,3],kind='right'))
  self.assertEqual(r.i.tolist(),[2]);self.assertEqual(r.ambiguous,3)
 def test_zero_and_export(self):
  a=dataset([1]);b=dataset([1],kind='right');a.s['S11'][0]=0
  r=compare(a,b);self.assertTrue(np.isnan(r.delta['S11']['相位差 (°)'][0]))
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'out.csv';export_comparison(r,f)
   with f.open(encoding='utf-8-sig') as stream: rows=list(csv.DictReader(stream))
   self.assertEqual(rows[0]['S2P_Row'],'1')
 def test_no_match(self):
  with self.assertRaises(ValueError):compare(dataset([1]),dataset([5],kind='right'))
