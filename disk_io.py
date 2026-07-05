# disk_io.py - 增强版，添加重试与 flush
import time

class DiskIO:
    def __init__(self, disk_path):
        self.disk_path = disk_path
        self.f = None
        self.sector_size = 512
        self.max_retries = 3          # 读写重试次数

    def open_disk(self):
        """以二进制读写模式打开设备或文件"""
        try:
            self.f = open(self.disk_path, "rb+")
        except Exception as e:
            raise Exception(f"磁盘打开失败: {str(e)}")

    def read_sector(self, sector_num, sector_size=None):
        if sector_size is None:
            sector_size = self.sector_size
        offset = sector_num * sector_size
        for attempt in range(self.max_retries):
            try:
                self.f.seek(offset)
                data = self.f.read(sector_size)
                if len(data) == sector_size:
                    return data
                # 读取不足，可能设备繁忙，稍后重试
                time.sleep(0.1)
            except Exception:
                time.sleep(0.2)
        raise Exception(f"读取扇区 {sector_num} 失败，重试耗尽")

    def write_sector(self, sector_num, data, sector_size=None):
        if sector_size is None:
            sector_size = self.sector_size
        offset = sector_num * sector_size
        buf = data.ljust(sector_size, b'\x00')
        for attempt in range(self.max_retries):
            try:
                self.f.seek(offset)
                self.f.write(buf)
                self.f.flush()               # 强制刷新到磁盘
                return
            except Exception:
                time.sleep(0.2)
        raise Exception(f"写入扇区 {sector_num} 失败，重试耗尽")

    def read_cluster(self, first_sector, sec_per_cluster):
        total = sec_per_cluster * self.sector_size
        offset = first_sector * self.sector_size
        for attempt in range(self.max_retries):
            try:
                self.f.seek(offset)
                return self.f.read(total)
            except Exception:
                time.sleep(0.2)
        raise Exception(f"读取簇（起始扇区 {first_sector}）失败")

    def write_cluster(self, first_sector, sec_per_cluster, data):
        total = sec_per_cluster * self.sector_size
        offset = first_sector * self.sector_size
        buf = bytearray(total)
        buf[:len(data)] = data
        for attempt in range(self.max_retries):
            try:
                self.f.seek(offset)
                self.f.write(buf)
                self.f.flush()
                return
            except Exception:
                time.sleep(0.2)
        raise Exception(f"写入簇（起始扇区 {first_sector}）失败")

    def close_disk(self):
        if self.f:
            self.f.close()
            self.f = None

    def __del__(self):
        self.close_disk()