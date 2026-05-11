"""
Second-pass fixer: corrects two types of bad patterns left by the first fix script in app.py:

1. f-string with empty {}: logger.warning(f"...{}")  -> SyntaxError
   These happened when the regex matched but left the f prefix.
   
2. logger.opt(exception=True).info("...{len(...)}")  -> called on non-error path
   These should just be logger.info() without exception=True.
   
3. logger.error(f"...", e) with f-string still present -> wrong args style.
"""
import re
import os

TARGET = r"C:\Users\ABDULLAH\OneDrive\Desktop\YouBot\langgraph_agent\app.py"

with open(TARGET, 'r', encoding='utf-8') as f:
    content = f.read()

original = content

# Fix 1: f"...{}" -> SyntaxError on line 205
# logger.warning(f"⚠️ Redis not available, using in-memory cache: {}")
# Should be: logger.warning("⚠️ Redis not available, using in-memory cache: {}", e)
content = content.replace(
    'logger.warning(f"⚠️ Redis not available, using in-memory cache: {}")',
    'logger.warning("⚠️ Redis not available, using in-memory cache: {}", e)'
)

# Fix 2: logger.opt(exception=True).info("...{len(verified_tables)}")
# This is a non-error info log — remove exception=True and fix formatting
content = content.replace(
    'logger.opt(exception=True).info("✅ Runtime tables verified/created: {len(verified_tables)}")',
    'logger.info("✅ Runtime tables verified/created: {}", len(verified_tables))'
)

# Fix 3: logger.error(f"Error getting FAQ cache stats: {str(e)}", e)
# The f-string was NOT converted (still has f prefix), and now has double e arg
content = content.replace(
    'logger.error(f"Error getting FAQ cache stats: {str(e)}", e)',
    'logger.opt(exception=True).error("Error getting FAQ cache stats: {}", str(e))'
)

# Generic sweep: find any remaining  logger.*(f"...", exc_info=True)  that slipped through
# (f prefix still present, exc_info=True still there)
pat_remaining = re.compile(
    r'logger\.(error|warning|info|debug)\(f"([^"]*?)", exc_info=True\)'
)
def fix_remaining(m):
    level = m.group(1)
    msg = m.group(2)
    return f'logger.opt(exception=True).{level}("{msg}")'

content, n = pat_remaining.subn(fix_remaining, content)
if n:
    print(f"Fixed {n} remaining f-string+exc_info patterns")

if content != original:
    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(content)
    print("app.py patched successfully.")
else:
    print("No changes needed.")
