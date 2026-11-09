"""Offline stdio peer for the pinned 2024-11-05 prompt wire protocol."""

import json
import sys

initialized = False
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "notifications/initialized":
        initialized = True
        continue
    response = {"jsonrpc": "2.0", "id": request.get("id")}
    if method == "initialize":
        response["result"] = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"prompts": {}},
            "serverInfo": {"name": "offline-prompts", "version": "1"},
        }
    elif not initialized:
        response["error"] = {"code": -32600, "message": "Not initialized"}
    elif method == "prompts/list":
        response["result"] = {"prompts": [{"name": "review", "arguments": [
            {"name": "code", "required": True},
        ]}]}
    elif method == "prompts/get":
        params = request.get("params", {})
        if params.get("name") != "review":
            response["error"] = {"code": -32602, "message": "Unknown prompt"}
        elif "code" not in params.get("arguments", {}):
            response["error"] = {"code": -32602, "message": "Missing required argument: code"}
        else:
            response["result"] = {"messages": [
                {"role": "user", "content": {"type": "text", "text": "Review: " + params["arguments"]["code"]}},
                {"role": "assistant", "content": {"type": "text", "text": "Ready"}},
            ]}
    else:
        response["error"] = {"code": -32601, "message": "Method not found"}
    print(json.dumps(response), flush=True)
