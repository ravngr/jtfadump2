import contextlib
import enum
import logging
import struct
import threading

import serial
import visa

import util

__author__ = 'chris'


class ConnectorException(Exception):
    pass


class HardwareException(Exception):
    pass


class Connector(object):
    def __init__(self, name):
        self._name = name

        self._lock = threading.RLock()
        self._log = logging.getLogger(type(self).__name__)

    @contextlib.contextmanager
    def get_lock(self, **kwargs):
        result = self._lock.acquire(**kwargs)

        yield result

        if result:
            self._lock.release()

    def get_address(self):
        raise NotImplementedError()

    def get_name(self):
        return self._name

    def reset(self):
        pass

    def read(self, size=None):
        raise NotImplementedError()

    def write(self, data):
        raise NotImplementedError()

    def write_raw(self, data, raw_data):
        raise NotImplementedError()

    def query(self, data, read_size=None):
        raise NotImplementedError()

    def query_raw(self, data, read_size=None):
        raise NotImplementedError()


rs232retry = util.decorator_factory(util.ExceptionRetry, [serial.SerialException], log_attribute='_log',
                                    retry_attribute='_retry_attempt', reset_method='reset',
                                    wait_attribute='_retry_delay')


class RS232Connector(Connector):
    _retry_delay = 1
    _retry_attempt = 3

    def __init__(self, name, port, **kwargs):
        super().__init__(name)

        self._serial = serial.Serial(port, **kwargs)

    def get_address(self):
        return self._serial.name

    def reset(self):
        # Clear input and output buffers
        self._serial.flushInput()
        self._serial.flushOutput()

    @rs232retry
    def read(self, size=None):
        if size:
            return self._serial.read(size)
        else:
            return self._serial.readline()

    @rs232retry
    def write(self, data):
        return self._serial.write(data)

    @rs232retry
    def write_raw(self, data, raw_data):
        raise self.write(data + raw_data)

    @rs232retry
    def query(self, data, read_size=None):
        self._serial.write(data)
        self._serial.flush()
        return self.read(read_size)

    @rs232retry
    def query_raw(self, data, read_size=None):
        return self.query(data, read_size)


class RS232toRS485BusConnector(RS232Connector):
    def __init__(self, name, port, **kwargs):
        super().__init__(name, port, **kwargs)


class RS485AdapterConnector(Connector):
    _rs232_connectors = {}

    def __init__(self, name, port, bus_address, **kwargs):
        super().__init__(name)

        if port not in RS485AdapterConnector._rs232_connectors:
            RS485AdapterConnector._rs232_connectors[port] = RS232Connector(port, **kwargs)

        self._parent = RS485AdapterConnector._rs232_connectors[port]

        self._bus_address = bus_address

    def get_lock(self, **kwargs):
        with self._parent.get_lock() as lock:
            if lock:
                super().get_lock(**kwargs)
            else:
                raise HardwareException('Cannot acquire parent RS232 resource lock')


class VISAConnector(Connector):
    def __init__(self, visa_address, term_char=None):
        super().__init__()

        self._visa_address = visa_address

        # Connect to VISA resource
        resource_manager = visa.ResourceManager()

        self._resource = resource_manager.open_resource(self._visa_address)

        # Set terminator characters if provided
        if term_char:
            self._resource.read_termination = term_char
            self._resource.write_termination = term_char

    def get_resource(self):
        return self._resource

    def get_address(self):
        return self._visa_address

    def read(self, size=None):
        pass

    def write(self, data):
        pass

    def write_raw(self, data, raw_data):
        pass

    def query(self, data, read_size=None):
        pass

    def query_raw(self, data, read_size=None):
        pass

    @staticmethod
    def _cast_bool(value):
        return 'ON' if value else 'OFF'


class VISATerminatorWrapper():
    def __init__(self, visa_connector, term_char_read, term_char_write):
        self._visa_connector = visa_connector
        self._term_char = (term_char_read, term_char_write)
        self._original_term_char = None

    def __enter__(self):
        visa_resource = self._visa_connector.get_resource()

        self._original_term_char = (visa_resource.read_termination, visa_resource.write_termination)

        # Use alternate termination characters
        visa_resource.read_termination = self._term_char[0]
        visa_resource.write_termination = self._term_char[1]

        return self._visa_connector

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_type, exc_val, exc_tb

        visa_resource = self._visa_connector.get_resource()

        # Restore original termination characters
        visa_resource.read_termination = self._original_term_char[0]
        visa_resource.write_termination = self._original_term_char[1]

        self._original_term_char = None


class VISABusAddressConnector(Connector):
    _visa_connectors = {}

    def __init__(self, visa_address, bus_address, term_char=None):
        super().__init__()

        self._visa_address = visa_address
        self._term_char = term_char

        # Instantiate the VISAConnector if it doesn't already exist
        if visa_address not in VISABusAddressConnector._visa_connectors:
            VISABusAddressConnector._visa_connectors[visa_address] = [VISAConnector(visa_address), None]

        self._bus_address = bus_address

    def reset(self):
        VISABusAddressConnector._visa_connectors[self._visa_address][1] = None

    def get_address(self):
        return self._visa_address + ',' + self._bus_address

    def read(self, size=None):
        with self._get_visa_connector() as connector:
            return connector.read()

    def write(self, data):
        pass

    def write_raw(self, data, raw_data):
        pass

    def query(self, data, read_size=None):
        pass

    def query_raw(self, data, read_size=None):
        pass

    def _get_visa_connector(self):
        return VISATerminatorWrapper(VISABusAddressConnector._visa_connectors[self._visa_address][0], self._term_char,
                                     self._term_char)

    def _get_last_address(self):
        return VISABusAddressConnector._visa_connectors[self._visa_address][1]

    def _set_last_address(self):
        VISABusAddressConnector._visa_connectors[self._visa_address][1] = None

    def _select_bus_address(self):
        if self._get_last_address() is not self._bus_address:
            self._get_visa_connector().write("*ADR {}".format(self._bus_address))


class Hardware(object):
    def __init__(self, connector):
        self._connector = connector

        self._lock = threading.RLock()

        self._log = logging.getLogger(type(self).__name__)

    @contextlib.contextmanager
    def get_lock(self, **kwargs):
        result = self._lock.acquire(**kwargs)

        yield result

        if result:
            self._lock.release()


class VISAHardware(Hardware):
    def clear(self):
        self._connector.write("*CLS")

    def get_event_status_enable(self):
        return int(self._connector.query("*ESE?"))

    def get_event_status_opc(self):
        return bool(self._connector.query("*OPC?"))

    def get_service_request(self):
        return bool(self._connector.query("*SRE?"))

    def get_status(self):
        return bool(self._connector.query("*STB?"))

    def get_event_status(self):
        return int(self._connector.ask("*ESR?"))

    def set_event_status_enable(self, mask):
        self._connector.write("*ESE {}".format(mask))

    def set_service_request_enable(self, mask):
        self._connector.write("*SRE {}".format(mask))

    def set_event_status_opc(self):
        self._connector.write("*OPC")

    def get_id(self):
        return self._connector.query("*IDN?")

    def get_options(self):
        return self._connector.query("*OPT?")

    def reset(self):
        self._connector.write("*RST")
        self._connector.reset()

    def trigger(self):
        self._connector.write("*TRG")

    def wait(self):
        self._connector.write("*WAI")

    def wait_measurement(self):
        self._connector.query("*OPC?")

    @staticmethod
    def _cast_bool(value):
        return "ON" if value else "OFF"


class FrequencyCounter(VISAHardware):
    pass


class MassFlowController(Hardware):
    pass


class Oscilloscope(VISAHardware):
    pass


class PowerSupply(VISAHardware):
    def clear_alarm(self):
        self._connector.write(":OUTP:PROT:CLE")

    def get_current(self):
        return float(self._connector.query(":MEAS:CURR?"))

    def get_voltage(self):
        return float(self._connector.query(":MEAS?"))

    def get_power(self):
        return self.get_voltage() * self.get_current()

    def set_output_enable(self, enabled):
        self._connector.write(":OUTP {}".format(self._cast_bool(enabled)))

    def set_voltage(self, voltage):
        self._connector.write(":VOLT {}".format(voltage))

    def set_current(self, current):
        self._connector.write(":CURR {}".format(current))


class SignalGenerator(VISAHardware):
    class PulseModSource(enum.Enum):
        internal_pulse = 'INT'
        internal_square = 'INT'
        internal_10M = 'INT1'
        internal_40M = 'INT2'
        external_front = 'EXT1'
        external_rear = 'EXT2'

    def set_output(self, enabled):
        self._connector.write(":OUTP:STAT {}".format(VISAHardware._cast_bool(enabled)))

    def set_frequency(self, frequency):
        self._connector.write(":FREQ:MODE CW")
        self._connector.write(":FREQ {}".format(frequency))

    def set_power(self, power):
        self._connector.write(":POW {}dBm".format(power))

    def set_pulse(self, enabled):
        self._connector.write(":PULM:STAT ".format(VISAHardware._cast_bool(enabled)))

    def set_pulse_source(self, source):
        self._connector.write(":PULM:SOUR {}".format(source.value))

        if source is self.PulseModSource.internal_pulse:
            self._connector.write(":PULM:INT:FUNC:SHAP PULS")
        elif source is self.PulseModSource.internal_square:
            self._connector.write(":PULM:INT:FUNC:SHAP SQU")

    def set_pulse_count(self, count):
        self._connector.write(":PULM:COUN {}".format(count))

    def set_pulse_period(self, t):
        self._connector.write(":PULS:PER {}".format(t))

    def set_pulse_width(self, nPulse, t):
        self._connector.write(":PULS:WIDT{} {}".format(nPulse, t))

    def set_pulse_delay(self, nPulse, t):
        self._connector.write(":PULS:DEL{} {}".format(nPulse, t))


class TemperatureLogger(Hardware):
    _PAYLOAD_CHANNELS = [1, 2, 3, 4]
    _PAYLOAD_OFFSET_LOW = 7
    _PAYLOAD_OFFSET_HIGH = 9
    _PAYLOAD_REQUEST = 'A'
    _PAYLOAD_SIZE = 45

    def __init__(self, connector):
        super().__init__(connector)

        self._log.debug("TemperatureLogger on ".format(connector.get_address()))

    def get_temperature(self, channel=None):
        payload_data = self._connector.query(TemperatureLogger._PAYLOAD_REQUEST, TemperatureLogger._PAYLOAD_SIZE)

        if not channel:
            channel = TemperatureLogger._PAYLOAD_CHANNELS

        if type(channel) is list:
            data = []

            for c in channel:
                offset_low = TemperatureLogger._PAYLOAD_OFFSET_LOW + c
                offset_high = TemperatureLogger._PAYLOAD_OFFSET_HIGH + c

                data.append((struct.unpack('>h', payload_data[offset_low:offset_high + c])[0]) / 10.0)

            return data
        else:
            offset_low = TemperatureLogger._PAYLOAD_OFFSET_LOW + channel
            offset_high = TemperatureLogger._PAYLOAD_OFFSET_HIGH + channel

            return (struct.unpack('>h', payload_data[offset_low:offset_high])[0]) / 10.0


class VectorNetworkAnalyzer(Hardware):
    pass
