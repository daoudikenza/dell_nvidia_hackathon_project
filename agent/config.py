import os, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

def load():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    cfg["repo"] = pathlib.Path(os.path.expanduser(cfg["repo"]))
    cfg["_root"] = ROOT
    cfg["_packets"] = ROOT / "packets"
    cfg["_packets"].mkdir(exist_ok=True)
    return cfg

CFG = load()
