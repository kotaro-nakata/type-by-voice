# MyVoiceOS automation roadmap

## Goal

Keep dictation local and unchanged, add deterministic desktop commands first,
then add an optional local Qwen agent with a DeepSeek fallback for tasks that
need planning. Browser automation remains a replaceable backend.

## Phase 1: deterministic commands

- Treat speech as a command only when it begins with a configured wake word
  (`コンピューター` or `パソコン` by default).
- Keep ordinary speech on the existing clipboard/type output path.
- Parse commands locally without an LLM or network request.
- Allow only fixed actions and arguments; never execute generated shell text.
- Initial actions: open browser/terminal/file manager/settings, open known
  folders, web search, safe HTTP(S) URL opening, volume control, date and time.
- Report success or failure through the existing desktop notification path.

## Phase 2: local agent

1. Run `qwen3.5:4b` through Ollama with a deliberately small context limit.
2. Add a provider-neutral OpenAI-compatible client and structured tool schema.
3. Expose only reviewed tools from Phase 1; Qwen chooses tools but never runs
   operating-system commands directly.
4. Validate tool names and JSON arguments, cap steps and time, and log results.
5. Add confirmation states for file changes, account actions, messages,
   purchases, downloads, and any irreversible operation.
6. Build a Japanese command benchmark and measure tool selection, arguments,
   latency, and unsafe-action rejection on the target 8 GB GPU.

## Phase 3: paid fallback

1. Add DeepSeek behind the same provider interface.
2. Use it only after a local-model parse failure, repeated tool failure, or an
   explicitly complex request.
3. Never send secrets, clipboard contents, files, or page data by default.
4. Add per-request token limits, monthly budget limits, and an off switch.

## Phase 4: browser automation

1. Define a `BrowserBackend` interface: execute, status, stop.
2. Prototype PageAgent Extension + MCP as the first backend, using local Qwen.
3. Require confirmation for submit, publish, delete, purchase, authentication,
   upload, and download actions.
4. Add domain allowlists, task/step timeouts, stop control, and audit history.
5. Evaluate success rate against a Playwright implementation before making
   PageAgent a packaged dependency.
6. Fall back to DeepSeek only when the local model cannot complete the task.

## Phase 5: broader desktop control

- Prefer operating-system APIs and accessibility trees over screen coordinates.
- Use Windows UI Automation/pywinauto on Windows and supported accessibility
  APIs on Linux.
- Add screenshot/vision control only for interfaces inaccessible through APIs,
  with visible execution and mandatory confirmation for risky actions.

## Architecture boundary

The command router, model provider, tool registry, safety policy, and browser
backend must remain separate. This keeps basic commands free and reliable and
allows Qwen, DeepSeek, PageAgent, or Playwright to be replaced independently.
