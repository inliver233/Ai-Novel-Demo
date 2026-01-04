【输出格式契约：必须严格遵守】
你必须只输出一个 JSON 对象；不能输出任何额外文字；不要 Markdown，不要代码块。
JSON Schema：
{
  "chapter_summary": string,
  "hooks": [{"excerpt": string, "note": string}],
  "foreshadows": [{"excerpt": string, "note": string}],
  "plot_points": [{"beat": string, "excerpt": string}],
  "suggestions": [{"title": string, "excerpt": string, "issue": string, "recommendation": string, "priority": string}],
  "overall_notes": string
}
