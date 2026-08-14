"""Regression tests for reporting a spool exactly as its tag names it.

Both routes a spool takes into the printer's filament state, the hardware tag read and the
filament_detect/set webhook, must report the tag's own words: brand, material and variant.
Snapmaker Orca then lists the spool when a filament preset carries exactly that glued name.
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


def _relay_reading_tags(detector):
    relay = object.__new__(bespok3d_rfid.Bespok3dRfid)
    relay.printer = PrinterStub({'filament_detect': detector})
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


def test_spool_is_reported_exactly_as_its_tag_names_it():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(detector)
    tagged_spool = _spool_as_written_on_the_tag()

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_reading(tagged_spool))

    assert error == FILAMENT_PROTO_OK
    assert reported == tagged_spool


def test_unreadable_tag_stays_unreadable():
    detector = FilamentDetectStub()
    relay = _relay_reading_tags(detector)

    error, reported = _what_the_printer_reports(
        relay, detector, _parser_that_cannot_read_the_tag)

    assert error == FILAMENT_PROTO_ERR
    assert reported is None


def test_spool_pushed_over_the_webhook_keeps_its_own_words():
    detector = FilamentDetectStub()
    ntag = object.__new__(rfid_ntag.RfidNtag)
    ntag.printer = PrinterStub({'filament_detect': detector})
    request = WebRequestStub(
        CHANNEL, {'VENDOR': 'eSun', 'MAIN_TYPE': 'PETG', 'SUB_TYPE': 'Basic'})

    ntag._handle_filament_detect_set(request)

    assert request.response == {'state': 'success'}
    assert detector.spool_per_channel[CHANNEL]['VENDOR'] == 'eSun'
    assert detector.spool_per_channel[CHANNEL]['SUB_TYPE'] == 'Basic'
    assert detector.spool_per_channel[CHANNEL]['MAIN_TYPE'] == 'PETG'
