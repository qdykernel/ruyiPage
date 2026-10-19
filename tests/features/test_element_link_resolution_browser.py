"""Verify href completion against the browser's URL and document base rules."""

import pytest
from lxml import etree

from ruyipage import FirefoxPage

from tests.test_element_links import BASE_URL, LINK_CASES


pytestmark = pytest.mark.browser


@pytest.fixture
def link_page(opts_factory):
    page = FirefoxPage(opts_factory(headless=True))
    try:
        yield page
    finally:
        page.quit()


def test_live_and_static_href_use_document_base_uri(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic'))
    page.run_js('''
        const base = document.createElement('base');
        base.href = arguments[0];
        document.head.prepend(base);
        document.body.innerHTML = '<section id="links"></section>';
        for (const [index, href] of arguments[1].entries()) {
            const a = document.createElement('a');
            a.id = 'link-' + index;
            if (href !== null) a.setAttribute('href', href);
            a.textContent = 'link';
            document.querySelector('#links').appendChild(a);
        }
    ''', BASE_URL, [href for href, _ in LINK_CASES])

    snapshots = [
        page.s_eles('tag:a'),
        page.s_ele('#links').eles('tag:a'),
        page.ele('#links').s_eles('tag:a'),
        page.ele('#links').s_ele().eles('tag:a'),
    ]
    for index, (href, expected) in enumerate(LINK_CASES):
        element = page.ele('#link-{}'.format(index))
        assert element.attr('href') == expected
        assert element.attr('HREF') == expected
        assert element.link == (expected or '')
        assert element.attrs.get('href') == href
        for snapshot in snapshots:
            assert snapshot[index].attr('href') == expected
            assert snapshot[index].link == (expected or '')
            assert snapshot[index].attrs.get('href') == href

    # Snapshots retain their original document's base when the live base changes.
    page.run_js("document.querySelector('base').href = 'https://other.example/new/';")
    assert page.ele('#link-1').link == 'https://other.example/video/7394355341351259418'
    assert snapshots[0][1].link == LINK_CASES[1][1]


def test_href_uses_page_location_when_no_base_element_exists(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic'))
    page.run_js("document.body.innerHTML = '<a id=target href=../video/123>link</a>';")
    expected = server.get_url('/video/123')
    element = page.ele('#target')

    assert element.link == element.attr('href') == expected
    assert element.attr('id') == 'target'
    assert page.s_ele('#target').link == expected
    assert element.s_ele().link == expected


def test_href_resolves_against_frame_document_not_top_level_page(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic'))
    page.run_js('''
        return new Promise(resolve => {
            const iframe = document.createElement('iframe');
            iframe.id = 'child';
            iframe.onload = () => resolve(true);
            iframe.srcdoc = '<base href="https://frame.example/nested/">' +
                '<a id="target" href="video/123">link</a>';
            document.body.appendChild(iframe);
        });
    ''')
    frame = page.get_frame('#child')
    assert frame is not None
    element = frame.ele('#target')
    expected = 'https://frame.example/nested/video/123'

    assert element.link == element.attr('href') == expected
    assert frame.s_ele('#target').link == expected
    assert element.s_ele().link == expected


def _snapshot_variants(page, locator, scope):
    """Exercise both whole-document and element-fragment snapshot entry points."""
    live_scope = page.ele(scope)
    elements = page.eles(locator)
    return {
        'page.s_ele': page.s_ele(scope).eles(locator),
        'page.s_eles': page.s_eles(locator),
        'element.s_ele': live_scope.s_ele().eles(locator),
        'element.s_eles': live_scope.s_eles(locator),
        'selected page.s_ele': [page.s_ele(locator, index=index + 1)
                                for index in range(len(elements))],
        'selected element.s_ele': [live_scope.s_ele(locator, index=index + 1)
                                   for index in range(len(elements))],
        'direct element.s_ele': [element.s_ele() for element in elements],
    }


def _href_mismatches(variants, expected):
    """Report all entry-point failures without hiding later URL edge cases."""
    mismatches = []
    for route, elements in variants.items():
        assert len(elements) == len(expected), route
        for element, row in zip(elements, expected):
            for name, actual in [('link', element.link), ('attr', element.attr('href'))]:
                if actual != row['resolved']:
                    mismatches.append((route, row['raw'], name, actual, row['resolved']))
            if element.attrs.get('href') != row['raw']:
                mismatches.append((route, row['raw'], 'attrs', element.attrs.get('href'), row['raw']))
            # Serialization keeps relative hrefs and existing attrs, without metadata.
            # lxml historically percent-encodes non-ASCII URL characters on output.
            parsed = etree.HTML(element.html)
            serialized = parsed.xpath('//*[@id=$id]', id=row['id'])
            if len(serialized) != 1:
                mismatches.append((route, row['raw'], 'html node', element.html, row['id']))
            else:
                raw_node = etree.Element(serialized[0].tag, attrib=row['attrs'])
                serialized_raw = etree.tostring(raw_node, encoding='unicode', method='html')
                expected_attrs = dict(etree.HTML(serialized_raw).xpath('//*[@id=$id]', id=row['id'])[0].attrib)
                if dict(serialized[0].attrib) not in (row['attrs'], expected_attrs):
                    mismatches.append((route, row['raw'], 'html attrs', dict(serialized[0].attrib), expected_attrs))
    return mismatches


def test_url_edge_cases_match_dom_href_across_snapshot_entry_points(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic?old=1#previous'))
    hrefs = ['?', '?#', '#', r'\\other.example\video\123',
             '%2e%2e/video/123', '/\u4f5c\u54c1 \u96c6/123', ' ?q=\u4f5c\u54c1 \u96c6# ']
    expected = page.run_js('''
        document.body.innerHTML = '<section id="edges"></section>';
        return arguments[0].map((href, index) => {
            const a = document.createElement('a');
            a.id = 'edge-' + index;
            a.setAttribute('href', href);
            a.setAttribute('data-ruyi-snapshot-href', 'preserved-' + index);
            a.textContent = 'link';
            document.querySelector('#edges').appendChild(a);
            return {id: a.id, raw: href, resolved: a.href,
                    attrs: Object.fromEntries(Array.from(a.attributes, a => [a.name, a.value]))};
        });
    ''', hrefs)

    variants = _snapshot_variants(page, 'tag:a', '#edges')
    variants['live'] = page.eles('tag:a')
    mismatches = _href_mismatches(variants, expected)
    assert not mismatches, '\n'.join(map(str, mismatches))


def test_each_relative_base_href_uses_document_location(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic?old=1'))
    expected = page.run_js('''
        for (const [index, href] of ['assets/', '../other/'].entries()) {
            const base = document.createElement('base');
            base.id = 'base-' + index;
            base.setAttribute('href', href);
            document.head.appendChild(base);
        }
        document.body.innerHTML = '<a id="content-link" href="video/123">link</a>';
        return Array.from(document.querySelectorAll('base'), base => ({
            id: base.id, raw: base.getAttribute('href'), resolved: base.href,
            attrs: Object.fromEntries(Array.from(base.attributes, a => [a.name, a.value]))
        }));
    ''', as_expr=False)

    assert [row['resolved'] for row in expected] == [
        server.get_url('/nav/assets/'), server.get_url('/other/'),
    ]
    variants = _snapshot_variants(page, 'tag:base', 'tag:head')
    variants['live'] = page.eles('tag:base')
    mismatches = _href_mismatches(variants, expected)
    assert not mismatches, '\n'.join(map(str, mismatches))
    assert page.ele('#content-link').link == server.get_url('/nav/assets/video/123')
    assert page.s_ele('#content-link').link == server.get_url('/nav/assets/video/123')


def test_generic_href_and_snapshot_reads_stay_local_after_page_changes(
        link_page, server, monkeypatch):
    page = link_page
    page.get(server.get_url('/nav/basic?old=1'))
    expected = page.run_js('''
        const base = document.createElement('base');
        base.href = 'assets/?old=1';
        document.head.appendChild(base);
        document.body.innerHTML = '<section id="generic"></section>';
        return ['?', '#', '%2e%2e/\u4f5c\u54c1 \u96c6'].map((href, index) => {
            const node = document.createElement('div');
            node.id = 'generic-' + index;
            node.setAttribute('href', href);
            document.querySelector('#generic').appendChild(node);
            return {id: node.id, raw: href, resolved: new URL(href, node.baseURI).href,
                    attrs: Object.fromEntries(Array.from(node.attributes, a => [a.name, a.value]))};
        });
    ''', as_expr=False)
    variants = _snapshot_variants(page, 'css:div[href]', '#generic')
    root_snapshot = page.s_ele('#generic')
    live_mismatches = _href_mismatches({'live': page.eles('css:div[href]')}, expected)
    page.run_js('''
        document.querySelector('base').href = 'https://changed.example/';
        document.querySelectorAll('[href]').forEach(node => node.setAttribute('href', '/changed'));
        document.body.innerHTML = '<p>The original nodes are gone.</p>';
    ''')
    page.quit()

    def unexpected_browser_call(*args, **kwargs):
        pytest.fail('Reading or traversing a static snapshot contacted the browser')

    with monkeypatch.context() as patch:
        patch.setattr(page, '_run_js', unexpected_browser_call)
        patch.setattr(page._driver._browser_driver, 'run', unexpected_browser_call)
        variants['post-close traversal'] = root_snapshot.child().parent().children()
        mismatches = _href_mismatches(variants, expected)
        assert root_snapshot.child().next().prev().attrs['href'] == '?'
    assert not live_mismatches + mismatches, '\n'.join(map(str, live_mismatches + mismatches))


def test_template_href_captures_its_own_document_resolution(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic?old=1'))
    expected = page.run_js('''
        document.body.innerHTML = '<section id="templates" data-ruyi-snapshot-href="original">' +
            '<template id="outer-template"><a id="template-link" href="?">outer</a>' +
            '<template id="inner-template"><a id="nested-link" href="../video/123">nested</a>' +
            '</template></template></section>';
        const outer = document.querySelector('#outer-template');
        const anchors = [outer.content.querySelector('a'),
            outer.content.querySelector('template').content.querySelector('a')];
        return anchors.map(a => ({id: a.id, raw: a.getAttribute('href'), resolved: a.href,
            attrs: Object.fromEntries(Array.from(a.attributes, a => [a.name, a.value]))}));
    ''', as_expr=False)

    variants = {
        'page.s_ele': page.s_ele('#templates').eles('tag:a'),
        'page.s_eles': page.s_eles('tag:template')[0].eles('tag:a'),
        'element.s_ele': page.ele('#outer-template').s_ele().eles('tag:a'),
        'element.s_eles': page.ele('#templates').s_eles('tag:template')[0].eles('tag:a'),
    }
    root_snapshot = page.s_ele('#templates')
    assert root_snapshot.attrs['data-ruyi-snapshot-href'] == 'original'
    assert root_snapshot.attr('id') == 'templates'
    mismatches = _href_mismatches(variants, expected)
    assert not mismatches, '\n'.join(map(str, mismatches))


def test_snapshot_does_not_run_custom_element_constructors(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic?old=1'))
    page.run_js('''
        window.snapshotConstructorCalls = 0;
        customElements.define('snapshot-card', class extends HTMLElement {
            constructor() {
                super();
                window.snapshotConstructorCalls += 1;
            }
        });
        document.body.innerHTML = '<snapshot-card id="card">' +
            '<a id="card-link" href="?">link</a></snapshot-card>';
    ''')
    assert page.run_js('window.snapshotConstructorCalls') == 1

    variants = _snapshot_variants(page, '#card-link', '#card')

    assert page.run_js('window.snapshotConstructorCalls') == 1
    for elements in variants.values():
        assert elements[0].link == server.get_url('/nav/basic?')
        assert elements[0].attrs['href'] == '?'


def test_svg_href_case_and_existing_snapshot_attribute_are_preserved(link_page, server):
    page = link_page
    page.get(server.get_url('/nav/basic'))
    page.run_js('''
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.id = 'svg-links';
        const a = document.createElementNS('http://www.w3.org/2000/svg', 'a');
        a.id = 'svg-link';
        a.setAttribute('href', '/lower');
        a.setAttribute('HREF', '/upper');
        a.setAttribute('DATA-RUYI-SNAPSHOT-HREF', 'site-value');
        svg.appendChild(a);
        document.body.replaceChildren(svg);
    ''')
    live = page.ele('#svg-link')
    original_attrs = {
        'id': 'svg-link', 'href': '/lower', 'HREF': '/upper',
        'DATA-RUYI-SNAPSHOT-HREF': 'site-value',
    }
    expected = server.get_url('/lower')
    assert live.attr('HREF') == server.get_url('/upper')
    assert live.link == live.attr('href') == expected
    assert live.attrs == original_attrs

    variants = _snapshot_variants(page, '#svg-link', '#svg-links')
    expected_static_attrs = {
        'id': 'svg-link', 'href': '/lower',
        'data-ruyi-snapshot-href': 'site-value',
    }
    for route, elements in variants.items():
        assert len(elements) == 1, route
        snapshot = elements[0]
        assert snapshot.link == snapshot.attr('href') == expected, route
        assert snapshot.attrs == expected_static_attrs, route
        serialized = etree.HTML(snapshot.html).xpath('//*[@id="svg-link"]')[0]
        assert dict(serialized.attrib) == expected_static_attrs, route

    # Snapshot metadata is attached to clones; the actual SVG stays untouched.
    assert live.attrs == original_attrs
    assert live.attr('HREF') == server.get_url('/upper')
    assert live.link == expected
