# -*- coding: utf-8 -*-
"""最小示例：用 shadow_roots(mode="all") 处理 Copilot Cloudflare。"""

import random

from ruyipage import FirefoxOptions, FirefoxPage, Keys
from ruyipage._bidi.input_ import build_human_click_actions


BROWSER_PATH = r"D:\firefox\src\firefox\obj-release\dist\bin\firefox.exe"
QUESTION = "你好，今天天气怎么样？"

SHADOW_CLICK_SELECTORS = (
    'css:input[type="checkbox"]',
    'css:[role="checkbox"]',
    "css:label",
    "css:button",
    "css:[tabindex]",
)


def find_input_box(page: FirefoxPage):
    for _ in range(30):
        box = page.ele("css:textarea")
        if not box:
            box = page.ele('css:[contenteditable="true"]')
        if box:
            return box
        page.wait(1)
    return None


def human_bidi_click(ele) -> None:
    owner = ele._owner
    owner.scroll.to_see(ele, center=True)
    owner.wait(0.1)

    pos = ele._run_safe(
        """
        (el) => {
            const r = el.getBoundingClientRect();
            return {
                x: Math.round(r.left + r.width / 2),
                y: Math.round(r.top + r.height / 2)
            };
        }
        """
    )
    if not pos:
        raise RuntimeError("无法获取元素点击坐标")

    viewport = owner.run_js(
        """
        return {
            w: Math.round(window.innerWidth || document.documentElement.clientWidth || 0),
            h: Math.round(window.innerHeight || document.documentElement.clientHeight || 0)
        };
        """
    ) or {}
    max_x = max(1, int(viewport.get("w") or pos["x"] + 40) - 1)
    max_y = max(1, int(viewport.get("h") or pos["y"] + 40) - 1)
    x = max(1, min(int(pos["x"]), max_x))
    y = max(1, min(int(pos["y"]), max_y))

    start_x = random.randint(min(x + 10, max_x), max(min(x + 40, max_x), 1))
    start_y = random.randint(max(1, min(y - 10, max_y)), max(1, min(y + 10, max_y)))
    actions = build_human_click_actions(
        x,
        y,
        sx=start_x,
        sy=start_y,
        min_x=1,
        max_x=max_x,
        min_y=1,
        max_y=max_y,
    )
    owner._driver._browser_driver.run(
        "input.performActions",
        {"context": owner._context_id, "actions": actions},
    )


def click_cloudflare_shadow(page: FirefoxPage) -> bool:
    roots = page.shadow_roots(mode="all")
    print(f"shadow roots: {len(roots)}")

    for root in roots:
        for selector in SHADOW_CLICK_SELECTORS:
            target = root.ele(selector, timeout=0.2)
            if not target:
                continue
            if getattr(target, "tag", "") == "iframe":
                continue
            print(f"click {selector}: {target}")
            human_bidi_click(target)
            return True
    return False


opts = FirefoxOptions()
opts.enable_marionette(False)
opts.set_browser_path(BROWSER_PATH)

page = FirefoxPage(opts)
try:
    page.get("https://copilot.microsoft.com/", wait="none")
    page.wait(5)

    box = find_input_box(page)
    if box:
        box.click()
        box.input(QUESTION, clear=True)
        page.wait(0.8)
        page.actions.press(Keys.ENTER).perform()
        page.wait(15)

    if click_cloudflare_shadow(page):
        print("shadow_roots click sent")
        page.wait(20)
    else:
        print("no clickable target found in shadow roots")

finally:
    page.quit()
