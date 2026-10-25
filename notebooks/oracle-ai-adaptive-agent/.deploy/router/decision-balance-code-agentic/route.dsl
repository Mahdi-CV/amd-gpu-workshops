ROUTE code_agentic (
  description = "Code-review and debugging requests that use tools go to Flash-Next, while non-code tool work and recovery still use GLM.",
  on_unknown = "no_match"
) {
  PRIORITY 750
  WHEN decision("task", label: "code")
    AND (conversation("has_tools") OR conversation("tool_loop"))

  MODEL "qwen/qwen3.8-flash-next" (
    reasoning = true,
    effort = "medium"
  )

  ALGORITHM static
}
