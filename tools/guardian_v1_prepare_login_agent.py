"""Generate (but never install/load) a per-login read-only notification LaunchAgent.

Review generated plist before manually installing. No startup Guardian service here.
"""
import argparse
from pathlib import Path
import plistlib
import sys


def make_login_agent(*, project_dir, recovery_file, python_executable):
    project_dir = Path(project_dir).resolve(strict=True)
    recovery_file = Path(recovery_file).expanduser().resolve()
    python_executable = Path(python_executable).expanduser().absolute()
    if not python_executable.is_file():
        raise FileNotFoundError(
            f'Python executable not found: {python_executable}'
        )
    script = project_dir / 'modules' / 'guardian_v1_login_notice.py'
    if not script.is_file():
        raise FileNotFoundError(f'Notification script not found: {script}')
    return {
        'Label': 'org.guardian.v1.recovery-login-notice',
        'ProgramArguments': [str(python_executable), '-m', 'modules.guardian_v1_login_notice',
                             '--recovery-file', str(recovery_file)],
        'WorkingDirectory': str(project_dir),
        'RunAtLoad': True,
        'KeepAlive': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prepare read-only login notification plist; do not install')
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--recovery-file', required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    target = Path(args.output).expanduser()
    if target.exists():
        parser.error('Refusing to overwrite existing plist')
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = make_login_agent(project_dir=args.project_dir, recovery_file=args.recovery_file,
                               python_executable=args.python)
    with target.open('xb') as f:
        plistlib.dump(payload, f)
    print(f'Prepared (NOT installed): {target}')


if __name__ == '__main__':
    main()
