# 清洗文章的提示词，去除引用格式、参考文献等内容
clean_article_prompt_zh = """
<system_role>你是一名专业的文章编辑，擅长整理和清洗文章内容。</system_role>

<user_prompt>
下面给你的内容可能是一篇完整研究文章，也可能只是其中的一个连续片段（chunk）。
请只针对输入的这部分内容进行清洗，不要假设、补全或引用片段之外的上下文。

清洗目标：去除所有引用链接、引用标记（如[1]、[2]、1、2 等或其他复杂引用格式）、参考文献列表、脚注，并确保文章内容连贯流畅。
保留文章的所有其他原本内容、只移除引用。如果文章中使用引用标记中的内容作为语句的一部分，保留这其中的文字内容，移除其他标记。

特殊情况：如果输入的这段内容整段都属于某个文章的参考文献区（reference 列表 / 脚注定义等），不包含任何正文，请返回空字符串。

输入内容：
"{article}"

请返回清洗后的全文，不要添加任何额外说明或评论。
</user_prompt>
"""

clean_article_prompt_en = """
<system_role>You are a professional article editor who is good at cleaning and refining article content.</system_role>

<user_prompt>
The input below may be a complete research article or just a continuous fragment (chunk) of one.
Operate only on the content provided; do not assume, complete, or quote any context outside this fragment.

Cleaning goal: remove all citation links, citation marks (such as [1], [2], 1, 2, etc. or other complex citation formats), reference lists, footnotes, and ensure the content reads smoothly.
Keep all other original content; remove only citations. If a citation mark wraps content that is part of a sentence, keep the text inside and drop only the marks.

Special case: if the entire input is a reference / bibliography / footnote-definition section of some article with no body text, return an empty string.

Input:
"{article}"

Return the cleaned text in full, without any additional explanation or comment.
</user_prompt>
"""
