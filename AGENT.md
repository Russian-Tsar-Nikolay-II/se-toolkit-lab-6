Lab assistant agent
  A CLI agent for answering questions about a project using LLM and tools for working with files and the backend API.

Architecture
  The agent implements the LLM + Tools approach:
  The user asks a question
  LLM chooses a tool
  The agent executes the tool
  The result is returned to the LLM
  The final response is being generated
  The work takes place in a cycle (up to 10 steps).

Tools
  read_file(path)
  Reads a file from a project (with path protection and size limitation).
    list_files(path)
  Shows the contents of the directory.
    query_api(method, path, body)
  Sends an HTTP request to the backend API and returns the status and response.

Working with LLM
  The OpenAI API is used
  System prompt forces LLM to always use tools
  There are rules for different types of issues (wiki, code, API, bugs)

Json
{
"response": "...",
"tool calls": [...],
"source": "..."
}

Error handling
  Handled:
  API errors
  network and timeout issues
  incorrect paths
  file reading errors

Environment variables
  LLM_API_KEY
  LLM_API_BASE
  LLM_MODEL
  LMS_API_KEY
  AGENT_API_BASE_URL

Conclusion
  The agent combines LLM and tools, adding security, error handling, and fallback logic for reliable operation.