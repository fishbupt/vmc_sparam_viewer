"""Existing engineering-light theme, preserved verbatim."""

STYLE = '''
QMainWindow, QDialog { background: #f3f6fa; }
QWidget { font-family: "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"; font-size: 10pt; color: #24344a; }
QGroupBox { background: white; border: 1px solid #dce3ec; border-radius: 7px; margin-top: 12px; padding: 12px 8px 8px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; }
QListWidget,QTableView,QTextEdit,QPlainTextEdit { background: white; border: 1px solid #dce3ec; border-radius: 4px; selection-background-color: #dbeafe; selection-color: #143e78; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 5px; padding: 7px 12px; }
QPushButton:hover { background: #eaf2fd; }
QPushButton:disabled { color: #94a3b8; background: #eef2f6; }
QPushButton#primary { background: #2563eb; color: white; border-color: #2563eb; }
QComboBox,QLineEdit { background: white; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px; }
QComboBox QAbstractItemView { background: white; color: #24344a; selection-background-color: #dbeafe; }
QTabWidget::pane { background: white; border: 1px solid #dce3ec; }
QTabBar::tab { padding: 9px 16px; background: #e9eef5; }
QTabBar::tab:selected { background: white; color: #2563eb; }
QMenuBar, QMenu { background: white; color: #24344a; }
QMenu::item:selected { background: #dbeafe; }
QListWidget#workflowNavigation, QWidget#viewerSidebar { background: white; border: 1px solid #dce3ec; }
QListWidget#workflowNavigation::item { padding: 12px 8px; }
QListWidget#workflowNavigation::item:selected { background: #e7effd; color: #2563eb; }
QListWidget#workflowNavigation::item:disabled { color: #64748b; padding-top: 15px; font-size: 9pt; }
QHeaderView::section { background: #edf2f8; padding: 6px; border: 0; border-right: 1px solid #dce3ec; }
'''
