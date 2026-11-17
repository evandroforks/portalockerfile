"""Keep the existing setup entry point backed by the project metadata."""
import setuptools


def install():
    setuptools.setup()


if __name__ == '__main__':
    install()
