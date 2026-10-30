"""Validate and remove duplicate rows in the four EICV7 section 9 files.

The raw `.dta` files are read only. Every row that is removed is logged with its
reason and its position in the raw file, so the cleaning can be audited and undone.
No value in a kept row is changed.

Natural keys (EICV7 questionnaire, PDF pages 60, 61, 62 and 70):

| File | Key | Design |
|---|---|---|
| S9A transfers out | `hhid` + `s9aq2a` (recipient line) | one row per recipient; one "no" row if none |
| S9B transfers in | `hhid` + `s9bq3` (sender line) | one row per sender; one "no" row if none |
| S9C other expenditure | `hhid` + `s9cq1` (item code 1-13) | fixed list: every item once |
| S9E other income | `hhid` + `s9eq1` (item code 1-26) | fixed list: every item once |

Dedup rule, applied in order:

1. Exact repeat: a row identical to an earlier row on every variable is dropped.
2. Contradictory "no" row (S9A, S9B): a row answering "no transfers" in a household
   that also lists transfers is dropped. These rows carry no amounts.
3. Key conflict: a later row with the same key as an earlier row but different
   content is dropped; the first row in file order is kept.
   - "non_amount": the rows agree on every amount, so totals are unaffected.
   - "amount": the rows disagree on an amount, so the household's total for that
     file is not reliable and `use_in_totals` is set to False.
4. Version conflict: a household with an amount conflict in a fixed-list file (S9C or
   S9E) has two different versions of section 9 under one `hhid`. Which version
   belongs to the household in the poverty file cannot be determined, so
   `use_in_totals` is set to False for that household in all four files.

Rows with `use_in_totals` False stay in the clean files (key-unique), but their
household totals must be treated as missing, not as zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EICV7_DIR = PROJECT_ROOT / "Microdata" / "Cross_Section"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

HOUSEHOLD_COLS = ["hhid", "clust", "province", "district", "ur", "strata_id", "weight",
                  "quintile", "pov_jan", "poverty", "epov_jan"]
DROP_REASONS = ["exact_repeat", "contradictory_no_row", "key_conflict"]
CONFLICT_RANK = {"none": 0, "non_amount": 1, "amount": 2}


@dataclass(frozen=True)
class S9File:
    name: str
    file: str
    item: str                   # roster line or item code; `hhid` + `item` is the key
    amounts: tuple[str, ...]    # RWF amounts that are summed downstream
    out: str
    flag: str | None = None     # filter question "any transfers?" (1 yes, 2 no)
    fixed_list: bool = False    # every household answers every item exactly once

    @property
    def path(self) -> Path:
        return EICV7_DIR / self.file

    @property
    def key(self) -> list[str]:
        return ["hhid", self.item]


S9_FILES = (
    S9File("transfers_out", "CS_S9A_transfers_out.dta", "s9aq2a", ("s9aq7", "s9aq10", "s9aq12"),
           "s9a_transfers_out_dedup.parquet", flag="s9aq0"),
    S9File("transfers_in", "CS_S9B_transfers_in.dta", "s9bq3", ("s9bq8",),
           "s9b_transfers_in_dedup.parquet", flag="s9bq0"),
    S9File("other_expenditure", "CS_S9C_other_expenditure.dta", "s9cq1", ("s9cq2",),
           "s9c_other_expenditure_dedup.parquet", fixed_list=True),
    S9File("other_income", "CS_S9E_other_income.dta", "s9eq1", ("s9eq3", "s9eq4"),
           "s9e_other_income_dedup.parquet", fixed_list=True),
)
SPECS = {s.name: s for s in S9_FILES}
# 12-month RWF amounts per file. `s9eq3` (last 4 weeks) is excluded.
ANNUAL_AMOUNTS = {"transfers_out": ["s9aq7", "s9aq10", "s9aq12"], "transfers_in": ["s9bq8"],
                  "other_expenditure": ["s9cq2"], "other_income": ["s9eq4"]}


def load_raw(spec: S9File) -> pd.DataFrame:
    """Read a raw file with stored codes, adding its 0-based row position."""
    raw = pd.read_stata(spec.path, convert_categoricals=False)
    raw.insert(0, "row_in_file", np.arange(len(raw), dtype=np.int64))
    return raw


def item_labels(spec: S9File) -> dict[int, str]:
    """Value labels attached to the item or line variable in the raw file."""
    codes = pd.read_stata(spec.path, columns=[spec.item], convert_categoricals=False)[spec.item]
    labels = pd.read_stata(spec.path, columns=[spec.item])[spec.item].astype("string")
    pairs = pd.DataFrame({"code": codes, "label": labels}).dropna().drop_duplicates("code")
    return {int(c): " ".join(str(l).split()) for c, l in zip(pairs["code"], pairs["label"])}


def annotate(raw: pd.DataFrame, spec: S9File) -> pd.DataFrame:
    """Apply rules 1-3: add `n_raw_copies`, `drop_reason`, `matches_row` and `key_conflict`.

    `matches_row` is the raw position of the kept row that a dropped row repeats or conflicts with.
    `key_conflict` is set on every row of a conflicting key group, including the kept one.
    """
    cols = [c for c in raw.columns if c != "row_in_file"]
    d = raw.copy()
    row_hash = pd.util.hash_pandas_object(d[cols], index=False)
    d["n_raw_copies"] = row_hash.map(row_hash.value_counts()).astype(np.int16)
    d["drop_reason"] = pd.Series(pd.NA, index=d.index, dtype="string")
    d["matches_row"] = pd.Series(pd.NA, index=d.index, dtype="Int64")
    d["key_conflict"] = "none"

    # Rule 1: exact repeats.
    exact = d.duplicated(cols, keep="first")
    d.loc[exact, "drop_reason"] = "exact_repeat"
    d.loc[exact, "matches_row"] = d.groupby(row_hash.values)["row_in_file"].transform("min")[exact]

    # Rule 2: "no transfers" rows in households that also list transfers.
    if spec.flag:
        live = d["drop_reason"].isna()
        has_yes = d["hhid"].isin(d.loc[live & d[spec.flag].eq(1), "hhid"])
        no_row = live & d[spec.flag].eq(2) & has_yes
        assert d.loc[no_row, list(spec.amounts)].isna().all().all(), "a 'no' row carries an amount"
        d.loc[no_row, "drop_reason"] = "contradictory_no_row"

    # Rule 3: same key, different content. Keep the first row in file order.
    live = d.loc[d["drop_reason"].isna()]
    size = live.groupby(spec.key, dropna=False)["row_in_file"].transform("size")
    cand = live.loc[size.gt(1)]
    if len(cand):
        by = [cand["hhid"], cand[spec.item].fillna(-1)]
        differs = cand[list(spec.amounts)].fillna(-1).groupby(by).transform("nunique").gt(1).any(axis=1)
        first_row = cand.groupby(by)["row_in_file"].transform("min")
        d.loc[cand.index, "key_conflict"] = np.where(differs, "amount", "non_amount")
        later = cand.index[cand["row_in_file"].ne(first_row)]
        d.loc[later, "drop_reason"] = "key_conflict"
        d.loc[later, "matches_row"] = first_row[later]
    return d


def version_conflicts(annotated: dict[str, pd.DataFrame]) -> set[int]:
    """Rule 4: households with an amount conflict in a fixed-list file."""
    hh = set()
    for name, d in annotated.items():
        if SPECS[name].fixed_list:
            hh |= set(d.loc[d["key_conflict"].eq("amount"), "hhid"].astype(np.int64))
    return hh


def set_use_in_totals(annotated: dict[str, pd.DataFrame]) -> set[int]:
    """Add `use_in_totals` to every annotated file and return the version-conflict households."""
    version_hh = version_conflicts(annotated)
    for d in annotated.values():
        hh = d["hhid"].astype(np.int64)
        amount_conflict_hh = set(hh[d["key_conflict"].eq("amount")])
        d["use_in_totals"] = ~hh.isin(version_hh | amount_conflict_hh)
    return version_hh


def clean_frame(annotated: pd.DataFrame) -> pd.DataFrame:
    """Kept rows with their original columns plus the audit columns."""
    keep = annotated["drop_reason"].isna()
    return (annotated.loc[keep]
            .drop(columns=["drop_reason"])
            .reset_index(drop=True))


def dropped_log(annotated: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per removed row: file, raw position, key, reason and the kept row it matches."""
    parts = []
    for name, d in annotated.items():
        spec = SPECS[name]
        x = d.loc[d["drop_reason"].notna()]
        parts.append(pd.DataFrame({
            "file": spec.file,
            "row_in_file": x["row_in_file"].to_numpy(),
            "hhid": x["hhid"].astype(np.int64).to_numpy(),
            "item": x[spec.item].to_numpy(),
            "drop_reason": x["drop_reason"].astype(str).to_numpy(),
            "matches_row": x["matches_row"].to_numpy(),
            "amount_sum": x[list(spec.amounts)].sum(axis=1, min_count=1).to_numpy(),
        }))
    return pd.concat(parts, ignore_index=True)


def household_flags(annotated: dict[str, pd.DataFrame], version_hh: set[int]) -> pd.DataFrame:
    """One row per household with row counts and the flags downstream code needs."""
    out = None
    for name, d in annotated.items():
        hh = d["hhid"].astype(np.int64)
        conflict_rank = d["key_conflict"].map(CONFLICT_RANK)
        f = pd.DataFrame({
            f"{name}_raw_rows": hh.groupby(hh).size(),
            f"{name}_clean_rows": d["drop_reason"].isna().groupby(hh).sum(),
            f"{name}_max_copies": d["n_raw_copies"].groupby(hh).max(),
            f"{name}_key_conflict": conflict_rank.groupby(hh).max().map({v: k for k, v in CONFLICT_RANK.items()}),
            f"{name}_use_in_totals": d["use_in_totals"].groupby(hh).all(),
        })
        out = f if out is None else out.join(f, how="outer")
    out["s9_repeated"] = out.filter(like="_max_copies").gt(1).any(axis=1)
    out["s9_version_conflict"] = out.index.isin(sorted(version_hh))
    return out.reset_index()


def run(write: bool = True) -> dict:
    """Run rules 1-4 on all four files and optionally write the outputs to `data/interim/`."""
    raw = {s.name: load_raw(s) for s in S9_FILES}
    annotated = {name: annotate(r, SPECS[name]) for name, r in raw.items()}
    version_hh = set_use_in_totals(annotated)
    clean = {name: clean_frame(d) for name, d in annotated.items()}
    dropped = dropped_log(annotated)
    flags = household_flags(annotated, version_hh)
    if write:
        INTERIM_DIR.mkdir(parents=True, exist_ok=True)
        for name, c in clean.items():
            c.to_parquet(INTERIM_DIR / SPECS[name].out, index=False)
        dropped.to_parquet(INTERIM_DIR / "s9_dedup_dropped_rows.parquet", index=False)
        flags.to_parquet(INTERIM_DIR / "s9_dedup_household_flags.parquet", index=False)
    return {"raw": raw, "annotated": annotated, "clean": clean, "dropped": dropped,
            "flags": flags, "version_conflict_hh": version_hh}


def stage_totals(annotated: pd.DataFrame, spec: S9File) -> pd.DataFrame:
    """Rows, households with an amount and weighted totals at each cleaning stage."""
    stages = {
        "0 raw": pd.Series(True, index=annotated.index),
        "1 exact repeats removed": annotated["drop_reason"].fillna("").ne("exact_repeat"),
        "2 clean file (all kept rows)": annotated["drop_reason"].isna(),
        "3 clean, use_in_totals only": annotated["drop_reason"].isna() & annotated["use_in_totals"],
    }
    rows = []
    for stage, m in stages.items():
        x = annotated.loc[m]
        for a in spec.amounts:
            v = x[a]
            rows.append({"file": spec.name, "stage": stage, "amount": a, "rows": len(x),
                         "households_with_amount": x.loc[v.gt(0), "hhid"].nunique(),
                         "sum_rwf": v.sum(), "weighted_sum_rwf": (v * x["weight"]).sum()})
    return pd.DataFrame(rows)
