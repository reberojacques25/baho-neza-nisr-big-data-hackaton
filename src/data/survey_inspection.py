"""Read-only inspection of the EICV7 and FinScope 2024 Stata files.

Profiles every dataset without changing it: metadata, keys, weights, missingness,
value-label coverage and topic tags. Used by notebooks/04_eicv7_finscope_inspection.ipynb.

Nothing here cleans, recodes or models the data. Files are streamed in chunks so
the 1.1 GB food file never has to fit in memory at once.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.io.stata import StataReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EICV7_DIR = PROJECT_ROOT / "Microdata" / "Cross_Section"
FINSCOPE_DIR = PROJECT_ROOT / "FINSCOPE_DATA"
REPORT_DIR = PROJECT_ROOT / "reports" / "data_inspection"

CHUNKSIZE = 250_000
DK_REFUSED_PATTERN = re.compile(r"don'?t know|do not know|refus|not applicable|\bdk\b|not stated|no answer", re.I)
SENTINEL_VALUES = (-99, -98, -9, -8, 9999, 99999, 999999, 9999999, 99999999)


@dataclass(frozen=True)
class Dataset:
    name: str
    survey: str
    file: str
    unit: str
    key: tuple[str, ...]
    description: str
    item_var: str | None = None  # code variable for long item-level modules
    topics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def path(self) -> Path:
        return (FINSCOPE_DIR if self.survey == "FinScope 2024" else EICV7_DIR) / self.file


E, F = "EICV7", "FinScope 2024"
DATASETS = [
    Dataset("poverty", E, "CS_EICV7_poverty_file.dta", "household", ("hhid",),
            "NISR consumption aggregates, poverty status and weights (January 2024 prices)",
            topics=("poverty_consumption", "survey_weight")),
    Dataset("household", E, "CS_S01_S5_S7_Household.dta", "household", ("hhid",),
            "Housing, utilities, sanitation, shocks (S5) and livestock (S7)",
            topics=("housing", "assets", "shocks")),
    Dataset("person", E, "CS_S0_S1_S2_S3_S4_S6A_S6B_S6C_Person.dta", "person", ("hhid", "pid"),
            "Demographics, migration, health, education, ICT and employment (S1-S4, S6)",
            topics=("demographics", "education", "employment", "health")),
    Dataset("credit", E, "CS_S10A1_A2_credits.dta", "loan", ("hhid", "s10aq4"),
            "Loans applied for and owed (S10A)", topics=("financial_inclusion",)),
    Dataset("durables", E, "CS_S10B_durables.dta", "household x durable item", ("hhid", "s10bq0"),
            "Durable goods owned, purchase year and value (S10B)", item_var="s10bq0", topics=("assets",)),
    Dataset("savings", E, "CS_S10C_Savings.dta", "account", ("hhid", "s10cq3"),
            "Accounts (bank, SACCO, mobile money) and tontines (S10C)", topics=("financial_inclusion",)),
    Dataset("services", E, "CS_S5F_access_to_services.dta", "household x service", ("hhid", "s5fq0"),
            "Use of, distance and travel time to 15 basic services (S5F)", item_var="s5fq0", topics=("service_access",)),
    Dataset("nonfood_annual", E, "CS_S8A1_Expenditure.dta", "household x item", ("hhid", "s8a1q0"),
            "Non-food purchases, 12-month recall (S8A1)", item_var="s8a1q0", topics=("nonfood_expenditure",)),
    Dataset("nonfood_monthly", E, "CS_S8A2_Expenditure.dta", "household x item", ("hhid", "s8a2q0"),
            "Non-food purchases, 4-week recall (S8A2)", item_var="s8a2q0", topics=("nonfood_expenditure",)),
    Dataset("nonfood_weekly", E, "CS_S8A3_Expenditure.dta", "household x item", ("hhid", "s8a3q0"),
            "Frequent non-food purchases and own production, 7-day recall (S8A3)", item_var="s8a3q0",
            topics=("nonfood_expenditure",)),
    Dataset("food", E, "CS_S8B_Food_Expenditure_Consumption.dta", "household x food item", ("hhid", "s8bq0"),
            "Food purchases and consumption over diary visits 2-5 (S8B)", item_var="s8bq0", topics=("food_expenditure",)),
    Dataset("food_away", E, "CS_S8C_Food_Away_from_home.dta", "person", ("hhid", "pid"),
            "Meals and drinks consumed away from home, visits 2-5 (S8C)", topics=("food_expenditure",)),
    Dataset("transfers_out", E, "CS_S9A_transfers_out.dta", "transfer sent", ("hhid", "s9aq2a", "s9aq2"),
            "Cash, food and in-kind transfers sent (S9A)", topics=("income_transfers",)),
    Dataset("transfers_in", E, "CS_S9B_transfers_in.dta", "transfer received", ("hhid", "s9bq1a", "s9bq2", "s9bq3"),
            "Cash transfers received (S9B)", topics=("income_transfers",)),
    Dataset("other_expenditure", E, "CS_S9C_other_expenditure.dta", "household x item", ("hhid", "s9cq1"),
            "Taxes, contributions, ceremonies and gifts (S9C)", item_var="s9cq1", topics=("nonfood_expenditure",)),
    Dataset("vup_direct_support", E, "CS_S9D1_Direct_Support.dta", "household (x beneficiary)", ("hhid", "pid"),
            "VUP direct support (S9D1)", topics=("social_protection",)),
    Dataset("vup_classic_pw", E, "CS_S9D2_Classic_Public_Work.dta", "household", ("hhid",),
            "VUP classic public works (S9D2)", topics=("social_protection",)),
    Dataset("vup_expanded_pw", E, "CS_S9D3_Expanded_Public_Work.dta", "household (x beneficiary)", ("hhid", "pid"),
            "VUP expanded public works (S9D3)", topics=("social_protection",)),
    Dataset("vup_nsds", E, "CS_S9D4_NSDS.dta", "household (x beneficiary)", ("hhid", "pid"),
            "Nutrition-sensitive direct support (S9D4)", topics=("social_protection",)),
    Dataset("vup_financial_services", E, "CS_S9D5_Financial_Services.dta", "household", ("hhid",),
            "VUP financial services loans (S9D5)", topics=("social_protection", "financial_inclusion")),
    Dataset("other_income", E, "CS_S9E_other_income.dta", "household x income source", ("hhid", "s9eq1"),
            "Pensions, public transfers, rents, farm income and other receipts (S9E)", item_var="s9eq1",
            topics=("income_transfers", "social_protection")),
    Dataset("finscope", F, "FinScope 2024 Rwanda.dta", "adult respondent (one per household)", ("key",),
            "FinScope Rwanda 2024 consumer survey, adults 16+",
            topics=("financial_inclusion", "demographics", "income_transfers")),
]
DATASETS_BY_NAME = {d.name: d for d in DATASETS}

GEO_VARS = {"province", "district", "ur", "clust", "strata_id", "a1", "a2", "a6"}
WEIGHT_VARS = {"weight", "pop_wt", "hh_wt"}
ID_VARS = {"hhid", "pid", "key"}
POVERTY_VARS = {"quintile", "pov_jan", "poverty", "epov_jan"}


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def read_metadata(ds: Dataset) -> tuple[pd.DataFrame, dict, int]:
    """Variable names, labels, storage types and value labels, without reading data.

    ``meta.attrs["latin1_fallback"]`` is True when some labels are not valid UTF-8.
    """
    with warnings.catch_warnings(record=True) as caught, StataReader(ds.path) as reader:
        warnings.simplefilter("always", UnicodeWarning)
        variable_labels = reader.variable_labels()
        value_labels = reader.value_labels()
        reader._ensure_open()
        nobs = reader._nobs
        label_names = dict(zip(reader._varlist, reader._lbllist))
        types = dict(zip(reader._varlist, reader._typlist))
    stata_type = {"b": "byte", "h": "int", "l": "long", "f": "float", "d": "double"}
    meta = pd.DataFrame(
        {
            "survey": ds.survey,
            "dataset": ds.name,
            "position": range(len(variable_labels)),
            "variable": list(variable_labels),
            "label": [str(v).strip() for v in variable_labels.values()],
            "stata_type": [
                f"str{types[v]}" if isinstance(types[v], int) else stata_type.get(types[v], str(types[v]))
                for v in variable_labels
            ],
            "value_label_name": [label_names.get(v, "") or "" for v in variable_labels],
        }
    )
    meta["n_value_labels"] = [len(value_labels.get(n, {})) for n in meta["value_label_name"]]
    meta.attrs["latin1_fallback"] = any(issubclass(w.category, UnicodeWarning) for w in caught)
    return meta, value_labels, nobs


def value_labels_for(ds: Dataset, variable: str) -> dict:
    """Value labels attached to one variable ({} if none)."""
    meta, value_labels, _ = read_metadata(ds)
    name = meta.set_index("variable").loc[variable, "value_label_name"]
    return value_labels.get(name, {})


def format_value_labels(labels: dict, max_chars: int = 400) -> str:
    text = "; ".join(f"{_fmt_code(k)}={str(v).strip()}" for k, v in sorted(labels.items()))
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def _fmt_code(code) -> str:
    return str(int(code)) if float(code).is_integer() else str(code)


# --------------------------------------------------------------------------- #
# Profiling
# --------------------------------------------------------------------------- #
class _VarStats:
    """Streaming statistics for one variable."""

    def __init__(self, track_counts: bool):
        self.n = self.n_missing = self.n_zero = self.n_negative = self.n_sentinel = 0
        self.total = self.total_sq = 0.0
        self.min = self.max = None
        self.numeric_uniques = np.array([], dtype="float64")
        self.string_uniques: set[str] = set()
        self.counts = {} if track_counts else None
        self.max_len = 0
        self.is_string = False

    def update(self, s: pd.Series) -> None:
        self.n += len(s)
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            self.is_string = True
            s = s.astype("string").str.strip()
            missing = s.isna() | s.eq("")
            self.n_missing += int(missing.sum())
            values = s[~missing]
            if len(values):
                self.max_len = max(self.max_len, int(values.str.len().max()))
                self.string_uniques.update(values.unique())
            return
        values = s.dropna().to_numpy(dtype="float64")
        self.n_missing += len(s) - len(values)
        if not len(values):
            return
        self.total += values.sum()
        self.total_sq += np.square(values).sum()
        self.n_zero += int((values == 0).sum())
        self.n_negative += int((values < 0).sum())
        self.n_sentinel += int(np.isin(values, SENTINEL_VALUES).sum())
        self.min = values.min() if self.min is None else min(self.min, values.min())
        self.max = values.max() if self.max is None else max(self.max, values.max())
        codes, counts = np.unique(values, return_counts=True)
        self.numeric_uniques = np.union1d(self.numeric_uniques, codes)
        if self.counts is not None:
            for c, k in zip(codes, counts):
                self.counts[c] = self.counts.get(c, 0) + int(k)

    def result(self, labels: dict) -> dict:
        n_valid = self.n - self.n_missing
        out = {
            "n_rows": self.n,
            "n_missing": self.n_missing,
            "pct_missing": round(100 * self.n_missing / self.n, 2) if self.n else np.nan,
            "n_unique": len(self.string_uniques) if self.is_string else len(self.numeric_uniques),
        }
        if self.is_string:
            out.update({"kind": "string", "max_length": self.max_len})
            return out
        mean = self.total / n_valid if n_valid else np.nan
        var = self.total_sq / n_valid - mean**2 if n_valid else np.nan
        out.update(
            {
                "kind": "numeric",
                "min": self.min,
                "max": self.max,
                "mean": mean,
                "std": float(np.sqrt(max(var, 0))) if n_valid else np.nan,
                "n_zero": self.n_zero,
                "n_negative": self.n_negative,
            }
        )
        if labels:
            dk_codes = [c for c, text in labels.items() if DK_REFUSED_PATTERN.search(str(text))]
            counts = self.counts or {}
            out["n_dk_refused"] = int(sum(counts.get(float(c), 0) for c in dk_codes))
            out["dk_refused_codes"] = ", ".join(_fmt_code(c) for c in dk_codes)
            unlabelled = [c for c in counts if c not in {float(k) for k in labels}]
            out["n_unlabelled_values"] = int(sum(counts[c] for c in unlabelled))
            out["unlabelled_codes"] = ", ".join(_fmt_code(c) for c in sorted(unlabelled)[:15])
        else:
            out["n_possible_sentinel"] = self.n_sentinel
        return out


@dataclass
class DatasetProfile:
    dataset: Dataset
    variables: pd.DataFrame  # one row per variable
    frame: pd.DataFrame  # the requested columns, all rows
    n_rows: int
    n_exact_duplicate_rows: int
    latin1_fallback: bool  # some labels are not valid UTF-8


def profile_dataset(ds: Dataset, keep: list[str] | None = None, chunksize: int = CHUNKSIZE) -> DatasetProfile:
    """Stream one file once: per-variable statistics plus the ``keep`` columns.

    Reads codes, not labels (``convert_categoricals=False``), so the stored values
    are what gets profiled.
    """
    meta, value_labels, _ = read_metadata(ds)
    labels_for = {v: value_labels.get(n, {}) for v, n in zip(meta["variable"], meta["value_label_name"])}
    stats = {v: _VarStats(track_counts=bool(labels_for[v])) for v in meta["variable"]}
    kept, row_hashes = [], []
    with warnings.catch_warnings(), pd.read_stata(ds.path, convert_categoricals=False, chunksize=chunksize) as reader:
        warnings.simplefilter("ignore", UnicodeWarning)  # already recorded by read_metadata
        for chunk in reader:
            for v in chunk.columns:
                stats[v].update(chunk[v])
            row_hashes.append(pd.util.hash_pandas_object(chunk, index=False).to_numpy())
            if keep:
                kept.append(chunk[[c for c in keep if c in chunk.columns]].copy())
    hashes = np.concatenate(row_hashes)
    variables = meta.merge(
        pd.DataFrame([{"variable": v, **stats[v].result(labels_for[v])} for v in meta["variable"]]),
        on="variable",
        how="left",
    )
    variables["value_labels"] = [format_value_labels(labels_for[v]) if labels_for[v] else "" for v in variables["variable"]]
    variables["topic"] = [classify_topic(ds, v, lbl) for v, lbl in zip(variables["variable"], variables["label"])]
    variables["role"] = [variable_role(ds, v) for v in variables["variable"]]
    return DatasetProfile(
        dataset=ds,
        variables=variables,
        frame=pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(),
        n_rows=len(hashes),
        n_exact_duplicate_rows=int(len(hashes) - len(np.unique(hashes))),
        latin1_fallback=meta.attrs["latin1_fallback"],
    )


# --------------------------------------------------------------------------- #
# Topic tags
# --------------------------------------------------------------------------- #
def variable_role(ds: Dataset, var: str) -> str:
    if var in ds.key:
        return "key"
    if var in ID_VARS:
        return "identifier"
    if var in WEIGHT_VARS:
        return "weight"
    if var in {"clust", "strata_id"}:
        return "design"
    if var in GEO_VARS:
        return "geography"
    if ds.item_var == var:
        return "item_code"
    return "attribute"


_PERSON_PREFIX = [
    (r"^s1q", "demographics"), (r"^s2q", "demographics"), (r"^s3q", "health"),
    (r"^s4aq|^ed_", "education"), (r"^s4bq[1-7]$", "education"), (r"^s4bq23c$", "financial_inclusion"),
    (r"^s4bq", "ict"), (r"^s6bq9", "income_transfers"), (r"^s6", "employment"),
]
_HOUSEHOLD_PREFIX = [(r"^s5eq", "shocks"), (r"^s7", "assets"), (r"^s5[a-d]q", "housing")]
_FINSCOPE_PREFIX = [
    (r"^(hh_size|hh_head|bo|b\d)", "demographics"), (r"^c(1c|4a)", "education"), (r"^c[678]", "housing"),
    (r"^c", "demographics"), (r"^e\d", "financial_capability"), (r"^(qf|uf|k\d|f\d|g\d|h\d|i\d?|l\d|p\d|total_p)", "financial_inclusion"),
    (r"^j\d", "income_transfers"), (r"^n4|^n5|^n9", "employment"), (r"^n", "income_transfers"),
    (r"^m\d", "agriculture"), (r"^d\d", "service_access"), (r"^cc", "shocks"),
]


def classify_topic(ds: Dataset, var: str, label: str) -> str:
    """Assign one analysis topic per variable from the module and variable name."""
    if var in ID_VARS:
        return "identifier"
    if var in WEIGHT_VARS:
        return "survey_weight"
    if var in GEO_VARS:
        return "geography"
    if var in POVERTY_VARS or ds.name == "poverty":
        return "poverty_consumption"
    if ds.name == "person":
        rules = _PERSON_PREFIX
    elif ds.name == "household":
        rules = _HOUSEHOLD_PREFIX
    elif ds.name == "finscope":
        rules = _FINSCOPE_PREFIX
    else:
        return ds.topics[0]
    for pattern, topic in rules:
        if re.match(pattern, var):
            return topic
    return "other"


# --------------------------------------------------------------------------- #
# Quality checks
# --------------------------------------------------------------------------- #
def key_check(frame: pd.DataFrame, key: tuple[str, ...]) -> dict:
    dup = frame.duplicated(list(key), keep=False)
    return {
        "key": " + ".join(key),
        "n_key_missing": int(frame[list(key)].isna().any(axis=1).sum()),
        "n_duplicate_key_rows": int(dup.sum()),
        "key_unique": not dup.any(),
    }
