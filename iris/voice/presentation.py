"""Conservative speech formatting; never infer the meaning of arbitrary maths."""
import re

def spoken_text(text):
    text = re.sub(r'```[\s\S]*?```', 'The code is shown on screen.', text)
    text = re.sub(r'\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$',
                  'The mathematical expression is shown on screen.', text)
    text = re.sub(r'\$([^$\n]*[=^{}\\][^$\n]*)\$',
                  'The mathematical expression is shown on screen.', text)
    text = re.sub(r'\[([^\]\n]+)\]\(https?://[^\s)]+\)', r'\1', text)
    text = re.sub(r'(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+)', '', text)
    text = re.sub(r'\*\*([^*\n]+)\*\*|__([^_\n]+)__', lambda m:m[1] or m[2], text)
    text = re.sub(r'(\d(?:[\d,.]*\d)?)\s*%', r'\1 percent', text)
    return text.strip()
