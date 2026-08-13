"""Regression tests for describing a spool in words Snapmaker Orca already knows.

Orca lists a loaded spool under Machine Filament only when "<vendor> <type> <sub-type>" is exactly
the name of a filament it ships, and it ships none for third-party brands, so a spool read perfectly
off its tag used to vanish from that list with no error at all. Both routes a spool takes into the
printer's filament state, the hardware tag read and the filament_detect/set webhook, must end up
saying the same thing.
"""
from conftest import FILAMENT_PROTO_ERR, FILAMENT_PROTO_OK, load_printer_extra

bespok3d_rfid = load_printer_extra("bespok3d_rfid")
rfid_ntag = load_printer_extra("rfid_ntag")

NTAG_CARD_TYPE = 0x44
CHANNEL = 0
CARD_BYTES = b'\x01\x02\x03'


class WebRequestError(Exception):
    """Klipper's web_request.error: what a rejected request raises."""


class FilamentDetectStub:
    """Stands in for Snapmaker's patched filament_detect, which holds the printer's spool state."""

    error = WebRequestError

    def __init__(self):
        self.channel_count = 4
        self.protocol_parsers = {}
        self.spool_per_channel = {}

    def register_card_protocol_parser(self, card_type, parser):
        self.protocol_parsers[card_type] = parser

    def set_filament_info(self, channel, filament_info):
        self.spool_per_channel[channel] = filament_info


class PrinterStub:
    def __init__(self, klipper_objects):
        self._klipper_objects = klipper_objects
        self.handled_events = []

    def lookup_object(self, name, default=None):
        return self._klipper_objects.get(name, default)

    def register_event_handler(self, event_name, handler):
        self.handled_events.append(event_name)


class ConfigStub:
    """Stands in for the [bespok3d_rfid] section as Klipper hands it over.

    getboolean is the strict reader: Klipper halts the printer on a value it cannot parse, which is
    exactly what a setting that never reached the printer looks like.
    """

    def __init__(self, options):
        self._options = options
        self._printer = PrinterStub({})

    def get_printer(self):
        return self._printer

    def get(self, option_name, default=None):
        return self._options.get(option_name, default)

    def getboolean(self, option_name, default=None):
        setting = self._options.get(option_name)
        if setting is None:
            return default
        if setting.lower() not in ('true', 'false'):
            raise ValueError(
                f"Unable to parse option '{option_name}' in section 'bespok3d_rfid'")

        return setting.lower() == 'true'


class WebRequestStub:
    """Stands in for the filament_detect/set call a slicer or Moonraker client makes."""

    error = WebRequestError

    def __init__(self, channel, spool_fields):
        self._channel = channel
        self._spool_fields = spool_fields
        self.response = None

    def get_int(self, field_name, default):
        return self._channel if field_name == 'channel' else default

    def get_dict(self, field_name, default):
        return dict(self._spool_fields) if field_name == 'info' else default

    def send(self, response):
        self.response = response


def _spool_as_written_on_the_tag(vendor='Elegoo'):
    return {'VENDOR': vendor, 'MAIN_TYPE': 'PETG', 'SUB_TYPE': 'Basic',
            'OFFICIAL': True, 'SPOOL_ID': 7}


def _relay_reading_tags(force_generic_vendor, detector):
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay.printer = PrinterStub({'filament_detect': detector})
    relay._force_generic_vendor = force_generic_vendor
    return relay


def _parser_reading(spool):
    def parse_card(card_bytes):
        return FILAMENT_PROTO_OK, dict(spool)
    return parse_card


def _parser_that_cannot_read_the_tag(card_bytes):
    return FILAMENT_PROTO_ERR, None


def _what_the_printer_reports(relay, detector, parser):
    relay._register_protocol_parser(NTAG_CARD_TYPE, parser)
    return detector.protocol_parsers[NTAG_CARD_TYPE](CARD_BYTES)


def test_third_party_spool_is_reported_as_generic():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(True, detector)

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_reading(_spool_as_written_on_the_tag()))

    assert error == FILAMENT_PROTO_OK
    assert reported['VENDOR'] == 'Generic'
    assert reported['SUB_TYPE'] == ''
    assert reported['MAIN_TYPE'] == 'PETG'
    assert reported['SPOOL_ID'] == 7


def test_snapmaker_spool_keeps_its_own_name():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(True, detector)
    snapmaker_spool = _spool_as_written_on_the_tag(vendor='Snapmaker')

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_reading(snapmaker_spool))

    assert error == FILAMENT_PROTO_OK
    assert reported == snapmaker_spool


def test_switch_off_reports_the_brand_written_on_the_tag():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(False, detector)
    third_party_spool = _spool_as_written_on_the_tag()

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_reading(third_party_spool))

    assert error == FILAMENT_PROTO_OK
    assert reported == third_party_spool


def test_unreadable_tag_stays_unreadable():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(True, detector)

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_that_cannot_read_the_tag)

    assert error == FILAMENT_PROTO_ERR
    assert reported is None


def test_setting_that_never_reached_the_printer_leaves_it_printing():
    unsubstituted = ConfigStub({'force_generic_vendor': '$RFID_FORCE_GENERIC_VENDOR'})

    relay = bespok3d_rfid.Bespok3dRfid(unsubstituted)

    assert relay._force_generic_vendor is True


def test_setting_absent_altogether_leaves_it_printing():
    relay = bespok3d_rfid.Bespok3dRfid(ConfigStub({}))

    assert relay._force_generic_vendor is True


def test_setting_turned_off_in_the_app_is_read_as_off():
    relay = bespok3d_rfid.Bespok3dRfid(ConfigStub({'force_generic_vendor': 'False'}))

    assert relay._force_generic_vendor is False


def test_spool_pushed_over_the_webhook_is_reported_as_generic_too():
    detector = FilamentDetectStub()
    ntag = object.__new__(rfid_ntag.RfidNtag)
    ntag.printer = PrinterStub({'filament_detect': detector})
    ntag._rfid_hub = _relay_reading_tags(True, detector)
    request = WebRequestStub(
        CHANNEL, {'VENDOR': 'eSun', 'MAIN_TYPE': 'PETG', 'SUB_TYPE': 'Basic'})

    ntag._handle_filament_detect_set(request)

    assert request.response == {'state': 'success'}
    assert detector.spool_per_channel[CHANNEL]['VENDOR'] == 'Generic'
    assert detector.spool_per_channel[CHANNEL]['SUB_TYPE'] == ''
    assert detector.spool_per_channel[CHANNEL]['MAIN_TYPE'] == 'PETG'
