<PROJECT>
{{project_name}} / {{genre}} / {{logline}}
</PROJECT>

{% if world_setting %}<WORLD_SETTING>
{{world_setting}}
</WORLD_SETTING>

{% endif %}{% if characters %}<CHARACTERS>
{{characters}}
</CHARACTERS>

{% endif %}{% if outline %}<OUTLINE>
{{outline}}
</OUTLINE>

{% endif %}<CHAPTER_INFO>
第{{chapter_number}}章 {{chapter_title}}
本章要点：{{chapter_plan}}
</CHAPTER_INFO>

<USER_INSTRUCTION>
{{instruction}}
</USER_INSTRUCTION>
