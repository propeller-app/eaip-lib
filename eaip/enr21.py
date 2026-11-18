import re
import typing

from bs4 import BeautifulSoup


_LIMIT_LABELS = ('Upper limit:', 'Lower limit:', 'Minimum limit:', 'Class:')
_LIMIT_PATTERN = re.compile('|'.join(re.escape(label) for label in _LIMIT_LABELS))
_LANGUAGE_PATTERN = re.compile(r'\b(English|French|German)\b')
_HOURS_PATTERN = re.compile(r'\b\d{4}-\d{4}\b[^\n]*')


def _is_hidden(element) -> bool:
    """
    True if the node sits inside a ``span.sdParams`` (hidden eAIP metadata).
    """
    node = element.parent if isinstance(element, str) else element
    for parent in [node, *getattr(node, 'parents', [])]:
        if 'sdParams' in (parent.get('class') or []):
            return True
    return False


def _normalise(text: str) -> str:
    """
    Collapse runs of whitespace on each line and drop leading/trailing blanks.
    """
    lines = [re.sub(r'[ \t\xa0]+', ' ', line).strip() for line in text.split('\n')]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines)


def _text_with_breaks(element) -> str:
    """
    Visible text of ``element``, with ``<br>`` rendered as a newline and the
    hidden ``sdParams`` metadata excluded.

    Adjacent ``span.SD`` values are separated by a space: the eAIP prints
    ``FL`` and ``660`` as two spans with no whitespace between them.
    """
    parts = []
    previous_sd = None
    for node in element.descendants:
        if isinstance(node, str):
            if _is_hidden(node):
                continue
            parent = node.parent
            is_sd = 'SD' in (parent.get('class') or [])
            if is_sd and previous_sd is not None and previous_sd is not parent:
                if node and not node[0].isspace() and parts and not parts[-1][-1:].isspace():
                    parts.append(' ')
            parts.append(node)
            previous_sd = parent if is_sd else None
        elif node.name == 'br':
            parts.append('\n')
            previous_sd = None
    return _normalise(''.join(parts))


def _tags(element) -> typing.List[str]:
    """
    The leading part of every ``sdParams`` tag in ``element``, e.g. ``TUNIT``.
    """
    return [span.get_text(strip=True).split(';')[0]
            for span in element.find_all('span', class_='sdParams')]


def _sd_pairs(element) -> typing.Iterator[typing.Tuple[str, str]]:
    """
    Yield ``(visible value, full sdParams tag)`` for every tagged field.
    """
    for span in element.find_all('span', class_='SD'):
        sibling = span.find_next_sibling('span', class_='sdParams')
        tag = sibling.get_text(strip=True) if sibling is not None else ''
        yield _text_with_breaks(span), tag


def _name_span(cell) -> typing.Optional[typing.Any]:
    """
    The visible span holding a record name, if ``cell`` starts a record.
    """
    for span in cell.find_all('span', class_='sdParams'):
        if span.get_text(strip=True).startswith('TAIRSPACE;TXT_NAME'):
            return span.find_previous_sibling('span', class_='SD')
    return None


def _parse_first_cell(cell, name: str) -> typing.Tuple[str, typing.List[dict]]:
    """
    Split the first cell into the raw lateral-limit text and the vertical
    bands. Bands keep the order printed on the page; a record with two
    Upper/Lower/Class triplets gets two bands.
    """
    text = _text_with_breaks(cell)
    rest = text[len(name):] if text.startswith(name) else text
    matches = list(_LIMIT_PATTERN.finditer(rest))
    boundary = (rest[:matches[0].start()] if matches else rest).strip()

    bands = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(rest)
        value = rest[match.end():end].strip()
        label = match.group()
        if label == 'Upper limit:':
            bands.append({'upper': value, 'lower': None, 'minimum': None, 'class': None})
        elif label == 'Lower limit:' and bands:
            bands[-1]['lower'] = value
        elif label == 'Minimum limit:' and bands:
            bands[-1]['minimum'] = None if value == '-' else value
        elif label == 'Class:' and bands:
            bands[-1]['class'] = value
    return boundary, bands


def _current_unit(record: dict) -> dict:
    if not record['units']:
        record['units'].append({'name': None, 'callsign': None, 'language': None,
                                'hours': None, 'frequencies': []})
    return record['units'][-1]


def _add_units(record: dict, cell) -> None:
    """
    Start a new unit for every ``TUNIT`` tag in ``cell``.
    """
    for value, tag in _sd_pairs(cell):
        if tag.startswith('TUNIT'):
            record['units'].append({'name': value, 'callsign': None, 'language': None,
                                    'hours': None, 'frequencies': []})


def _apply_callsign_block(record: dict, cell) -> None:
    """
    Fill callsign/language/hours on the unit the block belongs to.
    """
    unit = _current_unit(record)
    text = _text_with_breaks(cell)
    hours = []
    for value, tag in _sd_pairs(cell):
        if tag.startswith('TCALLSIGN_DETAIL;TXT_CALL_SIGN') and unit['callsign'] is None:
            unit['callsign'] = value
        elif tag.startswith('TCALLSIGN_DETAIL;CODE_LANG') and unit['language'] is None:
            unit['language'] = value
        elif tag.startswith('TSERVICE_STS'):
            hours.append(value)

    if unit['language'] is None:
        language = _LANGUAGE_PATTERN.search(text)
        if language is not None:
            unit['language'] = language.group(1)
    if not hours:
        found = _HOURS_PATTERN.search(text)
        if found is not None:
            hours.append(found.group(0).strip())
    if hours:
        unit['hours'] = '\n'.join(hours)


def _frequencies(cell) -> typing.List[str]:
    """
    Frequency values as printed (e.g. ``132.955``, or ``119.005 MHz``).
    ``TFREQUENCY`` annotations are not frequencies and are skipped.
    """
    values = []
    for span in cell.find_all('span', class_='SD'):
        sibling = span.find_next_sibling('span', class_='sdParams')
        tag = sibling.get_text(strip=True) if sibling is not None else ''
        if not tag.startswith('TFREQUENCY;VAL_FREQ_TRANS'):
            continue
        value = _text_with_breaks(span)
        following = sibling.next_sibling
        if isinstance(following, str) and re.match(r'\s*MHz\b', following):
            value = f'{value} MHz'
        values.append(value)
    return values


def _consume_record_row(record: dict, cells) -> None:
    """
    Read the unit/callsign/frequency/remarks cells of the row owning a record.
    """
    _add_units(record, cells[0])
    last = len(cells) - 1
    for index, cell in enumerate(cells[1:], start=1):
        tags = _tags(cell)
        if index == last:
            text = _text_with_breaks(cell)
            record['remarks'] = None if text in ('', '-') else text
        elif 'TUNIT' in tags:
            _add_units(record, cell)
        elif any(tag.startswith(('TCALLSIGN_DETAIL', 'TSERVICE_STS')) for tag in tags):
            _apply_callsign_block(record, cell)
        elif any(tag.startswith('TFREQUENCY') for tag in tags):
            _current_unit(record)['frequencies'].extend(_frequencies(cell))


def _consume_continuation_row(record: dict, cells) -> None:
    """
    Read the extra units and extra frequency rows that belong to a record.
    """
    for cell in cells:
        tags = _tags(cell)
        if 'TUNIT' in tags:
            _add_units(record, cell)
        elif any(tag.startswith(('TCALLSIGN_DETAIL', 'TSERVICE_STS')) for tag in tags):
            _apply_callsign_block(record, cell)
        elif any(tag.startswith('TFREQUENCY') for tag in tags):
            _current_unit(record)['frequencies'].extend(_frequencies(cell))


def parse_enr21(html: str) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Parses an eAIP ENR-2.1 (FIR, UIR, TMA and CTA) document into raw records.

    Boundary geometry is kept as text; nothing is resolved or parsed into
    coordinates. The ENR-2.1.1 table at the end of the page (Brize Norton CTR)
    is read through the same loop and has ``row_id`` ``None``.

    Example:

    ::

        with open('EG-ENR-2.1-en-GB.html') as f:
            records = parse_enr21(f.read())
        records[0]['name']
        # Expected output: 'LONDON FIR'

    :param html: The eAIP ENR-2.1 HTML document.
    :return: One record per airspace, in document order. Each record is a dict
        with ``row_id`` (str or None), ``name`` (str), ``boundary_text`` (str,
        whitespace-normalised lateral-limit text, unparsed), ``bands`` (list of
        ``{'upper', 'lower', 'minimum', 'class'}`` dicts in printed order;
        ``minimum`` is None when printed as '-'), ``units`` (list of
        ``{'name', 'callsign', 'language', 'hours', 'frequencies'}`` dicts;
        ``frequencies`` strings are as printed) and ``remarks`` (str with
        ``<br>`` turned into newlines, or None).
    """
    soup = BeautifulSoup(html, 'html.parser')
    records = []
    current = None

    for row in soup.find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue
        name_span = _name_span(cells[0])
        if name_span is not None:
            name = _normalise(name_span.get_text(' ', strip=True))
            boundary, bands = _parse_first_cell(cells[0], name)
            current = {
                'row_id': row.get('row_id') or None,
                'name': name,
                'boundary_text': boundary,
                'bands': bands,
                'units': [],
                'remarks': None,
            }
            records.append(current)
            _consume_record_row(current, cells)
        elif current is not None:
            _consume_continuation_row(current, cells)

    return records
