import pandas as pd
from tools_nutrition_local import TSV_PATH

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 0)
pd.set_option("display.max_colwidth", None)

df = pd.read_csv(TSV_PATH, sep="\t")  # read full file
first_two = df.head(2)                # or: df.iloc[:2]

print("Column names:", list(first_two.columns), "\n")
print(first_two.to_string(index=False))

print("\nDtypes:")
print(first_two.dtypes)