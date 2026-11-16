"""Demo with Composio: the Gmail mailbox of an AI agent, with Centinela in front.

Set in .env:

    COMPOSIO_API_KEY=...   # platform.composio.dev → Settings → API Keys
    COMPOSIO_USER_ID=...   # the User ID the Gmail account was connected with (see «accounts»)

Commands::

    uv run --group composio python examples/composio_mailbox.py connect
    uv run --group composio python examples/composio_mailbox.py accounts
    uv run --group composio python examples/composio_mailbox.py send [--recipient email] [--only 2 4]
    uv run --group composio python examples/composio_mailbox.py watch [--from-address email] [--apply-label]
    uv run --group composio python examples/composio_mailbox.py agent [--from-address email]

- connect: gives the link to connect the Gmail account to the project, with the authentication
  that Composio manages, and waits for it to be authorized.
- accounts: the Gmail accounts connected in Composio, with their User ID.
- send: sends the five fictional emails of the demo, by default to the same mailbox.
- watch: checks every new email. With --apply-label, it takes the suspicious ones out of the
  inbox and puts the Centinela-Quarantine label on them.
- agent: shows what an agent that reads its email through Composio receives with the safe inbox.

With watch and agent, the notices and the review cards come out in English; with --lang es, in
Spanish.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from send_test_emails import MAILS
from watch_mailbox import LINE, show

from centinela import LEAD_LABELS, Guard, RulesDetector, render_card
from centinela._env import load_env
from centinela.catalog import DEFAULT_LANG, LANGS
from centinela.safe_inbox import check_message, modifiers

LABEL = "Centinela-Quarantine"


class Gmail:
    """Runs Composio's Gmail tools on behalf of a user."""

    def __init__(self, user: str):
        from composio import Composio

        self.version = os.environ.get("COMPOSIO_GMAIL_VERSION", "latest")
        self.composio = Composio(
            api_key=os.environ["COMPOSIO_API_KEY"], toolkit_versions={"gmail": self.version}
        )
        self.user = user

    def execute(self, tool: str, arguments: dict, modifiers: list | None = None):
        extra: dict = {"modifiers": modifiers} if modifiers else {}
        if self.version == "latest":
            extra["dangerously_skip_version_check"] = True
        response = self.composio.tools.execute(tool, arguments, user_id=self.user, **extra)
        if not response.get("successful"):
            raise RuntimeError(f"{tool}: {response.get('error')}")
        data = response.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
        return data

    def address(self) -> str:
        profile = self.execute("GMAIL_GET_PROFILE", {}) or {}
        return str(profile.get("emailAddress") or profile.get("email_address") or "")

    def ids(self, query: str) -> list[str]:
        data = self.execute(
            "GMAIL_FETCH_EMAILS",
            {"query": query, "max_results": 25, "ids_only": True, "include_spam_trash": True},
        )
        messages = (data or {}).get("messages") or []
        return [
            str(m.get("messageId") or m.get("id"))
            for m in messages
            if m.get("messageId") or m.get("id")
        ]

    def label(self, name: str) -> str:
        data = self.execute("GMAIL_LIST_LABELS", {}) or {}
        for label in data.get("labels") or []:
            if label.get("name") == name:
                return str(label.get("id"))
        created = self.execute("GMAIL_CREATE_LABEL", {"label_name": name}) or {}
        return str(created.get("id") or created.get("labelId"))


def query(from_address: str | None) -> str:
    return "newer_than:1d" + (f" from:{from_address}" if from_address else "")


def connect(user: str) -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    request = composio.toolkits.authorize(user_id=user, toolkit="gmail")
    print("Open this link, sign in with the test Gmail account and authorize the access:\n")
    print(request.redirect_url)
    print("\nWaiting for the authorization (up to 5 minutes)…")
    sys.stdout.flush()
    account = request.wait_for_connection(300)
    print(f"Connected: {getattr(account, 'id', '?')} · User ID: {user}")
    return 0


def accounts() -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    response = composio.connected_accounts.list(toolkit_slugs=["gmail"])
    items = getattr(response, "items", None) or []
    if not items:
        print("There are no Gmail accounts connected in this Composio project.")
        return 1
    for account in items:  # only fields that are not secrets
        user = getattr(account, "user_id", None) or getattr(account, "userId", None) or "?"
        print(
            f"User ID: {user} · connected account: {getattr(account, 'id', '?')} · "
            f"status: {getattr(account, 'status', '?')}"
        )
    return 0


def send(gmail: Gmail, recipient: str | None, only: list[int] | None) -> int:
    recipient_address = recipient or gmail.address()
    if not recipient_address:
        print("No recipient to send to: use --recipient.", file=sys.stderr)
        return 1
    for n in only or range(1, len(MAILS) + 1):
        subject, plain, html, _ = MAILS[n - 1]
        gmail.execute(
            "GMAIL_SEND_EMAIL",
            {
                "recipient_email": recipient_address,
                "subject": subject,
                "body": html or plain,
                "is_html": bool(html),
                "include_signature": False,
            },
        )
        print(f"Sent {n}: {subject} → {recipient_address}")
        time.sleep(1)
    return 0


def watch(
    gmail: Gmail, guard: Guard, from_address: str | None, apply_label: bool, each: float
) -> int:
    search = query(from_address)
    seen = set(gmail.ids(search))  # only the emails that arrive from now on count
    label = gmail.label(LABEL) if apply_label else None
    filter_note = f", only emails from {from_address}" if from_address else ""
    print(
        f"Watching the mailbox of {gmail.address() or gmail.user} through Composio{filter_note}. "
        "Press Ctrl+C to exit."
    )
    while True:
        for message_id in gmail.ids(search):
            if message_id in seen:
                continue
            seen.add(message_id)
            message = gmail.execute(
                "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", {"message_id": message_id, "format": "raw"}
            )
            mail, verdict, card = check_message(message or {}, guard)
            show(
                "Gmail (Composio)",
                mail,
                verdict,
                render_card(card) if card else None,
            )
            if card and label:
                gmail.execute(
                    "GMAIL_ADD_LABEL_TO_EMAIL",
                    {
                        "message_id": message_id,
                        "add_label_ids": [label],
                        "remove_label_ids": ["INBOX"],
                    },
                )
                print(f"\n→ Taken out of the inbox and labeled {LABEL}.")
            sys.stdout.flush()
        time.sleep(each)


def agent(gmail: Gmail, guard: Guard, from_address: str | None) -> int:
    held_cards = []
    data = gmail.execute(
        "GMAIL_FETCH_EMAILS",
        {"query": query(from_address), "max_results": 10},
        modifiers=modifiers(guard, on_hold=lambda c, v, t: held_cards.append(t)),
    )
    print(
        "What the agent receives when it reads its email through Composio, with the safe inbox:\n"
    )
    for message in (data or {}).get("messages") or []:
        decision = (message.get("centinela") or {}).get("decision", "?")
        text = str(message.get("messageText") or message.get("preview") or "").strip()
        print(LINE)
        print(f"Subject: {message.get('subject')} · Centinela: {decision}")
        print(text[:400] + ("…" if len(text) > 400 else ""))
    if held_cards:
        print(f"\n{LINE}\nFor the person who reviews, {len(held_cards)} card(s):\n")
        for card in held_cards:
            print(render_card(card) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("connect", help="connect the Gmail account to the Composio project")
    sub.add_parser("accounts", help="list the Gmail accounts connected in Composio")
    p_send = sub.add_parser("send", help="send the fictional emails of the demo")
    p_send.add_argument("--recipient", help="recipient (by default, the same mailbox)")
    p_send.add_argument("--only", type=int, nargs="+", choices=range(1, len(MAILS) + 1))
    p_watch = sub.add_parser("watch", help="check every new email")
    p_watch.add_argument("--from-address", help="check only the emails from this address")
    p_watch.add_argument("--apply-label", action="store_true", help="set the suspicious ones aside")
    p_watch.add_argument("--each", type=float, default=8, help="seconds between checks")
    p_agent = sub.add_parser("agent", help="what an agent receives with the safe inbox")
    p_agent.add_argument("--from-address", help="only the emails from this address")
    for p in (p_watch, p_agent):
        p.add_argument("--claude", action="store_true", help="add Claude as a reviewer")
        p.add_argument(
            "--lang",
            choices=LANGS,
            default=DEFAULT_LANG,
            help="language of the notices and the review cards",
        )
    args = parser.parse_args(argv)

    load_env()
    if not os.environ.get("COMPOSIO_API_KEY"):
        print("COMPOSIO_API_KEY is missing from .env.", file=sys.stderr)
        return 1
    if os.environ["COMPOSIO_API_KEY"].startswith("ck_"):
        print(
            "COMPOSIO_API_KEY is a Composio Connect key (ck_), which works for its MCP. "
            "This script uses the developer platform: use the key of a project "
            "(it starts with ak_, in platform.composio.dev → Settings → API Keys).",
            file=sys.stderr,
        )
        return 1
    if args.command == "accounts":
        return accounts()
    user = os.environ.get("COMPOSIO_USER_ID")
    if not user:
        print(
            "COMPOSIO_USER_ID is missing from .env (the «accounts» command shows it).",
            file=sys.stderr,
        )
        return 1
    if args.command == "connect":
        return connect(user)
    gmail = Gmail(user)
    if args.command == "send":
        return send(gmail, args.recipient, args.only)
    detectors = [RulesDetector(labels=LEAD_LABELS)]
    if args.claude:
        from centinela import LLMDetector
        from centinela.providers.anthropic import AnthropicProvider

        detectors.append(LLMDetector(AnthropicProvider()))
    guard = Guard(detectors, lang=args.lang)
    try:
        if args.command == "watch":
            return watch(gmail, guard, args.from_address, args.apply_label, args.each)
        return agent(gmail, guard, args.from_address)
    except KeyboardInterrupt:
        print("\nDone.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
