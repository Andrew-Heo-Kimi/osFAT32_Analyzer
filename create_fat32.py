#!/usr/bin/env python3
"""
FAT32 空白映像生成器（修复整数类型错误）
用法：python create_fat32.py 输出文件路径 [大小MB]
示例：python create_fat32.py D:/fat32.img 128
"""

import os
import sys
import struct

# ---------- FAT32 常量 ----------
FAT32_EOF      = 0x0FFFFFFF
FAT32_BAD      = 0x0FFFFFF7
FAT32_FREE     = 0x00000000
ATTR_DIRECTORY = 0x10

class FAT32Formatter:
    """
    FAT32 格式化器，生成一个空白的 FAT32 映像文件。
    """

    def __init__(self, image_path, size_mb):
        """
        :param image_path: 保存路径，如 "D:/my.img"
        :param size_mb:    映像大小（MB），必须为整数，建议 ≥ 64
        """
        # 强制类型检查
        if not isinstance(size_mb, int):
            raise TypeError("size_mb 必须是整数")
        if size_mb < 64:
            print("警告：大小小于 64MB，自动设为 64MB")
            size_mb = 64

        self.image_path = image_path
        self.size_mb = size_mb

        # FAT32 固定参数
        self.bytes_per_sector = 512
        self.sectors_per_cluster = 8      # 4KB 每簇
        self.reserved_sectors = 32        # 保留扇区数
        self.num_fats = 2                 # FAT 副本数

        # 总扇区数
        self.total_sectors = (size_mb * 1024 * 1024) // self.bytes_per_sector

        # 计算 FAT 大小（扇区数）和总簇数
        self._calc_fat_size()

        # 数据区起始扇区
        self.data_start_sector = self.reserved_sectors + self.num_fats * self.sectors_per_fat

        # 根目录簇号（FAT32 固定为 2）
        self.root_cluster = 2

    def _calc_fat_size(self):
        """
        纯整数迭代法计算 FAT 表所需扇区数。
        """
        fat_sectors = 1  # 初始假设 1 个扇区
        while True:
            # 数据区起始扇区
            data_start = self.reserved_sectors + self.num_fats * fat_sectors
            # 数据区扇区数
            data_sectors = self.total_sectors - data_start
            # 可容纳的簇数
            clusters = data_sectors // self.sectors_per_cluster
            # 根据簇数计算需要的 FAT 扇区数（每簇 4 字节）
            needed = ((clusters + 2) * 4 + self.bytes_per_sector - 1) // self.bytes_per_sector
            if needed == fat_sectors:
                break
            fat_sectors = needed

        self.sectors_per_fat = fat_sectors
        # 重新计算实际总簇数
        data_start = self.reserved_sectors + self.num_fats * fat_sectors
        data_sectors = self.total_sectors - data_start
        self.total_clusters = data_sectors // self.sectors_per_cluster

    def _write_dbr(self, f):
        """写入引导扇区 (DBR)"""
        dbr = bytearray(512)

        dbr[0:3]   = b'\xEB\x58\x90'
        dbr[3:11]  = b'MSDOS5.0'

        struct.pack_into('<H', dbr, 0x0B, self.bytes_per_sector)
        struct.pack_into('<B', dbr, 0x0D, self.sectors_per_cluster)
        struct.pack_into('<H', dbr, 0x0E, self.reserved_sectors)
        struct.pack_into('<B', dbr, 0x10, self.num_fats)
        dbr[0x11:0x12] = b'\x00'
        struct.pack_into('<H', dbr, 0x12, 0)
        dbr[0x14] = 0xF8
        struct.pack_into('<H', dbr, 0x15, 0)
        struct.pack_into('<H', dbr, 0x18, 0x3F)
        struct.pack_into('<H', dbr, 0x1A, 0xFF)
        struct.pack_into('<I', dbr, 0x1C, 0x3F)
        struct.pack_into('<I', dbr, 0x20, self.total_sectors)
        struct.pack_into('<I', dbr, 0x24, self.sectors_per_fat)
        struct.pack_into('<H', dbr, 0x28, 0)
        struct.pack_into('<H', dbr, 0x2A, 0)
        struct.pack_into('<I', dbr, 0x2C, self.root_cluster)
        struct.pack_into('<H', dbr, 0x30, 1)
        struct.pack_into('<H', dbr, 0x32, 6)

        dbr[0x40:0x1FE] = b'\x00' * (0x1FE - 0x40)
        dbr[0x1FE] = 0x55
        dbr[0x1FF] = 0xAA

        f.write(dbr)

    def _write_fat(self, f):
        """写入 FAT 表（全部标记为空闲）"""
        fat_size = self.sectors_per_fat * self.bytes_per_sector
        fat_table = bytearray(fat_size)

        # 表项 0 和 1 保留
        struct.pack_into('<I', fat_table, 0, 0x0FFFFFF8)
        struct.pack_into('<I', fat_table, 4, 0x0FFFFFFF)

        for _ in range(self.num_fats):
            f.write(fat_table)

    def _write_root_dir(self, f):
        """写入根目录（仅包含 "." 和 ".."）"""
        cluster_size = self.bytes_per_sector * self.sectors_per_cluster
        dir_data = bytearray(cluster_size)

        # "." 条目
        entry_dot = bytearray(32)
        entry_dot[0:8]   = b'.' + b' ' * 7
        entry_dot[8:11]  = b'   '
        entry_dot[0x0B]  = ATTR_DIRECTORY
        entry_dot[0x1A:0x1C] = struct.pack('<H', self.root_cluster & 0xFFFF)
        entry_dot[0x14:0x16] = struct.pack('<H', (self.root_cluster >> 16) & 0xFFFF)
        dir_data[0:32] = entry_dot

        # ".." 条目（根目录下指向自己）
        entry_dotdot = bytearray(32)
        entry_dotdot[0:8]   = b'.' + b'.' + b' ' * 6
        entry_dotdot[8:11]  = b'   '
        entry_dotdot[0x0B]  = ATTR_DIRECTORY
        entry_dotdot[0x1A:0x1C] = struct.pack('<H', self.root_cluster & 0xFFFF)
        entry_dotdot[0x14:0x16] = struct.pack('<H', (self.root_cluster >> 16) & 0xFFFF)
        dir_data[32:64] = entry_dotdot

        f.write(dir_data)

    def format(self):
        """执行格式化，生成映像文件"""
        try:
            with open(self.image_path, 'wb') as f:
                # 预分配文件大小
                f.truncate(self.total_sectors * self.bytes_per_sector)
                f.seek(0)

                # 写入 DBR
                self._write_dbr(f)

                # 填充保留扇区剩余部分（全 0）
                zero = b'\x00' * self.bytes_per_sector
                for _ in range(1, self.reserved_sectors):
                    f.write(zero)

                # 写入两个 FAT 表
                self._write_fat(f)

                # 定位到数据区，写入根目录
                f.seek(self.data_start_sector * self.bytes_per_sector)
                self._write_root_dir(f)

            return True
        except Exception as e:
            raise e


def main():
    if len(sys.argv) < 2:
        print("用法: python create_fat32.py <映像文件路径> [大小MB]")
        print("示例: python create_fat32.py D:/fat32.img 128")
        sys.exit(1)

    img_path = sys.argv[1]

    # 解析大小参数
    if len(sys.argv) >= 3:
        try:
            size_mb = int(sys.argv[2])
        except ValueError:
            print(f"错误: 大小参数 '{sys.argv[2]}' 不是有效整数，使用默认 64MB")
            size_mb = 64
    else:
        size_mb = 64

    if size_mb < 64:
        print("警告: 大小小于 64MB，自动设为 64MB")
        size_mb = 64

    try:
        formatter = FAT32Formatter(img_path, size_mb)
        formatter.format()
        print(f"✅ 成功创建 FAT32 映像: {img_path}")
        print(f"   大小: {size_mb} MB")
        print(f"   总扇区: {formatter.total_sectors}")
        print(f"   每簇扇区: {formatter.sectors_per_cluster}")
        print(f"   FAT 大小: {formatter.sectors_per_fat} 扇区")
        print(f"   总簇数: {formatter.total_clusters}")
        print("   根目录已初始化（空）")
    except Exception as e:
        print(f"❌ 格式化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()