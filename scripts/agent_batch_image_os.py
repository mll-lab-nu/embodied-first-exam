"""Install the exact Debian package set from a dated, signed archive snapshot."""
import json
from pathlib import Path
import re
import subprocess


def install(root=Path('/opt/build')):
    snapshot = json.loads((root / 'os-source.json').read_text())['snapshot']
    if not re.fullmatch(r'\d{8}T\d{6}Z', snapshot):
        raise ValueError('invalid snapshot')
    wanted = json.loads((root / 'os-packages.json').read_text())
    packages = []
    for line in wanted:
        state, name, version = line.split()
        if state != 'installed' or not re.fullmatch(r'[a-z0-9+.:_-]+', name) or not re.fullmatch(r'[A-Za-z0-9.+:~_-]+', version):
            raise ValueError('invalid frozen OS package')
        packages.append(name + '=' + version)
    for path in Path('/etc/apt/sources.list.d').glob('*'):
        path.unlink()
    Path('/etc/apt/sources.list').write_text(
        f'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/{snapshot}/ bookworm main\n'
        f'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/{snapshot}/ bookworm-updates main\n'
        f'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/{snapshot}/ bookworm-security main\n')
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=3', 'update'], check=True)
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=3', 'install', '-y', '--no-install-recommends', *packages], check=True)
    actual = subprocess.check_output(['dpkg-query', '-W', '-f=${db:Status-Status} ${Package}:${Architecture} ${Version}\n'], text=True)
    if sorted(actual.splitlines()) != wanted:
        raise ValueError('installed OS packages differ from frozen reference')


if __name__ == '__main__':
    install()
