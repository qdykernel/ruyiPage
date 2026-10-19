"""Fast regressions for picker recovery after browser context events."""

import threading
from types import SimpleNamespace

import pytest

from ruyipage._base import browser as browser_module
from ruyipage._base.browser import Firefox
from ruyipage._base.driver import ContextDriver
from ruyipage._pages.firefox_base import FirefoxBase


pytestmark = pytest.mark.fast


@pytest.fixture
def picker_browser(monkeypatch):
    browser = object.__new__(Firefox)
    browser._options = SimpleNamespace(xpath_picker_enabled=True)
    browser._driver = object()
    browser._context_ids = []
    browser._context_ids_lock = threading.Lock()
    browser._contexts = {}
    # Keep the old bookkeeping available so regressions fail on behavior,
    # rather than on missing fixture fields when run against the old code.
    browser._xpath_picker_last_reinject = {}

    def unexpected_tab_creation(*args, **kwargs):
        raise AssertionError("Picker recovery must not initialize a cached tab")

    monkeypatch.setattr(browser, "_get_or_create_tab", unexpected_tab_creation)
    monkeypatch.setattr(browser_module.time, "time", lambda: 1234.0)
    return browser


@pytest.fixture
def injected_contexts(monkeypatch):
    contexts = []

    def reinject(page):
        contexts.append(page._context_id)

    monkeypatch.setattr(FirefoxBase, "_reinject_xpath_picker_if_needed", reinject)
    return contexts


def test_disabled_picker_does_not_inject_on_context_or_navigation(
    picker_browser, injected_contexts
):
    picker_browser._options.xpath_picker_enabled = False

    picker_browser._on_context_created({"context": "new-tab", "parent": None})
    picker_browser._on_navigation_event({"context": "new-tab"})

    assert injected_contexts == []
    assert picker_browser._context_ids == ["new-tab"]
    assert picker_browser._contexts == {}


@pytest.mark.parametrize("parent_fields", [{}, {"parent": None}])
def test_new_native_tab_recovers_picker_without_a_page_object(
    picker_browser, injected_contexts, parent_fields
):
    picker_browser._on_context_created({"context": "new-tab", **parent_fields})

    assert injected_contexts == ["new-tab"]
    assert picker_browser._context_ids == ["new-tab"]
    assert picker_browser._contexts == {}


def test_each_navigation_recovers_picker_even_in_the_same_instant(
    picker_browser, injected_contexts
):
    for navigation in ("first-document", "second-document", "second-document"):
        picker_browser._on_navigation_event(
            {"context": "native-tab", "navigation": navigation}
        )

    assert injected_contexts == ["native-tab"] * 3
    assert picker_browser._contexts == {}


def test_injection_failure_does_not_suppress_the_next_event(
    picker_browser, monkeypatch
):
    attempts = []

    def reinject(page):
        attempts.append(page._context_id)
        if len(attempts) == 1:
            raise RuntimeError("Document is not ready yet")

    monkeypatch.setattr(FirefoxBase, "_reinject_xpath_picker_if_needed", reinject)

    picker_browser._on_context_created({"context": "new-tab", "parent": None})
    picker_browser._on_navigation_event({"context": "new-tab"})

    assert attempts == ["new-tab", "new-tab"]
    assert picker_browser._contexts == {}


def test_iframe_context_is_not_registered_as_a_top_level_tab(
    picker_browser, injected_contexts
):
    picker_browser._context_ids.append("top-level")

    picker_browser._on_context_created(
        {"context": "child-frame", "parent": "top-level"}
    )

    assert picker_browser._context_ids == ["top-level"]
    assert injected_contexts == []
    assert picker_browser._contexts == {}


class _PickerDriver:
    def __init__(self):
        self.calls = []
        self.preload_results = [{"script": "picker-preload-1"}]
        self.contexts = [{"context": "current-tab"}]

    def run(self, method, params=None, **kwargs):
        self.calls.append((method, params))
        if method == "script.addPreloadScript":
            result = self.preload_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if method == "browsingContext.getTree":
            return {"contexts": self.contexts}
        raise AssertionError("Unexpected browser command: {}".format(method))


@pytest.fixture
def picker_page(picker_browser, monkeypatch):
    picker_browser._driver = _PickerDriver()
    picker_browser._session_id = "session-1"
    page = object.__new__(FirefoxBase)
    page._browser = picker_browser
    page._context_id = "current-tab"
    page._driver = ContextDriver(picker_browser._driver, page._context_id)
    monkeypatch.setattr(
        FirefoxBase, "_get_xpath_picker_script", staticmethod(lambda: "() => {}")
    )
    return page


def test_disabled_picker_does_not_register_preload(
    picker_page, picker_browser, injected_contexts
):
    picker_browser._options.xpath_picker_enabled = False

    picker_page._maybe_enable_xpath_picker()

    assert picker_browser._driver.calls == []
    assert injected_contexts == []


def test_picker_preload_is_global_without_context_restriction(
    picker_page, picker_browser, injected_contexts
):
    picker_page._maybe_enable_xpath_picker()

    assert picker_browser._driver.calls == [
        ("script.addPreloadScript", {"functionDeclaration": "() => {}"}),
        ("browsingContext.getTree", {"maxDepth": 0}),
    ]
    assert injected_contexts == ["current-tab"]
    assert picker_browser._xpath_picker_global_preload_script_id == "picker-preload-1"


def test_preload_registration_failure_still_injects_current_page(
    picker_page, picker_browser, injected_contexts
):
    picker_browser._driver.preload_results = [RuntimeError("Preload unavailable")]

    picker_page._maybe_enable_xpath_picker()

    assert injected_contexts == ["current-tab"]
    assert [method for method, _ in picker_browser._driver.calls] == [
        "script.addPreloadScript"
    ]


def test_enabling_picker_covers_existing_tabs_once_per_registration(
    picker_page, picker_browser, injected_contexts
):
    picker_browser._driver.contexts = [
        {"context": "older-tab"},
        {"context": "current-tab"},
        {"context": "another-tab"},
    ]

    picker_page._maybe_enable_xpath_picker()
    assert injected_contexts == ["current-tab", "older-tab", "another-tab"]

    picker_page._maybe_enable_xpath_picker()
    assert injected_contexts == [
        "current-tab", "older-tab", "another-tab", "current-tab"
    ]
    assert [method for method, _ in picker_browser._driver.calls] == [
        "script.addPreloadScript", "browsingContext.getTree"
    ]
    assert picker_browser._contexts == {}


def test_new_session_registers_picker_preload_again(
    picker_page, picker_browser, injected_contexts
):
    picker_browser._driver.preload_results.append({"script": "picker-preload-2"})
    picker_page._maybe_enable_xpath_picker()

    picker_browser._session_id = "session-2"
    picker_page._maybe_enable_xpath_picker()

    assert picker_browser._xpath_picker_global_preload_script_id == "picker-preload-2"
    assert picker_browser._xpath_picker_preload_session_id == "session-2"
    assert [method for method, _ in picker_browser._driver.calls] == [
        "script.addPreloadScript", "browsingContext.getTree",
        "script.addPreloadScript", "browsingContext.getTree",
    ]
    assert injected_contexts == ["current-tab", "current-tab"]
