"""The assistant teaches the same generic models as the editor."""
from ...core.payscript.templates import TEMPLATES

EXTRA_EXAMPLES = {}

def all_examples():
    out = {key: dict(value, idioms=()) for key, value in TEMPLATES.items()}
    for key, value in out.items():
        idioms = []
        if 'STOP' in value['script']: idioms.append('stop')
        if 'MEMO' in value['script']: idioms.append('memoire')
        if 'PARAM()' in value['script']: idioms.append('param_array')
        if 'WOF_MIN' in value['script']: idioms.append('wof_min')
        value['idioms'] = tuple(idioms)
    return out
