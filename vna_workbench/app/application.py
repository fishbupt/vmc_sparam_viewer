"""Application startup; root main.py remains a direct-script entry point."""

import sys
from PyQt6.QtWidgets import QApplication
from vna_workbench.gui.main_window import Window
from vna_workbench.gui.theme import STYLE

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1:
        window.load_paths(sys.argv[1:])
    sys.exit(app.exec())
