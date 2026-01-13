你必须只输出 **JSON**，不要输出任何解释、不要输出代码块标记（```）、不要输出多余文本。

schema: memory_update_v1

输出必须是一个 JSON object：
{
  "title": "简短标题",
  "summary_md": "可选：用 Markdown 简述本次更新意图",
  "ops": [
    {
      "op": "upsert",
      "target_table": "entities|relations|events|foreshadows|evidence",
      "target_id": null,
      "after": { ... },
      "evidence_ids": []
    }
  ]
}

规则：
- ops 必须是非空数组
- op=upsert 时 after 必填；op=delete 时 target_id 必填且 after 必须为 null
- entity after: { entity_type, name, summary_md?, attributes? }
- relation after: { from_entity_id, to_entity_id, relation_type, description_md?, attributes? }
- event after: { chapter_id?, event_type, title?, content_md, attributes? }
- foreshadow after: { chapter_id?, resolved_at_chapter_id?, title?, content_md, resolved(0|1), attributes? }
- evidence after: { source_type, source_id?, quote_md, attributes? }

