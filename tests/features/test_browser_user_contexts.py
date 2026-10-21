# -*- coding: utf-8 -*-

import pytest


@pytest.mark.feature
@pytest.mark.parametrize("separate_settings_tab", [False, True])
def test_user_context_queries_with_settings_open(page, separate_settings_tab):
    """Browser-wide queries keep working while the settings page is open."""
    before = page.browser_tools.get_user_contexts()
    before_ids = {item["userContext"] for item in before}
    user_context = page.browser_tools.create_user_context()
    try:
        settings = page.new_tab() if separate_settings_tab else page
        settings.get("about:preferences")
        assert settings.url == "about:preferences"

        # Include a container without tabs: the result must enumerate browser
        # resources, rather than infer containers from the open tab tree.
        expected_ids = before_ids | {user_context}
        owners = (page, settings) if separate_settings_tab else (page,)
        for owner in owners:
            for method in ("get_user_contexts", "get_user_context"):
                contexts = getattr(owner.browser_tools, method)()
                assert {item["userContext"] for item in contexts} == expected_ids
    finally:
        page.browser_tools.remove_user_context(user_context)

    for method in ("get_user_contexts", "get_user_context"):
        contexts = getattr(page.browser_tools, method)()
        assert {item["userContext"] for item in contexts} == before_ids
