<CHAPTER_INFO>
第{{chapter_number}}章 {{chapter_title}}
{% if chapter_plan %}
本章要点：{{chapter_plan}}
{% endif %}</CHAPTER_INFO>

{% if instruction %}<INSTRUCTION>
{{instruction}}
</INSTRUCTION>

{% endif %}{% if analysis_json %}<ANALYSIS_JSON>
{{analysis_json}}
</ANALYSIS_JSON>

{% endif %}<RAW_CONTENT>
{{chapter_content_md}}
</RAW_CONTENT>
