"""Render the Markdown used by documents and answers in native Tk Text widgets."""

from dataclasses import dataclass
import re
import webbrowser


INLINE = re.compile(
    r'\[([^\]]+)\]\((https?://[^\s)]+)\)'
    r'|`([^`\n]+)`'
    r'|\*\*(.+?)\*\*|__(.+?)__'
    r'|~~(.+?)~~'
    r'|(?<!\*)\*(?!\*)(.+?)\*(?!\*)'
    r'|(?<!\w)_(?!_)(.+?)_(?!\w)'
)
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
UNORDERED = re.compile(r'^\s*[-*+]\s+(.+)$')
ORDERED = re.compile(r'^\s*(\d+)[.)]\s+(.+)$')
TABLE_RULE = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$')


@dataclass(frozen=True)
class Span:
    text: str
    tags: tuple[str, ...] = ()
    url: str | None = None


def _inline(value: str, tags: tuple[str, ...] = ()) -> list[Span]:
    spans = []
    cursor = 0
    for match in INLINE.finditer(value):
        if match.start() > cursor:
            spans.append(Span(value[cursor:match.start()], tags))
        link_label, url, code, strong_star, strong_under, strike, em_star, em_under = match.groups()
        if url:
            spans.append(Span(link_label, tags + ('link',), url))
        elif code is not None:
            spans.append(Span(code, tags + ('code',)))
        else:
            inner = strong_star or strong_under or strike or em_star or em_under or ''
            style = 'strong' if strong_star is not None or strong_under is not None else (
                'strike' if strike is not None else 'em')
            spans.extend(_inline(inner, tags + (style,)))
        cursor = match.end()
    if cursor < len(value):
        spans.append(Span(value[cursor:], tags))
    return spans


def parse_markdown(content: str) -> list[Span]:
    """Produce visible text and style spans without exposing Markdown delimiters."""
    result = []
    fenced = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if fenced:
            result.append(Span(line + '\n', ('codeblock',)))
            continue
        if TABLE_RULE.fullmatch(line):
            continue
        if not stripped:
            result.append(Span('\n'))
            continue
        heading = HEADING.match(line)
        tags: tuple[str, ...] = ()
        if heading:
            level = min(len(heading.group(1)), 3)
            tags = (f'h{level}',)
            line = heading.group(2)
        elif stripped in ('---', '***', '___'):
            result.append(Span('────────────────────────\n', ('rule',)))
            continue
        elif line.lstrip().startswith('>'):
            line = '│  ' + re.sub(r'^\s*>\s?', '', line)
            tags = ('quote',)
        elif match := UNORDERED.match(line):
            line = '•  ' + match.group(1)
            tags = ('list',)
        elif match := ORDERED.match(line):
            line = f'{match.group(1)}.  {match.group(2)}'
            tags = ('list',)
        elif line.startswith('|') and line.endswith('|'):
            line = '   │   '.join(cell.strip() for cell in line.strip('|').split('|'))
            tags = ('table',)
        result.extend(_inline(line, tags))
        result.append(Span('\n', tags))
    return result


def render_markdown(widget, content: str, *, font_size: int = 11, document: bool = False):
    """Insert styled Markdown into a Tk Text widget; caller controls its state."""
    family = 'Microsoft YaHei UI'
    widget.tag_configure('strong', font=(family, font_size, 'bold'))
    widget.tag_configure('em', font=(family, font_size, 'italic'))
    widget.tag_configure('strike', overstrike=True)
    widget.tag_configure('code', font=('Consolas', max(9, font_size - 1)), background='#eef2ed')
    widget.tag_configure('codeblock', font=('Consolas', max(9, font_size - 1)),
                         background='#eef2ed', lmargin1=16, lmargin2=16)
    widget.tag_configure('quote', foreground='#597461', lmargin1=12, lmargin2=12)
    widget.tag_configure('list', lmargin1=11, lmargin2=24)
    widget.tag_configure('table', font=(family, font_size))
    widget.tag_configure('rule', foreground='#bed1be')
    widget.tag_configure('h1', font=(family, 20 if document else 17, 'bold'),
                         foreground='#18342c', spacing1=16, spacing3=14)
    widget.tag_configure('h2', font=(family, 14 if document else 13, 'bold'),
                         foreground='#276349', spacing1=16, spacing3=9)
    widget.tag_configure('h3', font=(family, 12, 'bold'), foreground='#276349',
                         spacing1=12, spacing3=7)
    widget.tag_configure('link', foreground='#276349', underline=True)
    for span in parse_markdown(content):
        tags = span.tags
        if span.url:
            link_tag = f'url_{widget.index("end-1c").replace(".", "_")}'
            tags += (link_tag,)
            widget.tag_bind(link_tag, '<Button-1>',
                            lambda _event, address=span.url: webbrowser.open(address))
            widget.tag_bind(link_tag, '<Enter>', lambda _event: widget.configure(cursor='hand2'))
            widget.tag_bind(link_tag, '<Leave>', lambda _event: widget.configure(cursor='arrow'))
        widget.insert('end', span.text, tags)
