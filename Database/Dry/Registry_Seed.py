"""Seed the MLD2 registry with built-in trait and prediction definitions."""

from __future__ import annotations

from .Registry import DryRegistry


TRAIT_LABELS = (
    "Hydroxyl group", "Thiol group", "Thioether group", "Nitro group",
    "Nitroso group", "Azo group", "Diazo group", "Aldehyde group",
    "Carbonyl/Ketone group", "Carboxyl group", "Ester group", "Cyano group",
    "Thiocarbonyl group", "Acyl halide group", "Acid anhydride group",
    "Heavy atom (I/Br)", "Alkynyl group", "Sulfonic acid group",
    "Quaternary ammonium group", "Phosphate group", "Boronic acid group",
    "Isothiocyanate group", "Azide group", "Succinimidyl ester group",
    "Molecular Weight", "LogP", "LogD", "LogS", "Aromaticity", "TPSA",
    "Fsp3", "Rotatable Bonds", "Aromatic Rings", "Aliphatic Rings",
    "Atomic Connectivity", "Longest Conjugated Length", "Molar Refractivity",
    "Molecular Volume", "H-bond Acceptors", "H-bond Donors", "Formal Charge",
    "Dipole Moment", "Topological Polarizability", "pKa",
)

INTEGER_TRAITS = set(range(1, 25)) | {32, 33, 34, 35, 36, 39, 40, 41}

MODEL_ATTRIBUTES = {
    "DeepMPP": ("Abs_pred", "Emi_pred"),
    "Proby": (
        "abs", "emi", "plqy", "e", "log10e", "lifetime", "abs_fwhm_cm",
        "emi_fwhm_cm", "abs_fwhm_nm", "emi_fwhm_nm",
    ),
    "Tox21": (
        "NR-AR", "NR-AR-LBD", "NR-AhR", "NR-Aromatase", "NR-ER",
        "NR-ER-LBD", "NR-PPAR-gamma", "SR-ARE", "SR-ATAD5", "SR-HSE",
        "SR-MMP", "SR-p53",
    ),
}


def seed_registry(registry: DryRegistry | None = None) -> dict[str, int]:
    registry = registry or DryRegistry()
    registry.initialize()
    trait_source = registry.register_source(
        "toolscom.property",
        "ToolsCom Property",
        "system",
        description="Built-in molecular trait calculations from ToolsCom.",
    )

    attribute_count = 0
    for index, label in enumerate(TRAIT_LABELS, start=1):
        registry.register_attribute(
            f"trait.Trait{index}",
            label,
            "trait",
            "integer" if index in INTEGER_TRAITS else "float",
            source_id=trait_source,
            metadata={"legacy_key": f"Trait{index}"},
        )
        attribute_count += 1

    for model_name, columns in MODEL_ATTRIBUTES.items():
        source_id = registry.register_source(
            f"model.{model_name.lower()}",
            model_name,
            "derived",
            description=f"Prediction attributes produced by {model_name}.",
        )
        for column in columns:
            registry.register_attribute(
                f"prediction.{model_name}.{column}",
                column,
                "prediction",
                "float",
                model_name=model_name,
                source_id=source_id,
                metadata={"source_column": column},
            )
            attribute_count += 1

    registry.register_attribute(
        "annotation.solvent",
        "Solvent",
        "annotation",
        "string",
        description="Solvent SMILES associated with solvent-dependent predictions.",
    )
    attribute_count += 1
    return {"sources": 1 + len(MODEL_ATTRIBUTES), "attributes": attribute_count}


if __name__ == "__main__":
    print(seed_registry())
