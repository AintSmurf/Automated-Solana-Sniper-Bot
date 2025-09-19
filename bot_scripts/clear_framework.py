import os
import shutil


def clear():
    logs = os.path.join(os.path.dirname(__file__), "..", "logs")
    results = os.path.join(os.path.dirname(__file__), "..","results")

    if os.path.exists(logs) and os.path.isdir(logs):
        shutil.rmtree(logs)

    if os.path.exists(results) and os.path.isdir(results):
        shutil.rmtree(results)


clear()
