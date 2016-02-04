import contextlib
import threading

import serial

import util

__author__ = 'chris'


class ConnectorException(Exception):
    pass


class EquipmentException(Exception):
    pass


_connector_config = {}
_connector_list = {}
_equipment_config = {}
_equipment_list = {}

def add_connector(id, config):
    pass

def add_equipment(id, config):
    pass

def get_connector(id):
    if id not in _connector_config:
        raise ConnectorException("Connector {} not defined in configuration".format(id))

    if id not in _connector_list:
        pass

def get_equipment(id):
    if id not in _equipment_config:
        raise EquipmentException("Equipment {} not defined in configuration".format(id))

    if id not in _equipment_list:
        pass

def test_connector(id):
    pass

def test_equipment(id):
    pass


class ManagedResource(util.LoggingBaseClass):
    """
    Managed resource with unique identifier and lock for threading
    """

    def __init__(self, id):
        super().__init__()

        self._id = id
        self._lock = threading.RLock()

    def get_id(self):
        return self._id

    @contextlib.contextmanager
    def get_lock(self, *args, **kwargs):
        result = self._lock.acquire(*args, **kwargs)

        yield result

        if result:
            self._lock.release()


class Connector(ManagedResource):
    """
    Base class for connectors to instruments
    """

    def __init__(self, id, shared=False):
        super().__init__(id)

        self._shared = shared

    def read(self, length=None):
        raise NotImplementedError()

    def write(self, data):
        raise NotImplementedError()

    def query(self, data, read_length=None):
        raise NotImplementedError()


class Equipment(ManagedResource):
    """
    Base class for all equipment, stores handle to equipment connector
    """

    def __init__(self, id, connector):
        super().__init__(id)

        self._connector = connector


class SCPIEquipment(Equipment):
    """
    Base class for equipment implementing SCPI commands
    """

    def __init__(self, id, connector):
        super().__init__(id, connector)


class FrequencyCounter(SCPIEquipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class MassFlowController(Equipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class Oscilloscope(SCPIEquipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class PowerSupply(SCPIEquipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class SignalGenerator(SCPIEquipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class TemperatureLogger(Equipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)


class VectorNetworkAnalyzer(SCPIEquipment):
    def __init__(self, id, connector):
        super().__init__(id, connector)
