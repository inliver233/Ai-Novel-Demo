<CHAPTER_INFO>
第{{chapter_number}}章 {{chapter_title}}
{% if chapter_plan %}本章要点：{{chapter_plan}}
{% endif %}{% if story and story.plan %}<PLAN>
{{story.plan}}
</PLAN>
{% endif %}</CHAPTER_INFO>
