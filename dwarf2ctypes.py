import ctypes

from elftools.elf.elffile import ELFFile


def get_structure(binary_path, struct_name):
    with open(binary_path, 'rb') as f:
        elf_file = ELFFile(f)
        if not elf_file.has_dwarf_info():
            raise RuntimeError(f'<{binary_path}> has no DWARF info')
        dwarf_info = elf_file.get_dwarf_info()
        structure_type_die = _find_structure_type_die(dwarf_info, struct_name)
        ctype_structure = _convert_structure_type_die_to_ctypes(dwarf_info, structure_type_die)


def _find_structure_type_die(dwarf_info, struct_name):

    def inner(die):
        for child in die.iter_children():
            if (child.tag == 'DW_TAG_structure_type' and
                    child.attributes.get('DW_AT_name').value == struct_name):
                yield child
            elif child.has_children:
                yield from inner(child)

    found_dies = []
    for compilation_unit in dwarf_info.iter_CUs():
        top_die = compilation_unit.get_top_DIE()
        found_dies.extend(inner(top_die))

    if len(found_dies) > 1:
        raise ValueError(f"There's more than one structure type DIE named <{struct_name}>: {found_dies}")
    if not found_dies:
        raise ValueError(f"Not structure type DIE named <{struct_name}> found")
    return found_dies[0]


def _convert_structure_type_die_to_ctypes(dwarf_info, struct_die):
    assert struct_die.tag == 'DW_TAG_structure_type'
    struct_name = struct_die.attributes['DW_AT_name'].value.decode('utf-8')
    struct_fields = [
        _convert_member_die_to_ctypes_field(dwarf_info, member)
        for member in struct_die.iter_children()
    ]
    return type(struct_name, (ctypes.Structure,), {'_fields_': struct_fields})


def _convert_member_die_to_ctypes_field(dwarf_info, member_die):
    assert member_die.tag == 'DW_TAG_member'
    member_name = member_die.attributes['DW_AT_name'].value.decode('utf-8')
    member_type_die = dwarf_info.get_DIE_from_refaddr(
            member_die.attributes['DW_AT_type'].value)
    member_type = _convert_type_die_to_ctypes(dwarf_info, member_type_die)
    return (member_name, member_type)


_DWARF_BASE_TYPES_TO_CTYPES = {
    b'int': ctypes.c_int,
}


def _convert_type_die_to_ctypes(dwarf_info, type_die):
    if type_die.tag != 'DW_TAG_base_type':
        raise NotImplementedError(
            f'Converting {type_die.tag} type DIEs is not yet supported')

    type_name = type_die.attributes['DW_AT_name'].value
    if type_name not in _DWARF_BASE_TYPES_TO_CTYPES:
        raise NotImplementedError(
            f'Converting {type_name} DWARF type is not yet supported')
    return _DWARF_BASE_TYPES_TO_CTYPES[type_name]



def main():
    path = './prog'
    get_structure(path, b'global_struct')


if __name__ == '__main__':
    main()
