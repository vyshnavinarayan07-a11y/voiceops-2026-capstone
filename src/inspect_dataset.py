
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

data_folder = PROJECT_ROOT / "data"
kb_folder = PROJECT_ROOT / "kb"
practice_folder = PROJECT_ROOT / "practice"

print("ZentroMart Voice AI - Dataset Inspector")
print("-" * 45)

documents = list(kb_folder.glob("*.md"))
print(f"Knowledge-base documents: {len(documents)}")

csv_files = sorted(data_folder.glob("*.csv"))

for file_path in csv_files:
    df = pd.read_csv(file_path, dtype=str)
    print(f"{file_path.name}: {len(df)} rows")

questions_path = practice_folder / "questions.csv"
questions = pd.read_csv(questions_path, dtype=str)
print(f"Practice questions: {len(questions)}")

policy_path = kb_folder / "pol_returns_v4.md"
print(f"Current returns policy exists: {policy_path.exists()}")

print("-" * 45)
print("Dataset inspection complete!")
