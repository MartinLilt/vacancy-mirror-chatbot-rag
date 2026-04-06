import re

def strip_markdown(text):
    text = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', text)
    text = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text

tests = [
    ('**/end ticket** VM-000005', True),
    ('/end ticket VM-000005', True),
    ('**Some other text**', False),
    ('Hello world', False),
    ('__/end ticket__ VM-000005', True),
    ('/End Ticket VM-000005', True),
]

for raw, expected in tests:
    clean = strip_markdown(raw).strip().lower()
    result = clean.startswith('/end ticket')
    status = 'OK' if result == expected else 'FAIL'
    print(f'{status} | raw={raw!r:40s} | clean={clean!r}')

