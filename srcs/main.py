import base64
import json
import random
import secrets
import sqlite3
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from DrissionPage import ChromiumOptions, ChromiumPage
from jwt import JWT
from names_generator import generate_name
from oauth import (
    build_authorization_url,
    exchange_authorization_code,
    generate_pkce_pair,
)
from payload_server import OTPS, run_payload_http_server

BASE_URL = "https://chatgpt.com"
HEADLESS = False

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "creds.db"
PROXIES_FILE = ROOT_DIR / "proxies.txt"
NUM_THREADS = 1


def init_db() -> None:
    """Create SQLite database and creds table if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS creds (
                proxy TEXT,
                email TEXT,
                password TEXT
            )
            """
        )
        conn.commit()


def read_random_proxy() -> str:
    """Read first non-empty proxy line from proxies.txt."""
    if not PROXIES_FILE.exists():
        return ""
    proxies = PROXIES_FILE.read_text(encoding="utf-8").splitlines()
    n = len(proxies)
    return proxies[random.randint(0, n - 1)]


def save_cred(proxy: str, email: str, password: str) -> None:
    """Insert one credential row into creds table."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO creds (proxy, email, password) VALUES (?, ?, ?)",
            (proxy, email, password),
        )
        conn.commit()


def parse_proxy(proxy: str):
    """
    Parse proxy string in format: host:port:username:password
    """
    parts = proxy.split(":")
    host, port = parts
    return host, port


def get_proxy() -> str:
    return read_random_proxy()


def reg(email: str, password: str):
    proxy = get_proxy()

    opts = ChromiumOptions()
    if HEADLESS:
        opts.set_argument("--headless")
        opts.headless()

    opts.auto_port()

    parsed = parse_proxy(proxy)
    if parsed:
        host, port = parsed
        opts.set_proxy(f"http://{host}:{port}")

    page = ChromiumPage(addr_or_opts=opts)
    try:
        page.get(BASE_URL)
        page.wait.doc_loaded()
        time.sleep(3)

        page.wait.ele_displayed("@data-testid=signup-button")
        page.ele("@data-testid=signup-button").click()

        while True:
            try:
                page.wait.ele_displayed("#email", timeout=1)
                break
            except:
                page.ele("@data-testid=signup-button").click()
                continue
        page.ele("#email").input(email)
        page.ele(
            ".btn relative group-focus-within/dialog:focus-visible:[outline-width:1.5px] group-focus-within/dialog:focus-visible:[outline-offset:2.5px] group-focus-within/dialog:focus-visible:[outline-style:solid] group-focus-within/dialog:focus-visible:[outline-color:var(--text-primary)] btn-primary mt-1.5 h-13 w-full rounded-full text-base"
        ).click()
        page.wait.ele_displayed("#_r_4_-new-password")
        page.ele("#_r_4_-new-password").input(password)
        page.ele("@data-dd-action-name=Continue").click()

        otp = None
        timeout = 30
        count = 0
        while True:
            count += 1
            if count > timeout:
                raise TimeoutError()
            time.sleep(1)
            if email in OTPS:
                otp = OTPS[email]
                break

        page.wait.ele_displayed("@autocomplete=one-time-code")
        page.ele("@autocomplete=one-time-code").input(otp)
        page.ele("@data-dd-action-name=Continue").click()

        page.wait.doc_loaded()
        page.wait.ele_displayed("@placeholder=Full name")
        name_input = page.ele("@placeholder=Full name")
        name_input.click()
        name_input.input(" ".join(email.split("@")[0].split("_")))

        year = random.randint(1980, 2000)
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        birthday_fs = page.ele("tag:fieldset")
        selects = birthday_fs.eles("tag:select", timeout=0.5)

        if len(selects) >= 3:
            page.run_js(
                """
                const month = String(arguments[0]);
                const day = String(arguments[1]);
                const year = String(arguments[2]);

                const fieldset = document.querySelector('fieldset');
                if (!fieldset) return;

                const sels = fieldset.querySelectorAll('select');
                if (sels.length < 3) return;

                sels[0].value = month;
                sels[0].dispatchEvent(new Event('change', { bubbles: true }));

                sels[1].value = day;
                sels[1].dispatchEvent(new Event('change', { bubbles: true }));

                sels[2].value = year;
                sels[2].dispatchEvent(new Event('change', { bubbles: true }));
                """,
                month,
                day,
                year,
            )
        else:
            page.run_js(
                """
                const month = String(arguments[0]);
                const day = String(arguments[1]);
                const year = String(arguments[2]);

                const root = document.querySelector('.react-aria-DateField');
                if (!root) return;

                const setSegment = (type, value) => {
                    const el = root.querySelector(`div[role="spinbutton"][data-type="${type}"]`);
                    if (!el) return;

                    el.focus();

                    const sel = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    sel.removeAllRanges();
                    sel.addRange(range);

                    document.execCommand('delete', false, null);

                    for (const ch of value) {
                        el.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true }));
                        document.execCommand('insertText', false, ch);
                        el.dispatchEvent(
                            new InputEvent('input', { bubbles: true, data: ch, inputType: 'insertText' })
                        );
                        el.dispatchEvent(new KeyboardEvent('keyup', { key: ch, bubbles: true }));
                    }

                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                };

                setSegment('month', month);
                setSegment('day', day);
                setSegment('year', year);

                const hidden = root.querySelector('input[name="birthday"]');
                if (hidden) {
                    const normalized = `${year.padStart(4, '0')}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                    if (setter) {
                        setter.call(hidden, normalized);
                    } else {
                        hidden.value = normalized;
                    }
                    hidden.dispatchEvent(new Event('input', { bubbles: true }));
                    hidden.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                month,
                day,
                year,
            )
            page.ele("@data-type=month").input(month)
            page.ele("@data-type=day").input(day)
            page.ele("@data-type=year").input(year)

        finish_btn = page.ele("@data-dd-action-name=Continue")
        finish_btn.click()
        page.wait.doc_loaded()
        save_cred(proxy, email, password)
        code_verifier, code_challenge = generate_pkce_pair()
        state_token = secrets.token_urlsafe(16)
        auth_url = build_authorization_url(
            state=state_token,
            code_challenge=code_challenge,
        )
        time.sleep(5)
        page.wait.doc_loaded()
        page.get(auth_url)
        page.wait.ele_displayed("@for=_r_1_-email")
        page.ele("@for=_r_1_-email").input(email)
        page.ele("@data-dd-action-name=Continue").click()
        time.sleep(3)
        page.wait.doc_loaded()
        page.wait.ele_displayed("@autocomplete=current-password webauthn")
        page.ele("@autocomplete=current-password webauthn").input(password)
        page.ele("@data-dd-action-name=Continue").click()
        time.sleep(5)
        page.wait.doc_loaded()
        page.ele("@data-dd-action-name=Continue").click()
        time.sleep(3)
        callback_url = page.url
        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)

        error = params.get("error", [None])[0]
        code = params.get("code", [None])[0]

        if error:
            raise Exception(error)
        if not code:
            raise Exception("No code received")
        token = exchange_authorization_code(code=code, code_verifier=code_verifier)
        token_data = token.__dict__
        token_data["last_refresh"] = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        token_data["type"] = "codex"
        # jwt_claims = json.loads(base64.b64decode(token.access_token.split(".")[1]))
        jwt_claims = JWT().decode(
            token.access_token, do_verify=False, do_time_check=False
        )
        exp = jwt_claims["exp"]
        token_data["expired"] = (
            datetime.fromtimestamp(exp, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        token_data["email"] = email
        token_data["disabled"] = False
        token_data["account_id"] = jwt_claims["https://api.openai.com/auth"][
            "chatgpt_account_id"
        ]

        print(token_data)
        with open(f"out/{email}_codex.json", "w") as f:
            json.dump(token_data, f)
    finally:
        page.quit()


def gen_cred() -> tuple[str, str]:
    email = f"{generate_name()}@hwemite.lol"

    uppercase = random.choice(string.ascii_uppercase)
    required_special = "!"
    remaining_chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"

    # Ensure password length > 13 and includes at least one uppercase + "!"
    password_length = 16
    password_core = [uppercase, required_special]
    password_core.extend(random.choices(remaining_chars, k=password_length - 2))
    random.shuffle(password_core)
    password = "".join(password_core)

    return email, password


def main():
    init_db()
    threading.Thread(target=run_payload_http_server, daemon=True).start()

    def _reg_worker() -> None:
        email, password = gen_cred()
        try:
            reg(email, password)
        except Exception as exc:
            print(exc)

    while True:
        threads = []
        for _ in range(NUM_THREADS):
            t = threading.Thread(target=_reg_worker)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()


if __name__ == "__main__":
    threading.Thread()
    main()
