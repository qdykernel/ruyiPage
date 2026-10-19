# -*- coding: utf-8 -*-
"""StaticElement 的查找与导航能力。

这些用例不需要浏览器：StaticElement 是纯本地 HTML 解析，
直接喂字符串即可。
"""

import pytest

from ruyipage._elements.firefox_element import FirefoxElement
from ruyipage._elements.none_element import NoneElement
from ruyipage._elements.static_element import (
    StaticElement,
    make_static_ele,
    make_static_eles,
)
from ruyipage.errors import LocatorError


DOC = """<!doctype html>
<html><body>
  <div class="card" id="c1" data-rank="1">
    <h2><a href="/a" class="title">标题一</a></h2>
    <p class="sum">摘要一</p>
    <ul class="tags"><li class="t">tag1</li><!--注释--><li class="t">tag2</li></ul>
  </div>
  <div class="card" id="c2" data-rank="2">
    <h2><a href="/b" class="title">标题二</a></h2>
    <p class="sum">摘要二</p>
  </div>
</body></html>"""

FRAGMENT = '<div class="card" id="c1"><h2><a href="/a">标题一</a></h2><p>摘要</p></div>'


@pytest.fixture
def card():
    """文档里的第一张卡片。"""
    return make_static_ele(DOC, '.card')


# ===== 查找 =====

def test_ele_searches_inside_the_element(card):
    assert card.ele('css:h2 a').text == '标题一'
    assert card.ele('css:h2 a').link == '/a'


def test_eles_returns_all_matches_in_document_order(card):
    assert [e.text for e in card.eles('.t')] == ['tag1', 'tag2']


def test_ele_not_found_returns_none_element(card):
    missing = card.ele('#nope')
    assert isinstance(missing, NoneElement)
    assert not missing
    # 空对象模式：继续链式调用不炸
    assert missing.ele('.x').text == ''
    assert missing.eles('.x') == []


def test_ele_index_counts_from_one_and_accepts_negative(card):
    assert card.ele('.t', index=2).text == 'tag2'
    assert card.ele('.t', index=-1).text == 'tag2'
    assert isinstance(card.ele('.t', index=5), NoneElement)


def test_s_ele_and_s_eles_are_aliases(card):
    assert card.s_ele('.sum').text == '摘要一'
    assert [e.text for e in card.s_eles('.t')] == ['tag1', 'tag2']
    # 不传定位器就是自己，不会再解析一次
    assert card.s_ele() is card


def test_relative_search_excludes_the_element_itself(card):
    """``card.ele('tag:div')`` 要找卡片里面的 div，不能把卡片自己算进去。

    cssselect 生成的是 descendant-or-self::，不剔除自身的话这里会命中 card。
    """
    assert isinstance(card.ele('tag:div'), NoneElement)
    # 从文档层面找则可以命中它自己
    assert make_static_ele(DOC, 'tag:div').attr('id') == 'c1'


def test_relative_xpath_is_scoped_to_the_subtree(card):
    """``//li`` 在元素上调用时会被改写成 ``.//li``，只找子树内的。"""
    assert [e.text for e in card.eles('x://li')] == ['tag1', 'tag2']
    # 文档级查找仍是全文档语义
    assert len(make_static_eles(DOC, 'x://li')) == 2


def test_text_locators(card):
    assert card.ele('text:标题').tag == 'a'
    assert card.ele('text=摘要一').tag == 'p'
    # 文本按「元素自身的直接文本」匹配，不会一路命中所有祖先
    assert make_static_ele(DOC, 'text:标题一').tag == 'a'


def test_attribute_locators():
    assert make_static_ele(DOC, '@data-rank=2').attr('id') == 'c2'
    assert make_static_ele(DOC, '@@class=card@@data-rank=1').attr('id') == 'c1'


# ===== DOM 导航 =====

def test_child_and_children(card):
    assert card.child().tag == 'h2'
    assert card.child(index=2).tag == 'p'
    assert card.child(index=-1).tag == 'ul'
    assert [c.tag for c in card.children()] == ['h2', 'p', 'ul']


def test_children_skips_comment_nodes(card):
    """lxml 会把注释当节点挂在树上，children() 必须过滤掉。"""
    tags = card.ele('.tags')
    assert [c.tag for c in tags.children()] == ['li', 'li']


def test_child_with_locator_searches_whole_subtree(card):
    """与 FirefoxElement.child() 保持一致：带定位器时等价于 ele()。"""
    assert card.child('.title').text == '标题一'


def test_parent_climbs_levels(card):
    li = card.ele('.t')
    assert li.parent().tag == 'ul'
    assert li.parent(index=2).tag == 'div'


def test_parent_with_locator_finds_matching_ancestor(card):
    li = card.ele('.t')
    assert li.parent('.card').attr('id') == 'c1'
    assert isinstance(li.parent('#nope'), NoneElement)


def test_parent_stops_at_root():
    root = make_static_ele(FRAGMENT)
    # 片段根之上只剩解析器补出来的包装层，再往上必须停住
    assert isinstance(root.parent(index=10), NoneElement)


def test_next_and_prev(card):
    first = card.ele('.t')
    assert first.next().text == 'tag2'
    assert isinstance(first.prev(), NoneElement)
    assert first.next().prev().text == 'tag1'


def test_next_prev_across_siblings():
    c1 = make_static_ele(DOC, '.card')
    c2 = make_static_ele(DOC, '.card', index=2)
    assert c1.next().attr('id') == 'c2'
    assert c2.prev().attr('id') == 'c1'


def test_next_with_locator_filter(card):
    h2 = card.child()
    assert h2.next('.sum').text == '摘要一'
    assert h2.next('tag:ul').attr('class') == 'tags'


def test_sibling_filter_rejects_xpath(card):
    with pytest.raises(LocatorError):
        card.ele('.t').next('x://li')


# ===== 根节点与片段 =====

def test_fragment_root_is_the_element_itself():
    """元素片段要剥掉 lxml 补出来的 <html>/<body>，否则根节点就不是那个元素。"""
    root = make_static_ele(FRAGMENT)
    assert root.tag == 'div'
    assert root.attr('id') == 'c1'


def test_document_root_is_html():
    assert make_static_ele(DOC).tag == 'html'


def test_multiple_top_level_elements_keep_a_container():
    container = make_static_ele('<li>a</li><li>b</li>')
    assert [e.text for e in container.eles('tag:li')] == ['a', 'b']


def test_empty_html():
    assert isinstance(make_static_ele(''), NoneElement)
    assert make_static_eles('', 'tag:a') == []


# ===== 属性与序列化 =====

def test_text_vs_raw_text():
    ele = make_static_ele('<a>he<b>l</b>llo</a>')
    assert ele.text == 'helllo'
    assert ele.raw_text == 'hello'


def test_outer_html_excludes_tail_text():
    """lxml 的 tostring 会把元素后面的游离文本一起吐出来，必须剪掉。"""
    assert make_static_ele('<p>x</p>尾巴').outer_html == '<p>x</p>'


def test_inner_and_outer_html(card):
    sum_ele = card.ele('.sum')
    assert sum_ele.inner_html == '摘要一'
    assert sum_ele.outer_html == '<p class="sum">摘要一</p>'
    assert sum_ele.html == sum_ele.outer_html


def test_attrs_returns_a_copy(card):
    attrs = card.attrs
    attrs['id'] = 'changed'
    assert card.attr('id') == 'c1'


def test_link_src_value():
    assert make_static_ele('<a href="/x">y</a>').link == '/x'
    assert make_static_ele('<img src="/i.png">', 'tag:img').src == '/i.png'
    assert make_static_ele('<input value="v">', 'tag:input').value == 'v'


def test_legacy_constructor_without_node():
    """老的构造方式（只传字符串、不带 node）仍然可用。"""
    ele = StaticElement(tag='div', attrs={'id': 'x'}, text='hi',
                        inner_html='hi', outer_html='<div id="x">hi</div>')
    assert ele.tag == 'div'
    assert ele.attr('id') == 'x'
    assert ele.text == 'hi'
    assert ele.outer_html == '<div id="x">hi</div>'
    # 没有节点就没法继续导航，但不能抛异常
    assert isinstance(ele.ele('.x'), NoneElement)
    assert ele.eles('.x') == []
    assert ele.children() == []
    assert isinstance(ele.parent(), NoneElement)


# ===== 错误处理 =====

def test_bad_css_selector_raises():
    with pytest.raises(LocatorError):
        make_static_ele(DOC, 'css:[[[')


def test_bad_xpath_raises():
    with pytest.raises(LocatorError):
        make_static_ele(DOC, 'x://a[')


# ===== 元素 / 空对象上的入口 =====

class _FakeElement(object):
    """提供 HTML 和 baseURI 快照的假元素。

    借此可以在不起浏览器的情况下验证静态快照的取根逻辑。
    """

    def __init__(self, html):
        self.html = html

    def _run_safe(self, declaration):
        return {'html': self.html, 'baseURL': None}

    s_ele = FirefoxElement.s_ele
    s_eles = FirefoxElement.s_eles


def test_element_s_ele_roots_at_the_element_itself():
    """s_ele() 用 outerHTML 建快照，根节点就是元素自己。"""
    ele = _FakeElement(FRAGMENT)
    assert ele.s_ele().tag == 'div'
    assert ele.s_ele().attr('id') == 'c1'


def test_element_s_ele_searches_descendants():
    ele = _FakeElement(FRAGMENT)
    assert ele.s_ele('tag:a').text == '标题一'
    assert ele.s_ele('tag:p').text == '摘要'
    assert isinstance(ele.s_ele('#nope'), NoneElement)


def test_element_s_ele_result_can_climb_back_to_the_element():
    """根是元素自身，所以结果上的 parent() 能回到它，不会断在半路。"""
    ele = _FakeElement(FRAGMENT)
    assert ele.s_ele('tag:a').parent('.card').attr('id') == 'c1'


def test_element_s_eles():
    ele = _FakeElement('<ul class="tags"><li>a</li><li>b</li></ul>')
    assert [e.text for e in ele.s_eles('tag:li')] == ['a', 'b']
    assert ele.s_eles('#nope') == []


def test_none_element_has_the_whole_chain():
    """定位失败后继续链式调用必须安全，且与成功路径的方法集一致。"""
    none = NoneElement()
    for name in ('ele', 'eles', 's_ele', 's_eles', 'child', 'children',
                 'parent', 'next', 'prev'):
        assert hasattr(none, name), name
    assert none.s_eles('x') == []
    assert isinstance(none.s_ele('x'), NoneElement)


def test_static_and_live_elements_expose_the_same_navigation_api():
    """StaticElement 不能比 FirefoxElement 少方法，否则链式写法换个入口就崩。"""
    expected = {'ele', 'eles', 's_ele', 's_eles',
                'child', 'children', 'parent', 'next', 'prev'}
    assert expected <= set(dir(StaticElement))
    assert expected <= set(dir(FirefoxElement))
    assert expected <= set(dir(NoneElement))
