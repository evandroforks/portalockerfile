import sys

from portalocker import __main__


def test_combined(tmpdir):
    output_file = tmpdir.mkdir('folder with spaces').join('combined.py')
    __main__.main(['combine', '--output-file', output_file.strpath])

    print(output_file)  # noqa: T201
    print('#################')  # noqa: T201
    print(output_file.read())  # noqa: T201
    print('#################')  # noqa: T201

    sys.path.append(output_file.dirname)
    # Combined is being generated above but linters won't understand that
    import combined  # type: ignore

    assert combined.__version__ == '2.10.1'
    assert combined.Lock.__module__ == 'combined'
    filename = str(tmpdir.join('combined.lock'))
    with combined.Lock(filename, timeout=0.1) as handle:
        handle.write('combined entry point')
    with open(filename) as handle:
        assert handle.read() == 'combined entry point'
