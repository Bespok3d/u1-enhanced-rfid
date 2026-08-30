import logging

from . import fm175xx_reader as fm_mod

_log = logging.getLogger('bespok3d.ntag_reader')

NTAG_SAK = 0x04  # cascade bit set = 7-byte UID (level-0 SAK for NTAG213/215/216)
NTAG_USER_START_PAGE = 0    # page 0: UID area; page 3: CC required by ndef_parse
NTAG_USER_PAGE_COUNT = 132  # covers pages 0-131 (UID + CC + full user area), no boundary risk
NTAG_CARD_TYPE = getattr(fm_mod, 'FM175XX_MIFARE_CARD_TYPE_NTAG', NTAG_SAK)
PAGES_PER_CHUNK = 4  # one physical READ operation width on NTAG21x / Ultralight family
BYTES_PER_PAGE = 4


class ChunkedType2PageReader:
    """Wraps read_nfc_type2_pages in fixed, full-width chunks and stops at the first failed
    chunk, keeping whatever pages already came back clean.

    read_nfc_type2_pages always performs its physical READs in full PAGES_PER_CHUNK groups
    regardless of the page count it was asked for (a request for 1 to PAGES_PER_CHUNK pages
    still returns a full chunk's worth of bytes), and it discards everything already
    collected within one call the moment any group in that call fails. This class only ever
    asks it for one full chunk at a time, so a failure never costs more than the one chunk it
    happened on, and trims the final buffer down to what the caller actually asked for, since
    the driver itself will not do that trimming.
    """

    def __init__(self, reader, pages_per_chunk=PAGES_PER_CHUNK):
        self.reader = reader
        self.pages_per_chunk = pages_per_chunk

    def read_available_pages(self, start_page, requested_page_count):
        collected_bytes = bytearray()
        pages_remaining = requested_page_count
        current_page = start_page

        while pages_remaining > 0:
            err, chunk_data = self.reader.read_nfc_type2_pages(current_page, self.pages_per_chunk)
            if err != fm_mod.FM175XX_OK:
                break
            collected_bytes.extend(chunk_data)
            current_page += self.pages_per_chunk
            pages_remaining -= self.pages_per_chunk

        if len(collected_bytes) == 0:
            return fm_mod.FM175XX_CARD_READ_ERR, None
        wanted_byte_count = requested_page_count * BYTES_PER_PAGE
        return fm_mod.FM175XX_OK, bytes(collected_bytes[:wanted_byte_count])


class NtagReader:
    sak = NTAG_SAK
    card_type = NTAG_CARD_TYPE

    def can_handle(self, card_type):
        return card_type == NTAG_CARD_TYPE

    def read_hw_tag(self, reader):
        chunked_reader = ChunkedType2PageReader(reader)
        _log.info("read_hw_tag: reading pages %d+%d", NTAG_USER_START_PAGE, NTAG_USER_PAGE_COUNT)
        err, data = chunked_reader.read_available_pages(NTAG_USER_START_PAGE, NTAG_USER_PAGE_COUNT)
        _log.info("read_hw_tag: err=%d bytes=%d", err, len(data) if data else 0)
        if err == fm_mod.FM175XX_OK:
            return NTAG_CARD_TYPE, data, fm_mod.FM175XX_OK
        _log.error("read_hw_tag: failed err=%d", err)
        return NTAG_CARD_TYPE, None, fm_mod.FM175XX_CARD_READ_ERR
