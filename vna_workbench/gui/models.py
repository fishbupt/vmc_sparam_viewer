from __future__ import annotations
from PyQt6.QtCore import Qt, QAbstractTableModel
from vna_workbench.analysis.csv_exports import table_data

class DataModel(QAbstractTableModel):
    def __init__(self, dataset):
        super().__init__()
        self.headers, self.columns = table_data(dataset)
        self.n = dataset.count
    def rowCount(self, parent=None):
        return self.n
    def columnCount(self, parent=None):
        return len(self.headers)
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            return f'{self.columns[index.column()][index.row()]:.12g}'
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section] if orientation == Qt.Orientation.Horizontal else str(section + 1)
