#!/usr/bin/env python3
"""
Least on Slack.

    export SLACK_BOT_TOKEN=xoxb-...   SLACK_APP_TOKEN=xapp-...
    .venv/bin/python -m slackbot.bot

A manager mentions the bot the way they'd mention a colleague:

    @Least onboard @Mikko Liivak to billing

The bot resolves the mentioned Slack user to a real name, finds or stages them
in Okta, scans the codebase, and replies in-thread with the brief and an
Approve button. Clicking Approve provisions the access.

Socket Mode: outbound websocket, no public URL, works on venue wifi.
Inference stays on the GB10; only message text crosses to Slack.
"""
import os, re, sys, threading, pathlib

def _load_env():
    """Read KEY=VALUE from a gitignored .env so tokens survive a new terminal."""
    env = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env.exists(): return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slackbot import core
from agent import execute

app = App(token=os.environ["SLACK_BOT_TOKEN"])
MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]*)?>")
_BOT_ID = None

def bot_id(client):
    global _BOT_ID
    if _BOT_ID is None:
        _BOT_ID = client.auth_test()["user_id"]
    return _BOT_ID

def display_name(client, uid):
    try:
        p = client.users_info(user=uid)["user"]
        return p.get("real_name") or p["profile"].get("real_name") or p["name"]
    except Exception:
        return None

def sections(text, limit=2900):
    """Slack caps a section block at 3000 chars; split on blank lines."""
    out, cur = [], ""
    for chunk in text.split("\n\n"):
        if len(cur) + len(chunk) + 2 > limit and cur:
            out.append(cur); cur = ""
        cur = f"{cur}\n\n{chunk}" if cur else chunk
    if cur: out.append(cur)
    return [{"type": "section", "text": {"type": "mrkdwn", "text": s}} for s in out]

def buttons(result):
    if not result.get("packet"):
        return []
    if result.get("gate_passed"):
        return [{"type": "actions", "elements": [
            {"type": "button", "style": "primary", "action_id": "approve_access",
             "text": {"type": "plain_text", "text": "Approve access"},
             "value": result["packet"],
             "confirm": {"title": {"type": "plain_text", "text": "Provision access?"},
                         "text": {"type": "mrkdwn", "text": f"Grant the proposed groups to *{result['name']}* in Okta."},
                         "confirm": {"type": "plain_text", "text": "Approve"},
                         "deny": {"type": "plain_text", "text": "Cancel"}}}]}]
    return [{"type": "actions", "elements": [
        {"type": "button", "action_id": "recheck_mfa",
         "text": {"type": "plain_text", "text": "Re-check Okta Verify"},
         "value": f'{result["user_id"]}|{result["packet"]}'}]}]

@app.event("app_mention")
def on_mention(event, client, say):
    thread = event.get("thread_ts") or event["ts"]
    me = bot_id(client)
    ids = [u for u in MENTION.findall(event.get("text", "")) if u != me]
    names = [n for n in (display_name(client, u) for u in ids) if n]
    text = MENTION.sub(lambda m: "" if m.group(1) == me else (display_name(client, m.group(1)) or ""),
                       event.get("text", "")).strip()

    say(text="Reading the codebase…", thread_ts=thread)

    def work():
        try:
            r = core.handle(text, names)
        except Exception as e:
            r = {"text": core.explain_failure(e)}
        client.chat_postMessage(channel=event["channel"], thread_ts=thread,
                                text=r["text"][:3000], blocks=sections(r["text"]) + buttons(r))
    threading.Thread(target=work, daemon=True).start()

def approver_of(client, user_id):
    """
    Who clicked, as an identity rather than a label.

    A workspace member sets their own display name, so it can read "Sarah Chen"
    whoever they are. The email on the Slack profile is set by the workspace, so
    that is what is matched against the packet and what goes in the audit record.
    """
    email, why = None, None
    try:
        email = client.users_info(user=user_id)["user"]["profile"].get("email")
        if not email:
            why = ("Slack returned no email for you. The app needs the "
                   "`users:read.email` scope, and adding a scope to an installed "
                   "app needs a reinstall to the workspace before it takes effect.")
    except Exception as e:
        why = f"I could not read your Slack profile ({type(e).__name__})."
    return execute.Approver(email=email, source="slack", slack_id=user_id,
                            display=display_name(client, user_id) or user_id), why


@app.action("approve_access")
def on_approve(ack, body, client):
    ack()
    channel = body["channel"]["id"]
    msg = body["message"]
    thread = msg.get("thread_ts") or msg["ts"]
    who, why = approver_of(client, body["user"]["id"])
    try:
        r = core.approve(body["actions"][0]["value"], who)
    except Exception as e:
        r = {"text": core.explain_failure(e), "refused": "error"}
    if r.get("refused") == "no_approver_identity" and why:
        # Say which scope is missing rather than leaving a configuration problem
        # looking like a refusal of the person who clicked.
        r["text"] += f"\n_{why}_"

    if r.get("refused"):
        # A refusal is about the person who clicked, so it goes to them only.
        # The buttons stay: the right approver has not acted yet.
        client.chat_postEphemeral(channel=channel, user=body["user"]["id"],
                                  thread_ts=thread, text=r["text"])
        return
    client.chat_update(channel=channel, ts=msg["ts"], text=msg.get("text", ""),
                       blocks=[b for b in msg.get("blocks", []) if b.get("type") != "actions"])
    client.chat_postMessage(channel=channel, thread_ts=thread, text=r["text"])

@app.action("recheck_mfa")
def on_recheck(ack, body, client):
    ack()
    msg = body["message"]
    thread = msg.get("thread_ts") or msg["ts"]
    # This handler had no error path at all, so a button carrying an id the
    # directory no longer knows -- the ordinary result of a reseed -- did
    # nothing at all, silently. Silence reads as "the bot is down".
    try:
        from agent import okta
        uid, _ = body["actions"][0]["value"].split("|", 1)
        u = okta.resolve(uid)
        r = core.onboard(u["profile"]["login"], u["profile"].get("department"))
    except Exception as e:
        r = {"text": core.explain_failure(e)}
    client.chat_postMessage(channel=body["channel"]["id"], thread_ts=thread,
                            text=r["text"][:3000], blocks=sections(r["text"]) + buttons(r))

@app.event("message")
def ignore_plain_messages():
    pass

if __name__ == "__main__":
    missing = [k for k in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")
    print("Least is listening on Slack (Socket Mode). Ctrl-C to stop.", flush=True)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
