"""URL resolution for static snapshots, including traversal and raw attrs."""

from html import escape

import pytest

from ruyipage._elements.firefox_element import FirefoxElement
from ruyipage._elements.static_element import (
    StaticElement,
    make_static_ele,
    make_static_eles,
)


BASE_URL = 'https://www.douyin.com/user/profile?old=1'
LINK_CASES = [
    ('//www.douyin.com/note/7394372414215294243',
     'https://www.douyin.com/note/7394372414215294243'),
    ('/video/7394355341351259418',
     'https://www.douyin.com/video/7394355341351259418'),
    ('video/123', 'https://www.douyin.com/user/video/123'),
    ('../video/123', 'https://www.douyin.com/video/123'),
    ('?page=2', 'https://www.douyin.com/user/profile?page=2'),
    ('?', 'https://www.douyin.com/user/profile?'),
    ('?#', 'https://www.douyin.com/user/profile?#'),
    ('#', 'https://www.douyin.com/user/profile?old=1#'),
    ('?page=2#', 'https://www.douyin.com/user/profile?page=2#'),
    ('#works', 'https://www.douyin.com/user/profile?old=1#works'),
    ('https://other.example/video/123', 'https://other.example/video/123'),
    ('mailto:hello@example.com', 'mailto:hello@example.com'),
    ('mailto:hello@example.com#', 'mailto:hello@example.com#'),
    ('javascript:void(0)', 'javascript:void(0)'),
    ('data:text/plain,hello', 'data:text/plain,hello'),
    ('http://[', 'http://['),
    ('', ''),
    (None, None),
]


@pytest.mark.parametrize(('href', 'expected'), LINK_CASES)
def test_static_href_resolves_without_changing_raw_attributes(href, expected):
    attribute = '' if href is None else ' href="{}"'.format(escape(href, quote=True))
    element = make_static_ele('<a{}>link</a>'.format(attribute), base_url=BASE_URL)

    assert element.attr('href') == expected
    assert element.link == (expected or '')
    assert element.attrs.get('href') == href
    assert element.attr('missing') is None


def test_static_snapshots_carry_base_url_through_search_and_traversal():
    html = '<section><a href="/first">one</a><a href="../second">two</a></section>'
    root = make_static_ele(html, base_url=BASE_URL)
    first = root.child()
    second = root.ele('tag:a', index=2)

    assert first.link == 'https://www.douyin.com/first'
    assert first.next().link == 'https://www.douyin.com/second'
    assert second.prev().link == first.link
    assert second.parent().s_ele('tag:a').link == first.link
    assert root.children()[1].link == second.link
    assert root.s_eles('tag:a')[1].link == second.link
    assert make_static_ele(html, 'tag:a', index=2, base_url=BASE_URL).link == second.link
    assert [e.link for e in make_static_eles(html, 'tag:a', base_url=BASE_URL)] == [
        first.link, second.link,
    ]


def test_static_html_without_a_document_url_retains_relative_href():
    element = make_static_ele('<a href="/video/123">link</a>')
    assert element.attr('href') == element.link == '/video/123'


def test_static_legacy_constructor_supports_url_resolution():
    element = StaticElement(tag='a', attrs={'href': '/video/123'}, base_url=BASE_URL)
    assert element.link == 'https://www.douyin.com/video/123'
    assert element.attrs['href'] == '/video/123'


@pytest.mark.parametrize('method', ['s_ele', 's_eles'])
def test_element_snapshot_captures_html_and_base_url_in_one_call(method):
    element = FirefoxElement(None, 'node-id')
    calls = []

    def capture(declaration):
        calls.append(declaration)
        return {'html': '<div><a href="/video/123">link</a></div>', 'baseURL': BASE_URL}

    element._run_safe = capture
    result = getattr(element, method)('tag:a')
    link = result[0] if isinstance(result, list) else result

    assert link.attr('href') == link.link == 'https://www.douyin.com/video/123'
    assert link.attrs['href'] == '/video/123'
    assert len(calls) == 1
