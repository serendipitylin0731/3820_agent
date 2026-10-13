from scripts.import_supplemental_materials import _normal_text, _prefer_ocr


def test_scanned_photo_caption_beats_long_garbled_text_layer():
    corrupt = ('• 、 -c, \xad., J r  • -、h ' * 80) + '插队回京探亲时的习近平'
    caption = '1972年，插队回京探亲时的习近平。'
    assert _prefer_ocr(corrupt, caption)
    assert _prefer_ocr('才979 年1 在中央军委办公厅工作时的习近平。',
                       '1979年，在中央军委办公厅工作时的习近平。')
    assert not _prefer_ocr('福建林业改革需要明确产权和利益归属。', '福建林业改革')


def test_public_reading_copy_removes_repeated_scan_watermark():
    assert _normal_text('第一章\n仅限于教学及科研使用\n正文') == '第一章\n\n正文'
