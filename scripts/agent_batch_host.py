"""Read-only host prerequisites, before installing tools or claiming trials."""
import platform
import shutil
import subprocess


def require_docker():
    """Check the engine and Compose; do not install software or start containers."""
    if platform.system() != 'Linux':
        raise ValueError('Run this batch in Bash on a Linux GPU host or GPU-enabled WSL 2, not Windows PowerShell.')
    wsl = 'microsoft' in platform.release().lower()
    hint = (' In Windows, start Docker Desktop in Linux-container mode and enable Settings > Resources > '
            'WSL Integration for this Ubuntu distribution, then reopen its terminal.' if wsl else
            ' Install and start Docker Engine with the Compose v2 plugin, and grant this user Docker access.')
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker CLI not found on PATH.' + hint +
                         ' The runner can build images automatically, but Docker is a host prerequisite. '
                         'No model request or trial was started.')

    def query(args, failure):
        try:
            result = subprocess.run([docker, *args], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError(failure + hint + ' No model request or trial was started.') from None
        if result.returncode:
            raise ValueError(failure + hint + ' No model request or trial was started.')
        return result.stdout.strip()

    engine = query(['info', '--format', '{{.OSType}}'],
                   'Docker CLI exists, but the Docker daemon is unavailable to this user (service, context or permission).')
    if engine != 'linux':
        raise ValueError('Docker must use Linux containers for these task images. No model request or trial was started.')
    version = query(['compose', 'version', '--short'], 'Docker Compose v2 is missing or unavailable.')
    if not version.lstrip('v').startswith('2.'):
        raise ValueError('Docker Compose v2 is required. No model request or trial was started.')
