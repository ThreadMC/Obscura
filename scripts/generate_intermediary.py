#!/usr/bin/env python3
"""
generate_intermediary.py
========================

Very small proof-of-concept script that turns Mojang's named mappings into
stable hashed “intermediary” names (class_XXXX, method_XXXX, field_XXXX).
"""
from pathlib import Path
import hashlib
import sys
import tempfile
import shutil

VERSIONS_DIR = Path('server-jars/versions').resolve()
OUTPUT_ROOT = Path('mappings').resolve()
OUTPUT_ROOT.mkdir(exist_ok=True)

TINY_HEADER = 'v1\tofficial\tintermediary\n'

def sha8(text: str) -> str:
    return hashlib.sha1(text.strip().encode('utf-8')).hexdigest()[:8]

def parse_type(type_str):
    """
    Convert a Java type string to a JVM descriptor.
    Handles primitives, arrays, generics, inner classes, and fully qualified names.
    """
    primitives = {
        'void': 'V', 'boolean': 'Z', 'byte': 'B', 'char': 'C',
        'short': 'S', 'int': 'I', 'float': 'F', 'long': 'J', 'double': 'D'
    }

    def clean_type(t):
        # Remove generics and extra whitespace
        t = t.strip()
        while '<' in t and '>' in t:
            # Remove innermost generics
            lt = t.rfind('<')
            gt = t.find('>', lt)
            if lt != -1 and gt != -1:
                t = t[:lt] + t[gt+1:]
            else:
                break
        return t.replace('...', '[]').strip()

    t = clean_type(type_str)
    # Handle arrays
    array_dim = 0
    while t.endswith('[]'):
        array_dim += 1
        t = t[:-2].strip()
    # Handle primitives
    if t in primitives:
        desc = primitives[t]
    else:
        # Handle inner classes (replace last '.' with '$' if needed)
        # e.g. com.example.Outer.Inner -> com/example/Outer$Inner
        parts = t.split('.')
        for i in range(len(parts)-1, 0, -1):
            if parts[i][0].isupper():
                # likely inner class
                parts[i-1] = parts[i-1] + '$' + parts[i]
                del parts[i]
        desc = 'L' + '/'.join(parts) + ';'
    return '[' * array_dim + desc

def parse_method_desc(ret_type, params):
    # params: comma-separated types
    param_types = []
    if params.strip():
        for p in params.split(','):
            param_types.append(parse_type(p.strip()))
    return '(' + ''.join(param_types) + ')' + parse_type(ret_type)

def gen_for_version(version_path: Path) -> None:
    version = version_path.name
    mojang = (version_path / 'mojang-mappings.txt').resolve()
    if not mojang.exists():
        print(f'[SKIP] {version} - no mojang-mappings.txt')
        return

    out_dir = (OUTPUT_ROOT / version).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'intermediary.tiny'
    tmp_file = out_file.with_suffix('.tiny.tmp')

    try:
        with mojang.open('r', encoding='utf-8') as src, tmp_file.open('w', encoding='utf-8') as dst:
            dst.write(TINY_HEADER)
            current_class_official = None
            current_class_obf = None
            current_class_inter = None
            for lineno, line in enumerate(src, 1):
                line = line.rstrip('\n')
                if not line.strip() or line.strip().startswith('#'):
                    continue

                # Class line: e.g. com.mojang.math.Axis -> a:
                if not line.startswith(' '):
                    if '->' in line and line.endswith(':'):
                        parts = line.split('->')
                        if len(parts) == 2:
                            official = parts[0].strip()
                            obf = parts[1].strip()[:-1]  # remove trailing ':'
                            current_class_official = official
                            current_class_obf = obf
                            current_class_inter = f'net/minecraft/class_{sha8(official)}'
                            dst.write(f'CLASS\t{obf}\t{current_class_inter}\n')
                        else:
                            print(f'[WARN] {version}:{lineno} Malformed class line: {line}')
                            current_class_official = None
                            current_class_obf = None
                            current_class_inter = None
                    else:
                        print(f'[WARN] {version}:{lineno} Unknown line type: {line}')
                        current_class_official = None
                        current_class_obf = None
                        current_class_inter = None
                    continue

                # Member line (field or method)
                if current_class_official is None or current_class_obf is None:
                    print(f'[WARN] {version}:{lineno} Member line outside class: {line}')
                    continue

                member_line = line.strip()
                if '->' not in member_line:
                    print(f'[WARN] {version}:{lineno} Malformed member line: {line}')
                    continue

                left, right = member_line.split('->', 1)
                left = left.strip()
                obf = right.strip()

                # Field or Method
                if '(' in left and ')' in left:
                    # Method
                    method_left = left
                    if ':' in method_left and method_left.split(':', 1)[0].isdigit():
                        method_left = method_left.split(':', 2)[-1]
                    try:
                        ret_and_rest = method_left.strip().split(' ', 1)
                        if len(ret_and_rest) != 2:
                            raise ValueError
                        ret_type, name_and_params = ret_and_rest
                        method_name = name_and_params[:name_and_params.index('(')]
                        params = name_and_params[name_and_params.index('(')+1:name_and_params.index(')')]
                        desc = parse_method_desc(ret_type, params)
                        inter = f'method_{sha8(current_class_official + method_name + desc)}'
                        dst.write(f'METHOD\t{current_class_obf}\t{desc}\t{obf}\t{inter}\n')
                    except Exception:
                        print(f'[WARN] {version}:{lineno} Malformed method line: {line}')
                        continue
                else:
                    # Field
                    field_left = left
                    if ':' in field_left and field_left.split(':', 1)[0].isdigit():
                        field_left = field_left.split(':', 2)[-1]
                    try:
                        type_and_name = field_left.strip().split(' ', 1)
                        if len(type_and_name) != 2:
                            raise ValueError
                        field_type, field_name = type_and_name
                        desc = parse_type(field_type)
                        inter = f'field_{sha8(current_class_official + field_name + desc)}'
                        dst.write(f'FIELD\t{current_class_obf}\t{desc}\t{obf}\t{inter}\n')
                    except Exception:
                        print(f'[WARN] {version}:{lineno} Malformed field line: {line}')
                        continue

        shutil.move(str(tmp_file), str(out_file))
        print(f'[DONE]   {version} -> {out_file.relative_to(OUTPUT_ROOT.parent)}')
    except Exception as e:
        print(f'[ERROR] {version} - {e}')
        if tmp_file.exists():
            tmp_file.unlink()

def main() -> None:
    for version_path in sorted(VERSIONS_DIR.iterdir()):
        if version_path.is_dir():
            gen_for_version(version_path)

if __name__ == '__main__':
    main()