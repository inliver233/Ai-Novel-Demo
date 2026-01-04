<PROJECT>
名称：{{project_name}}
题材：{{genre}}
一句话梗概：{{logline}}
</PROJECT>

{% if world_setting %}<WORLD_SETTING>
{{world_setting}}
</WORLD_SETTING>

{% endif %}{% if characters %}<CHARACTERS>
{{characters}}
</CHARACTERS>

{% endif %}{% if style_guide %}<STYLE_GUIDE>
{{style_guide}}
</STYLE_GUIDE>

{% endif %}{% if constraints %}<CONSTRAINTS>
{{constraints}}
</CONSTRAINTS>

{% endif %}<REQUIREMENTS_JSON>
{{requirements}}
</REQUIREMENTS_JSON>
