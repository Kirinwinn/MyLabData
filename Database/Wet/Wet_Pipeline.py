from pathlib import Path

from Database.Tools.Wet.Db_Maker import make_wet_database
from Database.Tools.Wet.Wet_Check import FolderParser, validator

WET_DIR = Path(__file__).resolve().parent
WET_DB_PATH = WET_DIR / "Wet.db"

# Fill wet data source directly here; no extra txt/csv dependency is required.
WET_DATA_ROOT = Path(r"C:\Users\Cenking\Documents\ExperimentData\WetData")

# Fill SMILES directly here; this is used by ViewMode structure rendering.
WET_SMILES_MAP = {
    "STL36": "CC[n+]1c(/C=C/C=C/C=C/N(c2ccccc2)C)sc2c1sc(c2C)C",
    "STL32": "CCCN(c1ccc(cc1)/C(=c/1\\ccc(=C(C#N)C#N)cc1)/NC(C)C)CCC",
    "STK79": "CC[n+]1c(/C=C\\2/C=C(/C=C/C=C/C=c/3\\sc4c(n3CC)cccc4)CC(C2)(C)C)sc2c1cccc2",
    "STL14": "CN1C=C\\C(=C\\C=C(\\C=C\\c2cc[n+](C)c3ccccc23)/c2ccccc2)c2ccccc12",
    "5107": "[n+]1(c(sc2c1cccc2)/C=C/C=C\\1/C=C(/C=C/N(c2ccccc2)C)CC(C1)(C)C)CC.[I-]",
    "OTA61": "[O-][Cl](=O)(=O)=O.CN(C)c1ccc(\\C=C2/CCCc3c2cc([o+]c3-c2ccccc2)-c2ccccc2)cc1",
    "BTB11": "CN(C)\\C=C\\C=C\\C=C1/c2ccccc2-c2ccc(cc12)[N+]([O-])=O",
}

WET_IGNORE_DIRS = {
    ".ipynb_checkpoints",
    "RData",
    "PData",
    "SData",
    "__pycache__",
    ".git",
    "$RECYCLE.BIN",
    "System Volume Information",
}


def get_wet_smiles_map():
    return dict(WET_SMILES_MAP)


def run_wet_pipeline(data_root=None, db_path=None):
    resolved_data_root = Path(data_root) if data_root else WET_DATA_ROOT
    resolved_db_path = Path(db_path) if db_path else WET_DB_PATH
    make_wet_database(
        data_root=resolved_data_root,
        db_path=resolved_db_path,
        folder_parser=FolderParser,
        validator=validator,
        ignore_dirs=WET_IGNORE_DIRS,
    )


if __name__ == "__main__":
    run_wet_pipeline()
