# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# Read all task_structs from /dev/mem, print them out as `pc -eo pid,comm`

import ctypes
from dataclasses import dataclass
import subprocess

import dwarf2ctypes


class Memory:

    def __init__(self, vm):
        self._vm = vm

    def read(self, virt_address, length):
        return self.read_phys(self._vm.translate(virt_address), length)

    def read_phys(self, phys_address, length):
        return subprocess.check_output(
            f"ssh root@localhost -p 2022 'dd if=/dev/mem bs=1 skip={phys_address} count={length}'",
            shell=True
        )


class VM:

    def __init__(self, areas):
        self._areas = tuple(areas)

    def translate(self, virt_address):
        for area in self._areas:
            if area.virt_addr <= virt_address < area.virt_addr + area.mem_siz:
                return area.phys_addr + (virt_address - area.virt_addr)
        raise IndexError(f"Can't translate 0x{virt_address:x}.")


def main():
    path = '/usr/local/google/home/ksp/mfiles/learn/linux/linux/vmlinux'
    task_struct = dwarf2ctypes.get_type(path, b'task_struct', relocate_dwarf_sections=False)
    mem = Memory(VM( _parse_readelf_output(readelf_l_proc_kcore)))
    buf = mem.read(0xffffffff82a12840, ctypes.sizeof(task_struct))
    init_task = task_struct.from_buffer_copy(buf)
    import pdb; pdb.set_trace()


@dataclass
class VMArea:
    type_: str
    offset: int
    virt_addr: int
    phys_addr: int
    file_siz: int
    mem_siz: int
    flags: int
    align: int


def _parse_readelf_output(s):
    program_headers = 'Program Headers:\n'
    s = s[s.find(program_headers) + len(program_headers):]
    lines = s.splitlines()[2:]
    for i in range(len(lines) // 2):
        type_, offset, virt_addr, phys_addr = (lines[i * 2]).split()
        parts = lines[i * 2 + 1].split()
        if len(parts) != 4:
            continue
        file_siz, mem_siz, flags, align = parts

        x = lambda s: int(s, 16)

        yield VMArea(type_=type_, offset=x(offset), virt_addr=x(virt_addr),
                     phys_addr=x(phys_addr), file_siz=x(file_siz), mem_siz=x(mem_siz),
                     flags=flags, align=x(align))


readelf_l_proc_kcore = """\
Elf file type is CORE (Core file)
Entry point 0x0
There are 11 program headers, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  NOTE           0x00000000000002a8 0x0000000000000000 0x0000000000000000
                 0x0000000000001e48 0x0000000000000000         0x0
  LOAD           0x00007fffff603000 0xffffffffff600000 0xffffffffffffffff
                 0x0000000000001000 0x0000000000001000  RWE    0x1000
  LOAD           0x00007fff81003000 0xffffffff81000000 0x0000000001000000
                 0x000000000222c000 0x000000000222c000  RWE    0x1000
  LOAD           0x0000490000003000 0xffffc90000000000 0xffffffffffffffff
                 0x00001fffffffffff 0x00001fffffffffff  RWE    0x1000
  LOAD           0x00007fffc0003000 0xffffffffc0000000 0xffffffffffffffff
                 0x000000003f000000 0x000000003f000000  RWE    0x1000
  LOAD           0x0000088000004000 0xffff888000001000 0x0000000000001000
                 0x000000000009e000 0x000000000009e000  RWE    0x1000
  LOAD           0x00006a0000003000 0xffffea0000000000 0xffffffffffffffff
                 0x0000000000003000 0x0000000000003000  RWE    0x1000
  LOAD           0x0000088000103000 0xffff888000100000 0x0000000000100000
                 0x00000000bfee0000 0x00000000bfee0000  RWE    0x1000
  LOAD           0x00006a0000007000 0xffffea0000004000 0xffffffffffffffff
                 0x0000000002ffc000 0x0000000002ffc000  RWE    0x1000
  LOAD           0x0000088100003000 0xffff888100000000 0x0000000100000000
                 0x0000000040000000 0x0000000040000000  RWE    0x1000
  LOAD           0x00006a0004003000 0xffffea0004000000 0xffffffffffffffff
                 0x0000000001000000 0x0000000001000000  RWE    0x1000
"""


if __name__ == '__main__':
    main()
