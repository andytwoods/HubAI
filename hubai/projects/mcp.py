"""A minimal stateless MCP server (Streamable HTTP transport, JSON responses only).

Each request is one JSON-RPC message POSTed to /mcp/ with `Authorization: Bearer <membership token>`.
No SSE stream is offered, so GET returns 405 as the spec allows.
"""

import json
import logging

from urllib.parse import urlsplit

from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hubai.projects.helpers import hub
from hubai.ratelimit import client_ip
from hubai.ratelimit import hit
from hubai.projects.models import Membership
from hubai.projects.models import Task

logger = logging.getLogger(__name__)

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = (
    "HubAI is a shared task board and message channel for a hackathon team's AI agents and humans. "
    "Always pass the same short `agent` name (e.g. 'claude-backend') so teammates can tell agents apart "
    "and you keep your own place in the inbox. "
    "Before starting work: call read_inbox and list_tasks. Claim a task with claim_task before working on it, "
    "so no one duplicates it. When you finish or get stuck, call update_task. Use post_message to tell the team "
    "what you changed (files, endpoints, decisions others depend on). Check read_inbox between steps."
)

PRIORITY_PROP = {
    "priority": {
        "type": "string",
        "enum": Task.Priority.values,
        "description": "Optional. 'high' puts the task at the top of its column (workers take the top To do task "
                       "first), 'low' at the bottom. Leave out for normal.",
    }
}

AGENT_PROP = {
    "agent": {
        "type": "string",
        "description": "Short name for you, e.g. 'claude-backend'. Use the same one every call.",
    }
}

TOOLS = [
    {
        "name": "whoami",
        "description": "Your identity, the project you're in, and how many unread messages you have.",
        "inputSchema": {"type": "object", "properties": {**AGENT_PROP}},
    },
    {
        "name": "list_members",
        "description": "People in this project and when their agents were last active.",
        "inputSchema": {"type": "object", "properties": {**AGENT_PROP}},
    },
    {
        "name": "list_tasks",
        "description": "Tasks on the project board in priority order (top first), optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": Task.Status.values}, **AGENT_PROP},
        },
    },
    {
        "name": "create_task",
        "description": "Add a task to the board (status 'todo'), optionally with a priority.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "description": {"type": "string"}, **PRIORITY_PROP, **AGENT_PROP},
            "required": ["title"],
        },
    },
    {
        "name": "claim_task",
        "description": "Take a 'todo' task so nobody else works on it. Fails if someone already has it.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}, **AGENT_PROP},
            "required": ["task_id"],
        },
    },
    {
        "name": "update_task",
        "description": (
            "Set a task's status (todo releases it; doing, blocked, done), a progress note, and/or its priority. "
            "While working, call it with status 'doing' and a short note after each major step. "
            "Priority alone may be set on any task, even one you don't hold."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {"type": "string", "enum": Task.Status.values},
                "note": {"type": "string"},
                **PRIORITY_PROP,
                **AGENT_PROP,
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "release_task",
        "description": (
            "Give up on a task you hold because your attempt failed. It goes back to To do for another try, "
            "or to Postpone (status 'blocked') after 3 attempts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}, "reason": {"type": "string"}, **AGENT_PROP},
            "required": ["task_id", "reason"],
        },
    },
    {
        "name": "post_message",
        "description": "Send a message to the whole team, or to one person by email or name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "to": {"type": "string", "description": "Email or name for a direct message. Omit for everyone."},
                **AGENT_PROP,
            },
            "required": ["body"],
        },
    },
    {
        "name": "read_inbox",
        "description": (
            "New messages and board events (claims, status changes) since you last checked, oldest first, "
            "up to 50. Each is returned once per agent name; call again if you got 50."
        ),
        "inputSchema": {"type": "object", "properties": {**AGENT_PROP}},
    },
]


def _str(args, key, default=""):
    value = args.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string.")
    return value


def _int(args, key):
    value = args[key]
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"'{key}' must be an integer.")
    return int(value)


def call_tool(membership, name, args):
    agent = _str(args, "agent")  # already normalised by agent_name()
    match name:
        case "whoami":
            return {
                "you": str(membership.user),
                "email": membership.user.email,
                "agent": agent or hub.DEFAULT_AGENT,
                "project": membership.project.name,
                "unread_messages": hub.unread_count(membership, agent),
            }
        case "list_members":
            return [
                {
                    "name": str(m.user),
                    "email": m.user.email,
                    "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
                }
                for m in membership.project.memberships.select_related("user")
            ]
        case "list_tasks":
            hub.release_stale_tasks(membership.project)
            tasks = membership.project.tasks.select_related("claimed_by__user", "created_by__user")
            if status := _str(args, "status"):
                tasks = tasks.filter(status=status)
            return [hub.task_dict(t) for t in tasks]
        case "create_task":
            return hub.task_dict(
                hub.create_task(membership, _str(args, "title"), _str(args, "description"), _str(args, "priority"))
            )
        case "release_task":
            return hub.task_dict(hub.release_task(membership, _int(args, "task_id"), _str(args, "reason"), agent))
        case "claim_task":
            hub.release_stale_tasks(membership.project)
            return hub.task_dict(hub.claim_task(membership, _int(args, "task_id"), agent))
        case "update_task":
            note = _str(args, "note") if "note" in args else None
            status = _str(args, "status") if "status" in args else None
            priority = _str(args, "priority") if "priority" in args else None
            if status is None and note is None and priority is None:
                raise ValueError("Give a status, a note or a priority.")
            task = hub.update_task(membership, _int(args, "task_id"), status, note, agent, priority=priority)
            return hub.task_dict(task)
        case "post_message":
            return hub.message_dict(hub.post_message(membership, _str(args, "body"), _str(args, "to"), agent))
        case "read_inbox":
            return [hub.message_dict(m) for m in hub.read_inbox(membership, agent)]
    raise KeyError(name)


def rpc_result(msg_id, result):
    return JsonResponse({"jsonrpc": "2.0", "id": msg_id, "result": result})


def rpc_error(msg_id, code, message, status=200):
    return JsonResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}, status=status)


def authenticate(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return (
        Membership.objects.select_related("project", "user").filter(token=header.removeprefix("Bearer ").strip()).first()
    )


def origin_allowed(request):
    """Spec: reject browser requests from other sites (DNS rebinding). CLIs send no Origin header."""
    origin = request.headers.get("Origin")
    return origin is None or urlsplit(origin).netloc == request.get_host()


@csrf_exempt
def mcp_endpoint(request):
    if request.method != "POST":
        return HttpResponse(status=405, headers={"Allow": "POST"})
    if not origin_allowed(request):
        return HttpResponse("Origin not allowed", status=403)
    version = request.headers.get("MCP-Protocol-Version")
    if version and version not in PROTOCOL_VERSIONS:
        return rpc_error(None, -32600, f"Unsupported MCP-Protocol-Version {version}", 400)

    membership = authenticate(request)
    if membership is None:
        if hit("mcp-bad-token", client_ip(request), 30, 60):
            return rpc_error(None, -32002, "Too many bad tokens. Wait a minute.", 429)
        return rpc_error(None, -32001, "Missing or invalid bearer token. Copy it from your project page.", 401)
    # A worker polls ~12/min and a busy agent a few more; 240/min per member covers several agents sharing a token.
    if hit("mcp", membership.pk, 240, 60):
        return rpc_error(None, -32002, "Rate limit: too many HubAI calls this minute. Slow down.", 429)

    try:
        msg = json.loads(request.body)
    except json.JSONDecodeError:
        return rpc_error(None, -32700, "Parse error", 400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return rpc_error(None, -32600, "Expected a single JSON-RPC 2.0 request", 400)

    method = msg["method"]
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    if not isinstance(params, dict) or isinstance(msg_id, (bool, dict, list)):
        return rpc_error(msg_id if isinstance(msg_id, (str, int)) else None, -32600, "Invalid request", 400)

    if "id" not in msg:
        # Notifications (e.g. notifications/initialized) need no reply.
        return HttpResponse(status=202)

    hub.touch(membership)

    match method:
        case "initialize":
            requested = params.get("protocolVersion")
            return rpc_result(
                msg_id,
                {
                    "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "hubai", "version": "0.1.0"},
                    "instructions": INSTRUCTIONS,
                },
            )
        case "ping":
            return rpc_result(msg_id, {})
        case "tools/list":
            return rpc_result(msg_id, {"tools": TOOLS})
        case "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                return rpc_error(msg_id, -32602, "'arguments' must be an object")
            try:
                args["agent"] = hub.agent_name(membership, args.get("agent") if isinstance(args.get("agent"), str) else "")
            except hub.HubError as exc:
                return rpc_result(msg_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
            hub.touch(membership, args["agent"], name if isinstance(name, str) else "")
            try:
                result = call_tool(membership, name, args)
            except KeyError as exc:
                if name not in {t["name"] for t in TOOLS}:
                    return rpc_error(msg_id, -32602, f"Unknown tool: {name}")
                text, is_error = f"Missing argument: {exc.args[0]}", True
            except (hub.HubError, ValueError) as exc:
                text, is_error = str(exc), True
            else:
                text, is_error = json.dumps(result, indent=1), False
            return rpc_result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
    return rpc_error(msg_id, -32601, f"Method not found: {method}")
