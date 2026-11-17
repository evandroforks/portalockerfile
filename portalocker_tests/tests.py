import dataclasses
import math
import multiprocessing
import os
import time
import typing

import pytest

import portalocker
import portalocker.portalocker
from portalocker import LockFlags, exceptions, utils

if os.name == 'posix':
    import fcntl

    LOCKERS = [
        fcntl.flock,
        fcntl.lockf,
    ]
else:
    LOCKERS = [None]  # type: ignore


@pytest.fixture
def locker(request, monkeypatch):
    monkeypatch.setattr(portalocker.portalocker, 'LOCKER', request.param)
    return request.param


def test_exceptions(tmpfile):
    with open(tmpfile, 'a') as a, open(tmpfile, 'a') as b:
        # Lock exclusive non-blocking
        lock_flags = portalocker.LOCK_EX | portalocker.LOCK_NB

        # First lock file a
        portalocker.lock(a, lock_flags)

        # Now see if we can lock file b
        with pytest.raises(portalocker.LockException):
            portalocker.lock(b, lock_flags)


def test_utils_base():
    class Test(utils.LockBase):
        pass


def test_with_timeout(tmpfile):
    # Open the file 2 times
    with pytest.raises(portalocker.AlreadyLocked):
        with portalocker.Lock(tmpfile, timeout=0.1) as fh:
            print('writing some stuff to my cache...', file=fh)
            with portalocker.Lock(
                tmpfile,
                timeout=0.1,
                mode='wb',
                fail_when_locked=True,
            ):
                pass
            print('writing more stuff to my cache...', file=fh)


def test_without_timeout(tmpfile, monkeypatch):
    # Open the file 2 times
    with pytest.raises(portalocker.LockException):
        with portalocker.Lock(tmpfile, timeout=None) as fh:
            print('writing some stuff to my cache...', file=fh)
            with portalocker.Lock(tmpfile, timeout=None, mode='w'):
                pass
            print('writing more stuff to my cache...', file=fh)


def test_without_fail(tmpfile):
    # Open the file 2 times
    with pytest.raises(portalocker.LockException):
        with portalocker.Lock(tmpfile, timeout=0.1) as fh:
            print('writing some stuff to my cache...', file=fh)
            lock = portalocker.Lock(tmpfile, timeout=0.1)
            lock.acquire(check_interval=0.05, fail_when_locked=False)


def test_simple(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    with open(tmpfile, 'r+') as fh:
        portalocker.lock(fh, portalocker.LOCK_EX)

        fh.seek(13)
        fh.write('foo')

        # Make sure we didn't overwrite the original text
        fh.seek(0)
        assert fh.read(13) == 'spam and eggs'

        portalocker.unlock(fh)


def test_truncate(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    with portalocker.Lock(tmpfile, mode='a+') as fh:
        # Make sure we didn't overwrite the original text
        fh.seek(0)
        assert fh.read(13) == 'spam and eggs'

    with portalocker.Lock(tmpfile, mode='w+') as fh:
        # Make sure we truncated the file
        assert fh.read() == ''


def test_class(tmpfile):
    lock = portalocker.Lock(tmpfile)
    lock2 = portalocker.Lock(tmpfile, fail_when_locked=False, timeout=0.01)

    with lock:
        lock.acquire()

        with pytest.raises(portalocker.LockException), lock2:
            pass

    with lock2:
        pass


def test_acquire_release(tmpfile):
    lock = portalocker.Lock(tmpfile)
    lock2 = portalocker.Lock(tmpfile, fail_when_locked=False)

    lock.acquire()  # acquire lock when nobody is using it
    with pytest.raises(portalocker.LockException):
        # another party should not be able to acquire the lock
        lock2.acquire(timeout=0.01)

        # re-acquire a held lock is a no-op
        lock.acquire()

    lock.release()  # release the lock
    lock.release()  # second release does nothing


def test_rlock_acquire_release_count(tmpfile):
    lock = portalocker.RLock(tmpfile)
    # Twice acquire
    h = lock.acquire()
    assert not h.closed
    lock.acquire()
    assert not h.closed

    # Two release
    lock.release()
    assert not h.closed
    lock.release()
    assert h.closed


def test_rlock_acquire_release(tmpfile):
    lock = portalocker.RLock(tmpfile)
    lock2 = portalocker.RLock(tmpfile, fail_when_locked=False)

    lock.acquire()  # acquire lock when nobody is using it
    with pytest.raises(portalocker.LockException):
        # another party should not be able to acquire the lock
        lock2.acquire(timeout=0.01)

    # Now acquire again
    lock.acquire()

    lock.release()  # release the lock
    lock.release()  # second release does nothing


def test_release_unacquired(tmpfile):
    with pytest.raises(portalocker.LockException):
        portalocker.RLock(tmpfile).release()


def test_exlusive(tmpfile):
    text_0 = 'spam and eggs'
    with open(tmpfile, 'w') as fh:
        fh.write(text_0)

    with open(tmpfile) as fh:
        portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)

        # Make sure we can't read the locked file
        with pytest.raises(portalocker.LockException), open(
            tmpfile,
            'r+',
        ) as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            assert fh2.read() == text_0

        # Make sure we can't write the locked file
        with pytest.raises(portalocker.LockException), open(
            tmpfile,
            'w+',
        ) as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            fh2.write('surprise and fear')

        # Make sure we can explicitly unlock the file
        portalocker.unlock(fh)


def test_shared(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    with open(tmpfile) as f:
        portalocker.lock(f, portalocker.LOCK_SH | portalocker.LOCK_NB)

        # Make sure we can read the locked file
        with open(tmpfile) as fh2:
            portalocker.lock(fh2, portalocker.LOCK_SH | portalocker.LOCK_NB)
            assert fh2.read() == 'spam and eggs'

        # Make sure we can't write the locked file
        with pytest.raises(portalocker.LockException), open(
            tmpfile,
            'w+',
        ) as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            fh2.write('surprise and fear')

        # Make sure we can explicitly unlock the file
        portalocker.unlock(f)


@pytest.mark.parametrize('locker', LOCKERS, indirect=True)
def test_blocking_timeout(tmpfile, locker):
    flags = LockFlags.SHARED

    with pytest.warns(UserWarning):
        with portalocker.Lock(tmpfile, 'a+', timeout=5, flags=flags):
            pass

    lock = portalocker.Lock(tmpfile, 'a+', flags=flags)
    with pytest.warns(UserWarning):
        lock.acquire(timeout=5)


@pytest.mark.skipif(
    os.name == 'nt',
    reason='Windows uses an entirely different lockmechanism',
)
@pytest.mark.parametrize('locker', LOCKERS, indirect=True)
def test_nonblocking(tmpfile, locker):
    with open(tmpfile, 'w') as fh, pytest.raises(RuntimeError):
        portalocker.lock(fh, LockFlags.NON_BLOCKING)


def shared_lock(filename, **kwargs):
    with portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=False,
        flags=LockFlags.SHARED | LockFlags.NON_BLOCKING,
    ):
        time.sleep(0.2)
        return True


def shared_lock_fail(filename, **kwargs):
    with portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=True,
        flags=LockFlags.SHARED | LockFlags.NON_BLOCKING,
    ):
        time.sleep(0.2)
        return True


def exclusive_lock(filename, **kwargs):
    with portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=False,
        flags=LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING,
    ):
        time.sleep(0.2)
        return True


@dataclasses.dataclass(order=True)
class LockResult:
    exception_class: typing.Union[typing.Type[Exception], None] = None
    exception_message: typing.Union[str, None] = None
    exception_repr: typing.Union[str, None] = None


def lock(
    filename: str,
    fail_when_locked: bool,
    flags: LockFlags,
    result_queue,
    release,
    locker=None,
) -> None:
    portalocker.portalocker.LOCKER = locker
    instance = portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=fail_when_locked,
        flags=flags,
    )
    try:
        instance.acquire()
    except Exception as exception:
        # Exception instances may contain unpicklable handles.
        result_queue.put(
            LockResult(type(exception), str(exception), repr(exception)),
        )
        return
    result_queue.put(LockResult())
    try:
        if not release.wait(timeout=30):
            raise TimeoutError('The test did not release its held lock')
    finally:
        instance.release()


@pytest.mark.parametrize('fail_when_locked', [True, False])
@pytest.mark.timeout(60)
def test_shared_processes(tmpfile, fail_when_locked):
    flags = LockFlags.SHARED | LockFlags.NON_BLOCKING
    context = multiprocessing.get_context('spawn')
    release = context.Event()
    results = [context.Queue(), context.Queue()]
    workers = [
        context.Process(
            target=lock,
            args=(
                tmpfile,
                fail_when_locked,
                flags,
                results[index],
                release,
            ),
        )
        for index in range(2)
    ]
    try:
        workers[0].start()
        assert results[0].get(timeout=10) == LockResult()
        workers[1].start()
        assert results[1].get(timeout=10) == LockResult()
        assert workers[0].is_alive()
        assert not release.is_set()
        release.set()
    finally:
        release.set()
        for worker in workers:
            if worker.pid is not None:
                worker.join(timeout=10)
                assert worker.exitcode == 0
        for result in results:
            result.close()


@pytest.mark.parametrize('fail_when_locked', [True, False])
@pytest.mark.parametrize('locker', LOCKERS, indirect=True)
@pytest.mark.timeout(60)
def test_exclusive_processes(tmpfile: str, fail_when_locked: bool, locker):
    flags = LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING
    context = multiprocessing.get_context('spawn')
    release = context.Event()
    results = [context.Queue(), context.Queue()]
    workers = [
        context.Process(
            target=lock,
            args=(
                tmpfile,
                fail_when_locked,
                flags,
                results[index],
                release,
                locker,
            ),
        )
        for index in range(2)
    ]
    try:
        workers[0].start()
        assert results[0].get(timeout=10) == LockResult()
        workers[1].start()
        blocked = results[1].get(timeout=10)
        assert blocked.exception_class is not None
        assert issubclass(blocked.exception_class, portalocker.LockException)
        assert workers[0].is_alive()
        assert not release.is_set()
        release.set()
    finally:
        release.set()
        for worker in workers:
            if worker.pid is not None:
                worker.join(timeout=10)
                assert worker.exitcode == 0
        for result in results:
            result.close()


@pytest.mark.skipif(
    os.name == 'nt',
    reason='Locking on Windows requires a file object',
)
@pytest.mark.parametrize('locker', LOCKERS, indirect=True)
def test_lock_fileno(tmpfile, locker):
    with open(tmpfile, 'a+') as a:
        with open(tmpfile, 'a+') as b:
            # Lock shared non-blocking
            flags = LockFlags.SHARED | LockFlags.NON_BLOCKING

            # First lock file a
            portalocker.lock(a, flags)

            # Now see if we can lock using fileno()
            portalocker.lock(b.fileno(), flags)


@pytest.mark.skipif(
    os.name != 'posix',
    reason='Only posix systems have different lockf behaviour',
)
@pytest.mark.parametrize('locker', LOCKERS, indirect=True)
def test_locker_mechanism(tmpfile, locker):
    '''Can we switch the locking mechanism?'''
    # We can test for flock vs lockf based on their different behaviour re.
    # locking the same file.
    with portalocker.Lock(tmpfile, 'a+', flags=LockFlags.EXCLUSIVE):
        # If we have lockf(), we cannot get another lock on the same file.
        if locker is fcntl.lockf:
            portalocker.Lock(
                tmpfile,
                'r+',
                flags=LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING,
            ).acquire(timeout=0.1)
        # But with other lock methods we can't
        else:
            with pytest.raises(portalocker.LockException):
                portalocker.Lock(
                    tmpfile,
                    'r+',
                    flags=LockFlags.EXCLUSIVE | LockFlags.NON_BLOCKING,
                ).acquire(timeout=0.1)


def test_exception(monkeypatch, tmpfile):
    '''Do we stop immediately if the locking fails, even with a timeout?'''

    def patched_lock(*args, **kwargs):
        raise ValueError('Test exception')

    monkeypatch.setattr('portalocker.utils.portalocker.lock', patched_lock)
    lock = portalocker.Lock(tmpfile, 'w', timeout=math.inf)

    with pytest.raises(exceptions.LockException):
        lock.acquire()
