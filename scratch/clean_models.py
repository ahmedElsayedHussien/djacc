import os

def clean_models():
    f = 'apps/sales/models.py'
    lines = open(f, encoding='utf-8').readlines()
    new_lines = []
    for i, line in enumerate(lines):
        # If this is a tax_percent and the previous line was tax_percent2, skip it
        if i > 0 and 'tax_percent =' in line and 'tax_percent2 =' in lines[i-1]:
            print(f"Skipping duplicate at line {i+1}")
            continue
        new_lines.append(line)
    
    with open(f, 'w', encoding='utf-8') as file:
        file.writelines(new_lines)

if __name__ == "__main__":
    clean_models()
