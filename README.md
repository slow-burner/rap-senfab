# rap-senfab

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
python -m rap_senfab.main
```

## Test

```bash
pytest
```

## Image processing pipeline

`rap_senfab.image_pipeline` holds the MPP recipe nodes for SEM defect images.
They run in this order and share state through the module level `_gv` cache:

1. `SetGlobalVariables(img, _, gv)` — reads the recipe globals (`gs_semimage`,
   `gs_resultdata.url`, `gs_defectid`, optional `gs_resultimage.url`, `mp_no`
   and `dcoll_list`), derives the result paths, and passes the image through.
2. `ResultTest(res, resultData, _)` — annotates the result image with the
   nm/pixel scale and the rotation.
3. `makeCSV(img, _, _)` — creates the result directories and writes
   `<defect id>_Dcoll.csv`.

`SetGlobalVariables` must run first; the other nodes raise `RuntimeError` when
it has not.
