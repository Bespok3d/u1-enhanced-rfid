import logging

from . import fm175xx_reader as fm_mod

_log = logging.getLogger('bespok3d.ntag_reader')

NTAG_SAK = 0x04  # cascade bit set = 7-byte UID (level-0 SAK for NTAG213/215/216)
NTAG_USER_START_PAGE = 0    # page 0: UID area; page 3: CC required by ndef_parse
NTAG_USER_PAGE_COUNT = 132  # covers pages 0-131 (UID + CC + full user area), no boundary risk
NTAG_CARD_TYPE = getattr(fm_mod, 'FM175XX_MIFARE_CARD_TYPE_NTAG', NTAG_SAK)


class NtagReader:
    sak = NTAG_SAK
    card_type = NTAG_CARD_TYPE

    def can_handle(self, card_type):
        return card_type == NTAG_CARD_TYPE

    def read_hw_tag(self, reader):
        _log.info("read_hw_tag: reading pages %d+%d", NTAG_USER_START_PAGE, NTAG_USER_PAGE_COUNT)
        err, data = reader.read_nfc_type2_pages(NTAG_USER_START_PAGE, NTAG_USER_PAGE_COUNT)
        _log.info("read_hw_tag: err=%d bytes=%d", err, len(data) if data else 0)
        if err == fm_mod.FM175XX_OK:
            return NTAG_CARD_TYPE, data, fm_mod.FM175XX_OK
        _log.error("read_hw_tag: failed err=%d", err)
        return NTAG_CARD_TYPE, None, fm_mod.FM175XX_CARD_READ_ERR
