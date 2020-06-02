# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
"""Generate a ctypes type out of DWARF debug information.

Not every possible C type is supported.  Places where some corners were cut are
marked with `XXX`.
"""
import ctypes
from dataclasses import dataclass
from collections import defaultdict
import threading

from elftools.elf.elffile import ELFFile


def main():
    path = '/usr/local/google/home/ksp/mfiles/learn/linux/linux/vmlinux'
    type_ = get_type(path, b'task_struct', relocate_dwarf_sections=False)


def get_type(binary_path, struct_name, relocate_dwarf_sections=True):
    dwarf_info = _get_dwarf_info(binary_path,
                                 relocate_dwarf_sections=relocate_dwarf_sections)
    print('Got dwarf_info')
    type_die = _find_type_die(dwarf_info, struct_name)
    type_ctypes = convert_type_die_to_ctypes(type_die)
    import pdb; pdb.set_trace()
    return type_ctypes


def _get_dwarf_info(binary_path, relocate_dwarf_sections=True):
    with open(binary_path, 'rb') as f:
        elf_file = ELFFile(f)
        if not elf_file.has_dwarf_info():
            raise RuntimeError(f'{binary_path} has no DWARF info')
        dwarf_info = elf_file.get_dwarf_info(
            relocate_dwarf_sections=relocate_dwarf_sections)
    return dwarf_info


def _find_type_die(dwarf_info, name: bytes):

    def check(die):
        return (die.attributes.get('DW_AT_name') and
                die.attributes.get('DW_AT_name').value == name)

    for compilation_unit in dwarf_info.iter_CUs():
        top_die = compilation_unit.get_top_DIE()
        if check(top_die):
            return top_die
        for child in top_die.iter_children():
            if check(child):
                return child
    else:
        raise ValueError(f'No type DIE named {name} found')


def convert_type_die_to_ctypes(type_die):
    # traverse the graph.  save structs and their relationships

    nodes = set()
    refs = defaultdict(set)
    pointer_refs = defaultdict(set)

    def traverse(type_die):
        if type_die in nodes:
            return
            # raise RuntimeError('Cycle :(')
        nodes.add(type_die)

        # print(type_die)

        if type_die.tag in ('DW_TAG_structure_type', 'DW_TAG_union_type'):
            for member_die in type_die.iter_children():
                refs[type_die].add(member_die)
                traverse(member_die)
        elif type_die.tag in ('DW_TAG_typedef', 'DW_TAG_volatile_type',
                              'DW_TAG_const_type', 'DW_TAG_member'):
            if 'DW_AT_type' not in type_die.attributes:
                return
            referenced_type = type_die.get_DIE_from_attribute('DW_AT_type')
            refs[type_die].add(referenced_type)
            traverse(referenced_type)
        elif ('DW_AT_declaration' in type_die.attributes and
              type_die.attributes['DW_AT_declaration'].value):
            # XXX
            resolved = _resolve_declaration(type_die)
            refs[type_die].add(resolved)
            traverse(resolved)
        elif type_die.tag == 'DW_TAG_base_type':
            pass
        elif type_die.tag == 'DW_TAG_pointer_type':
            if 'DW_AT_type' not in type_die.attributes:
                return
            referenced_type = type_die.get_DIE_from_attribute('DW_AT_type')
            # Track pointers as well?
            traverse(referenced_type)
        elif type_die.tag == 'DW_TAG_subroutine_type':
            # XXX: For the task of looking at program's data, we don't really care
            # about function pointers.  If a need arises, ctypes allow defining
            # `CFUNCTYPES`.
            pass
        elif type_die.tag == 'DW_TAG_array_type':
            item_type = type_die.get_DIE_from_attribute('DW_AT_type')
            refs[type_die].add(item_type)
            traverse(item_type)
        elif type_die.tag == 'DW_TAG_enumeration_type':
            pass
        else:
            print(type_die)
            import pdb; pdb.set_trace()
            raise NotImplementedError(
                f'Converting {type_die.tag} type DIEs is not yet supported.')

    traverse(type_die)

    for die in _toposort(refs):
        if die.tag != 'DW_TAG_structure_type':
            continue
        # print(die)
        if 'DW_AT_name' in die.attributes:
            name = die.attributes['DW_AT_name'].value
        else:
            name = 'anon_struct?'
        print('>>> ', name)
        _convert_type_die_to_ctypes(die)

    for decl in list(_declarations_to_be_resolved.values()):
        _convert_type_die_to_ctypes(decl)

    return _convert_type_die_to_ctypes(type_die)


def _toposort(refs):

    discovered = defaultdict(bool)
    processed = defaultdict(bool)
    sorted_nodes = []
    parent = {}

    def dfs(x):
        discovered[x] = True
        for y in refs[x]:
            if not discovered[y]:
                parent[y] = x
                process_edge(x, y)
                dfs(y)
            else:
                process_edge(x, y)
        sorted_nodes.append(x)
        processed[x] = True

    def process_edge(x, y):
        if parent.get(y) == x:
            return
        if discovered[y] and not processed[y]:
            raise RuntimeError('A cycle')

    for node in list(refs.keys()):
        if not discovered[node]:
            dfs(node)

    return tuple(reversed(sorted_nodes))


def _convert_type_die_to_ctypes(type_die, declaration=False):
    if type_die.tag in ('DW_TAG_typedef', 'DW_TAG_volatile_type', 'DW_TAG_const_type'):
        return _convert_type_die_to_ctypes(_resolve_type(type_die),
                                           declaration=declaration)
    elif ('DW_AT_declaration' in type_die.attributes and
          type_die.attributes['DW_AT_declaration'].value):
        return _convert_type_die_to_ctypes(_resolve_declaration(type_die),
                                           declaration=declaration)
    elif type_die.tag == 'DW_TAG_base_type':
        return _convert_base_type_die_to_ctypes(type_die)
    elif type_die.tag == 'DW_TAG_pointer_type':
        return _convert_pointer_type_die_to_ctypes(type_die)
    elif type_die.tag == 'DW_TAG_subroutine_type':
        # XXX: For the task of looking at program's data, we don't really care
        # about function pointers.  If a need arises, ctypes allow defining
        # `CFUNCTYPES`.
        return ctypes.c_void_p
    elif type_die.tag == 'DW_TAG_array_type':
        return _convert_array_type_die_to_ctypes(type_die)
    elif type_die.tag == 'DW_TAG_enumeration_type':
        return _convert_enum_type_die_to_ctypes(type_die)
    elif type_die.tag == 'DW_TAG_union_type':
        return _convert_unon_type_die_to_ctypes(type_die)
    elif type_die.tag == 'DW_TAG_structure_type':
        return _convert_structure_type_die_to_ctypes(type_die, declaration=declaration)
    else:
        print(type_die)
        import pdb; pdb.set_trace()
        raise NotImplementedError(
            f'Converting {type_die.tag} type DIEs is not yet supported.')


def _resolve_type(type_die):
    if type_die.tag in ('DW_TAG_typedef', 'DW_TAG_volatile_type', 'DW_TAG_const_type'):
        return _resolve_type(type_die.get_DIE_from_attribute('DW_AT_type'))
    return type_die


class DefinitionNotFound(Exception):
    pass


def _resolve_declaration(maybe_declaration_die):
    assert ('DW_AT_declaration' in maybe_declaration_die.attributes and
            maybe_declaration_die.attributes['DW_AT_declaration'].value)

    declaration_die = maybe_declaration_die
    type_name = declaration_die.attributes['DW_AT_name'].value
    for compilation_unit in declaration_die.dwarfinfo.iter_CUs():
            top_die = compilation_unit.get_top_DIE()
            for child in top_die.iter_children():
                if (('DW_AT_declaration' not in child.attributes or
                            not child.attributes['DW_AT_declaration'].value) and
                        child.attributes.get('DW_AT_name') and
                        child.tag == declaration_die.tag and
                        child.attributes.get('DW_AT_name').value == type_name):
                    return child

    raise DefinitionNotFound(f"Can't find declaration named {type_name}")


_DWARF_BASE_TYPES_TO_CTYPES = {
    b'char': ctypes.c_byte,
    b'unsigned char': ctypes.c_ubyte,
    b'short int': ctypes.c_short,
    b'short unsigned int': ctypes.c_ushort,
    b'int': ctypes.c_int,
    b'unsigned int': ctypes.c_uint,
    b'long int': ctypes.c_long,
    b'long unsigned int': ctypes.c_ulong,
    b'long long int': ctypes.c_longlong,
    b'long long unsigned int': ctypes.c_ulonglong,
    b'_Bool': ctypes.c_bool,
}


def _convert_base_type_die_to_ctypes(type_die):
    type_name = type_die.attributes['DW_AT_name'].value
    if type_name not in _DWARF_BASE_TYPES_TO_CTYPES:
        print(type_die)
        raise NotImplementedError(
            f'Converting {type_name} DWARF type is not yet supported')
    return _DWARF_BASE_TYPES_TO_CTYPES[type_name]


def _convert_pointer_type_die_to_ctypes(pointer_die):
    if 'DW_AT_type' not in pointer_die.attributes:
        return ctypes.c_void_p
    type_die = pointer_die.get_DIE_from_attribute('DW_AT_type')
    if type_die.tag == 'DW_TAG_const_type' and not type_die.attributes:
        return ctypes.c_void_p
    try:
        pointed_to_type = _convert_type_die_to_ctypes(type_die, declaration=True)
    except DefinitionNotFound:
        return ctypes.c_void_p  # XXX
    return ctypes.POINTER(pointed_to_type)


def _convert_array_type_die_to_ctypes(array_die):
    (subrange_die,) = list(array_die.iter_children())
    item_type = _convert_type_die_to_ctypes(array_die.get_DIE_from_attribute('DW_AT_type'))
    if 'DW_AT_upper_bound' not in subrange_die.attributes:
        # XXX: That should be only the last item in struct.
        # import pdb; pdb.set_trace()
        return item_type * 0
    return item_type * subrange_die.attributes['DW_AT_upper_bound'].value


def _convert_enum_type_die_to_ctypes(enum_die):
    return _convert_type_die_to_ctypes(enum_die.get_DIE_from_attribute('DW_AT_type'))


def _convert_unon_type_die_to_ctypes(union_die):
    assert union_die.tag == 'DW_TAG_union_type'

    if 'DW_AT_name' in union_die.attributes:
        union_name = union_die.attributes['DW_AT_name'].value.decode('utf-8')
    else:
        union_name = _get_anon_name('union_')

    union = type(union_name, (ctypes.Union,), {})

    members_info = [
        _get_member_info(member_die)
        for member_die in union_die.iter_children()
    ]

    fields = [(member.name, member.ctypes_type, member.bit_size) for member in members_info]
    _set_fields(union, fields)

    return union


def _split_anon_fields(struct_fields):
    """For each field definition with None name, get a anon name, and return
    a list of anonymous fields."""
    fields = []
    anonymous = []
    anon_field_counter = 1
    for name, ctypes_type, maybe_bit_size in struct_fields:
        if name is None:
            name = f'__anon_field_{anon_field_counter}'
            anonymous.append(name)
        if maybe_bit_size is None:
            fields.append((name, ctypes_type))
        else:
            fields.append((name, ctypes_type, maybe_bit_size))

    return fields, anonymous


def _set_fields(struct_or_union, fields):
    struct_fields, anon_field_names = _split_anon_fields(fields)
    struct_or_union._pack_ = 1  # We pad manually.
    struct_or_union._anonymous_ = anon_field_names
    struct_or_union._fields_ = struct_fields


_structures = {}
_structures_lock = threading.Lock()
_declarations_to_be_resolved = {}

import inspect


def _dump(struct_die, struct_name=None, verbose=False):

    if verbose:
        print('\n' + '+' * 100)
        print(struct_die)
        for member in struct_die.iter_children():
            print('\n' + '=' * 100)
            print(member)
            print('-' * 30)
            print(member.get_DIE_from_attribute('DW_AT_type'))
    else:
        print(f'>>> {struct_name}')
        for member_die in struct_die.iter_children():
            if 'DW_AT_name' not in member_die.attributes:
                member_name = '<anon>'
            else:
                member_name = member_die.attributes['DW_AT_name'].value.decode('utf-8')
            member_type_die = _resolve_type(member_die.get_DIE_from_attribute('DW_AT_type'))
            if 'DW_AT_byte_size' in member_type_die.attributes:
                byte_size = member_type_die.attributes['DW_AT_byte_size'].value
            else:
                byte_size = '-'
            offset = member_die.attributes['DW_AT_data_member_location'].value
            if 'DW_AT_bit_size' in member_die.attributes:
                bit_size = member_die.attributes['DW_AT_bit_size'].value
            else:
                bit_size = '-'
            if 'DW_AT_bit_offset' in member_die.attributes:
                bits_offset = member_die.attributes['DW_AT_bit_offset'].value
            else:
                bits_offset = '-'
            print(f'    {member_name:25}'
                  f'oft={offset:5} sz={byte_size:5} bits={bit_size:5} bits_oft={bits_offset:5}'
                  f'type={member_type_die.tag:20}')


def _dump_ctype_struct(struct):
    for field_tuple in struct._fields_:
        print(f'{field_tuple[0]}: {getattr(struct, field_tuple[0])}')


def _convert_structure_type_die_to_ctypes(struct_die, declaration=False):
    assert struct_die.tag == 'DW_TAG_structure_type'

    stack_len = len(inspect.stack(0))

    if 'DW_AT_name' in struct_die.attributes:
        struct_name = struct_die.attributes['DW_AT_name'].value.decode('utf-8')
        is_anon_struct = False
    else:
        struct_name = _get_anon_name('struct_')
        is_anon_struct = True
        # Can't have a declaration of an anon struct.
        declaration = False

    print(f'{stack_len}> converting {struct_name}')

    if struct_name in _declarations_to_be_resolved and not declaration:
        resolve_declaration = True
    else:
        resolve_declaration = False

    if not is_anon_struct:
        with _structures_lock:
            if struct_name in _structures:
                struct = _structures[struct_name]
                if not resolve_declaration:
                    print(f'{stack_len}> returning {struct_name} from cache')
                    return _structures[struct_name]

    if not resolve_declaration:
        # Forward declare the struct for self referencing structures.
        struct = type(struct_name, (ctypes.Structure,), {})
        if not is_anon_struct:
            with _structures_lock:
                print(f'{stack_len}> saving not yet completed {struct_name} in cache')
                _structures[struct_name] = struct

    if declaration:
        if is_anon_struct:
            import pdb; pdb.set_trace()
        assert not is_anon_struct
        _declarations_to_be_resolved[struct_name] = struct_die
        return struct

    members_info = [
        _get_member_info(member_die)
        for member_die in struct_die.iter_children()
    ]

    # if struct_name in (b'task_struct', 'task_struct'):
    #     import pdb; pdb.set_trace()

    def pad_fields(members_info):
        struct_fields = []
        struct_size = struct_die.attributes['DW_AT_byte_size'].value
        padding_nr = 0
        bytes_so_far = 0

        def pad(n):
            nonlocal padding_nr, bytes_so_far
            if not n:
                return
            assert n > 0
            struct_fields.append((f'__padding_{padding_nr}', ctypes.c_byte * n, None))
            padding_nr += 1
            bytes_so_far += n

        for member in members_info:
            if member.offset > bytes_so_far:
                pad(member.offset - bytes_so_far)

            if member.offset < bytes_so_far:
                assert member.bit_size is not None
                # XXX
                if member.offset + member.size != bytes_so_far:
                    continue
                continue  # XXX
                # assert member.offset + member.size == bytes_so_far
            else:
                bytes_so_far += member.size

            struct_fields.append((
                    member.name,
                    member.ctypes_type,
                    None # member.bit_size,
            ))

        pad(struct_size - bytes_so_far)

        return struct_fields

    # TODO: Try to resolve flexible array members?

    struct_fields = pad_fields(members_info)
    try:
        print(f'{stack_len}> setting fields on {struct_name}')
        _set_fields(struct, struct_fields)
    except Exception as e:
        # import pdb; pdb.set_trace()
        print(e)
        raise

    # struct_size = struct_die.attributes['DW_AT_byte_size'].value
    # if ctypes.sizeof(struct) != struct_size:
    #     print(f"{struct_name} size doesn't match.  Struct's DW_AT_byte_size: {struct_size}; sizeof(struct): {ctypes.sizeof(struct)}")
    #     print(struct_die)
    #
    #     import pdb; pdb.set_trace()
    #
    #     for member_die in struct_die.iter_children():
    #         member_name = member_die.attributes['DW_AT_name'].value.decode('ascii')
    #         member_type = _resolve_type(member_die.get_DIE_from_attribute('DW_AT_type'))
    #         ctypes_field = getattr(struct, member_name)
    #         die_offset = member_die.attributes['DW_AT_data_member_location'].value
    #         # if die_offset != ctypes_field.offset:
    #         print(f'field: {member_name}:')
    #         print(f'             DIE offset: {die_offset},\tfield offset: {ctypes_field.offset}')
    #         die_size = _get_type_size(member_type)
    #         # if die_size != ctypes_field.size:
    #         print(f'             DIE size:   {die_size},\tfield size: {ctypes_field.size}')
    #
    #     import pdb; pdb.set_trace()
    #

    _validate(struct_die, struct)
    print(f'{stack_len}> returning {struct_name}')

    if resolve_declaration:
        _declarations_to_be_resolved.pop(struct_name)

    _dump(struct_die, struct_name=struct_name)
    _dump_ctype_struct(struct)

    return struct


def _validate(struct_die, struct):
    struct_size = struct_die.attributes['DW_AT_byte_size'].value
    return # XXX
    assert ctypes.sizeof(struct) == struct_size
    # print(struct_die)
    for member_die in struct_die.iter_children():
        # print(member_die)
        if 'DW_AT_name' in member_die.attributes:
            member_name = member_die.attributes['DW_AT_name'].value.decode('ascii')
        else:
            member_name = None
        member_type = _resolve_type(member_die.get_DIE_from_attribute('DW_AT_type'))
        ctypes_field = getattr(struct, member_name)
        die_offset = member_die.attributes['DW_AT_data_member_location'].value
        if die_offset != ctypes_field.offset:
            print(f'field: {member_name}:')
            print(f'             DIE offset: {die_offset},\tfield offset: {ctypes_field.offset}')
            import pdb; pdb.set_trace()
        die_size = _get_type_size(member_type)
        if die_size != ctypes_field.size:
            print(f'             DIE size:   {die_size},\tfield size: {ctypes_field.size}')
            import pdb; pdb.set_trace()


_anon_name_counter = 0
_anon_name_counter_lock = threading.Lock()


def _get_anon_name(what=''):
    global _anon_name_counter
    with _anon_name_counter_lock:
        _anon_name_counter += 1
        return f'anon_{what}{_anon_name_counter}'


@dataclass
class MemberInfo:
    name: str
    ctypes_type: object
    die: object
    size: int
    offset: int
    bit_size: int = None


def _get_member_info(member_die):
    assert member_die.tag == 'DW_TAG_member'
    type_die = _resolve_type(member_die.get_DIE_from_attribute('DW_AT_type'))
    size = _get_type_size(type_die)
    if 'DW_AT_data_member_location' in member_die.attributes:
        offset = member_die.attributes['DW_AT_data_member_location'].value
    else:
        offset = None

    if 'DW_AT_name' not in member_die.attributes:
        name = None
        ctypes_type = _convert_type_die_to_ctypes(type_die)
    else:
        name = member_die.attributes['DW_AT_name'].value.decode('utf-8')
        ctypes_type = _convert_type_die_to_ctypes(type_die)

    if 'DW_AT_bit_size' in member_die.attributes:
        bit_size = member_die.attributes['DW_AT_bit_size'].value
    else:
        bit_size = None

    return MemberInfo(name=name, ctypes_type=ctypes_type, die=member_die,
                      size=size, offset=offset, bit_size=bit_size)


def _get_type_size(type_die):
    type_die = _resolve_type(type_die)
    if 'DW_AT_byte_size' in type_die.attributes:
        return type_die.attributes['DW_AT_byte_size'].value
    elif type_die.tag == 'DW_TAG_array_type':
        (subrange_die,) = list(type_die.iter_children())
        item_size = _get_type_size(type_die.get_DIE_from_attribute('DW_AT_type'))
        if 'DW_AT_upper_bound' not in subrange_die.attributes:
            # XXX: That should be only the last item in struct.
            # import pdb; pdb.set_trace()
            return 0
        return item_size * subrange_die.attributes['DW_AT_upper_bound'].value
    elif 'DW_AT_type' in type_die.attributes:
        import pdb; pdb.set_trace()
        types_type_die = type_die.get_DIE_from_attribute('DW_AT_type')
        return types_type_die.attributes['DW_AT_byte_size'].value
    else:
        import pdb; pdb.set_trace()
        raise NotImplementedError(f"Can't find size of {type_die}.")


if __name__ == '__main__':
    main()
