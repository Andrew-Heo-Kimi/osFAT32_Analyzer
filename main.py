# main.py - 增强版：目录树点击、文件预览、右键菜单、新建目录、删除文件

import sys
import os
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from disk_io import DiskIO
from fat32_parser import FAT32Parser
from fat32_writer import FAT32Writer
from gui import FAT32GUI

class ParseThread(QThread):
    finish_sig = pyqtSignal(FAT32Parser, FAT32Writer)
    err_sig = pyqtSignal(str)

    def __init__(self, disk_obj):
        super().__init__()
        self.disk = disk_obj

    def run(self):
        try:
            parser = FAT32Parser(self.disk)
            parser.parse_bpb()
            parser.read_fat()
            writer = FAT32Writer(parser)
            self.finish_sig.emit(parser, writer)
        except Exception as e:
            self.err_sig.emit(str(e))

class MainApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.gui = FAT32GUI()
        self.disk = None
        self.parser = None
        self.writer = None
        self.current_cluster = None
        self.current_entries = []

        # 路径管理
        self.path_stack = []
        self.current_path = "/"

        self.connect_signal()
        self.gui.show()

    def connect_signal(self):
        self.gui.open_btn.clicked.connect(self.open_disk)
        self.gui.parse_btn.clicked.connect(self.parse_fat)
        self.gui.create_btn.clicked.connect(self.create_file)
        self.gui.mkdir_btn.clicked.connect(self.create_directory)      # 新增
        self.gui.delete_btn.clicked.connect(self.delete_selected)      # 新增
        self.gui.file_table.cellClicked.connect(self.select_item)
        self.gui.file_table.cellDoubleClicked.connect(self.open_item)
        self.gui.btn_up.clicked.connect(self.go_up)
        self.gui.btn_root.clicked.connect(self.go_root)
        self.gui.btn_refresh.clicked.connect(self.refresh_current)
        self.gui.dir_tree.itemClicked.connect(self.tree_item_clicked)
        # 双击磁盘路径可浏览文件
        self.gui.disk_edit.mouseDoubleClickEvent = self.browse_image

    def browse_image(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self.gui, "选择磁盘或映像文件", "",
            "所有文件 (*.*);;映像文件 (*.img *.bin);;物理磁盘 (\\\\.\\*)"
        )
        if path:
            self.gui.disk_edit.setText(path)

    def open_disk(self):
        path = self.gui.disk_edit.text().strip()
        if not path:
            QMessageBox.warning(self.gui, "提示", "请输入设备或映像文件路径")
            return
        try:
            self.disk = DiskIO(path)
            self.disk.open_disk()
            QMessageBox.information(self.gui, "成功", "磁盘打开成功")
        except Exception as e:
            QMessageBox.critical(self.gui, "错误", str(e))

    def parse_fat(self):
        if self.disk is None or self.disk.f is None:
            QMessageBox.warning(self.gui, "提示", "请先打开磁盘")
            return
        self.parse_thread = ParseThread(self.disk)
        self.parse_thread.finish_sig.connect(self.parse_done)
        self.parse_thread.err_sig.connect(lambda msg: QMessageBox.critical(self.gui, "解析失败", msg))
        self.parse_thread.start()

    def parse_done(self, parser, writer):
        self.parser = parser
        self.writer = writer
        self.current_cluster = parser.root_clus
        self.current_path = "/"
        self.path_stack.clear()
        self.gui.set_path(self.current_path)
        self.load_directory(self.current_cluster)
        # 构建目录树
        self.gui.populate_tree(parser, parser.root_clus)
        free = self.parser.get_free_clusters()
        info = f"""FAT32 解析完成
每扇区：{self.parser.bytes_per_sec}
每簇扇区：{self.parser.sec_per_clus}
根目录簇：{self.parser.root_clus}
空闲簇总数：{free}"""
        self.gui.show_info(info)

    def load_directory(self, cluster):
        """加载指定簇的目录内容"""
        entries = self.parser.read_directory(cluster)
        self.gui.show_files(entries)
        self.gui.draw_cluster_map(self.parser.fat)
        self.current_entries = entries
        self.current_cluster = cluster

    def select_item(self, row, col):
        """点击表格项显示簇链信息"""
        if row < 0 or row >= len(self.current_entries):
            return
        item = self.current_entries[row]
        cluster = item["cluster"]
        chain = self.parser.get_file_clusters(cluster)
        self.gui.draw_cluster_map(self.parser.fat, chain)
        text = f"""
名称: {item["name"]}
大小: {item["size"]} 字节
起始簇: {cluster}
类型: {"目录" if item["is_dir"] else "文件"}
占用簇: {chain}
"""
        self.gui.show_info(text)

    def open_item(self, row, col):
        """双击打开：目录则进入，文件则预览内容"""
        if row < 0 or row >= len(self.current_entries):
            return
        item = self.current_entries[row]
        if item["is_dir"]:
            self.enter_directory(item)
        else:
            self.preview_file(item)

    def enter_directory(self, item):
        cluster = item["cluster"]
        if cluster < 2:
            return
        self.path_stack.append((self.current_path, self.current_cluster))
        if self.current_path == "/":
            new_path = "/" + item["name"]
        else:
            new_path = self.current_path + "/" + item["name"]
        self.current_path = new_path
        self.gui.set_path(self.current_path)
        self.load_directory(cluster)

    def preview_file(self, item):
        """预览文件内容（文本或十六进制）"""
        cluster = item["cluster"]
        chain = self.parser.get_file_clusters(cluster)
        data = b""
        for c in chain:
            data += self.parser.read_cluster_data(c)
        # 截取实际文件大小
        data = data[:item["size"]]

        # 尝试判断是否为文本
        try:
            text = data.decode("utf-8")
            preview = f"【文本预览】\n{text}"
        except UnicodeDecodeError:
            # 显示十六进制
            hex_str = " ".join(f"{b:02x}" for b in data[:256])
            if len(data) > 256:
                hex_str += " ... (截断)"
            preview = f"【二进制预览（前256字节）】\n{hex_str}"

        QMessageBox.information(self.gui, f"文件: {item['name']}", preview)

    def tree_item_clicked(self, item, column):
        """点击目录树节点，切换到对应目录"""
        cluster = item.data(0, Qt.UserRole)
        if cluster is not None and cluster >= 2:
            # 重建路径字符串
            path_parts = []
            node = item
            while node.parent() is not None:
                path_parts.insert(0, node.text(0))
                node = node.parent()
            new_path = "/" + "/".join(path_parts)
            self.path_stack.clear()
            self.current_path = new_path
            self.gui.set_path(new_path)
            self.load_directory(cluster)

    def go_up(self):
        if not self.path_stack:
            QMessageBox.information(self.gui, "提示", "已在根目录")
            return
        prev_path, prev_cluster = self.path_stack.pop()
        self.current_path = prev_path
        self.gui.set_path(self.current_path)
        self.load_directory(prev_cluster)

    def go_root(self):
        self.path_stack.clear()
        self.current_path = "/"
        self.gui.set_path(self.current_path)
        self.load_directory(self.parser.root_clus)

    def refresh_current(self):
        if self.parser:
            self.parser.read_fat()
            self.load_directory(self.current_cluster)
            self.gui.show_info("已刷新")

    def create_file(self):
        if not self.writer:
            QMessageBox.warning(self.gui, "提示", "请先解析 FAT32")
            return
        filename, ok = QInputDialog.getText(self.gui, "创建文件", "文件名")
        if not ok or not filename:
            return
        content, ok = QInputDialog.getMultiLineText(self.gui, "内容", "输入文件内容")
        if not ok:
            return
        try:
            self.writer.create_file(self.current_cluster, filename, content)
            QMessageBox.information(self.gui, "成功", "文件创建成功")
            self.parser.read_fat()
            self.load_directory(self.current_cluster)
            # 刷新目录树（简单起见，重新构建）
            self.gui.populate_tree(self.parser, self.parser.root_clus)
        except Exception as e:
            QMessageBox.critical(self.gui, "错误", str(e))

    # ---------- 新增：创建目录 ----------
    def create_directory(self):
        if not self.writer:
            QMessageBox.warning(self.gui, "提示", "请先解析 FAT32")
            return
        dirname, ok = QInputDialog.getText(self.gui, "创建目录", "请输入目录名")
        if not ok or not dirname:
            return
        try:
            new_cluster = self.writer.create_directory(self.current_cluster, dirname)
            QMessageBox.information(self.gui, "成功", f"目录 '{dirname}' 创建成功 (簇 {new_cluster})")
            self.parser.read_fat()
            self.load_directory(self.current_cluster)
            self.gui.populate_tree(self.parser, self.parser.root_clus)
        except Exception as e:
            QMessageBox.critical(self.gui, "错误", str(e))

    # ---------- 新增：删除文件 ----------
    def delete_selected(self):
        if not self.writer:
            QMessageBox.warning(self.gui, "提示", "请先解析 FAT32")
            return
        current_row = self.gui.file_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self.gui, "提示", "请先在文件列表中选择一个文件")
            return
        item = self.current_entries[current_row]
        if item["is_dir"]:
            QMessageBox.warning(self.gui, "提示", "暂不支持删除目录，仅可删除文件")
            return
        filename = item["name"]
        reply = QMessageBox.question(self.gui, "确认删除",
                                     f"确定要删除文件 '{filename}' 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self.writer.delete_file(self.current_cluster, filename)
            QMessageBox.information(self.gui, "成功", f"文件 '{filename}' 已删除")
            self.parser.read_fat()
            self.load_directory(self.current_cluster)
            # 目录树无需刷新（文件不影响目录结构）
        except Exception as e:
            QMessageBox.critical(self.gui, "删除失败", str(e))

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    MainApp().run()