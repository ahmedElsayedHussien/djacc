import os
import re

apps_dir = 'e:/djacc/apps'
templates_dir = 'e:/djacc/templates'

missing_templates = []

for root, dirs, files in os.walk(apps_dir):
    for file in files:
        if file == 'views.py' or file.endswith('.py'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Find all template_name = '...' or template_name = "..."
                matches = re.findall(r"template_name\s*=\s*['\"]([^'\"]+)['\"]", content)
                for template in matches:
                    full_template_path = os.path.join(templates_dir, template.replace('/', os.sep))
                    if not os.path.exists(full_template_path):
                        missing_templates.append((path, template))

if missing_templates:
    print("MISSING TEMPLATES FOUND:")
    for view_file, template in missing_templates:
        print(f"  File: {view_file} -> Template: {template}")
else:
    print("No missing templates found!")
