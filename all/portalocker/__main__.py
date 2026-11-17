import argparse
import logging
import pathlib
import re
import shutil
import subprocess
import sys
import typing

base_path = pathlib.Path(__file__).resolve().parents[2]
src_path = pathlib.Path(__file__).resolve().parent
dist_path = base_path / 'dist'
_default_output_path = base_path / 'dist' / 'portalocker.py'

_NAMES_RE = re.compile(r'(?P<names>[^()]+)$')
_RELATIVE_IMPORT_RE = re.compile(
    r'^from \.(?P<from>.*?) import (?P<paren>\(?)(?P<names>[^()]+)$',
)
_USELESS_ASSIGNMENT_RE = re.compile(r'^(?P<name>\w+) = \1\n$')

_TEXT_TEMPLATE = """'''
{}
'''

"""

logger = logging.getLogger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(required=True)
    combine_parser = subparsers.add_parser(
        'combine',
        help='Combine all Python files into a single unified `portalocker.py` '
        'file for easy distribution',
    )
    combine_parser.add_argument(
        '--output-file',
        '-o',
        type=pathlib.Path,
        default=_default_output_path,
    )

    combine_parser.set_defaults(func=combine)
    args = parser.parse_args(argv)
    args.func(args)


def _read_file(path: pathlib.Path, seen_files: typing.Set[pathlib.Path]):
    if path in seen_files:
        return

    names = set()
    seen_files.add(path)
    paren = False
    from_ = None
    for line in path.open():
        if paren:
            if ')' in line:
                line = line.split(')', 1)[1]
                paren = False
                continue

            match = _NAMES_RE.match(line)
        else:
            match = _RELATIVE_IMPORT_RE.match(line)

        if match:
            if not paren:
                paren = bool(match.group('paren'))
                from_ = match.group('from')

            if from_:
                names.add(from_)
                yield from _read_file(src_path / f'{from_}.py', seen_files)
            else:
                for name in match.group('names').split(','):
                    name = name.strip()
                    names.add(name)
                    yield from _read_file(src_path / f'{name}.py', seen_files)
        else:
            yield _clean_line(line, names)


def _clean_line(line, names):
    # Replace `some_import.spam` with `spam`
    if names:
        joined_names = '|'.join(names)
        line = re.sub(fr'\b({joined_names})\.', '', line)

    # Replace useless assignments (e.g. `spam = spam`)
    return _USELESS_ASSIGNMENT_RE.sub('', line)


def combine(args):
    output_path = args.output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w') as output_file:
        output_file.write(
            _TEXT_TEMPLATE.format((base_path / 'README.rst').read_text()),
        )
        output_file.write(
            _TEXT_TEMPLATE.format((base_path / 'LICENSE').read_text()),
        )

        seen_files: typing.Set[pathlib.Path] = set()
        for line in _read_file(src_path / '__init__.py', seen_files):
            output_file.write(line)

    logger.info(f'Wrote combined file to {output_path}')
    # Run black and ruff if available. If not then just run the file.
    startupinfo = None
    if sys.platform == 'win32':  # pragma: no cover
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 7

    for command in (
        ('black', str(output_path)),
        ('ruff', 'check', '--fix', str(output_path)),
    ):
        executable = shutil.which(command[0])
        if executable:
            subprocess.run(
                [executable, *command[1:]],
                check=False,
                startupinfo=startupinfo,
            )
    subprocess.run(
        [sys.executable, str(output_path)],
        check=True,
        startupinfo=startupinfo,
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
