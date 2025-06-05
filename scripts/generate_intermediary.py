#!/usr/bin/env python3
"""
generate_intermediary.py
========================

Very small proof-of-concept script that turns Mojang's named mappings into
stable hashed “intermediary” names (class_XXXX, method_XXXX, field_XXXX).

❗ Replace the hashing / name scheme with your preferred logic or hook up
Fabric's Stitch/Tiny-Remapper for production use.
"""
from pathlib import Path
import hashlib
import re
import sys

VERSIONS_DIR = Path('server-jars/versions')
OUTPUT_ROOT = Path('mappings')
OUTPUT_ROOT.mkdir(exist_ok=True)

TINY_HEADER = 'tiny\t2\t0\tofficial\tintermediary\n'

def sha8(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]

def gen_for_version(version_path: Path) -> None:
    version = version_path.name
    mojang = version_path / 'mojang-mappings.txt'
    if not mojang.exists():
        print(f'[SKIP] {version} - no mojang-mappings.txt')
        return

    out_dir = OUTPUT_ROOT / version
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'intermediary.tiny'

    with mojang.open('r') as src, out_file.open('w') as dst:
        dst.write(TINY_HEADER)
        current_class_official = None
        for line in src:
            if line.startswith('#') or not line.strip():
                continue

            if line.startswith('CLASS'):
                _, official, named = line.strip().split('\t')
                inter = f'class_{sha8(official)}'
                dst.write(f'c\t{official}\t{inter}\n')
                current_class_official = official

            elif line.startswith('FIELD'):
                _, official, desc, named = line.strip().split('\t')
                inter = f'field_{sha8(official + desc)}'
                dst.write(f'\tf\t{official}\t{desc}\t{inter}\n')

            elif line.startswith('METHOD'):
                _, official, desc, named = line.strip().split('\t')
                inter = f'method_{sha8(official + desc)}'
                dst.write(f'\tm\t{official}\t{desc}\t{inter}\n')

    print(f'[DONE]   {version} -> {out_file.relative_to(Path.cwd())}')

def main() -> None:
    for version_path in sorted(VERSIONS_DIR.iterdir()):
        if version_path.is_dir():
            gen_for_version(version_path)

if __name__ == '__main__':
    main()
