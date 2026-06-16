# DLC Gait Assembler

## Setup

```bash
conda env create -f GAIT_ASSEMBLER.yaml
conda activate gait-assembler
python gait_assembler.py
```

## Imports

Imported runtime/configuration files live under `imports/`:

- `imports/alma/`: ALMA runtime files used by gait parameter analysis.
- `imports/DEEPLABCUT.yaml`: DeepLabCut conda environment used by the DeepLabCut install button.
