from __future__ import annotations

from app.schemas.prompts import PromptTemplateItem


def default_prompt_templates() -> list[PromptTemplateItem]:
    return [
        PromptTemplateItem(
            type="outline_generate",
            system_template="你是一个专业小说策划与结构编辑。请严格按用户要求输出 JSON（只输出 JSON，不要解释/不要 Markdown/不要代码块）。",
            user_template=(
                "项目信息：{{project_name}} / {{genre}} / {{logline}}\\n"
                "世界观：{{world_setting}}\\n"
                "角色：{{characters}}\\n"
                "要求：{{requirements}}\\n\\n"
                "请只输出 JSON（对象），schema：{\\n"
                "  \"outline_md\": string,\\n"
                "  \"chapters\": [{\"number\": int, \"title\": string, \"beats\": [string]}]\\n"
                "}"
            ),
        ),
        PromptTemplateItem(
            type="chapter_generate",
            system_template="你是一名小说写作助手。请严格按用户要求输出内容，避免使用 JSON（长文本容易截断/转义失败）。",
            user_template=(
                "项目信息：{{project_name}} / {{genre}} / {{logline}}\\n"
                "设定：{{world_setting}}\\n"
                "风格：{{style_guide}}\\n"
                "约束：{{constraints}}\\n"
                "大纲：{{outline}}\\n"
                "角色：{{characters}}\\n"
                "上一章：{{previous_chapter}}\\n\\n"
                "当前章节：第{{chapter_number}}章 {{chapter_title}}\\n"
                "本章要点：{{chapter_plan}}\\n"
                "用户指令：{{instruction}}\\n\\n"
                "目标字数（中文按字数=字符数，可为空）：{{target_word_count}}（若填写：允许±10%，且不得少于目标的80%）\\n"
                "生成要求（JSON）：{{requirements}}\\n\\n"
                "请按以下格式输出（只输出这两段，不要额外文本）：\\n"
                "<<<CONTENT>>>\\n"
                "（这里输出 Markdown 正文，必须是完整章节）\\n"
                "<<<SUMMARY>>>\\n"
                "（这里输出纯文本摘要，1-3 句）"
            ),
        ),
    ]
