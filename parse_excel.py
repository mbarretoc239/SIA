import pandas as pd

xl = pd.ExcelFile(r'C:\Users\matheus.cardoso\Downloads\Alinhamento (3).xlsx')
text = ""
for s in xl.sheet_names:
    df = pd.read_excel(xl, sheet_name=s, header=1)
    df = df.dropna(how='all')
    text += f'\n\n# {s}\n'
    text += df.to_csv(index=False)

with open('temp_alinhamentos.md', 'w', encoding='utf-8') as f:
    f.write(text)
