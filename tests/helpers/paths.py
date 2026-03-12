from pathlib import Path

def tests_root() -> Path:
    return Path(__file__).resolve().parents[1]

def schema_file(folder:str,*parts: str) -> Path:
    return tests_root() / "data" / "schemas" / Path(folder) / Path(*parts)

def fixture_file(folder:str,*parts: str) -> Path:
    return tests_root() / "data" / "fixtures" / Path(folder) / Path(*parts)
