"""Check the formatting that appears in the native document and answers."""

import pytest

from desktop_markdown import parse_markdown


pytestmark = pytest.mark.offline


def test_inline_formatting_and_links_keep_their_visible_text():
    spans = parse_markdown('**1995 年：三年起步。**以 1990 年为基期。\n'
                           '参见[政府解读](https://example.org/source)，以及*补充说明*。')
    visible = ''.join(span.text for span in spans)
    assert visible.startswith('1995 年：三年起步。以 1990 年为基期。')
    assert '**' not in visible and '[政府解读]' not in visible
    assert any(span.text == '1995 年：三年起步。' and 'strong' in span.tags for span in spans)
    assert any(span.text == '补充说明' and 'em' in span.tags for span in spans)
    assert any(span.text == '政府解读' and span.url == 'https://example.org/source'
               for span in spans)


def test_block_formatting_does_not_show_markers():
    spans = parse_markdown('# 标题\n- **要点**\n> 引文\n```python\nprint(1)\n```\n')
    visible = ''.join(span.text for span in spans)
    assert '# 标题' not in visible
    assert '•  要点' in visible
    assert '│  引文' in visible
    assert '```' not in visible
    assert any(span.text == 'print(1)\n' and 'codeblock' in span.tags for span in spans)
