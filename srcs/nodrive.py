import asyncio

import nodriver as uc
import time


async def main():
    browser = await uc.start(headless=True, lang="en-US", no_sandbox=True)
    tab = await browser.get("https://chatgpt.com")
    await tab.select('body')
    # take a screenshot every 1 sec for 10 sec
    count = 0
    for i in range(10):
        if count == 3:
            await tab.verify_cf(flash=True)
        await tab.save_screenshot(f"screenshot_{i}.png")
        await asyncio.sleep(1)


if __name__ == "__main__":
    uc.loop().run_until_complete(main())