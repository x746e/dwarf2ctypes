# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
import ctypes
import unittest
import unittest.mock

import dwarf2ctypes


class DieTypeLoaderMixin:

    OBJECT_PATH = None

    def setUp(self):
        dwarf_info = dwarf2ctypes._get_dwarf_info(self.OBJECT_PATH)
        (compilation_unit,) = list(dwarf_info.iter_CUs())
        top_die = compilation_unit.get_top_DIE()
        assert top_die.tag == 'DW_TAG_compile_unit'

        self.die_types = {}
        self.ctypes_types = {}
        for child in top_die.iter_children():
            if not child.tag.endswith('_type'):
                continue
            if not 'DW_AT_name' in child.attributes:
                continue
            name = child.attributes['DW_AT_name'].value.decode('ascii')
            self.die_types[name] = child
            self.ctypes_types[name] = dwarf2ctypes.convert_type_die_to_ctypes(child)


class BaseTypeTest(DieTypeLoaderMixin, unittest.TestCase):

    OBJECT_PATH = 'testdata/base_types.o'

    def setUp(self):
        super(BaseTypeTest, self).setUp()
        self.type_die = self.die_types['base_types']
        self.type_ctypes = self.ctypes_types['base_types']

    def test_fields(self):
        self.assertEqual(
                self.type_ctypes._fields_,
                [('f_char', ctypes.c_byte),
                 ('f_uchar', ctypes.c_ubyte),
                 ('f_short', ctypes.c_short),
                 ('f_ushort', ctypes.c_ushort),
                 ('__padding_0', unittest.mock.ANY),
                 ('f_int', ctypes.c_int),
                 ('f_uint', ctypes.c_uint),
                 ('f_long', ctypes.c_long),
                 ('f_ulong', ctypes.c_ulong),
                 ('f_longlong', ctypes.c_long),
                 ('f_ulonglong', ctypes.c_ulong)]
        )


class BaseTypesOffsetSizePaddingTest(DieTypeLoaderMixin, unittest.TestCase):

    OBJECT_PATH = 'testdata/base_types.o'

    def setUp(self):
        super(BaseTypesOffsetSizePaddingTest, self).setUp()
        self.type_die = self.die_types['base_types']
        self.type_ctypes = self.ctypes_types['base_types']

    def test_struct_size(self):
        self.assertEqual(self.type_die.attributes['DW_AT_byte_size'].value,
                         ctypes.sizeof(self.type_ctypes))

    def test_field_offsets(self):
        for member in self.type_die.iter_children():
            member_name = member.attributes['DW_AT_name'].value.decode('ascii')
            ctypes_field = getattr(self.type_ctypes, member_name)
            self.assertEqual(member.attributes['DW_AT_data_member_location'].value,
                             ctypes_field.offset)

    def test_field_sizes(self):
        for member in self.type_die.iter_children():
            member_type = member.get_DIE_from_attribute('DW_AT_type')
            member_name = member.attributes['DW_AT_name'].value.decode('ascii')
            ctypes_field = getattr(self.type_ctypes, member_name)
            self.assertEqual(member_type.attributes['DW_AT_byte_size'].value,
                             ctypes_field.size)


class UnionsTest(DieTypeLoaderMixin, unittest.TestCase):

    OBJECT_PATH = 'testdata/unions.o'

    def test_it(self):
        struct = self.ctypes_types['union_struct']()
        self.assertEqual(ctypes.sizeof(struct.f_union), 2)
        # Assuming little endian system..
        struct.f_union.f_short = 0x1234
        self.assertEqual(struct.f_union.f_char, 0x34)

    def test_anon_union(self):
        struct = self.ctypes_types['anon_union_struct']()
        # Assuming little endian system..
        struct.f_short = 0x1234
        self.assertEqual(struct.f_char, 0x34)

    def test_nested_anon_union(self):
        struct = self.ctypes_types['nested_anon_union_struct']()
        # Assuming little endian system..
        struct.f_short = 0x1234
        self.assertEqual(struct.f_char, 0x34)


class BitFieldsTest(DieTypeLoaderMixin, unittest.TestCase):

    OBJECT_PATH = 'testdata/bitfields.o'

    def test_it(self):
        return
        s = self.ctypes_types['bitfield_struct']
        self.assertEqual(repr(s.f_bit1), '<Field type=c_int, ofs=4:0, bits=1>')
        self.assertEqual(repr(s.f_bit2), '<Field type=c_int, ofs=4:1, bits=2>')
        self.assertEqual(repr(s.f_bit3), '<Field type=c_int, ofs=4:3, bits=3>')

    def test_force_alignment(self):
        s = self.ctypes_types['tty_struct']
        # import pdb; pdb.set_trace()
        # print('sched_remote_wakeup:', s.sched_remote_wakeup)
        # print('in_execve', s.in_execve)


class CircularReferencesTest(DieTypeLoaderMixin, unittest.TestCase):

    OBJECT_PATH = 'testdata/circular_references.o'

    def test_it(self):
        pass


class TopoSortTest(unittest.TestCase):

    def test_it(self):
        refs = {'a': {'b', 'c'},
                'b': {'c', 'd'},
                'c': {'e', 'f'},
                'd': set(),
                'e': {'d'},
                'f': {'e'},
                'g': {'a', 'f'}}
        # The graph above has only one topological sort.
        # See Fig. 5.15 in Skiena's Algorithm Design Manual.
        self.assertEqual(dwarf2ctypes._toposort(refs),
                         ('g', 'a', 'b', 'c', 'f', 'e', 'd'))

    def test_cycle(self):
        refs = {'a': {'b'},
                'b': {'a'}}
        with self.assertRaises(RuntimeError):
            dwarf2ctypes._toposort(refs)


if __name__ == '__main__':
    unittest.main()

