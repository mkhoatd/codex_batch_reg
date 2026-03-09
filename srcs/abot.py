
from nodriver import *


async def main():
    browser = await start(headless=True)

    tab = await browser.get('https://deviceandbrowserinfo.com/are_you_a_bot')

    await tab.save_screenshot(full_page=True, filename='./bot.png')

if __name__ == "__main__":
    loop().run_until_complete(main())

