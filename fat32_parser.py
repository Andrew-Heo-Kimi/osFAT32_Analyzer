import construct as c

# FAT32 BPB结构定义
FAT32_BPB = c.Struct(
    "BS_jmpBoot" / c.Bytes(3),
    "BS_OEMName" / c.Bytes(8),
    "BPB_BytsPerSec" / c.Int16ul,
    "BPB_SecPerClus" / c.Byte,
    "BPB_RsvdSecCnt" / c.Int16ul,
    "BPB_NumFATs" / c.Byte,
    "BPB_RootEntCnt" / c.Int16ul,
    "BPB_TotSec16" / c.Int16ul,
    "BPB_Media" / c.Byte,
    "BPB_FATSz16" / c.Int16ul,
    "BPB_SecPerTrk" / c.Int16ul,
    "BPB_NumHeads" / c.Int16ul,
    "BPB_HiddSec" / c.Int32ul,
    "BPB_TotSec32" / c.Int32ul,
    "BPB_FATSz32" / c.Int32ul,
    "BPB_ExtFlags" / c.Int16ul,
    "BPB_FSVer" / c.Int16ul,
    "BPB_RootClus" / c.Int32ul,
    "BPB_FSInfo" / c.Int16ul,
    "BPB_BkBootSec" / c.Int16ul,
    "BPB_Reserved" / c.Bytes(12),
    "BS_DrvNum" / c.Byte,
    "BS_Reserved1" / c.Byte,
    "BS_BootSig" / c.Byte,
    "BS_VolID" / c.Int32ul,
    "BS_VolLab" / c.Bytes(11),
    "BS_FilSysType" / c.Bytes(8),
    c.Padding(420),
    "Signature" / c.Int16ul
)

# 目录项结构
DIR_ENTRY = c.Struct(
    "DIR_Name" / c.Bytes(11),
    "DIR_Attr" / c.Byte,
    "DIR_NTRes" / c.Byte,
    "DIR_CrtTimeTenth" / c.Byte,
    "DIR_CrtTime" / c.Int16ul,
    "DIR_CrtDate" / c.Int16ul,
    "DIR_LstAccDate" / c.Int16ul,
    "DIR_FstClusHI" / c.Int16ul,
    "DIR_WrtTime" / c.Int16ul,
    "DIR_WrtDate" / c.Int16ul,
    "DIR_FstClusLO" / c.Int16ul,
    "DIR_FileSize" / c.Int32ul
)

class FAT32Parser:
    def __init__(self, disk_io):
        self.disk = disk_io
        self.bpb = None
        self.bytes_per_sec = 512
        self.sec_per_clus = 0
        self.rsvd_sec_cnt = 0
        self.fat_sz32 = 0
        self.num_fats = 0
        self.root_clus = 0
        self.fat_start = 0

    def parse_bpb(self):
        boot_sec = self.disk.read_sector(0)
        self.bpb = FAT32_BPB.parse(boot_sec)
        self.bytes_per_sec = self.bpb.BPB_BytsPerSec
        self.sec_per_clus = self.bpb.BPB_SecPerClus
        self.rsvd_sec_cnt = self.bpb.BPB_RsvdSecCnt
        self.fat_sz32 = self.bpb.BPB_FATSz32
        self.num_fats = self.bpb.BPB_NumFATs
        self.root_clus = self.bpb.BPB_RootClus
        self.fat_start = self.rsvd_sec_cnt

    def read_fat(self):
        fat_data = b""
        for i in range(self.fat_sz32):
            fat_data += self.disk.read_sector(self.fat_start + i)
        fat_entries = []
        for i in range(0, len(fat_data), 4):
            entry = int.from_bytes(fat_data[i:i+4], "little") & 0x0FFFFFFF
            fat_entries.append(entry)
        return fat_entries

    def clus_to_sector(self, clus):
        return self.fat_start + self.num_fats * self.fat_sz32 + (clus - 2) * self.sec_per_clus

    def read_dir(self, clus, fat_entries):
        sectors = []
        current = clus
        while current not in (0x0FFFFFFF, 0x0FFFFFF7, 0):
            sec = self.clus_to_sector(current)
            for i in range(self.sec_per_clus):
                sectors.append(self.disk.read_sector(sec + i))
            current = fat_entries[current]
        dir_data = b"".join(sectors)
        entries = []
        for i in range(0, len(dir_data), 32):
            raw = dir_data[i:i+32]
            if raw[0] == 0: break
            if raw[0] == 0xE5: continue
            entry = DIR_ENTRY.parse(raw)
            entries.append(entry)
        return entries

    def create_file(self, fat_entries, filename, content):
        free_clus = None
        for i, v in enumerate(fat_entries):
            if v == 0:
                free_clus = i
                break
        if not free_clus:
            raise Exception("无空闲簇")
        sec = self.clus_to_sector(free_clus)
        self.disk.write_sector(sec, content.encode("gbk"))
        fat_entries[free_clus] = 0x0FFFFFFF
        return free_clus