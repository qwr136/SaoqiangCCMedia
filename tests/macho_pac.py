#!/usr/bin/env python3
"""Strict offline arm64e Mach-O, CFString PAC and CodeDirectory checker.

inspect_macho accepts a filesystem path (str or pathlib.Path) or an in-memory
bytes-like object, returns JSON-safe evidence, and raises ValueError/OSError on
any failed gate. It verifies embedded page hashes, not CMS trust or device load.
The CodeDirectory layout/page hashing follows the checked TrollFools verifier
pattern at xiaofei-tweaks/assets/trollfools/tests/verify_dylib.py, extended here
for arm64e chained fixups and authenticated CFString ISAs.
"""

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path
from uuid import UUID

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
FILETYPES = {2: "MH_EXECUTE", 6: "MH_DYLIB", 8: "MH_BUNDLE"}
LC_SEGMENT_64 = 0x19
LC_UUID = 0x1B
LC_CODE_SIGNATURE = 0x1D
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LAZY_LOAD_DYLIB = 0x20
LC_LOAD_UPWARD_DYLIB = 0x80000023
LOAD_DYLIBS = {LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB,
               LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB}
LC_DYLD_CHAINED_FIXUPS = 0x80000034
LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_IPHONEOS = 0x25
EMBEDDED_SIGNATURE = 0xFADE0CC0
CODEDIRECTORY = 0xFADE0C02
HASHES = {2: ("sha256", 32), 4: ("sha384", 48)}
CD_HEADERS = {0x20000: 44, 0x20100: 48, 0x20200: 52, 0x20300: 88,
              0x20400: 92, 0x20500: 96, 0x20600: 108}
CHAINED_IMPORT = 1
CHAINED_IMPORT_ADDEND = 2
CHAINED_IMPORT_ADDEND64 = 3
CHAINED_PTR_ARM64E = 1
CHAINED_PTR_ARM64E_USERLAND = 9
CHAINED_PTR_ARM64E_USERLAND24 = 12
SUPPORTED_POINTER_FORMATS = {CHAINED_PTR_ARM64E, CHAINED_PTR_ARM64E_USERLAND,
                             CHAINED_PTR_ARM64E_USERLAND24}
CFSTRING_ISA_SYMBOL = "___CFConstantStringClassReference"
CFSTRING_DIVERSITY = 0x6AE1
PAC_KEYS = {0: "IA", 1: "IB", 2: "DA", 3: "DB"}
MAX_FILE_SIZE = 512 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_range(data, offset, size, end=None, label="range"):
    if end is None:
        end = len(data)
    require(isinstance(offset, int) and isinstance(size, int) and offset >= 0 and
            size >= 0 and offset <= end and size <= end - offset,
            label + " out of bounds")
    return offset + size


def c_string(data, offset, end, label, encoding="utf-8"):
    require(0 <= offset < end <= len(data), label + " offset out of bounds")
    terminator = data.find(b"\0", offset, end)
    require(terminator >= offset, "unterminated " + label)
    try:
        return data[offset:terminator].decode(encoding)
    except UnicodeDecodeError as error:
        raise ValueError("invalid " + label + " encoding") from error


def version_text(value):
    return f"{value >> 16}.{(value >> 8) & 255}.{value & 255}"


def _input_bytes(source):
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
        require(len(data) <= MAX_FILE_SIZE, "Mach-O exceeds the verifier size limit")
        return data, None
    path = Path(source)
    require(path.is_file(), "Mach-O is not a regular file: " + str(path))
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_SIZE + 1)
    require(len(data) <= MAX_FILE_SIZE, "Mach-O exceeds the verifier size limit")
    return data, path


def _segment_name(raw):
    try:
        return raw.split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("non-ASCII Mach-O segment or section name") from error


def _parse_macho(data):
    require(len(data) >= 32, "truncated Mach-O header")
    magic, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from(
        "<8I", data, 0)
    require(magic == MH_MAGIC_64, "requires a thin little-endian 64-bit Mach-O (fat/other rejected)")
    require(cpu == CPU_TYPE_ARM64 and (subtype & 0x00FFFFFF) == CPU_SUBTYPE_ARM64E,
            "requires CPU_TYPE_ARM64 / arm64e subtype")
    require(filetype in FILETYPES and reserved == 0, "unsupported Mach-O file type or reserved header")
    commands_end = checked_range(data, 32, sizeofcmds, label="load-command table")
    require(ncmds > 0 and ncmds <= sizeofcmds // 8, "invalid load-command count")

    commands = []
    segments = []
    dependencies = []
    uuid = None
    deployment = None
    signature = None
    chained = None
    cursor = 32
    for index in range(ncmds):
        require(cursor + 8 <= commands_end, "truncated load command")
        cmd, size = struct.unpack_from("<2I", data, cursor)
        require(size >= 8 and size % 8 == 0 and cursor + size <= commands_end,
                "invalid load-command size at index " + str(index))
        item = {"index": index, "cmd": hex(cmd), "offset": cursor, "size": size}
        commands.append(item)

        if cmd == LC_SEGMENT_64:
            require(size >= 72, "short LC_SEGMENT_64")
            (raw_name, vmaddr, vmsize, fileoff, filesize, maxprot, initprot,
             nsects, segflags) = struct.unpack_from("<16s4Q4I", data, cursor + 8)
            name = _segment_name(raw_name)
            require(name and all(seg["name"] != name for seg in segments),
                    "empty or duplicate segment name")
            require(size == 72 + nsects * 80, "malformed LC_SEGMENT_64 section count")
            require(filesize <= vmsize and fileoff <= len(data) and
                    filesize <= len(data) - fileoff, "segment file range out of bounds")
            require(vmaddr + vmsize <= 1 << 64, "segment VM range overflows")
            seg = {"name": name, "vmaddr": vmaddr, "vmsize": vmsize,
                   "fileoff": fileoff, "filesize": filesize,
                   "maxprot": maxprot, "initprot": initprot, "flags": segflags,
                   "sections": []}
            for section_index in range(nsects):
                off = cursor + 72 + section_index * 80
                values = struct.unpack_from("<16s16sQQIIIIIIII", data, off)
                sectname, segname, addr, section_size, section_off, align, reloff, nreloc = values[:8]
                section_flags, reserved1, reserved2, reserved3 = values[8:]
                sec_name = _segment_name(sectname)
                sec_seg = _segment_name(segname)
                require(sec_name and sec_seg == name, "section segment name mismatch")
                require(addr >= vmaddr and addr + section_size <= vmaddr + vmsize,
                        "section VM range outside segment")
                require(align <= 63, "invalid section alignment")
                sec_type = section_flags & 0xFF
                zerofill = sec_type in (0x01, 0x0C, 0x12)
                if not zerofill:
                    require(section_off >= fileoff and section_off <= fileoff + filesize and
                            section_size <= fileoff + filesize - section_off,
                            "section file range outside segment")
                    require(addr - vmaddr == section_off - fileoff,
                            "section VM/file mapping mismatch")
                if nreloc:
                    checked_range(data, reloff, nreloc * 8, label="section relocations")
                sec = {"segment": name, "name": sec_name, "addr": addr,
                       "size": section_size, "offset": section_off,
                       "align": align, "flags": section_flags,
                       "zerofill": zerofill, "reserved1": reserved1,
                       "reserved2": reserved2, "reserved3": reserved3}
                seg["sections"].append(sec)
            segments.append(seg)
        elif cmd in LOAD_DYLIBS:
            require(size >= 24, "short dylib load command")
            nameoff, timestamp, current, compatibility = struct.unpack_from(
                "<4I", data, cursor + 8)
            require(24 <= nameoff < size, "dylib path offset out of range")
            name = c_string(data, cursor + nameoff, cursor + size, "dylib install name", "ascii")
            dependencies.append(name)
            item["name"] = name
            item["current_version"] = version_text(current)
            item["compatibility_version"] = version_text(compatibility)
        elif cmd == LC_UUID:
            require(uuid is None and size == 24, "malformed or duplicate LC_UUID")
            uuid = str(UUID(bytes=data[cursor + 8:cursor + 24]))
            item["uuid"] = uuid
        elif cmd in (LC_BUILD_VERSION, LC_VERSION_MIN_IPHONEOS):
            require(deployment is None, "multiple deployment-version commands")
            if cmd == LC_BUILD_VERSION:
                require(size >= 24, "short LC_BUILD_VERSION")
                platform, minimum, sdk, ntools = struct.unpack_from("<4I", data, cursor + 8)
                require(size == 24 + ntools * 8, "malformed LC_BUILD_VERSION tool list")
                require(platform == 2, "LC_BUILD_VERSION is not iOS device platform")
                deployment = {"minimum": minimum, "sdk": sdk, "platform": "iOS"}
            else:
                require(size == 16, "malformed LC_VERSION_MIN_IPHONEOS")
                minimum, sdk = struct.unpack_from("<2I", data, cursor + 8)
                deployment = {"minimum": minimum, "sdk": sdk, "platform": "iOS (legacy command)"}
        elif cmd == LC_CODE_SIGNATURE:
            require(signature is None and size == 16, "malformed or duplicate LC_CODE_SIGNATURE")
            signature = struct.unpack_from("<2I", data, cursor + 8)
            item["dataoff"], item["datasize"] = signature
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            require(chained is None and size == 16, "malformed or duplicate LC_DYLD_CHAINED_FIXUPS")
            chained = struct.unpack_from("<2I", data, cursor + 8)
            item["dataoff"], item["datasize"] = chained
        cursor += size
    require(cursor == commands_end, "load-command size/count disagreement")
    require(uuid is not None, "missing LC_UUID")
    require(deployment is not None, "missing iOS deployment-version command")
    require(deployment["minimum"] >> 16 >= 15, "minimum iOS deployment target is below 15.0")
    require(deployment["sdk"] >= deployment["minimum"], "SDK version precedes deployment target")
    require(signature is not None, "missing LC_CODE_SIGNATURE")
    require(chained is not None, "missing LC_DYLD_CHAINED_FIXUPS")
    require(any(seg["name"] == "__TEXT" for seg in segments), "missing __TEXT segment")
    linkedit = next((seg for seg in segments if seg["name"] == "__LINKEDIT"), None)
    require(linkedit is not None, "missing __LINKEDIT segment")
    file_ranges = sorted((s["fileoff"], s["fileoff"] + s["filesize"])
                         for s in segments if s["filesize"])
    require(all(a[1] <= b[0] for a, b in zip(file_ranges, file_ranges[1:])),
            "overlapping file-backed segments")
    sigoff, sigsize = signature
    require(sigsize >= 12 and sigoff + sigsize == len(data),
            "signature must cover the final file range with no trailing bytes")
    require(linkedit["fileoff"] <= sigoff and sigoff + sigsize == linkedit["fileoff"] + linkedit["filesize"],
            "signature range is not the final __LINKEDIT data")
    fixoff, fixsize = chained
    checked_range(data, fixoff, fixsize, label="chained-fixups data")
    require(linkedit["fileoff"] <= fixoff and fixoff + fixsize <= sigoff,
            "chained-fixups data is outside pre-signature __LINKEDIT")
    return {"cpu_type": cpu, "cpu_subtype": subtype, "filetype": filetype,
            "header_flags": flags, "uuid": uuid, "deployment": deployment,
            "commands": commands, "segments": segments, "dependencies": dependencies,
            "signature_range": signature, "chained_range": chained}


def _vm_to_file(data, segments, vmaddr, size=1):
    for segment in segments:
        start = segment["vmaddr"]
        end = start + segment["filesize"]
        if start <= vmaddr and vmaddr <= end and size <= end - vmaddr:
            offset = segment["fileoff"] + (vmaddr - start)
            checked_range(data, offset, size, label="VM-to-file mapping")
            return offset
    raise ValueError("VM address is not in file-backed segment: " + hex(vmaddr))


def _parse_imports(data, fix_start, fix_end, imports_offset, symbols_offset,
                   imports_count, imports_format, symbols_format):
    require(imports_format in (CHAINED_IMPORT, CHAINED_IMPORT_ADDEND,
                               CHAINED_IMPORT_ADDEND64), "unsupported chained import format")
    entry_size = {CHAINED_IMPORT: 4, CHAINED_IMPORT_ADDEND: 8,
                  CHAINED_IMPORT_ADDEND64: 16}[imports_format]
    imports_start = fix_start + imports_offset
    symbols_start = fix_start + symbols_offset
    checked_range(data, imports_start, imports_count * entry_size, fix_end,
                  "chained imports table")
    require(fix_start + 28 <= imports_start <= fix_end and
            fix_start + 28 <= symbols_start <= fix_end,
            "chained-fixups offsets out of bounds")
    raw_symbols = data[symbols_start:fix_end]
    if symbols_format == 0:
        symbols = raw_symbols
    elif symbols_format == 1:
        require(len(raw_symbols) >= 5, "short compressed chained symbol pool")
        expected_size = struct.unpack_from("<I", raw_symbols, 0)[0]
        try:
            decoder = zlib.decompressobj()
            symbols = decoder.decompress(raw_symbols[4:]) + decoder.flush()
        except zlib.error as error:
            raise ValueError("invalid compressed chained symbol pool") from error
        require(decoder.eof and not decoder.unused_data and len(symbols) == expected_size,
                "compressed chained symbol pool size mismatch")
    else:
        raise ValueError("unsupported chained symbols format")

    result = []
    for index in range(imports_count):
        pos = imports_start + index * entry_size
        if imports_format in (CHAINED_IMPORT, CHAINED_IMPORT_ADDEND):
            word = struct.unpack_from("<I", data, pos)[0]
            ordinal = word & 0xFF
            if ordinal & 0x80:
                ordinal -= 0x100
            weak = bool((word >> 8) & 1)
            name_offset = word >> 9
            addend = struct.unpack_from("<i", data, pos + 4)[0] if imports_format == CHAINED_IMPORT_ADDEND else 0
        else:
            word = struct.unpack_from("<Q", data, pos)[0]
            ordinal = word & 0xFFFF
            if ordinal & 0x8000:
                ordinal -= 0x10000
            weak = bool((word >> 16) & 1)
            require((word >> 17) & 0x7FFF == 0, "reserved chained import bits are nonzero")
            name_offset = (word >> 32) & 0xFFFFFFFF
            addend = struct.unpack_from("<q", data, pos + 8)[0]
        symbol = c_string(symbols, name_offset, len(symbols), "chained import symbol", "utf-8")
        result.append({"index": index, "library_ordinal": ordinal, "weak": weak,
                       "symbol": symbol, "addend": addend})
    return result


def _validate_import_libraries(imports, dependencies):
    for item in imports:
        ordinal = item["library_ordinal"]
        require(ordinal <= 0 or ordinal <= len(dependencies),
                "chained import library ordinal out of range")
        item["library"] = dependencies[ordinal - 1] if ordinal > 0 else {
            0: "self", -1: "main executable", -2: "flat lookup", -3: "weak lookup"
        }.get(ordinal, "special ordinal " + str(ordinal))


def _decode_pointer(raw, pointer_format, imports, image_base, segments, location_vm):
    auth = (raw >> 63) & 1
    bind = (raw >> 62) & 1
    next_count = (raw >> 51) & 0x7FF
    ordinal_bits = 24 if pointer_format == CHAINED_PTR_ARM64E_USERLAND24 else 16
    result = {"vm": location_vm, "raw": f"0x{raw:016x}", "auth": bool(auth),
              "bind": bool(bind), "next": next_count,
              "pointer_format": pointer_format}
    if bind:
        ordinal_mask = (1 << ordinal_bits) - 1
        reserved = (raw >> ordinal_bits) & ((1 << (32 - ordinal_bits)) - 1)
        require(reserved == 0, "nonzero reserved bits in chained bind pointer")
        import_index = raw & ordinal_mask
        require(import_index < len(imports), "chained pointer import ordinal out of range")
        item = imports[import_index]
        result.update({"import_index": import_index, "symbol": item["symbol"],
                       "library_ordinal": item["library_ordinal"], "library": item["library"],
                       "weak": item["weak"], "import_addend": item["addend"]})
        if auth:
            result.update({"diversity": (raw >> 32) & 0xFFFF,
                           "addr_div": (raw >> 48) & 1,
                           "key": (raw >> 49) & 3,
                           "key_name": PAC_KEYS[(raw >> 49) & 3]})
        else:
            addend = (raw >> 32) & 0x7FFFF
            if addend & 0x40000:
                addend -= 0x80000
            result["addend"] = addend
    else:
        if auth:
            target_field = raw & 0xFFFFFFFF
            target_vm = target_field if pointer_format == CHAINED_PTR_ARM64E else image_base + target_field
            result.update({"target": target_vm, "diversity": (raw >> 32) & 0xFFFF,
                           "addr_div": (raw >> 48) & 1, "key": (raw >> 49) & 3,
                           "key_name": PAC_KEYS[(raw >> 49) & 3]})
        else:
            low_target = raw & ((1 << 43) - 1)
            high8 = (raw >> 43) & 0xFF
            target_vm = ((high8 << 56) | low_target) if pointer_format == CHAINED_PTR_ARM64E else image_base + low_target
            result.update({"target": target_vm, "high8": high8})
        normalized_target = target_vm & 0x00FFFFFFFFFFFFFF
        require(any(seg["vmaddr"] <= normalized_target < seg["vmaddr"] + seg["vmsize"]
                    for seg in segments),
                "chained rebase target is outside image segments")
    return result


def _parse_chained_fixups(data, fix_range, segments, dependencies):
    fixoff, fixsize = fix_range
    fixend = checked_range(data, fixoff, fixsize, label="chained-fixups data")
    require(fixsize >= 28, "short chained-fixups header")
    version, starts_offset, imports_offset, symbols_offset, imports_count, imports_format, symbols_format = struct.unpack_from(
        "<7I", data, fixoff)
    require(version == 0, "unsupported chained-fixups version")
    require(all(28 <= fixoff + value <= fixend for value in
                (starts_offset, imports_offset, symbols_offset)),
            "chained-fixups table offset out of bounds")
    starts = fixoff + starts_offset
    require(starts + 4 <= fixend, "short chained starts-in-image")
    segment_count = struct.unpack_from("<I", data, starts)[0]
    require(segment_count == len(segments) and segment_count <= (fixend - starts - 4) // 4,
            "chained starts segment count mismatch")
    segment_offsets = struct.unpack_from("<" + "I" * segment_count, data, starts + 4) if segment_count else ()
    imports = _parse_imports(data, fixoff, fixend, imports_offset, symbols_offset,
                             imports_count, imports_format, symbols_format)
    _validate_import_libraries(imports, dependencies)
    image_base = min(seg["vmaddr"] for seg in segments if seg["vmsize"])
    fixups = []
    summaries = []
    visited_locations = set()
    start_records_seen = set()

    for seg_index, relative in enumerate(segment_offsets):
        if relative == 0:
            continue
        record = starts + relative
        require(record not in start_records_seen, "duplicate chained segment-start record")
        start_records_seen.add(record)
        require(record + 22 <= fixend, "short chained starts-in-segment record")
        record_size, page_size, pointer_format, segment_offset, max_valid, page_count = struct.unpack_from(
            "<IHHQIH", data, record)
        require(record_size >= 22 + 2 * page_count and record + record_size <= fixend,
                "chained starts-in-segment size out of bounds")
        require(pointer_format in SUPPORTED_POINTER_FORMATS,
                "unsupported chained pointer format " + str(pointer_format))
        require(page_size >= 4096 and page_size <= 65536 and page_size & (page_size - 1) == 0,
                "invalid chained-fixups page size")
        segment = segments[seg_index]
        require(segment_offset == segment["vmaddr"] - image_base,
                "chained segment offset does not match Mach-O segment")
        require(max_valid == 0, "unexpected max_valid_pointer for arm64e chain")
        page_array = record + 22
        page_starts_end = page_array + 2 * page_count
        require(page_starts_end <= record + record_size, "chained page-start array out of bounds")
        starts_array_count = record_size - 22
        starts_array_count //= 2
        visited_count = 0

        def chain_starts_for_page(page_start):
            if page_start == 0xFFFF:
                return []
            if not page_start & 0x8000:
                return [page_start]
            index = page_start & 0x7FFF
            require(index >= page_count, "multi-start index overlaps page-start entries")
            seen_indices = set()
            result = []
            while True:
                require(index not in seen_indices, "cycle in chained multi-start list")
                seen_indices.add(index)
                require(index < starts_array_count, "chained multi-start index out of bounds")
                value = struct.unpack_from("<H", data, page_array + index * 2)[0]
                result.append(value & 0x7FFF)
                last = bool(value & 0x8000)
                if last:
                    break
                index += 1
            return result

        for page_index in range(page_count):
            page_start = struct.unpack_from("<H", data, page_array + page_index * 2)[0]
            page_base = segment["vmaddr"] + page_index * page_size
            page_file_bytes = min(page_size, max(0, segment["filesize"] - page_index * page_size))
            page_end_vm = page_base + page_file_bytes
            for chain_start in chain_starts_for_page(page_start):
                require(chain_start % 8 == 0, "unaligned chained pointer start")
                location = page_base + chain_start
                require(location + 8 <= page_end_vm,
                        "chained pointer start outside file-backed page")
                chain_seen = set()
                while True:
                    require(location not in chain_seen, "cycle in chained pointer chain")
                    require(location not in visited_locations,
                            "overlapping/cyclic chained pointer chains")
                    chain_seen.add(location)
                    visited_locations.add(location)
                    require(location + 8 <= page_end_vm,
                            "chained pointer leaves page or file-backed segment")
                    fileoff = _vm_to_file(data, segments, location, 8)
                    raw = struct.unpack_from("<Q", data, fileoff)[0]
                    item = _decode_pointer(raw, pointer_format, imports, image_base,
                                           segments, location)
                    item["file_offset"] = fileoff
                    item["segment"] = segment["name"]
                    fixups.append(item)
                    visited_count += 1
                    next_count = item["next"]
                    if not next_count:
                        break
                    location += next_count * 8
                    require(location < page_end_vm,
                            "chained pointer next offset leaves page or file-backed segment")
        summaries.append({"segment": segment["name"], "segment_index": seg_index,
                          "pointer_format": pointer_format, "page_size": page_size,
                          "page_count": page_count, "fixup_count": visited_count})

    require(fixups, "no chained fixups were walked")
    formats = sorted({item["pointer_format"] for item in fixups})
    return {"version": version, "imports_format": imports_format,
            "symbols_format": symbols_format, "import_count": len(imports),
            "imports": imports, "pointer_formats": formats,
            "segments": summaries, "fixup_count": len(fixups), "fixups": fixups}


def _check_code_directory(data, start, end, code_limit, blobs_by_slot):
    directory = data[start:end]
    require(len(directory) >= 44, "short CodeDirectory")
    magic, length = struct.unpack_from(">2I", directory, 0)
    require(magic == CODEDIRECTORY and length == len(directory), "invalid CodeDirectory blob")
    version, flags, hash_offset, ident_offset, special_slots, code_slots, limit32 = struct.unpack_from(
        ">7I", directory, 8)
    require(version in CD_HEADERS and len(directory) >= CD_HEADERS[version],
            "unsupported or truncated CodeDirectory version")
    hash_size, hash_type, platform, page_shift = struct.unpack_from("4B", directory, 36)
    require(hash_type in HASHES and HASHES[hash_type][1] == hash_size,
            "unsupported CodeDirectory hash type/size")
    if version >= 0x20100:
        scatter_offset = struct.unpack_from(">I", directory, 44)[0]
        require(scatter_offset == 0, "scatter CodeDirectory hashing is unsupported")
    if version >= 0x20300:
        limit64 = struct.unpack_from(">Q", directory, 56)[0]
    else:
        limit64 = 0
    effective_limit = limit64 or limit32
    require(effective_limit == code_limit and
            (not limit64 or limit32 in (0, code_limit, 0xFFFFFFFF)),
            "CodeDirectory does not cover the complete pre-signature image")
    require(code_limit > 0 and (page_shift == 0 or 12 <= page_shift <= 16),
            "invalid CodeDirectory page size")
    page_size = (1 << page_shift) if page_shift else code_limit
    expected_slots = (code_limit + page_size - 1) // page_size
    require(code_slots == expected_slots, "wrong CodeDirectory code hash count")
    special_offset = hash_offset - special_slots * hash_size
    require(hash_offset >= 0 and special_offset >= 0 and
            CD_HEADERS[version] <= ident_offset < special_offset and
            hash_offset + code_slots * hash_size <= len(directory),
            "CodeDirectory identifier or hash table out of bounds")
    identifier = c_string(directory, ident_offset, special_offset, "CodeDirectory identifier", "utf-8")
    team_id = None
    if version >= 0x20200:
        team_offset = struct.unpack_from(">I", directory, 48)[0]
        if team_offset:
            require(CD_HEADERS[version] <= team_offset < special_offset,
                    "CodeDirectory team identifier offset out of bounds")
            team_id = c_string(directory, team_offset, special_offset, "CodeDirectory team identifier", "utf-8")
    if version >= 0x20500:
        pre_encrypt_offset = struct.unpack_from(">I", directory, 92)[0]
        require(pre_encrypt_offset == 0, "pre-encryption CodeDirectory hashes are unsupported")
    if version >= 0x20600:
        linkage_offset = struct.unpack_from(">I", directory, 100)[0]
        linkage_size = struct.unpack_from(">I", directory, 104)[0]
        require(linkage_offset == 0 and linkage_size == 0,
                "CodeDirectory linkage data is unsupported")

    algorithm = HASHES[hash_type][0]
    for slot in range(1, special_slots + 1):
        offset = hash_offset - slot * hash_size
        stored = directory[offset:offset + hash_size]
        payload = blobs_by_slot.get(slot)
        if payload is not None:
            expected = hashlib.new(algorithm, payload).digest()[:hash_size]
            require(stored == expected, "CodeDirectory special-slot hash mismatch: " + str(slot))
    for slot, page_start in enumerate(range(0, code_limit, page_size)):
        offset = hash_offset + slot * hash_size
        expected = hashlib.new(algorithm, data[page_start:min(page_start + page_size, code_limit)]).digest()[:hash_size]
        require(directory[offset:offset + hash_size] == expected,
                "CodeDirectory page hash mismatch: " + str(slot))
    return {"identifier": identifier, "team_id": team_id, "version": hex(version),
            "flags": hex(flags), "ad_hoc": bool(flags & 0x2),
            "hash_type": hash_type, "hash_algorithm": algorithm,
            "page_size": page_size, "page_count": code_slots,
            "page_hashes_verified": code_slots, "special_slots": special_slots}


def _check_signature(data, signature_range):
    sigoff, sigsize = signature_range
    sigend = checked_range(data, sigoff, sigsize, label="embedded signature")
    require(sigsize >= 12, "short embedded signature SuperBlob")
    magic, super_length, count = struct.unpack_from(">3I", data, sigoff)
    require(magic == EMBEDDED_SIGNATURE and count > 0 and count <= 64,
            "invalid embedded signature SuperBlob header")
    index_end = 12 + count * 8
    require(index_end <= super_length <= sigsize, "SuperBlob index/length out of bounds")
    require(not any(data[sigoff + super_length:sigend]), "nonzero padding after signature SuperBlob")
    slots = {}
    ranges = []
    for index in range(count):
        slot, offset = struct.unpack_from(">2I", data, sigoff + 12 + index * 8)
        require(index_end <= offset <= super_length - 8 and slot not in slots,
                "invalid or duplicate embedded signature slot")
        blob_start = sigoff + offset
        kind, length = struct.unpack_from(">2I", data, blob_start)
        require(length >= 8 and length <= super_length - offset,
                "embedded signature blob out of bounds")
        blob_end = blob_start + length
        slots[slot] = (kind, blob_start, blob_end)
        ranges.append((blob_start, blob_end))
    ranges.sort()
    require(all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:])),
            "overlapping embedded signature blobs")
    require(0 in slots, "missing primary CodeDirectory")

    blobs_by_slot = {slot: data[start:end] for slot, (_, start, end) in slots.items()}
    directories = []
    cms_present = False
    for slot, (kind, start, end) in slots.items():
        if slot == 0 or 0x1000 <= slot < 0x1006:
            require(kind == CODEDIRECTORY, "CodeDirectory slot has wrong blob magic")
            directories.append((slot, start, end))
        elif slot == 0x10000:
            require(kind == 0xFADE0B01, "CMS signature slot has wrong blob magic")
            cms_present = True
    checked = [_check_code_directory(data, start, end, sigoff, blobs_by_slot)
               for _, start, end in sorted(directories)]
    require(any(directory["hash_type"] == 2 for directory in checked),
            "missing full SHA-256 CodeDirectory")
    require(len({directory["identifier"] for directory in checked}) == 1,
            "CodeDirectory identifiers disagree")
    return {"verified": True, "offset": sigoff, "size": sigsize,
            "superblob_size": super_length, "cms_present": cms_present,
            "trust_verified": False, "code_limit": sigoff,
            "full_pre_signature_coverage": True,
            "code_directories": checked,
            "page_hashes_verified": sum(item["page_hashes_verified"] for item in checked)}


def _inspect_bytes(data, path):
    macho = _parse_macho(data)
    fixups = _parse_chained_fixups(data, macho["chained_range"], macho["segments"],
                                   macho["dependencies"])
    sections = [section for segment in macho["segments"] for section in segment["sections"]]
    cf_sections = [section for section in sections if section["name"] == "__cfstring"]
    require(cf_sections, "missing __cfstring section")
    cstring_sections = [section for section in sections
                        if section["name"] in ("__cstring", "__ustring") and not section["zerofill"]]
    by_vm = {item["vm"]: item for item in fixups["fixups"]}
    cfstrings = []
    for section in cf_sections:
        require(section["size"] % 32 == 0, "__cfstring size is not a multiple of 32")
        for vm in range(section["addr"], section["addr"] + section["size"], 32):
            fileoff = _vm_to_file(data, macho["segments"], vm, 32)
            isa_raw, string_flags, string_vm, length = struct.unpack_from("<4Q", data, fileoff)
            require(string_flags in (0x7C8, 0x7D0),
                    "unsupported or non-constant CFString flags at " + hex(vm))
            isa_fixup = by_vm.get(vm)
            require(isa_fixup is not None and isa_fixup["bind"],
                    "CFString ISA is missing a chained bind at " + hex(vm))
            require(isa_fixup["auth"],
                    "CFString ISA is not pointer-authenticated at " + hex(vm))
            require(isa_fixup["symbol"] == CFSTRING_ISA_SYMBOL and
                    "CoreFoundation.framework/CoreFoundation" in isa_fixup["library"],
                    "CFString ISA does not bind CoreFoundation constant-string class")
            require(not isa_fixup["weak"] and isa_fixup["import_addend"] == 0,
                    "CFString ISA import is weak or has nonzero addend")
            require(isa_fixup["key"] == 2 and isa_fixup["addr_div"] == 1 and
                    isa_fixup["diversity"] == CFSTRING_DIVERSITY,
                    "CFString ISA PAC key/address-diversity/discriminator mismatch")
            data_fixup = by_vm.get(vm + 16)
            require(data_fixup is not None and not data_fixup["bind"],
                    "CFString text pointer is missing an in-image rebase")
            # The on-disk word includes chain bits, not a runtime pointer.
            require(not data_fixup["auth"], "CFString text rebase must be unauthenticated")
            string_vm = data_fixup["target"]
            unit = 2 if string_flags & 0x10 else 1
            byte_count = length * unit
            require(length <= (1 << 31), "CFString length is unreasonable")
            text_end = string_vm + byte_count
            text_fileoff = _vm_to_file(data, macho["segments"], string_vm, byte_count + unit)
            backing = next((item for item in cstring_sections
                            if item["addr"] <= string_vm and
                            text_end + unit <= item["addr"] + item["size"]), None)
            require(backing is not None,
                    "CFString text and terminator are outside __cstring/__ustring")
            terminator = data[text_fileoff + byte_count:text_fileoff + byte_count + unit]
            require(terminator == b"\0" * unit, "CFString text is not terminated")
            raw_text = data[text_fileoff:text_fileoff + byte_count]
            try:
                text = raw_text.decode("utf-16-le" if unit == 2 else "utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("invalid CFString text encoding at " + hex(vm)) from error
            cfstrings.append({"vm": vm, "file_offset": fileoff,
                              "flags": string_flags, "length": length,
                              "text": text, "data_vm": string_vm,
                              "data_file_offset": text_fileoff,
                              "isa_fixup": isa_fixup, "data_fixup": data_fixup,
                              "text_section": backing["name"]})
    require(cfstrings, "no CFString constants were verified")
    signature = _check_signature(data, macho["signature_range"])
    authenticated_count = sum(1 for item in cfstrings if item["isa_fixup"]["auth"])
    return {"schema": 1, "path": str(path) if path is not None else None,
            "file_size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "architecture": "arm64e", "cpu_type": hex(macho["cpu_type"]),
            "cpu_subtype": hex(macho["cpu_subtype"]),
            "cpu_subtype_base": macho["cpu_subtype"] & 0x00FFFFFF,
            "cpu_subtype_capabilities": hex(macho["cpu_subtype"] & 0xFF000000),
            "filetype": FILETYPES[macho["filetype"]], "uuid": macho["uuid"],
            "minimum_os": version_text(macho["deployment"]["minimum"]),
            "sdk": version_text(macho["deployment"]["sdk"]),
            "platform": macho["deployment"]["platform"],
            "dependencies": macho["dependencies"], "load_commands": macho["commands"],
            "segments": [{k: seg[k] for k in ("name", "vmaddr", "vmsize", "fileoff", "filesize")}
                         for seg in macho["segments"]],
            "chained_fixups": fixups,
            "cfstring": {"count": len(cfstrings),
                         "isa_auth_counts": {"authenticated": authenticated_count,
                                              "unauthenticated": len(cfstrings) - authenticated_count},
                         "required_key": "DA", "required_addr_div": 1,
                         "required_diversity": hex(CFSTRING_DIVERSITY),
                         "strings": cfstrings},
            "signature": signature}


def inspect_macho(source):
    """Inspect a thin arm64e Mach-O path or bytes; raise ValueError/OSError on failure."""
    data, path = _input_bytes(source)
    return _inspect_bytes(data, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="thin arm64e Mach-O file")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect_macho(args.path), indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
