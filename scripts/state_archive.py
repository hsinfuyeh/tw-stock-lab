"""Only public application data; exclude locks and derived duplicate bundles."""
from pathlib import Path
import sys
import tarfile


def main():
    command,filename=sys.argv[1:]
    root=Path('data')
    if command=='pack':
        if not root.exists(): return
        with tarfile.open(filename,'w:gz') as archive:
            for path in root.rglob('*'):
                if path.is_file() and not path.is_symlink() and 'snapshots' not in path.parts and path.name not in ('update.lock','market-bundles.json'):
                    archive.add(path,arcname=path.as_posix(),recursive=False)
    elif command=='restore':
        with tarfile.open(filename,'r:gz') as archive:
            for member in archive.getmembers():
                path=Path(member.name)
                if not member.isfile() or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='data':
                    raise ValueError('Unsafe state archive member')
            archive.extractall('.',filter='data')
    else: raise ValueError('Unknown archive command')


if __name__=='__main__': main()
