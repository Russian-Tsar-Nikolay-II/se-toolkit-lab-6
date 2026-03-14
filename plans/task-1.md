# Task plan 1

## Provider
- LLM: Qwen Code API
- Model: QWEN3-coder-plus

## The logic of the work
1. Accept the question from the command line argument
2. Download the key and settings from .env.agent.secret
3. Send a request to the LLM (OpenAI-compatible API)
4. Get a response, generate JSON
5. Output {"answer": "...", "tool_calls": []} to stdout
6. All logs and errors are in stderr only