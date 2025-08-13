import time


def pytest_runtest_teardown(item, nextitem):  # noqa
    if nextitem is not None:
        time.sleep(0.25)
