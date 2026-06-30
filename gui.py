from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

class FAT32GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FAT32文件系统解析器")
        self.setGeometry(100, 100, 1200, 800)
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout()

        # 左侧控制栏
        left = QVBoxLayout()
        self.disk_edit = QLineEdit("\\\\.\\H:")
        self.open_btn = QPushButton("打开U盘")
        self.parse_btn = QPushButton("解析FAT32")
        self.file_list = QListWidget()
        left.addWidget(QLabel("U盘路径:"))
        left.addWidget(self.disk_edit)
        left.addWidget(self.open_btn)
        left.addWidget(self.parse_btn)
        left.addWidget(QLabel("目录文件列表:"))
        left.addWidget(self.file_list)

        # 右侧簇状态图
        right = QVBoxLayout()
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        right.addWidget(QLabel("磁盘簇分配状态(绿=空闲,红=占用)"))
        right.addWidget(self.view)

        layout.addLayout(left, 3)
        layout.addLayout(right, 7)
        central.setLayout(layout)

    def draw_cluster_map(self, fat_entries):
        self.scene.clear()
        x, y, w, h = 0, 0, 20, 20
        for i, entry in enumerate(fat_entries[:500]):
            rect = QGraphicsRectItem(x, y, w, h)
            if entry == 0:
                rect.setBrush(QBrush(QColor(0,255,0)))
            else:
                rect.setBrush(QBrush(QColor(255,0,0)))
            self.scene.addItem(rect)
            x += w + 2
            if x > 1000:
                x = 0
                y += h + 2