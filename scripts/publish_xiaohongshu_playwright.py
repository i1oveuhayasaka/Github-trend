#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path


PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
VIEWPORT = {"width": 1440, "height": 900}
SUCCESS_TEXT = re.compile(r"发布成功|提交成功|发布中|审核|已发布")
LONG_ARTICLE_TEXT = re.compile(r"^\s*(发长文|写长文|长文)\s*$")
PUBLISH_BUTTON_TEXT = re.compile(r"^\s*(发布|立即发布|确认发布|确定发布)\s*$")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_draft_text(text: str) -> tuple[str, str]:
    text = text.strip()
    if not text:
        return "每日资讯", ""

    lines = text.splitlines()
    title = (lines[0] if lines else "每日资讯").strip()[:20] or "每日资讯"
    body = "\n".join(lines[1:]).strip()
    return title, body or text


def _parse_draft(path: Path) -> tuple[str, str]:
    return _parse_draft_text(path.read_text(encoding="utf-8"))


def _wait_for_login(page, timeout_ms: int) -> None:
    page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if "login" not in page.url.lower():
            return
        time.sleep(2)
    raise RuntimeError("login timeout: please run with --login and sign in manually")


def _launch_context(playwright, profile_dir: Path, headless: bool):
    no_sandbox = _env_flag("XHS_CHROMIUM_NO_SANDBOX", default=sys.platform.startswith("linux"))
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
    if no_sandbox:
        launch_args.append("--no-sandbox")

    kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "locale": "zh-CN",
        "viewport": VIEWPORT,
        "args": launch_args,
    }
    if no_sandbox:
        kwargs["chromium_sandbox"] = False
    return playwright.chromium.launch_persistent_context(**kwargs)


def _safe_click(locator, timeout_ms: int) -> None:
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.scroll_into_view_if_needed(timeout=timeout_ms)
    try:
        locator.click(timeout=10000)
    except Exception:
        locator.evaluate(
            """
            element => {
              const target = element.closest('button, [role="button"], a, .creator-tab, .d-button')
                || element;
              target.click();
            }
            """
        )


def _try_click(locator, timeout_ms: int = 3000) -> bool:
    try:
        _safe_click(locator.first, timeout_ms)
        return True
    except Exception:
        return False


def _fill_locator(page, locator, value: str, timeout_ms: int) -> None:
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.scroll_into_view_if_needed(timeout=timeout_ms)
    try:
        locator.fill(value, timeout=timeout_ms)
        return
    except Exception:
        pass

    locator.click(timeout=timeout_ms)
    modifier = "Meta" if sys.platform == "darwin" else "Control"
    try:
        page.keyboard.press(f"{modifier}+A")
        page.keyboard.press("Backspace")
    except Exception:
        pass
    page.keyboard.insert_text(value)


def _fill_first(page, locators: list, value: str, timeout_ms: int, description: str) -> None:
    for locator in locators:
        try:
            _fill_locator(page, locator.first, value, min(timeout_ms, 8000))
            return
        except Exception:
            continue
    raise RuntimeError(f"{description} input not found")


def _largest_contenteditable(page):
    page.evaluate(
        """
        () => {
          document
            .querySelectorAll('[data-xhs-auto-body]')
            .forEach((node) => node.removeAttribute('data-xhs-auto-body'));
          const candidates = Array.from(document.querySelectorAll('[contenteditable="true"]'))
            .filter((node) => {
              const rect = node.getBoundingClientRect();
              const style = window.getComputedStyle(node);
              return rect.width >= 240
                && rect.height >= 60
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && !node.closest('[aria-hidden="true"]');
            })
            .sort((a, b) => {
              const ar = a.getBoundingClientRect();
              const br = b.getBoundingClientRect();
              return (br.width * br.height) - (ar.width * ar.height);
            });
          if (candidates[0]) {
            candidates[0].setAttribute('data-xhs-auto-body', '1');
          }
        }
        """
    )
    return page.locator("[data-xhs-auto-body='1']")


def _open_publish_page(page, timeout_ms: int) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(2000)


def _editor_is_open(page) -> bool:
    locators = [
        page.get_by_placeholder(re.compile(r"标题|输入标题|填写标题|请输入标题")),
        page.locator("textarea[placeholder*='标题'], input[placeholder*='标题']"),
        page.locator(".ProseMirror[contenteditable='true'], .ql-editor[contenteditable='true']"),
    ]
    for locator in locators:
        try:
            locator.first.wait_for(state="visible", timeout=1000)
            return True
        except Exception:
            continue
    return False


def _open_new_long_article_editor(page, timeout_ms: int) -> None:
    if _editor_is_open(page):
        return

    new_article_entries = [
        page.get_by_role("button", name=re.compile(r"新的创作|新建长文|开始创作")),
        page.get_by_text(re.compile(r"^\s*(新的创作|新建长文|开始创作)\s*$")),
        page.locator("button:has-text('新的创作'), [role='button']:has-text('新的创作')"),
    ]
    for entry in new_article_entries:
        if _try_click(entry, min(timeout_ms, 10000)):
            page.wait_for_timeout(3000)
            if _editor_is_open(page):
                return

    raise RuntimeError("new long article editor not found")


def _select_long_article_mode(page, timeout_ms: int) -> None:
    if _try_click(page.get_by_text(LONG_ARTICLE_TEXT), 5000):
        page.wait_for_timeout(1500)
        _open_new_long_article_editor(page, timeout_ms)
        return

    publish_entries = [
        page.get_by_role("button", name=re.compile(r"发布笔记|发布内容|去发布|立即发布")),
        page.get_by_role("link", name=re.compile(r"发布笔记|发布内容|去发布|立即发布")),
        page.get_by_text(re.compile(r"^\s*(发布笔记|发布内容|去发布|立即发布|上传图文|图文发布)\s*$")),
    ]
    for entry in publish_entries:
        if _try_click(entry, 3000):
            page.wait_for_timeout(1200)
            break

    long_article_entries = [
        page.get_by_role("button", name=re.compile(r"发长文|写长文|长文")),
        page.get_by_role("tab", name=re.compile(r"发长文|写长文|长文")),
        page.get_by_role("link", name=re.compile(r"发长文|写长文|长文")),
        page.get_by_text(LONG_ARTICLE_TEXT),
        page.locator("button:has-text('发长文'), [role='button']:has-text('发长文')"),
        page.locator("button:has-text('写长文'), [role='button']:has-text('写长文')"),
    ]
    for entry in long_article_entries:
        if _try_click(entry, min(timeout_ms, 10000)):
            page.wait_for_timeout(1500)
            _open_new_long_article_editor(page, timeout_ms)
            return

    raise RuntimeError("long article entry not found on publish page")


def _fill_long_article(page, title: str, body: str, timeout_ms: int) -> None:
    title_locators = [
        page.get_by_placeholder(re.compile(r"标题|输入标题|填写标题|请输入标题")),
        page.locator("input[placeholder*='标题'], textarea[placeholder*='标题']"),
        page.locator("[contenteditable='true'][data-placeholder*='标题']"),
        page.locator("[contenteditable='true'][aria-label*='标题']"),
    ]
    _fill_first(page, title_locators, title, timeout_ms, "title")

    body_locators = [
        page.get_by_placeholder(re.compile(r"正文|内容|分享")),
        page.locator("textarea[placeholder*='正文'], textarea[placeholder*='内容'], textarea[placeholder*='分享']"),
        page.locator("[contenteditable='true'][data-placeholder*='正文']"),
        page.locator("[contenteditable='true'][data-placeholder*='内容']"),
        page.locator("[contenteditable='true'][aria-label*='正文']"),
        page.locator(".ProseMirror[contenteditable='true'], .ql-editor[contenteditable='true']"),
        _largest_contenteditable(page),
    ]
    _fill_first(page, body_locators, body, timeout_ms, "body")


def _prepare_long_article_for_publish(page, timeout_ms: int) -> None:
    if _try_click(page.get_by_text("一键排版", exact=True), 5000):
        next_button = page.locator(
            "button.custom-button.submit, .custom-button.submit, "
            "button:has-text('下一步'), [role='button']:has-text('下一步')"
        ).first
        next_button.wait_for(state="visible", timeout=timeout_ms)
        _safe_click(next_button, timeout_ms)

    final_markers = [
        page.get_by_text("公开可见", exact=False),
        page.get_by_text("笔记预览", exact=False),
        page.locator(".d-button:has-text('发布'), button:has-text('发布')"),
    ]
    for marker in final_markers:
        try:
            marker.first.wait_for(state="visible", timeout=min(timeout_ms, 90000))
            return
        except Exception:
            continue
    raise RuntimeError("final publish page not ready")


def _click_publish(page, timeout_ms: int) -> None:
    custom_publish = page.locator("xhs-publish-btn[submit-text='发布'][submit-disabled='false']").first
    if custom_publish.count() > 0:
        custom_publish.wait_for(state="visible", timeout=timeout_ms)
        for attempt in range(2):
            custom_publish.evaluate(
                """
                async element => {
                  if (typeof element._onPublish === 'function') {
                    const result = element._onPublish();
                    if (result && typeof result.then === 'function') {
                      await result;
                    }
                    return;
                  }
                  element.click();
                }
                """
            )
            page.wait_for_timeout(3000)
            _try_click(page.get_by_role("button", name=re.compile(r"确认发布|确定发布|仍要发布")), 3000)
            try:
                page.wait_for_function(
                    "() => !document.body.innerText.includes('笔记图片生成中')",
                    timeout=min(timeout_ms, 120000),
                )
            except Exception:
                pass
            body_text = page.locator("body").inner_text(timeout=5000)
            if "公开可见" not in body_text or "笔记预览" not in body_text:
                return
            if attempt == 0:
                page.wait_for_timeout(2000)
                custom_publish = page.locator(
                    "xhs-publish-btn[submit-text='发布'][submit-disabled='false']"
                ).first
                custom_publish.wait_for(state="visible", timeout=timeout_ms)
                continue
        return

    publish_locators = [
        page.get_by_role("button", name=PUBLISH_BUTTON_TEXT),
        page.get_by_text("发布", exact=True),
        page.locator("button:has-text('发布'), [role='button']:has-text('发布')"),
        page.locator(".d-button:has-text('发布')"),
    ]
    for locator in publish_locators:
        count = locator.count()
        for index in range(count):
            button = locator.nth(index)
            try:
                text = button.inner_text(timeout=1000).strip()
                if any(skip in text for skip in ("发布笔记", "发布内容", "去发布", "上传图文")):
                    continue
                if button.is_visible(timeout=1000) and button.is_enabled(timeout=1000):
                    _safe_click(button, timeout_ms)
                    page.wait_for_timeout(1500)
                    _try_click(page.get_by_role("button", name=re.compile(r"确认发布|确定发布|仍要发布")), 3000)
                    return
            except Exception:
                continue

    final_page_text = page.locator("body").inner_text(timeout=5000)
    if "公开可见" in final_page_text and "笔记预览" in final_page_text:
        page.mouse.click(750, 855)
        page.wait_for_timeout(1500)
        _try_click(page.get_by_role("button", name=re.compile(r"确认发布|确定发布|仍要发布")), 3000)
        return

    raise RuntimeError("publish button not found or disabled")


def _wait_for_publish_result(page) -> None:
    try:
        page.get_by_text(SUCCESS_TEXT).first.wait_for(state="visible", timeout=15000)
    except Exception:
        pass


def login(profile_dir: Path, headless: bool, timeout_ms: int) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _open_publish_page(page, timeout_ms)
            print("请在打开的浏览器中登录小红书创作者中心，完成后回到终端按 Enter。")
            input()
            _wait_for_login(page, timeout_ms)
            print("登录状态已保存。")
        finally:
            context.close()


def publish(profile_dir: Path, draft_path: Path, headless: bool, timeout_ms: int) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    title, body = _parse_draft(draft_path)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headless)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _wait_for_login(page, timeout_ms)
            _open_publish_page(page, timeout_ms)
            _select_long_article_mode(page, timeout_ms)
            _fill_long_article(page, title, body, timeout_ms)
            _prepare_long_article_for_publish(page, timeout_ms)
            _click_publish(page, timeout_ms)
            _wait_for_publish_result(page)
            print("published")
        finally:
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Xiaohongshu note via creator center.")
    parser.add_argument("draft_path", nargs="?", help="Path to xiaohongshu draft markdown.")
    parser.add_argument("--login", action="store_true", help="Open browser and save login state.")
    parser.add_argument(
        "--profile-dir",
        default=os.environ.get("XHS_BROWSER_PROFILE_DIR", "data/xhs-browser-profile"),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.environ.get("XHS_BROWSER_HEADLESS", "0") == "1",
    )
    parser.add_argument("--timeout-ms", type=int, default=120000)
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir)
    try:
        if args.login:
            login(profile_dir, headless=False, timeout_ms=args.timeout_ms)
            return 0
        draft_path = Path(args.draft_path or os.environ.get("XHS_DRAFT_PATH", ""))
        if not draft_path.exists():
            raise RuntimeError(f"draft not found: {draft_path}")
        publish(profile_dir, draft_path, headless=args.headless, timeout_ms=args.timeout_ms)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
