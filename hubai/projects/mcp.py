"""A minimal stateless MCP server (Streamable HTTP transport, JSON responses only).

Each request is one JSON-RPC message POSTed to /mcp/ with `Authorization: Bearer <membership token>`.
No SSE stream is offered, so GET returns 405 as the spec allows.
"""

import json
import logging

from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hubai.projects.helpers import hub
from hubai.projects.models import Membership
from hubai.projects.models import Task

logger = logging.getLogger(__name__)

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = (
    "HubAI is a shared task board and message channel for a hackathon team's AI agents and humans. "
    "Before starting work: call read_inbox and list_tasks. Claim a task with claim_task before working on it, "
    "so no one duplicates it. When you finish or get stuck, call update_task. Use post_message to tell the team "
    "what you changed (files, endpoints, decisions others depend on). Check read_inbox between steps."
)

AGENT_PROP = {
    "agent": {"type": "string", "description": "Short name for you, e.g. 'claude-backend'. Shown to the team."}
}

TOOLS = [
    {
        "name": "whoami",
        "description": "Your identity, the project you're in, and how many unread messages you have.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_members",
        "description": "People in this project and when their agents were last active.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_tasks",
        "description": "Tasks on the project board, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": Task.Status.values}},
        },
    },
    {
        "name": "create_task",
        "description": "Add a task to the board (status 'todo').",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "description": {"type": "string"}},
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
        "description": "Set a task's status (todo releases it; doing, blocked, done) and optionally a progress note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {"type": "string", "enum": Task.Status.values},
                "note": {"type": "string"},
            },
            "required": ["task_id", "status"],
        },
    },
    {
        "name": "post_message",
        "description": "Send a message to the whole team, or to one person by email or name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "to": {"type": "string", "description": "Email or name. Omit to message everyone."},
                **AGENT_PROP,
            },
            "required": ["body"],
        },
    },
    {
        "name": "read_inbox",
        "description": "New messages from others since you last checked. Each message is returned once.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(membership, name, args):
    match name:
        case "whoami":
            return {
                "you": str(membership.user),
                "email": membership.user.email,
                "project": membership.project.name,
                "unread_messages": hub.unread_count(membership),
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
            tasks = membership.project.tasks.select_related("claimed_by__user")
            if args.get("status"):
                tasks = tasks.filter(status=args["status"])
            return [hub.task_dict(t) for t in tasks]
        case "create_task":
            return hub.task_dict(hub.create_task(membership, args["title"], args.get("description", "")))
        case "claim_task":
            return hub.task_dict(hub.claim_task(membership, int(args["task_id"]), args.get("agent", "")))
        case "update_task":
            return hub.task_dict(hub.update_task(membership, int(args["task_id"]), args["status"], args.get("note")))
        case "post_message":
            message = hub.post_message(membership, args["body"], args.get("to", ""), args.get("agent", ""))
            return hub.message_dict(message)
        case "read_inbox":
            return [hub.message_dict(m) for m in hub.read_inbox(membership)]
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


@csrf_exempt
def mcp_endpoint(request):
    if request.method != "POST":
        return HttpResponse(status=405, headers={"Allow": "POST"})

    membership = authenticate(request)
    if membership is None:
        return rpc_error(None, -32001, "Missing or invalid bearer token. Copy it from your project page.", 401)

    try:
        msg = json.loads(request.body)
    except json.JSONDecodeError:
        return rpc_error(None, -32700, "Parse error", 400)
    if not isinstance(msg, dict) or "method" not in msg:
        return rpc_error(None, -32600, "Expected a single JSON-RPC request", 400)

    method = msg["method"]
    msg_id = msg.get("id")
    params = msg.get("params") or {}

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
