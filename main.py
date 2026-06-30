import sys
from disk_io import DiskIO
from fat32_parser import FAT32Parser
from gui import FAT32GUI
from PyQt5.QtWidgets import QApplication,QMessageBox

class MainApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.gui = FAT32GUI()
        self.disk_io = None
        self.parser = None
        self.connect_slots()
        self.gui.show()

    def connect_slots(self):
        self.gui.open_btn.clicked.connect(self.open_disk)
        self.gui.parse_btn.clicked.connect(self.parse_fat32)

    def open_disk(self):
        path = self.gui.disk_edit.text()
        try:
            self.disk_io = DiskIO(path)
            self.disk_io.open_disk()
            QMessageBox.information(self.gui, "成功", "U盘打开成功")
        except Exception as e:
            QMessageBox.critical(self.gui, "错误", f"打开失败:{str(e)}")

    def parse_fat32(self):
        if not self.disk_io:
            QMessageBox.warning(self.gui, "提示", "先打开U盘")
            return
        try:
            self.parser = FAT32Parser(self.disk_io)
            self.parser.parse_bpb()
            fat = self.parser.read_fat()
            self.gui.draw_cluster_map(fat)
            root_entries = self.parser.read_dir(self.parser.root_clus, fat)
            self.gui.file_list.clear()
            for e in root_entries:
                name = e.DIR_Name.decode("gbk", errors='ignore').strip()
                size = e.DIR_FileSize
                attr = e.DIR_Attr
                typ = "目录" if attr & 0x10 else "文件"
                self.gui.file_list.addItem(f"{typ} | {name} | 大小:{size}")
        except Exception as e:
            QMessageBox.critical(self.gui, "解析错误", str(e))

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    MainApp().run()