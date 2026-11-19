import plistlib
import pytest
from tools.guardian_v1_prepare_login_agent import make_login_agent, main


def test_agent_runs_once_at_login_without_guardian_or_hardware(tmp_path):
    (tmp_path / 'modules').mkdir()
    (tmp_path / 'modules' / 'guardian_v1_login_notice.py').write_text('# notice')
    python = tmp_path / 'python'
    python.touch()
    d = make_login_agent(project_dir=tmp_path, recovery_file=tmp_path / 'recovery.json',
                         python_executable=python)
    assert d['RunAtLoad'] is True and d['KeepAlive'] is False
    assert d['ProgramArguments'][1:3] == ['-m', 'modules.guardian_v1_login_notice']
    assert not any('guardian_v1.py' in x for x in d['ProgramArguments'])


def test_generator_does_not_install_or_overwrite(tmp_path):
    (tmp_path / 'modules').mkdir()
    (tmp_path / 'modules' / 'guardian_v1_login_notice.py').write_text('# notice')
    python = tmp_path / 'python'
    python.touch()
    output = tmp_path / 'review.plist'
    args = ['--project-dir', str(tmp_path), '--recovery-file', str(tmp_path / 'recovery.json'),
            '--python', str(python), '--output', str(output)]
    main(args)
    assert plistlib.loads(output.read_bytes())['RunAtLoad']
    with pytest.raises(SystemExit):
        main(args)
