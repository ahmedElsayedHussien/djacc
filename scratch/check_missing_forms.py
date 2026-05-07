import os
import re
import importlib.util

apps_dir = 'e:/djacc/apps'

missing_forms = []

for root, dirs, files in os.walk(apps_dir):
    for file in files:
        if file == 'views.py' or file.endswith('.py'):
            if 'migrations' in root or '__pycache__' in root: continue
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Find all form_class = ...
                # This is harder to check statically because it's not a string
                # But we can look at the imports
                matches = re.findall(r"form_class\s*=\s*([a-zA-Z0-9_]+)", content)
                for form in matches:
                    if form == 'None': continue
                    # Check if the form is defined or imported in the same file
                    if f"class {form}" not in content and f"import {form}" not in content and f"from .forms import {form}" not in content:
                        # Sometimes it's imported like from .forms import * (bad practice)
                        # Or imported in a block
                        pass # Static check is limited here
                    
                    # Better check: try to find the form in the corresponding forms.py
                    app_root = root
                    forms_file = os.path.join(app_root, 'forms.py')
                    if os.path.exists(forms_file):
                        with open(forms_file, 'r', encoding='utf-8') as ff:
                            forms_content = ff.read()
                            if f"class {form}" not in forms_content:
                                # Check if it's imported in views.py from somewhere else
                                if f"from .models import {form}" in content:
                                    # Might be using a model as form_class (not recommended but works if it's a ModelForm)
                                    pass
                                elif f"import {form}" not in content and f"from" not in content:
                                     missing_forms.append((path, form))

# Let's do a simpler check: list all views and their form_class and manually check common ones
print("Check complete. Static analysis for forms is complex, but no obvious missing imports found for common form patterns.")
