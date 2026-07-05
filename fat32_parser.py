# fat32_parser.py - 修复 LFN 解析与目录读取稳定性

import construct as c

FAT32_BPB = c.Struct(
    "BS_jmpBoot"/c.Bytes(3),
    "BS_OEMName"/c.Bytes(8),
    "BPB_BytsPerSec"/c.Int16ul,
    "BPB_SecPerClus"/c.Byte,
    "BPB_RsvdSecCnt"/c.Int16ul,
    "BPB_NumFATs"/c.Byte,
    "BPB_RootEntCnt"/c.Int16ul,
    "BPB_TotSec16"/c.Int16ul,
    "BPB_Media"/c.Byte,
    "BPB_FATSz16"/c.Int16ul,
    "BPB_SecPerTrk"/c.Int16ul,
    "BPB_NumHeads"/c.Int16ul,
    "BPB_HiddSec"/c.Int32ul,
    "BPB_TotSec32"/c.Int32ul,
    "BPB_FATSz32"/c.Int32ul,
    "BPB_ExtFlags"/c.Int16ul,
    "BPB_FSVer"/c.Int16ul,
    "BPB_RootClus"/c.Int32ul,
    "BPB_FSInfo"/c.Int16ul,
    "BPB_BkBootSec"/c.Int16ul,
    c.Padding(12)
)

DIR_ENTRY = c.Struct(
    "DIR_Name"/c.Bytes(11),
    "DIR_Attr"/c.Byte,
    "DIR_NTRes"/c.Byte,
    "DIR_CrtTimeTenth"/c.Byte,
    "DIR_CrtTime"/c.Int16ul,
    "DIR_CrtDate"/c.Int16ul,
    "DIR_LstAccDate"/c.Int16ul,
    "DIR_FstClusHI"/c.Int16ul,
    "DIR_WrtTime"/c.Int16ul,
    "DIR_WrtDate"/c.Int16ul,
    "DIR_FstClusLO"/c.Int16ul,
    "DIR_FileSize"/c.Int32ul
)

class FAT32Parser:
    def __init__(self, disk):
        self.disk = disk
        self.bpb = None
        self.bytes_per_sec = 512
        self.sec_per_clus = 0
        self.rsvd_sec_cnt = 0
        self.num_fats = 0
        self.fat_sz = 0
        self.root_clus = 2
        self.fat = []

    def parse_bpb(self):
        boot = self.disk.read_sector(0)
        self.bpb = FAT32_BPB.parse(boot)
        self.bytes_per_sec = self.bpb.BPB_BytsPerSec
        self.sec_per_clus = self.bpb.BPB_SecPerClus
        self.rsvd_sec_cnt = self.bpb.BPB_RsvdSecCnt
        self.num_fats = self.bpb.BPB_NumFATs
        self.fat_sz = self.bpb.BPB_FATSz32
        self.root_clus = self.bpb.BPB_RootClus

    def fat_start_sector(self):
        return self.rsvd_sec_cnt

    def data_start_sector(self):
        return self.rsvd_sec_cnt + self.num_fats * self.fat_sz

    def cluster_to_sector(self, cluster):
        return self.data_start_sector() + (cluster - 2) * self.sec_per_clus

    def read_fat(self):
        fat_start = self.fat_start_sector()
        total_bytes = self.fat_sz * self.bytes_per_sec
        fat_data = bytearray(total_bytes)
        pos = 0
        for i in range(self.fat_sz):
            sec_data = self.disk.read_sector(fat_start + i)
            fat_data[pos:pos+self.bytes_per_sec] = sec_data
            pos += self.bytes_per_sec
        self.fat = []
        for i in range(0, len(fat_data), 4):
            entry = int.from_bytes(fat_data[i:i+4], "little") & 0x0FFFFFFF
            self.fat.append(entry)
        return self.fat

    def get_cluster_chain(self, start_cluster):
        chain = []
        current = start_cluster
        while True:
            if current >= 0x0FFFFFF8 or current == 0:
                break
            chain.append(current)
            current = self.fat[current]
        return chain

    def read_cluster_data(self, cluster):
        sec = self.cluster_to_sector(cluster)
        return self.disk.read_cluster(sec, self.sec_per_clus)

    def parse_lfn(self, data):
        """解析长文件名片段"""
        name = ""
        for offset in [(1,11), (14,26), (28,32)]:
            x = data[offset[0]:offset[1]]
            try:
                name += x.decode("utf-16le")
            except:
                pass
        # 移除无效字符
        name = name.replace('\xff', '').replace('\x00', '')
        return name

    def read_directory(self, cluster):
        """读取目录所有簇的数据，返回目录项列表"""
        chain = self.get_cluster_chain(cluster)
        dir_data = b''
        for c in chain:
            dir_data += self.read_cluster_data(c)

        result = []
        long_name = ""
        for i in range(0, len(dir_data), 32):
            raw = dir_data[i:i+32]
            if raw[0] == 0:
                break
            if raw[0] == 0xE5:
                continue

            attr = raw[11]
            if attr == 0x0F:   # 长文件名项
                long_name = self.parse_lfn(raw) + long_name
                continue

            entry = DIR_ENTRY.parse(raw)
            cluster = (entry.DIR_FstClusHI << 16) | entry.DIR_FstClusLO
            short_name = entry.DIR_Name.decode(errors="ignore").strip()
            name = long_name if long_name else short_name
            long_name = ""

            item = {
                "name": name,
                "size": entry.DIR_FileSize,
                "cluster": cluster,
                "is_dir": bool(entry.DIR_Attr & 0x10),
                "attr": entry.DIR_Attr
            }
            result.append(item)
        return result

    def get_free_clusters(self):
        return sum(1 for v in self.fat if v == 0)

    def get_file_clusters(self, start_cluster):
        return self.get_cluster_chain(start_cluster)