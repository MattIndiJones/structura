"""Read explicit private workshop credentials; no shared credential fallback."""
import json


BOOTSTRAP_FILENAME = 'bootstrap_credentials.json'


def simulation_credentials(directory):
    path = directory / BOOTSTRAP_FILENAME
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        password = value.get('password')
        if (value.get('username') != 'workshop_admin' or not isinstance(value.get('email'), str)
                or not isinstance(password, str) or len(password) < 32 or len(password.encode()) > 72):
            raise ValueError('Invalid private bootstrap credentials')
    except (ValueError, AttributeError, OSError) as exc:
        raise RuntimeError('Identifiants techniques privés de simulation absents ou invalides.') from exc
    return value
