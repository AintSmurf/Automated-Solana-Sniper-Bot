import os
import shutil


def clear():
    current_path = os.getcwd()
    logs = os.path.join(current_path, "logs")
    results = os.path.join(current_path, "results")
    tokens_to_track = os.path.join(current_path, "tokens_to_track")

    if os.path.exists(logs) and os.path.isdir(logs):
        shutil.rmtree(logs)

    if os.path.exists(results) and os.path.isdir(results):
        shutil.rmtree(results)

    if os.path.exists(tokens_to_track) and os.path.isdir(tokens_to_track):
        shutil.rmtree(tokens_to_track)


clear()
