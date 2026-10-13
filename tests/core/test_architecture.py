"""Guard headless numerical layers and independent forward models after migration."""
import ast
import importlib
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
PACKAGE=ROOT/'vna_workbench'

class ArchitectureTests(unittest.TestCase):
    def test_numerical_layers_do_not_import_gui(self):
        for folder in ('core','data','analysis','calibration'):
            for path in (PACKAGE/folder).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    names=[node.module] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
                    for name in names:
                        self.assertFalse(name and name.startswith(('PyQt6','vna_workbench.gui')),str(path))
                module='.'.join(path.relative_to(ROOT).with_suffix('').parts)
                importlib.import_module(module)

    def test_package_imports_do_not_use_flat_legacy_modules(self):
        legacy={'parser','characterization','simulation','vmc_simulation','vmc_calibration','frequency_mapping','main','characterize_gui','simulate_gui','compare_gui','comparison','viewer_gui','workbench_gui'}
        for path in PACKAGE.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                names=[node.module] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
                self.assertFalse(legacy.intersection(names),str(path))

    def test_forward_models_do_not_call_calibration(self):
        for filename,functions in [('vmc.py',('simulate_vmc','forward_wave','generate_vmc_files')),('mixer_characterization.py',('simulate','generate_files'))]:
            tree=ast.parse((PACKAGE/'simulation'/filename).read_text())
            for node in tree.body:
                if isinstance(node,ast.FunctionDef) and node.name in functions:
                    for part in ast.walk(node):
                        if isinstance(part,ast.Call):
                            name=part.func.id if isinstance(part.func,ast.Name) else part.func.attr if isinstance(part.func,ast.Attribute) else ''
                            self.assertNotIn(name,('calibrate','calibrate_mut','characterize','solve_sol'))
