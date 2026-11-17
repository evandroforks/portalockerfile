import importlib.util
import os
import subprocess
import sys

import pytest

from portalocker import __main__


@pytest.mark.parametrize('tools_available', [False, True])
def test_combined(tmpdir, monkeypatch, tools_available):
    real_run = subprocess.run
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        assert kwargs['check'] is (command[0] == sys.executable)
        if os.name == 'nt':
            assert kwargs['startupinfo'].wShowWindow == 7
            assert (
                kwargs['startupinfo'].dwFlags & subprocess.STARTF_USESHOWWINDOW
            )
        else:
            assert kwargs['startupinfo'] is None
        if command[0] == sys.executable:
            return real_run(command, **kwargs)
        return subprocess.CompletedProcess(command, 2)

    def resolve_tool(name):
        return name if tools_available else None

    monkeypatch.setattr(__main__.shutil, 'which', resolve_tool)
    monkeypatch.setattr(__main__.subprocess, 'run', invoke)
    output_file = tmpdir.mkdir('folder with spaces').join('combined.py')
    __main__.main(['combine', '--output-file', output_file.strpath])
    expected = [[sys.executable, output_file.strpath]]
    if tools_available:
        expected[:0] = [
            ['black', output_file.strpath],
            ['ruff', 'check', '--fix', output_file.strpath],
        ]
    assert calls == expected

    print(output_file)  # noqa: T201
    print('#################')  # noqa: T201
    print(output_file.read())  # noqa: T201
    print('#################')  # noqa: T201

    specification = importlib.util.spec_from_file_location(
        'combined',
        output_file.strpath,
    )
    assert specification is not None
    assert specification.loader is not None
    combined = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, 'combined', combined)
    specification.loader.exec_module(combined)

    assert combined.__file__ is not None
    assert os.path.samefile(combined.__file__, output_file.strpath)
    assert combined.__version__ == '2.10.1'
    assert combined.Lock.__module__ == 'combined'
    filename = str(tmpdir.join('combined.lock'))
    with combined.Lock(filename, timeout=0.1) as handle:
        handle.write('combined entry point')
    with open(filename) as handle:
        assert handle.read() == 'combined entry point'
