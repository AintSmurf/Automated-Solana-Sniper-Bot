import os
import shutil
from datetime import date

root_dir = os.path.dirname(os.path.dirname(__file__))

results = os.path.join(root_dir, "results")
logs = os.path.join(root_dir, "logs")

analysis_root = os.path.join(root_dir, "analysis")
os.makedirs(analysis_root, exist_ok=True)

today = date.today().strftime("%Y-%m-%d")
today_folder = os.path.join(analysis_root, today)
os.makedirs(today_folder, exist_ok=True)

for folder in [results, logs]:
    if os.path.exists(folder):
        shutil.move(folder, today_folder)
