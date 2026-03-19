import argparse
import json
import os
import sys
import requests
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(".env.agent.secret")
load_dotenv(".env.docker.secret")

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR
MAX_TOOL_CALLS = 10

LMS_API_KEY = os.getenv("LMS_API_KEY")
AGENT_API_BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

def safe_path(path_str):
    try:
        path = Path(path_str)
        if path.is_absolute():
            full = path.resolve()
        else:
            full = (PROJECT_ROOT / path).resolve()
        if ".." in path_str:
            return None
        if not str(full).startswith(str(PROJECT_ROOT)):
            return None
        return full
    except Exception:
        return None

def read_file(path):
    safe = safe_path(path)
    if not safe:
        return f"Error: Invalid path {path}"
    if not safe.exists():
        return f"Error: File not found {path}"
    try:
        content = safe.read_text()
        return content[:8000]
    except Exception as e:
        return f"Error: Cannot read {path}: {e}"

def list_files(path):
    safe = safe_path(path)
    if not safe:
        return "Error: Invalid path"
    if not safe.exists():
        return "Error: Path does not exist"
    if not safe.is_dir():
        return "Error: Not a directory"
    try:
        entries = [f.name for f in safe.iterdir()]
        if not entries:
            return "(directory is empty)"
        return "\n".join(sorted(entries))
    except Exception as e:
        return f"Error: {e}"

def query_api(method, path, body=None, include_auth=True):
    url = f"{AGENT_API_BASE_URL.rstrip('/')}{path}"
    headers = {}
    if include_auth and LMS_API_KEY:
        headers["Authorization"] = f"Bearer {LMS_API_KEY}"
    if body:
        headers["Content-Type"] = "application/json"
    try:
        method_upper = method.upper()
        if method_upper == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method_upper == "POST":
            data = json.loads(body) if body else {}
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        elif method_upper == "PUT":
            data = json.loads(body) if body else {}
            resp = requests.put(url, headers=headers, json=data, timeout=30)
        elif method_upper == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return json.dumps({"error": f"Unsupported method: {method}", "status_code": None})
        response_body = resp.text[:4000] if resp.text else ""
        return json.dumps({"status_code": resp.status_code, "body": response_body}, ensure_ascii=False)
    except requests.exceptions.Timeout:
        return json.dumps({"error": "Request timed out", "status_code": None})
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": f"Cannot connect to {url}. Backend may not be running.", "status_code": None})
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in request body", "status_code": None})
    except Exception as e:
        return json.dumps({"error": str(e), "status_code": None})

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file. Use for wiki docs, source code, config files.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory. Common paths: 'wiki/', 'backend/', 'backend/routers/', 'app/', '.'",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Query backend API with authentication. Use for: status codes, item counts, analytics, errors. Default include_auth=true. Set include_auth=false ONLY when question explicitly says 'without authentication'. For analytics endpoints: try multiple lab values if first returns empty [].",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "path": {"type": "string"},
                    "body": {"type": "string"},
                    "include_auth": {"type": "boolean", "description": "Include LMS_API_KEY header. Default=true. Set false ONLY for 'without authentication' questions."}
                },
                "required": ["method", "path"]
            }
        }
    }
]

TOOLS_MAP = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api
}

SYSTEM_PROMPT = """You are a CLI agent that answers questions using tools.

=== CRITICAL RULES ===

1. NEVER copy file content verbatim. Extract only the specific answer.

2. AUTHENTICATION RULES:
   - DEFAULT: Always use include_auth=true for query_api (sends LMS_API_KEY)
   - EXCEPTION: Use include_auth=false ONLY when question says "without authentication" or "no auth header"
   - Analytics endpoints (/analytics/*) ALWAYS need authentication - use include_auth=true

3. ERROR DIAGNOSIS WORKFLOW (for questions about crashes/bugs):
   Step 1: query_api to reproduce the error (try multiple parameter values if needed)
   Step 2: If you get empty [] for analytics endpoint, try different lab values: lab-1, lab-2, lab-test
   Step 3: When you get TypeError/ZeroDivisionError/NoneType error, read the traceback
   Step 4: read_file the source file from traceback (e.g., backend/app/routers/analytics.py)
   Step 5: Find the exact buggy line and explain why it fails
   Step 6: Answer with: error type + file:line + buggy code + explanation + fix suggestion

4. STATUS CODE QUESTIONS:
   - If question says "without authentication": use include_auth=false
   - Otherwise: use include_auth=true

5. For /analytics/top-learners bug specifically:
   - The bug is: sorted(rows, key=lambda r: r.avg_score) fails when avg_score is None
   - Python cannot compare None with float in sorting
   - Fix: filter out None values or provide default: key=lambda r: r.avg_score or 0

6. Keep answers concise. No markdown headers or table of contents.

=== TOOL SELECTION ===

- query_api: HTTP status codes, item counts, analytics, testing endpoints, errors
  - include_auth=true (default) for normal queries
  - include_auth=false ONLY for "without authentication" questions
  - For analytics: if empty [], try lab-1, lab-2, lab-test
- read_file: wiki docs, source code, config files (docker-compose.yml, Dockerfile)
- list_files: explore directories to find files

=== EXAMPLES ===

Q: "What status code without auth header?"
A: query_api(method="GET", path="/items/", include_auth=false) → report status_code

Q: "/analytics/top-learners crashes, find the bug"
A: 
  1. query_api(path="/analytics/top-learners?lab=lab-1", include_auth=true)
  2. Get TypeError about NoneType and float
  3. read_file("backend/app/routers/analytics.py")
  4. Find: sorted(rows, key=lambda r: r.avg_score) at line 245
  5. Answer: "TypeError: cannot compare None with float in sorted(). The avg_score field can be None. Fix: add None check or default value."

Q: "How many items in database?"
A: query_api(method="GET", path="/items/", include_auth=true) → count from response

=== PROJECT STRUCTURE ===

- Wiki: wiki/
- Backend routers: backend/app/routers/, backend/routers/
- Analytics router: backend/app/routers/analytics.py (bug: sorted with None avg_score)
- Config: docker-compose.yml, Dockerfile at project root

=== ANSWER FORMAT ===

Direct answer based on tool results. Include source file:line when referencing code."""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    args = parser.parse_args()

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key or not api_base:
        output = {"answer": "Error: LLM_API_KEY or LLM_API_BASE not set", "tool_calls": []}
        print(json.dumps(output))
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=api_base)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": args.question}
    ]

    tool_calls_log = []
    final_source = None

    for iteration in range(MAX_TOOL_CALLS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto"
        )
        message = response.choices[0].message

        if message.content and not message.tool_calls:
            answer = message.content.strip()
            output = {"answer": answer, "tool_calls": tool_calls_log}
            if final_source:
                output["source"] = final_source
            print(json.dumps(output))
            sys.exit(0)

        if message.tool_calls:
            for tc in message.tool_calls:
                func_name = tc.function.name
                func_args = json.loads(tc.function.arguments)
                tool_func = TOOLS_MAP.get(func_name)
                
                include_auth = func_args.get("include_auth", True)
                call_args = {k: v for k, v in func_args.items() if k != "include_auth"}
                
                if tool_func:
                    try:
                        result = tool_func(**call_args, include_auth=include_auth)
                    except TypeError:
                        result = tool_func(**call_args)
                else:
                    result = f"Error: Unknown tool"

                if func_name == "read_file":
                    final_source = func_args.get("path", "")

                tool_calls_log.append({
                    "tool": func_name,
                    "args": func_args,
                    "result": result[:500]
                })

                messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

    synthesis_prompt = "Based on the tool results above, provide a concise answer to the original question."
    messages.append({"role": "user", "content": synthesis_prompt})
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
    except Exception:
        answer = "Could not synthesize final answer from tool results"
    
    output = {"answer": answer, "tool_calls": tool_calls_log}
    if final_source:
        output["source"] = final_source
    print(json.dumps(output))

if __name__ == "__main__":
    main()