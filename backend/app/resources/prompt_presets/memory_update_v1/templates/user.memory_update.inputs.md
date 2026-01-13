<MEMORY_UPDATE_INPUT>
chapter_id: {{chapter_id}}
chapter_number: {{chapter_number}}
chapter_title: {{chapter_title}}
{% if focus %}focus: {{focus}}
{% endif %}
{% if chapter_plan %}<CHAPTER_PLAN>
{{chapter_plan}}
</CHAPTER_PLAN>
{% endif %}
{% if chapter_content_md %}<CHAPTER_CONTENT>
{{chapter_content_md}}
</CHAPTER_CONTENT>
{% endif %}
</MEMORY_UPDATE_INPUT>

