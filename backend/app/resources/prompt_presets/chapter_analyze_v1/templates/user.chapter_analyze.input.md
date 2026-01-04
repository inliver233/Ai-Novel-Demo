<CHAPTER_INFO>
第{{chapter_number}}章 {{chapter_title}}
{% if chapter_plan %}
本章要点：{{chapter_plan}}
{% endif %}{% if chapter_summary %}
本章摘要：{{chapter_summary}}
{% endif %}</CHAPTER_INFO>

{% if instruction %}<FOCUS>
{{instruction}}
</FOCUS>

{% endif %}<CHAPTER_CONTENT>
{{chapter_content_md}}
</CHAPTER_CONTENT>
