"""Ephemeral molecule-structure transformations.

The functions in this module operate only on structure strings held in memory.
They never write conformers or derived files into DryData.
"""

from rdkit import Chem
from rdkit.Chem import AllChem


def mol_block_from_smiles(canonical_smiles: str) -> str:
    """Generate one deterministic 3D conformer and serialize it as a MolBlock."""
    molecule = Chem.MolFromSmiles(canonical_smiles)
    if molecule is None:
        raise ValueError("The molecule has an invalid canonical SMILES")

    molecule = Chem.AddHs(molecule)
    status = AllChem.EmbedMolecule(molecule, randomSeed=0x4D4C44)
    if status != 0:
        raise ValueError("A 3D conformer could not be generated for this molecule")

    AllChem.UFFOptimizeMolecule(molecule, maxIters=200)
    return Chem.MolToMolBlock(molecule)
