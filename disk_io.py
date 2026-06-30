import os
import platform

class DiskIO:
    def __init__(self, disk_path):
        self.disk_path = disk_path
        self.fd = None

    def open_disk(self):
        if platform.system() != "Windows":
            raise Exception("仅支持Windows系统")
        self.fd = os.open(self.disk_path, os.O_BINARY | os.O_RDWR)

    def read_sector(self, sector_num, sector_size=512):
        os.lseek(self.fd, sector_num * sector_size, os.SEEK_SET)
        return os.read(self.fd, sector_size)

    def write_sector(self, sector_num, data, sector_size=512):
        os.lseek(self.fd, sector_num * sector_size, os.SEEK_SET)
        os.write(self.fd, data.ljust(sector_size, b'\x00'))

    def close_disk(self):
        if self.fd:
            os.close(self.fd)