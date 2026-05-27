import pandas as pd
fn = "c:/Users/Madhvendra Sood/Desktop/ahu_ai_dashboard/backend/7F FRONT SIDE AHU REPORT 26(1).XLSX"
df = pd.read_excel(fn)
print(list(df.columns))
