from __future__ import annotations

from app.schemas.prompts import PromptTemplateItem


def default_prompt_templates() -> list[PromptTemplateItem]:
    return [
        PromptTemplateItem(
            type="outline_generate",
            system_template="你是一个专业小说策划与结构编辑。请严格按用户要求输出 JSON。",
            user_template=(
                "项目信息：{{project_name}} / {{genre}} / {{logline}}\\n"
                "世界观：{{world_setting}}\\n"
                "角色：{{characters}}\\n"
                "要求：{{requirements}}\\n\\n"
                "请输出 JSON：{\\n"
                "  \"outline_md\": \"...\",\\n"
                "  \"chapters\": [{\"number\":1,\"title\":\"...\",\"beats\":[\"...\"]}]\\n"
                "}"
            ),
        ),
        PromptTemplateItem(
            type="chapter_generate",
            system_template="你是一名小说写作助手。请严格按用户要求输出 JSON。",
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
                "请输出 JSON：{\\n"
                "  \"content_md\": \"...\",\\n"
                "  \"summary\": \"...\"\\n"
                "}"
            ),
        ),
    ]

