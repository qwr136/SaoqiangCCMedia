import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("macho_pac", TESTS / "macho_pac.py")
macho_pac = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(macho_pac)

BASE = 0x100000000
TEXT_FILE = 0
TEXT_FILESIZE = 0x1000
DATA_FILE = 0x2000
LINKEDIT_FILE = 0x3000
CF_OFF = 0x100
TEXT_OFF = 0x900
SIGNATURE_SIZE = 0x100


def p16(buf, off, value):
    struct.pack_into("<H", buf, off, value)


def p32(buf, off, value):
    struct.pack_into("<I", buf, off, value)


def p64(buf, off, value):
    struct.pack_into("<Q", buf, off, value)


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def align(value, boundary):
    return (value + boundary - 1) & ~(boundary - 1)


def fixed_name(text):
    raw = text.encode("ascii")
    if len(raw) > 16:
        raise ValueError(text)
    return raw + bytes(16 - len(raw))


def segment_command(name, vmaddr, vmsize, fileoff, filesize, sections=()):
    size = 72 + 80 * len(sections)
    result = bytearray(size)
    struct.pack_into("<II16sQQQQiiII", result, 0, 0x19, size,
                     fixed_name(name), vmaddr, vmsize, fileoff, filesize,
                     7, 5, len(sections), 0)
    for index, section in enumerate(sections):
        pos = 72 + index * 80
        sectname, addr, section_size, offset = section
        struct.pack_into("<16s16sQQIIIIIIII", result, pos,
                         fixed_name(sectname), fixed_name(name), addr,
                         section_size, offset, 0, 0, 0, 0, 0, 0, 0)
    return bytes(result)


def dylib_command(name):
    name_bytes = name.encode("ascii") + b"\0"
    size = align(24 + len(name_bytes), 8)
    result = bytearray(size)
    struct.pack_into("<6I", result, 0, 0x0C, size, 24, 0, 0, 0)
    result[24:24 + len(name_bytes)] = name_bytes
    return bytes(result)


def make_fixups(pointer_format, *, auth=True, key=2, addr_div=1,
                diversity=0x6AE1, symbol="___CFConstantStringClassReference",
                library_ordinal=2, import_index=0, cycle=False, out_of_bounds=False):
    symbol_bytes = symbol.encode("utf-8") + b"\0"
    starts_offset = 28
    starts_image_size = 16
    overflow_count = 2 if cycle else 0
    record_size = 22 + 2 + overflow_count * 2
    starts_record_offset = starts_offset + starts_image_size
    imports_offset = starts_record_offset + record_size
    symbols_offset = imports_offset + 4
    result = bytearray(symbols_offset + len(symbol_bytes))
    struct.pack_into("<7I", result, 0, 0, starts_offset, imports_offset,
                     symbols_offset, 1, 1, 0)
    struct.pack_into("<I3I", result, starts_offset, 3, 0,
                     starts_record_offset - starts_offset, 0)
    page_start = 0x8001 if cycle else CF_OFF
    struct.pack_into("<IHHQIH", result, starts_record_offset,
                     record_size, 0x1000, pointer_format,
                     DATA_FILE, 0, 1)
    p16(result, starts_record_offset + 22, page_start)
    if cycle:
        p16(result, starts_record_offset + 24, CF_OFF)
        p16(result, starts_record_offset + 26, CF_OFF | 0x8000)
    import_word = (library_ordinal & 0xFF) | (0 << 8) | (0 << 9)
    p32(result, imports_offset, import_word)
    result[symbols_offset:] = symbol_bytes

    next_count = 2
    raw_isa = (1 << 62) | (next_count << 51) | (import_index & 0xFFFF)
    if auth:
        raw_isa |= 1 << 63
        raw_isa |= (diversity & 0xFFFF) << 32
        raw_isa |= (addr_div & 1) << 48
        raw_isa |= (key & 3) << 49
    if out_of_bounds:
        raw_isa = (raw_isa & ~0xFFFF) | 0xFFFF
    return bytes(result), raw_isa


def make_signature(unsigned, sigoff, version=0x20000):
    identifier = b"fixture.arm64e\0"
    hash_size = 32
    header_size = {0x20000:44,0x20100:48,0x20200:52,0x20300:64,0x20400:88,0x20500:96,0x20600:108}[version]
    ident_offset = header_size
    hash_offset = ident_offset + len(identifier)
    page_size = 4096
    page_count = (sigoff + page_size - 1) // page_size
    directory_size = hash_offset + page_count * hash_size
    directory_size = align(directory_size, 16)
    directory = bytearray(directory_size)
    struct.pack_into(">9I", directory, 0,
                     macho_pac.CODEDIRECTORY, directory_size,
                     version, 0x2, hash_offset, ident_offset,
                     0, page_count, sigoff)
    struct.pack_into(">4B", directory, 36, hash_size, 2, 0, 12)
    directory[ident_offset:ident_offset + len(identifier)] = identifier
    for index, page_start in enumerate(range(0, sigoff, page_size)):
        digest = hashlib.sha256(unsigned[page_start:min(page_start + page_size, sigoff)]).digest()
        directory[hash_offset + index * hash_size:hash_offset + (index + 1) * hash_size] = digest
    super_length = 20 + len(directory)
    superblob = bytearray(align(super_length, 16))
    struct.pack_into(">3I", superblob, 0, macho_pac.EMBEDDED_SIGNATURE,
                     super_length, 1)
    struct.pack_into(">2I", superblob, 12, 0, 20)
    superblob[20:20 + len(directory)] = directory
    return bytes(superblob)


def fixture(*, pointer_format=12, auth=True, key=2, addr_div=1,
            diversity=0x6AE1, symbol="___CFConstantStringClassReference",
            library_ordinal=2, import_index=0, cycle=False, out_of_bounds=False,
            signature=True, flags=0x7C8, string="unit test"):
    text = string.encode("utf-8") if not flags & 0x10 else string.encode("utf-16-le")
    unit = 2 if flags & 0x10 else 1
    text_bytes = text + bytes(unit)
    fixups, raw_isa = make_fixups(pointer_format, auth=auth, key=key,
                                  addr_div=addr_div, diversity=diversity,
                                  symbol=symbol, library_ordinal=library_ordinal,
                                  import_index=import_index,
                                  cycle=cycle, out_of_bounds=out_of_bounds)
    fixoff = LINKEDIT_FILE
    sigoff = 0x4000
    total = sigoff + len(make_signature(bytes(sigoff), sigoff))
    data_vm = BASE + TEXT_FILE + TEXT_OFF
    data_target = data_vm if pointer_format == 1 else data_vm - BASE
    data_raw = data_target
    cf_vm = BASE + DATA_FILE + CF_OFF
    image_data = bytearray(0x1000)
    struct.pack_into("<4Q", image_data, CF_OFF, raw_isa, flags, data_vm, len(string))
    p64(image_data, CF_OFF + 16, data_raw)

    dependency_names = ["/usr/lib/libSystem.B.dylib",
                        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"]
    load_commands = []
    load_commands.append(segment_command("__TEXT", BASE, 0x1000, 0, TEXT_FILESIZE,
                        (("__text", BASE + 0x800, 0x20, 0x800),
                         ("__cstring" if unit == 1 else "__ustring",
                          BASE + TEXT_FILE + TEXT_OFF, len(text_bytes), TEXT_FILE + TEXT_OFF))))
    load_commands.append(segment_command("__DATA_CONST", BASE + DATA_FILE,
                        0x1000, DATA_FILE, 0x1000,
                        (("__cfstring", cf_vm, 32, DATA_FILE + CF_OFF),)))
    for name in dependency_names:
        load_commands.append(dylib_command(name))
    uuid_bytes = bytes.fromhex("00112233445566778899aabbccddeeff")
    load_commands.append(struct.pack("<II16s", 0x1B, 24, uuid_bytes))
    load_commands.append(struct.pack("<6I", 0x32, 24, 2,
                                     (15 << 16), (16 << 16) | (4 << 8), 0))
    load_commands.append(struct.pack("<4I", macho_pac.LC_DYLD_CHAINED_FIXUPS,
                                     16, fixoff, len(fixups)))
    signature_command_index = len(load_commands)
    load_commands.append(struct.pack("<4I", macho_pac.LC_CODE_SIGNATURE,
                                     16, sigoff, SIGNATURE_SIZE if signature else 0))
    load_commands.append(segment_command("__LINKEDIT", BASE + LINKEDIT_FILE,
                        0x2000, LINKEDIT_FILE, total - LINKEDIT_FILE))
    command_bytes = b"".join(load_commands)
    header = struct.pack("<8I", macho_pac.MH_MAGIC_64, macho_pac.CPU_TYPE_ARM64,
                         0x80000002, 8, len(load_commands), len(command_bytes), 0, 0)
    image = bytearray(total)
    image[:32] = header
    image[32:32 + len(command_bytes)] = command_bytes
    image[0x800:0x820] = bytes.fromhex("1f2003d5" * 8)
    image[TEXT_FILE + TEXT_OFF:TEXT_FILE + TEXT_OFF + len(text_bytes)] = text_bytes
    image[DATA_FILE:DATA_FILE + len(image_data)] = image_data
    image[fixoff:fixoff + len(fixups)] = fixups
    if signature:
        superblob = make_signature(image, sigoff)
        image[sigoff:sigoff + len(superblob)] = superblob
        p32(image, 32 + sum(len(c) for c in load_commands[:signature_command_index]) + 12,
            len(superblob))
        # The CodeDirectory hashes the complete unsigned prefix.
        rebuilt = make_signature(image, sigoff)
        image[sigoff:sigoff + len(rebuilt)] = rebuilt
    return bytes(image)


class MachOPACTests(unittest.TestCase):
    def test_real_code_directory_header_versions(self):
        unsigned=bytes(4096)
        for version in (0x20000,0x20100,0x20200,0x20300,0x20400,0x20500,0x20600):
            with self.subTest(version=hex(version)):
                sig=make_signature(unsigned,4096,version)
                checked=macho_pac._check_signature(unsigned+sig,(4096,len(sig)))
                self.assertEqual(checked['page_hashes_verified'],1)

    def test_authenticated_minimal_arm64e_passes_and_reports_contract(self):
        result = macho_pac.inspect_macho(fixture())
        self.assertEqual(result["architecture"], "arm64e")
        self.assertEqual(result["uuid"], "00112233-4455-6677-8899-aabbccddeeff")
        self.assertEqual(result["minimum_os"], "15.0.0")
        self.assertEqual(result["sdk"], "16.4.0")
        self.assertEqual(result["dependencies"][1],
                         "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.assertEqual(result["cfstring"]["isa_auth_counts"],
                         {"authenticated": 1, "unauthenticated": 0})
        isa = result["cfstring"]["strings"][0]["isa_fixup"]
        self.assertEqual((isa["key_name"], isa["addr_div"], isa["diversity"]),
                         ("DA", 1, 0x6AE1))
        self.assertTrue(result["signature"]["full_pre_signature_coverage"])
        self.assertGreater(result["signature"]["page_hashes_verified"], 1)
        self.assertEqual(result["sha256"], hashlib.sha256(fixture()).hexdigest())

    def test_arm64e_pointer_formats_1_9_and_12(self):
        for pointer_format in (1, 9, 12):
            with self.subTest(pointer_format=pointer_format):
                result = macho_pac.inspect_macho(fixture(pointer_format=pointer_format))
                self.assertEqual(result["chained_fixups"]["pointer_formats"], [pointer_format])
                self.assertEqual(result["cfstring"]["strings"][0]["text"], "unit test")

    def test_bytes_pathlib_and_cli_path_api(self):
        data = fixture()
        self.assertEqual(macho_pac.inspect_macho(data)["sha256"], hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.macho"
            path.write_bytes(data)
            self.assertEqual(macho_pac.inspect_macho(path)["file_size"], len(data))
            self.assertEqual(macho_pac.inspect_macho(str(path))["uuid"],
                             "00112233-4455-6677-8899-aabbccddeeff")

    def test_authenticated_legacy_panel_geometry_is_rejected(self):
        # Sanitized stand-in for the old panel's repeated 0x4010000000000042
        # unauthenticated CoreFoundation bind; no original binary is checked in.
        with self.assertRaisesRegex(ValueError, "not pointer-authenticated"):
            macho_pac.inspect_macho(fixture(auth=False))

    def test_rejects_wrong_key_diversity_and_addr_div(self):
        cases = (({"key": 0}, "PAC key/address-diversity/discriminator"),
                 ({"diversity": 0x6AE0}, "PAC key/address-diversity/discriminator"),
                 ({"addr_div": 0}, "PAC key/address-diversity/discriminator"))
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                macho_pac.inspect_macho(fixture(**kwargs))

    def test_rejects_wrong_symbol_import_ordinal_and_bad_import_library_ordinal(self):
        with self.assertRaisesRegex(ValueError, "does not bind CoreFoundation"):
            macho_pac.inspect_macho(fixture(symbol="_wrongSymbol"))
        with self.assertRaisesRegex(ValueError, "pointer import ordinal"):
            macho_pac.inspect_macho(fixture(out_of_bounds=True))
        with self.assertRaisesRegex(ValueError, "library ordinal out of range"):
            macho_pac.inspect_macho(fixture(library_ordinal=3))

    def test_rejects_duplicate_chain_start_cycle(self):
        with self.assertRaisesRegex(ValueError, "overlapping/cyclic"):
            macho_pac.inspect_macho(fixture(cycle=True))

    def test_rejects_out_of_bounds_string_and_bad_flags(self):
        data = bytearray(fixture())
        # CFString length word is its fourth 64-bit field.
        p64(data, DATA_FILE + CF_OFF + 24, 0x7FFFFFFF)
        # Rebuild signature so the failure is the CFString range, not its hash.
        data[0x4000:] = make_signature(data, 0x4000)
        with self.assertRaisesRegex(ValueError, "CFString|VM address|section"):
            macho_pac.inspect_macho(bytes(data))
        with self.assertRaisesRegex(ValueError, "CFString flags"):
            macho_pac.inspect_macho(fixture(flags=0x1234))

    def test_rejects_page_hash_tampering(self):
        data = bytearray(fixture())
        data[TEXT_FILE + TEXT_OFF] ^= 1
        with self.assertRaisesRegex(ValueError, "page hash mismatch"):
            macho_pac.inspect_macho(bytes(data))

    def test_rejects_missing_signature_and_out_of_bounds_fixups(self):
        data = bytearray(fixture())
        commands = 32
        for _ in range(u32(data, 16)):
            cmd, size = struct.unpack_from("<2I", data, commands)
            if cmd == macho_pac.LC_CODE_SIGNATURE:
                p32(data, commands, 0x77777777)
                break
            commands += size
        with self.assertRaisesRegex(ValueError, "missing LC_CODE_SIGNATURE"):
            macho_pac.inspect_macho(bytes(data))
        data = bytearray(fixture())
        commands = 32
        for _ in range(u32(data, 16)):
            cmd, size = struct.unpack_from("<2I", data, commands)
            if cmd == macho_pac.LC_DYLD_CHAINED_FIXUPS:
                p32(data, commands + 12, len(data) + 10)
                break
            commands += size
        with self.assertRaisesRegex(ValueError, "chained-fixups data out of bounds"):
            macho_pac.inspect_macho(bytes(data))

    def test_rejects_fat_truncated_and_unauthenticated_header(self):
        good = fixture()
        with self.assertRaisesRegex(ValueError, "thin little-endian"):
            macho_pac.inspect_macho(b"\xca\xfe\xba\xbe" + good)
        with self.assertRaisesRegex(ValueError, "truncated Mach-O header"):
            macho_pac.inspect_macho(good[:31])
        with self.assertRaisesRegex(ValueError, "arm64e subtype"):
            macho_pac.inspect_macho(good[:8] + struct.pack("<I", 0) + good[12:])

    def test_cli_reports_nonzero_on_bad_binary(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.macho"
            path.write_bytes(b"bad")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = macho_pac.main([str(path)])
            self.assertEqual(status, 1)
            self.assertIn("truncated Mach-O header", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
