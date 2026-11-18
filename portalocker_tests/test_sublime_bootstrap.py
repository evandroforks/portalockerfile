import builtins
import contextlib
import importlib.util
import os
import site
import sys
import typing
from types import SimpleNamespace

import pytest

from portalocker import portalocker as backend


@pytest.mark.skipif(os.name != 'nt', reason='Windows PyWin32 import boundary')
@pytest.mark.parametrize(
    'python_version,build,error_name,activates',
    [
        ((3, 8), 4143, 'pywintypes', True),
        ((3, 8), 4204, 'pywintypes', True),
        ((3, 8), 4205, 'pywintypes', False),
        ((3, 8), 4213, 'pywintypes', False),
        ((3, 14), 4143, 'pywintypes', False),
        ((3, 3), 3211, 'pywintypes', False),
        ((3, 8), None, 'pywintypes', False),
        ((3, 8), 4143, None, False),
        ((3, 8), 4143, 'other_prerequisite', False),
    ],
)
def test_sublime_pywin32_initialization(
    tmp_path,
    monkeypatch,
    python_version,
    build,
    error_name,
    activates,
):
    real_import = builtins.__import__
    attempts = []
    site_paths: typing.List[str] = []
    data = tmp_path / 'Data with spaces'

    def import_with_missing_pywin32(name, *args, **kwargs):
        if name == 'pywintypes':
            attempts.append(name)
            if len(attempts) == 1 and error_name:
                raise ModuleNotFoundError(
                    'Controlled missing PyWin32 prerequisite',
                    name=error_name,
                )
        return real_import(name, *args, **kwargs)

    specification = importlib.util.spec_from_file_location(
        'portalocker._sublime_import_probe',
        backend.__file__,
    )
    assert specification is not None
    assert specification.loader is not None
    probe = importlib.util.module_from_spec(specification)
    expected_import = (
        pytest.raises(ModuleNotFoundError, match='Controlled missing')
        if error_name and not activates
        else contextlib.nullcontext()
    )
    with monkeypatch.context() as scope, expected_import:
        scope.setattr(sys, 'version_info', python_version)
        if build is None:
            scope.delitem(sys.modules, 'sublime', raising=False)
        else:
            scope.setitem(
                sys.modules,
                'sublime',
                SimpleNamespace(
                    version=lambda: str(build),
                    packages_path=lambda: str(data / 'Packages'),
                ),
            )
        scope.setitem(sys.modules, specification.name, probe)
        scope.setattr(builtins, '__import__', import_with_missing_pywin32)
        scope.setattr(site, 'addsitedir', site_paths.append)
        specification.loader.exec_module(probe)

    expected_sites = [str(data / 'Lib' / 'python38')] if activates else []
    assert site_paths == expected_sites
    assert len(attempts) == (2 if activates else 1)
