# gui.py - 增强版：目录树 + 文件预览 + 右键菜单 + 新建目录/删除文件

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

class FAT32GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FAT32 文件系统浏览器")
        self.resize(1400, 800)
        self.init_ui()

    def init_ui(self):
        center = QWidget()
        self.setCentralWidget(center)
        layout = QHBoxLayout()

        # ----- 左侧：设备控制 + 目录树 -----
        left = QVBoxLayout()
        self.disk_edit = QLineEdit()
        self.disk_edit.setPlaceholderText("请输入设备或映像路径，如 D:/fat32.img")
        self.open_btn = QPushButton("打开磁盘")
        self.parse_btn = QPushButton("解析 FAT32")
        self.create_btn = QPushButton("新建文件")
        self.mkdir_btn = QPushButton("新建目录")          # 新增
        self.delete_btn = QPushButton("删除文件")        # 新增

        self.dir_tree = QTreeWidget()
        self.dir_tree.setHeaderLabels(["目录树"])
        self.dir_tree.setMinimumWidth(200)

        left.addWidget(QLabel("设备路径"))
        left.addWidget(self.disk_edit)
        left.addWidget(self.open_btn)
        left.addWidget(self.parse_btn)
        left.addWidget(self.create_btn)
        left.addWidget(self.mkdir_btn)                  # 新增
        left.addWidget(self.delete_btn)                # 新增
        left.addWidget(QLabel("目录结构"))
        left.addWidget(self.dir_tree)

        # ----- 中间：文件列表 + 导航栏 -----
        mid = QVBoxLayout()
        nav_layout = QHBoxLayout()
        self.path_edit = QLineEdit("/")
        self.path_edit.setReadOnly(True)
        self.path_edit.setStyleSheet("background-color: #f0f0f0;")
        self.btn_up = QPushButton("⬆ 上级")
        self.btn_root = QPushButton("🏠 根目录")
        self.btn_refresh = QPushButton("🔄 刷新")

        nav_layout.addWidget(QLabel("路径:"))
        nav_layout.addWidget(self.path_edit, 1)
        nav_layout.addWidget(self.btn_up)
        nav_layout.addWidget(self.btn_root)
        nav_layout.addWidget(self.btn_refresh)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["文件名", "类型", "大小 (字节)", "起始簇"])
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_table_context_menu)

        mid.addWidget(QLabel("目录内容"))
        mid.addLayout(nav_layout)
        mid.addWidget(self.file_table)

        # ----- 右侧：簇状态图 + 信息面板 -----
        right = QVBoxLayout()
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(200)

        right.addWidget(QLabel("磁盘簇状态（蓝：选中，绿：空闲，红：占用）"))
        right.addWidget(self.view)
        right.addWidget(QLabel("文件/目录信息"))
        right.addWidget(self.info_text)

        # ----- 布局组合 -----
        layout.addLayout(left, 2)
        layout.addLayout(mid, 4)
        layout.addLayout(right, 5)
        center.setLayout(layout)

    # ---------- 界面更新方法 ----------
    def show_files(self, entries):
        """更新文件列表表格"""
        self.file_table.clearContents()
        self.file_table.setRowCount(len(entries))
        for row, item in enumerate(entries):
            name = item["name"]
            size = item["size"]
            cluster = item["cluster"]
            t = "📁 目录" if item["is_dir"] else "📄 文件"
            self.file_table.setItem(row, 0, QTableWidgetItem(name))
            self.file_table.setItem(row, 1, QTableWidgetItem(t))
            self.file_table.setItem(row, 2, QTableWidgetItem(str(size)))
            self.file_table.setItem(row, 3, QTableWidgetItem(str(cluster)))

    def draw_cluster_map(self, fat, file_clusters=None):
        """绘制簇状态图（仅显示前 1200 个簇）"""
        self.scene.clear()
        if file_clusters is None:
            file_clusters = []
        width = 16
        height = 16
        x, y = 0, 0
        for i, v in enumerate(fat[2:1202]):  # 显示 1200 个簇
            rect = QGraphicsRectItem(x, y, width, height)
            if i in file_clusters:
                color = QColor(0, 0, 255)      # 蓝色
            elif v == 0:
                color = QColor(0, 255, 0)      # 绿色
            else:
                color = QColor(255, 0, 0)      # 红色
            rect.setBrush(QBrush(color))
            rect.setToolTip(f"簇 {i+2}: {hex(v)}")
            self.scene.addItem(rect)
            x += 18
            if x > 800:
                x = 0
                y += 18

    def show_info(self, text):
        """显示信息面板"""
        self.info_text.clear()
        self.info_text.append(text)

    def set_path(self, path_str):
        """更新路径显示"""
        self.path_edit.setText(path_str)

    def populate_tree(self, parser, root_cluster, parent_item=None):
        """
        递归构建目录树
        返回根节点（用于后续点击事件）
        """
        if parent_item is None:
            self.dir_tree.clear()
            root_item = QTreeWidgetItem(self.dir_tree)
            root_item.setText(0, "/")
            root_item.setData(0, Qt.UserRole, root_cluster)
            root_item.setExpanded(True)
            parent_item = root_item

        # 读取当前目录下的子目录
        entries = parser.read_directory(root_cluster)
        for entry in entries:
            if entry["is_dir"] and entry["name"] not in (".", ".."):
                child = QTreeWidgetItem(parent_item)
                child.setText(0, entry["name"])
                child.setData(0, Qt.UserRole, entry["cluster"])
                # 递归填充（对于小磁盘可直接全部展开）
                self.populate_tree(parser, entry["cluster"], child)
        return parent_item

    # ---------- 右键菜单 ----------
    def show_table_context_menu(self, pos):
        row = self.file_table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu()
        open_action = QAction("打开", self)
        prop_action = QAction("属性", self)
        delete_action = QAction("删除", self)        # 新增
        menu.addAction(open_action)
        menu.addAction(prop_action)
        menu.addAction(delete_action)               # 新增
        action = menu.exec_(self.file_table.viewport().mapToGlobal(pos))
        if action == open_action:
            self.file_table.cellDoubleClicked.emit(row, 0)
        elif action == prop_action:
            self.file_table.cellClicked.emit(row, 0)
        elif action == delete_action:               # 新增
            # 触发删除，由主窗口处理（需要传递信号或直接调用主窗口方法）
            # 这里我们通过自定义信号或者直接获取父窗口调用方法，但为了简单，我们模拟点击删除按钮
            # 或者我们可以在主窗口连接右键菜单的触发，但此处暂不实现，由主窗口监听
            pass