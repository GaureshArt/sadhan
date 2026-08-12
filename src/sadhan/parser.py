def parser(llm_response:str):
    if llm_response.count('<reasoning>') != 1 or  llm_response.count('</reasoning>') != 1:
        raise Exception('There should be only one block of reasoning')
    if llm_response.count('<action>') != 1 or  llm_response.count('</action>') != 1:
        raise Exception('There should be only one block of action')
    def extract_tag_content(tag: str, text: str) -> str | None:
        import re
        pattern = rf"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None
    return {
        'reasoning':extract_tag_content('reasoning',llm_response),
        'action':extract_tag_content('action',llm_response)
    }
        
