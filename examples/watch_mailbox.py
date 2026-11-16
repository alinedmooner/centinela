"""Demo bot: watches a mailbox over IMAP and checks every new email with Centinela.

- It only reads the emails that arrive after it starts.
- With --only-from, only the ones from that address: the server does the filtering, so the bot
  does not even open the other emails in the mailbox.
- It works without an AI key, using the rules alone.
- Without --move it changes nothing in the mailbox (it opens it read-only). With --move, the
  suspicious emails go to the Centinela-Quarantine folder.
- The notices and the review cards come out in English; with --lang es, in Spanish.

Credentials in .env (with Gmail, an app password, not the regular password):

    MAILBOX_USER=bot-mailbox@...
    MAILBOX_PASSWORD=...

Usage::

    uv run python examples/watch_mailbox.py --only-from test-account@...
    uv run python examples/watch_mailbox.py --only-from test-account@... --move
"""

from __future__ import annotations

import argparse
import imaplib
import os
import re
import ssl
import sys
import time

from centinela import (
    LEAD_LABELS,
    Guard,
    RulesDetector,
    Verdict,
    create_card,
    render_card,
)
from centinela._env import load_env
from centinela.catalog import DEFAULT_LANG, LANGS
from centinela.mail import Mail, read_mail, text_to_check

IMAP = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "zoho.com": "imap.zoho.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
}
QUARANTINE = "Centinela-Quarantine"
LINE = "─" * 72


def quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def server(user: str, value: str | None = None) -> str:
    host = value or IMAP.get(user.rsplit("@", 1)[-1].lower())
    if not host:
        raise ValueError("Unknown IMAP server for that account: set MAILBOX_IMAP=host in .env.")
    return host


def process(raw: bytes, guard: Guard) -> tuple[Mail, Verdict, str | None]:
    """Check an email. If it goes to review, also return the card for the person who reviews it."""
    mail = read_mail(raw)
    text = text_to_check(mail)
    verdict = guard.check(text)
    card = None
    if verdict.decision == "review":
        card = render_card(create_card(text, verdict, hidden_links=mail.links))
    return mail, verdict, card


def show(folder: str, mail: Mail, verdict: Verdict, card: str | None) -> None:
    print(LINE)
    print(f"New email in {folder}")
    print(f"From: {mail.sender}")
    print(f"Subject: {mail.subject}")
    if mail.hidden_fragments:
        print(f"It has {mail.hidden_fragments} fragment(s) of hidden text in the HTML.")
    if verdict.decision == "allow":
        print("Decision: allow. The assistant can read it.")
    else:
        print("Decision: review. It goes to the review room; the assistant does not read it.\n")
        print(card)
    sys.stdout.flush()


def spam_folder(imap: imaplib.IMAP4) -> str | None:
    """The spam folder, found by its \\Junk attribute (its name changes with the language)."""
    _, rows = imap.list()
    for row in rows or []:
        if not isinstance(row, bytes):
            continue
        m = re.match(
            r'\((?P<attrs>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', row.decode("utf-8", "replace")
        )
        if m and "\\Junk" in m.group("attrs"):
            name = m.group("name").strip()
            return name[1:-1] if name.startswith('"') else name
    return None


def next_uid(imap: imaplib.IMAP4, folder: str) -> int:
    _, data = imap.status(quote(folder), "(UIDNEXT)")
    m = re.search(rb"UIDNEXT (\d+)", data[0] or b"")
    return int(m.group(1)) if m else 1


def move(imap: imaplib.IMAP4, uid: bytes) -> None:
    if "MOVE" in imap.capabilities:
        imap.uid("MOVE", uid, quote(QUARANTINE))
        return
    imap.uid("COPY", uid, quote(QUARANTINE))
    imap.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
    if "UIDPLUS" in imap.capabilities:  # deletes only this email, never others already marked
        imap.uid("EXPUNGE", uid)


def connect(user: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(
        server(user, os.environ.get("MAILBOX_IMAP")),
        993,
        ssl_context=ssl.create_default_context(),
    )
    imap.login(user, os.environ["MAILBOX_PASSWORD"])
    return imap


def watch(args: argparse.Namespace, guard: Guard) -> None:
    user = os.environ["MAILBOX_USER"]
    imap = connect(user)
    folders = ["INBOX"]
    spam = spam_folder(imap)
    if spam:
        folders.append(spam)
    if args.move:
        imap.create(quote(QUARANTINE))  # if it already exists, the server answers NO: harmless
    last = {c: next_uid(imap, c) - 1 for c in folders}
    filter_note = f", only emails from {args.only_from}" if args.only_from else ""
    print(f"Watching {' and '.join(folders)} for {user}{filter_note}. Press Ctrl+C to exit.")

    while True:
        try:
            for folder in folders:
                imap.select(quote(folder), readonly=not args.move)
                criteria = ["UID", f"{last[folder] + 1}:*"]
                if args.only_from:
                    criteria += ["FROM", quote(args.only_from)]
                _, data = imap.uid("SEARCH", *criteria)
                for uid in (data[0] or b"").split():
                    if int(uid) <= last[folder]:
                        continue
                    _, parts = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                    raw = next(p[1] for p in parts if isinstance(p, tuple))
                    mail, verdict, card = process(raw, guard)
                    show(folder, mail, verdict, card)
                    if card and args.move:
                        move(imap, uid)
                        print(f"\n→ Moved to the {QUARANTINE} folder.")
                    last[folder] = max(last[folder], int(uid))
            time.sleep(args.each)
        except (imaplib.IMAP4.abort, OSError):
            print("Lost the connection to the server; reconnecting in 5 seconds.", file=sys.stderr)
            time.sleep(5)
            imap = connect(user)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only-from", help="check only the emails that come from this address")
    parser.add_argument(
        "--move", action="store_true", help="move the suspicious emails to the quarantine folder"
    )
    parser.add_argument("--each", type=float, default=5, help="seconds between checks")
    parser.add_argument("--claude", action="store_true", help="add Claude as a reviewer")
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument(
        "--lang",
        choices=LANGS,
        default=DEFAULT_LANG,
        help="language of the notices and the review cards",
    )
    args = parser.parse_args(argv)

    load_env()
    missing = [v for v in ("MAILBOX_USER", "MAILBOX_PASSWORD") if not os.environ.get(v)]
    if missing:
        print("Missing from .env: " + ", ".join(missing), file=sys.stderr)
        return 1
    detectors = [RulesDetector(labels=LEAD_LABELS)]
    if args.claude:
        from centinela import LLMDetector
        from centinela.providers.anthropic import AnthropicProvider

        detectors.append(LLMDetector(AnthropicProvider(args.model)))
    try:
        watch(args, Guard(detectors, lang=args.lang))
    except imaplib.IMAP4.error as error:
        print(
            f"The IMAP server answered: {error}. With Gmail you need an app password and IMAP "
            "turned on.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
