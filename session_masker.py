#!/usr/bin/env python
import re
def sanitize_code(code):
    # Remove local paths and keys
    code = re.sub(r'~/.*/', '/home/user/', code)
    code = re.sub(r'<your-.*-api-key>', 'API_KEY_REMOVED', code)
    return code