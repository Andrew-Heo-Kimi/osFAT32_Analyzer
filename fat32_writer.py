# fat32_writer.py - 修复目录写入跨簇问题，增加健壮性
# 新增：create_directory（创建目录）、delete_file（删除文件）

import math
import struct

class FAT32Writer:
    def __init__(self, parser):
        self.parser = parser
        self.disk = parser.disk

    def find_free_clusters(self, count):
        free = []
        for i in range(2, len(self.parser.fat)):
            if self.parser.fat[i] == 0:
                free.append(i)
                if len(free) >= count:
                    return free
        raise Exception("磁盘空间不足")

    def allocate_clusters(self, count):
        clusters = self.find_free_clusters(count)
        for i in range(len(clusters)-1):
            self.parser.fat[clusters[i]] = clusters[i+1]
        self.parser.fat[clusters[-1]] = 0x0FFFFFFF
        return clusters

    def write_fat_table(self):
        fat_start = self.parser.fat_start_sector()
        fat_bytes = b''
        for entry in self.parser.fat:
            fat_bytes += struct.pack("<I", entry)
        sector_size = self.parser.bytes_per_sec
        sector_count = len(fat_bytes) // sector_size
        for i in range(sector_count):
            start = i * sector_size
            end = start + sector_size
            self.disk.write_sector(fat_start + i, fat_bytes[start:end])

    def write_cluster_content(self, cluster_list, content):
        cluster_size = self.parser.bytes_per_sec * self.parser.sec_per_clus
        data = content.encode("utf-8")
        offset = 0
        for cluster in cluster_list:
            sec = self.parser.cluster_to_sector(cluster)
            chunk = data[offset:offset+cluster_size]
            self.disk.write_cluster(sec, self.parser.sec_per_clus, chunk)
            offset += cluster_size

    def create_dir_entry(self, parent_cluster, filename, file_size, start_cluster, attr=0x20):
        """
        在父目录中创建一个新目录项，支持自定义属性（0x20 文件，0x10 目录）
        """
        # 1. 读取父目录的完整数据（所有簇）
        dir_chain = self.parser.get_cluster_chain(parent_cluster)
        dir_data = b''
        for c in dir_chain:
            dir_data += self.parser.read_cluster_data(c)

        # 2. 查找空闲位置（0x00 或 0xE5）
        free_offset = None
        for i in range(0, len(dir_data), 32):
            if dir_data[i] == 0x00 or dir_data[i] == 0xE5:
                free_offset = i
                break
        if free_offset is None:
            raise Exception("目录已满，无法创建新文件")

        # 3. 构造短文件名 (8.3)
        name_part = filename.upper().replace(".", "")[:8].ljust(8)
        ext_part = ""
        if '.' in filename:
            ext_part = filename.split('.')[-1][:3].upper().ljust(3)
        else:
            ext_part = "   "  # 无扩展名
        short_name = (name_part + ext_part).encode()

        # 4. 构建目录项
        high = start_cluster >> 16
        low = start_cluster & 0xFFFF
        entry = bytearray(32)
        entry[0:11] = short_name
        entry[11] = attr        # 使用传入的属性
        # 写入高16位簇号 (偏移20)
        entry[20:22] = struct.pack("<H", high)
        # 写入低16位簇号 (偏移26)
        entry[26:28] = struct.pack("<H", low)
        # 写入文件大小 (偏移28)
        entry[28:32] = struct.pack("<I", file_size)

        # 5. 将新条目写入数据缓冲区
        dir_data = bytearray(dir_data)
        dir_data[free_offset:free_offset+32] = entry

        # 6. 将修改后的目录数据写回所有簇
        cluster_size = self.parser.bytes_per_sec * self.parser.sec_per_clus
        for idx, c in enumerate(dir_chain):
            start = idx * cluster_size
            chunk = dir_data[start:start+cluster_size]
            sec = self.parser.cluster_to_sector(c)
            self.disk.write_cluster(sec, self.parser.sec_per_clus, chunk)

    def create_file(self, parent_cluster, filename, content):
        cluster_size = self.parser.bytes_per_sec * self.parser.sec_per_clus
        file_data = content.encode("utf-8")
        file_size = len(file_data)
        cluster_num = math.ceil(file_size / cluster_size)
        if cluster_num == 0:
            cluster_num = 1

        clusters = self.allocate_clusters(cluster_num)
        self.write_cluster_content(clusters, content)
        self.create_dir_entry(parent_cluster, filename, file_size, clusters[0])
        self.write_fat_table()
        return clusters[0]

    # ---------- 新增：创建目录 ----------
    def create_directory(self, parent_cluster, dirname):
        """
        在指定父目录下创建一个空子目录
        返回新目录的簇号
        """
        # 1. 分配一个簇给新目录（空目录至少占用一个簇）
        clusters = self.allocate_clusters(1)
        new_cluster = clusters[0]
        cluster_size = self.parser.bytes_per_sec * self.parser.sec_per_clus

        # 2. 构建新目录的簇数据（包含 "." 和 ".." 条目）
        dir_data = bytearray(cluster_size)

        # "." 条目
        entry_dot = bytearray(32)
        entry_dot[0:8] = b'.' + b' ' * 7
        entry_dot[8:11] = b'   '
        entry_dot[11] = 0x10               # 目录属性
        entry_dot[26:28] = struct.pack('<H', new_cluster & 0xFFFF)
        entry_dot[20:22] = struct.pack('<H', (new_cluster >> 16) & 0xFFFF)
        dir_data[0:32] = entry_dot

        # ".." 条目
        entry_dotdot = bytearray(32)
        entry_dotdot[0:8] = b'.' + b'.' + b' ' * 6
        entry_dotdot[8:11] = b'   '
        entry_dotdot[11] = 0x10
        entry_dotdot[26:28] = struct.pack('<H', parent_cluster & 0xFFFF)
        entry_dotdot[20:22] = struct.pack('<H', (parent_cluster >> 16) & 0xFFFF)
        dir_data[32:64] = entry_dotdot

        # 写入新簇
        sec = self.parser.cluster_to_sector(new_cluster)
        self.disk.write_cluster(sec, self.parser.sec_per_clus, dir_data)

        # 3. 在父目录中添加该子目录的目录项（属性 0x10）
        self.create_dir_entry(parent_cluster, dirname, 0, new_cluster, attr=0x10)

        # 4. 更新 FAT 表（allocate_clusters 已修改内存，需写回磁盘）
        self.write_fat_table()

        return new_cluster

    # ---------- 新增：删除文件 ----------
    def delete_file(self, parent_cluster, filename):
        """
        删除文件（释放簇链并标记目录项为 0xE5）
        """
        # 构造短文件名 (8.3)
        name_part = filename.upper().replace(".", "")[:8].ljust(8)
        ext_part = ""
        if '.' in filename:
            ext_part = filename.split('.')[-1][:3].upper().ljust(3)
        else:
            ext_part = "   "
        short_name = (name_part + ext_part).encode()

        # 读取父目录所有簇
        dir_chain = self.parser.get_cluster_chain(parent_cluster)
        dir_data = b''
        for c in dir_chain:
            dir_data += self.parser.read_cluster_data(c)

        # 查找匹配的目录项（跳过已删除项和长文件名项）
        offset = None
        for i in range(0, len(dir_data), 32):
            raw = dir_data[i:i+32]
            if raw[0] == 0xE5 or raw[0] == 0x00:
                continue
            attr = raw[11]
            if attr == 0x0F:   # LFN 项，跳过
                continue
            if raw[0:11] == short_name:
                offset = i
                break

        if offset is None:
            raise Exception(f"文件 '{filename}' 未找到")

        # 解析起始簇号
        entry = self.parser.DIR_ENTRY.parse(dir_data[offset:offset+32])
        start_cluster = (entry.DIR_FstClusHI << 16) | entry.DIR_FstClusLO

        # 释放簇链（FAT 表项置 0）
        current = start_cluster
        while current >= 2 and current < 0x0FFFFFF8:
            next_cluster = self.parser.fat[current]
            self.parser.fat[current] = 0
            current = next_cluster

        # 标记目录项为已删除 (0xE5)
        dir_data = bytearray(dir_data)
        dir_data[offset] = 0xE5

        # 将修改后的目录数据写回所有簇
        cluster_size = self.parser.bytes_per_sec * self.parser.sec_per_clus
        for idx, c in enumerate(dir_chain):
            start = idx * cluster_size
            chunk = dir_data[start:start+cluster_size]
            sec = self.parser.cluster_to_sector(c)
            self.disk.write_cluster(sec, self.parser.sec_per_clus, chunk)

        # 写回 FAT 表
        self.write_fat_table()
        return True