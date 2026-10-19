# -*- coding: utf-8 -*-
"""Browser regressions for picker persistence across native navigation."""

import time

import pytest

from ruyipage import launch
from ruyipage._bidi import browsing_context, script
from ruyipage._functions.bidi_values import parse_value
from ruyipage._pages.firefox_base import FirefoxBase


pytestmark = [pytest.mark.browser, pytest.mark.feature]

PANEL_ID = "__ruyi_xpath_picker_panel__"


@pytest.fixture
def picker_page(test_browser_path, temp_user_dir):
    page = launch(
        headless=True,
        xpath_picker=True,
        browser_path=test_browser_path,
        user_dir=temp_user_dir,
    )
    try:
        yield page
    finally:
        page.quit()


def _evaluate(page, context_id, expression):
    result = script.evaluate(
        page.browser.driver,
        context_id,
        expression,
        result_ownership="none",
    )
    assert result.get("type") != "exception", result
    return parse_value(result.get("result", {}))


def _wait_for(page, context_id, expression, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = _evaluate(page, context_id, expression)
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("Picker condition was not met: {}".format(expression))


def _assert_picker(page, context_id):
    _wait_for(
        page,
        context_id,
        "document.querySelectorAll('#{}').length === 1".format(PANEL_ID),
    )
    assert _evaluate(
        page,
        context_id,
        "(() => { const panel = document.getElementById('%s'); "
        "const rect = panel.getBoundingClientRect(); "
        "return rect.width > 0 && rect.height > 0 "
        "&& getComputedStyle(panel).position === 'fixed'; })()" % PANEL_ID,
    )


def test_picker_survives_native_navigation_and_new_context(picker_page, server):
    page = picker_page
    driver = page.browser.driver

    # These commands bypass page.get()/new_tab() and their explicit reinjection.
    browsing_context.navigate(driver, page.tab_id, server.get_url("/nav/basic"))
    _assert_picker(page, page.tab_id)
    browsing_context.navigate(driver, page.tab_id, server.get_url("/nav/history"))
    _assert_picker(page, page.tab_id)

    context_id = browsing_context.create(driver, background=True)["context"]
    try:
        _assert_picker(page, context_id)
        browsing_context.navigate(driver, context_id, server.get_url("/nav/basic"))
        _assert_picker(page, context_id)
        browsing_context.navigate(driver, context_id, server.get_url("/nav/history"))
        _assert_picker(page, context_id)
    finally:
        browsing_context.close(driver, context_id)


def test_picker_handles_same_origin_frames_and_repeated_injection(picker_page, server):
    page = picker_page
    browsing_context.navigate(
        page.browser.driver, page.tab_id, server.get_url("/nav/basic")
    )
    _assert_picker(page, page.tab_id)
    _evaluate(
        page,
        page.tab_id,
        "(() => { const frame = document.createElement('iframe'); "
        "frame.id = 'picker-frame'; frame.src = '/nav/history'; "
        "document.body.appendChild(frame); })()",
    )
    _wait_for(
        page,
        page.tab_id,
        "(() => { const child = document.getElementById('picker-frame').contentWindow; "
        "return child.document.querySelector('#nav-history') "
        "&& child.__ruyiXPathPickerLocal__?.handlersBound "
        "&& !!child.document.getElementById('__ruyi_xpath_picker_highlight__'); })()",
    )
    assert _evaluate(
        page,
        page.tab_id,
        "document.getElementById('picker-frame').contentDocument"
        ".querySelectorAll('#{}').length".format(PANEL_ID),
    ) == 0

    picker_source = FirefoxBase._get_xpath_picker_script()
    for _ in range(3):
        _evaluate(page, page.tab_id, "({})()".format(picker_source))
    assert _evaluate(
        page,
        page.tab_id,
        "['__ruyi_xpath_picker_panel__', '__ruyi_xpath_picker_style__', "
        "'__ruyi_xpath_picker_highlight__'].map(id => "
        "document.querySelectorAll('#' + id).length)",
    ) == [1, 1, 1]


def test_picker_preload_waits_for_document_root(picker_page, server):
    page = picker_page
    driver = page.browser.driver
    # Isolate the preload path: navigation callbacks must not mask a failure at
    # document start by reinjecting after the DOM has already been parsed.
    for event in (
        "browsingContext.contextCreated",
        "browsingContext.load",
        "browsingContext.domContentLoaded",
    ):
        for immediate in (False, True):
            driver.remove_callback(event, immediate=immediate)
    script.remove_preload_script(
        driver, page.browser._xpath_picker_global_preload_script_id
    )
    source = FirefoxBase._get_xpath_picker_script()
    script.add_preload_script(
        driver,
        """() => {
            window.__pickerPreloadProbe = {
                hadDocumentRoot: !!document.documentElement,
                error: null,
            };
            try {
                (%s)();
            } catch (error) {
                window.__pickerPreloadProbe.error = String(error);
            }
        }""" % source,
    )

    browsing_context.navigate(driver, page.tab_id, server.get_url("/nav/basic"))
    probe = _evaluate(page, page.tab_id, "window.__pickerPreloadProbe")
    assert probe["hadDocumentRoot"] is False, probe
    assert probe["error"] is None, probe
    _assert_picker(page, page.tab_id)


def test_enabling_picker_updates_existing_tabs(
    test_browser_path, temp_user_dir, server
):
    page = launch(
        headless=True,
        xpath_picker=False,
        browser_path=test_browser_path,
        user_dir=temp_user_dir,
    )
    try:
        driver = page.browser.driver
        browsing_context.navigate(driver, page.tab_id, server.get_url("/nav/basic"))
        context_id = browsing_context.create(driver, background=True)["context"]
        browsing_context.navigate(driver, context_id, server.get_url("/nav/history"))
        for tab_id in (page.tab_id, context_id):
            assert _evaluate(
                page, tab_id, "document.getElementById('{}') === null".format(PANEL_ID)
            )

        page.browser.options.enable_xpath_picker(True)
        page._maybe_enable_xpath_picker()

        _assert_picker(page, page.tab_id)
        _assert_picker(page, context_id)
    finally:
        page.quit()
