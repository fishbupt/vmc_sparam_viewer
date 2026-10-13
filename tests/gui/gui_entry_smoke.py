"""Exercise direct root entry and installed package entry from another working directory."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as tmp:
    data=Path(tmp)/'entry.s2p'
    data.write_text('# Hz S RI R 50\n10000000000 0.1 0 0.5 0 0.4 0 0.2 0\n')
    for mode in ('root','package'):
        # Injection supplies a bounded event loop; the production entry remains unmodified.
        script='''
import sys, runpy
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings, QTimer
from vna_workbench.gui import main_window
from vna_workbench.app import application
settings_path=sys.argv[2]
main_window.QSettings=lambda *args:QSettings(settings_path,QSettings.Format.IniFormat)
BaseApplication=QApplication
class TestApplication(BaseApplication):
    def exec(self):
        def check():
            windows=[w for w in self.topLevelWidgets() if isinstance(w,main_window.Window)]
            if windows and windows[0].dataset is not None and not windows[0].busy():
                assert windows[0].dataset.count==1
                assert windows[0].analysis_tabs.currentIndex()==0
                windows[0].close()
                self.quit()
            else: QTimer.singleShot(20,check)
        QTimer.singleShot(20,check)
        QTimer.singleShot(8000,lambda: self.exit(9))
        return super().exec()
application.QApplication=TestApplication
path=settings=mode=None
path,settings,mode=sys.argv[1:]
sys.argv=['main.py',path]
if mode=='root':runpy.run_path(ROOT_MAIN,run_name='__main__')
else:runpy.run_path(str(Path(sys.executable).with_name('vna-calibration-workbench')),run_name='__main__')
'''.replace('ROOT_MAIN',repr(str(ROOT/'main.py')))
        env=dict(os.environ)
        if mode=='root':env['PYTHONPATH']=str(ROOT)
        else:env.pop('PYTHONPATH',None)
        result=subprocess.run([sys.executable,'-c',script,str(data),str(Path(tmp)/(mode+'.ini')),mode],cwd=tmp,env=env,text=True,capture_output=True,timeout=15)
        assert result.returncode==0,(mode,result.stdout,result.stderr)
print('Root / installed package entry and file loading passed')
