"""pytest 共享夹具：虚拟 CAN 总线、DBC、TCMS 仿真器。"""

import can
import pytest

CHANNEL = "tcms-test-bus"


@pytest.fixture(scope="session")
def db():
    from tcms.protocol import load_database

    return load_database()


@pytest.fixture(scope="session")
def bus():
    b = can.Bus(interface="virtual", channel=CHANNEL, receive_own_messages=True)
    yield b
    b.shutdown()


@pytest.fixture()
def drain(bus):
    """清空总线上的残留报文，保证用例隔离。"""
    while bus.recv(timeout=0.01) is not None:
        pass
    yield


@pytest.fixture()
def simulator(bus, db, drain):
    """每个用例独立的 TCMS 仿真器实例。"""
    from tcms.simulator import TCMSNodeSimulator

    sim = TCMSNodeSimulator(bus, db)
    sim.start()
    yield sim
    sim.stop()