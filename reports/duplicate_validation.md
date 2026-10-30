# Duplicate validation: EICV7 section 9 files

Run on 2026-10-16. Original `.dta` files were only read, never modified.

- **Notebook:** `notebooks/05_duplicate_validation.ipynb` (runs in under 30 seconds)
- **Code:** `src/data/deduplicate_s9.py`
- **Outputs in `data/interim/`:**

| File | Rows | Contents |
|---|---:|---|
| `s9a_transfers_out_dedup.parquet` | 66,861 | Clean S9A, unique on `hhid` + `s9aq2a` |
| `s9b_transfers_in_dedup.parquet` | 30,677 | Clean S9B, unique on `hhid` + `s9bq3` |
| `s9c_other_expenditure_dedup.parquet` | 195,702 | Clean S9C, exactly 13 items per household |
| `s9e_other_income_dedup.parquet` | 391,404 | Clean S9E, exactly 26 sources per household |
| `s9_dedup_dropped_rows.parquet` | 12,648 | Every removed row: file, raw row position, key, reason, the kept row it matches |
| `s9_dedup_household_flags.parquet` | 15,054 | One row per household: row counts, conflict type and `use_in_totals` per file |

The clean files keep every original column and value. They add `row_in_file`, `n_raw_copies`, `matches_row`, `key_conflict` and `use_in_totals`.

## Summary

1. **The duplicates come from one source.** 222 households had their whole section 9 written out twice. They are the same households in all four files. They sit in 32 of 1,674 clusters, where 222 of the 288 sampled households are affected. Almost half (108) are in rural Rutsiro. The cause is not documented; the pattern points to data processing, not questionnaire design.
2. **No legitimate rows were removed.** Several recipients, senders or items per household are normal and were kept. Only rows repeating an existing key were dropped.
3. **Doubling distorts households, not national totals.** For every doubled household with a positive amount, the raw total was exactly **twice** the clean total. National weighted totals fall by only 0.6–2.3% (4.0% for the 4-week income amount).
4. **Four households have two different versions of section 9:** `hhid` [ID withheld], [ID withheld], [ID withheld] and [ID withheld]. Neither version can be confirmed, so their section 9 totals are flagged unusable and must be treated as missing. One more household ([ID withheld]) has one conflicting transfer-out row and is flagged in S9A only.
5. **All 24 checks pass.** Each clean file is unique on its key and covers all 15,054 households. Kept rows are identical to their raw rows, and kept plus dropped rows equal the raw row count.

## 1. Keys

Questionnaire evidence: `EICV7_Final_Questionnaire_English.pdf`, PDF pages 60–62 and 70.

| File | One row is | Key |
|---|---|---|
| S9A transfers out | one recipient (`s9aq2a` = line number); one "no" row (`s9aq0` = 2) if none | `hhid` + `s9aq2a` |
| S9B transfers in | one sender (`s9bq3` = line number); one "no" row (`s9bq0` = 2) if none | `hhid` + `s9bq3` |
| S9C other expenditure | one of 13 fixed items, asked of every household | `hhid` + `s9cq1` |
| S9E other income | one of 26 fixed sources, asked of every household | `hhid` + `s9eq1` |

Notebook 04 recorded "no unique key" for these files because the repeats break every candidate key. The keys above hold once repeats are removed. Notebook 04 also tested wider S9A and S9B keys (with `s9aq2`, `s9bq1a` and `s9bq2`); the line numbers alone are enough.

## 2. What the duplicates are

| | S9A | S9B | S9C | S9E |
|---|---:|---:|---:|---:|
| Raw rows | 68,175 | 33,353 | 198,588 | 397,176 |
| Kept: several items in the household (legitimate) | 63,579 | 21,170 | 195,702 | 391,404 |
| Kept: single row in the household | 3,282 | 9,507 | 0 | 0 |
| **Dropped: exact repeat** | 1,292 | 2,670 | 2,859 | 5,749 |
| Dropped: contradictory "no" row | 5 | 2 | 0 | 0 |
| Dropped: key conflict, amounts agree | 2 | 0 | 0 | 0 |
| Dropped: key conflict, amounts differ | 15 | 4 | 27 | 23 |
| **Clean rows** | 66,861 | 30,677 | 195,702 | 391,404 |
| Households with exact repeats | 202 | 166 | 222 | 222 |
| Households not usable for totals | 5 | 4 | 4 | 4 |

**Exact repeats (12,570 rows).** Rows identical on every variable. There are two kinds.

- **Doubled sections.** 222 households appear twice in S9C and S9E. Of these, 200 also repeat in S9A and 143 in S9B; there are 246 households with repeats across all files. Rural Rutsiro has 108 of them, a quarter of its 459 sampled households, in 14 of its 51 clusters.
- **Placeholder floods.** In 23 households, the single "no transfers" row in S9B appears 99 times. Household [ID withheld] also has it 99 times in S9A. These rows contain no amounts.

**Contradictory "no" rows (7 rows).** These households answered "no transfers" and also listed recipients or senders:

| File | Households | `hhid` |
|---|---:|---|
| S9A | 4 | [ID withheld], [ID withheld], [ID withheld], [ID withheld] |
| S9B | 2 | [ID withheld], [ID withheld] |

The "no" rows have no amounts.

**Key conflicts (71 rows).** A key appears twice with different content:

| Households | What conflicts | Effect |
|---|---|---|
| [ID withheld], [ID withheld], [ID withheld], [ID withheld] (version conflicts) | Repeated items in S9C and S9E with different amounts, and differing rosters in S9A and S9B | The two versions give very different totals; see below |
| [ID withheld] | S9A recipient 1: "sent cash = yes" (amount withheld) vs "sent cash = no" | Amount conflict |
| [ID withheld] | S9A recipient 4: sex differs | Amounts are equal, so totals are unaffected |
| [ID withheld] | Two S9A "no" rows; `s9aq2` is 97 in one, blank in the other | Amounts are equal, so totals are unaffected |

Totals of the version-conflict households (RWF, 12 months; version 1 = first in file order):

_Per-household amounts for these households are withheld from the public copy (individual records)._

The versions differ by up to about 100 times (for one household's other income; amounts withheld). In S9A for [ID withheld], every recipient appears twice: once as a cash-only transfer and once as a food-only transfer. These look like two separate interviews. The file does not show which one matches the household's record in the poverty file.

## 3. The dedup rule

Applied in this order by `src/data/deduplicate_s9.py`:

| Step | Applies to | Action | Effect on totals |
|---|---|---|---|
| 1. Exact repeat | A row identical to an earlier row | Drop; keep the first copy | Removes double counting |
| 2. Contradictory "no" row (S9A, S9B) | A "no transfers" row in a household that lists transfers | Drop | None |
| 3a. Key conflict, amounts agree | Same key as an earlier row; non-amount fields differ | Drop the later row; keep the first | None |
| 3b. Key conflict, amounts differ | Same key; amounts differ | Drop the later row; keep the first; set `use_in_totals = False` for that household in that file | Household total becomes missing |
| 4. Version conflict | A household with a 3b conflict in S9C or S9E | Set `use_in_totals = False` in **all four** files | Household totals become missing |

**Why step 4 covers all four files.** S9C and S9E prove the section exists in two versions. In S9A and S9B the two versions' rows cannot be separated, so picking either would be a guess.

**Why "missing" and not "keep the first".** The first version is first only in file order. Marking 4–5 households as missing (0.03% of households) is safer than choosing an answer the data cannot confirm. Every dropped row stays in the log, so the decision can be reversed.

## 4. Totals before and after

National weighted totals, using the household weight `weight`, in RWF billions. Stage 2 is the clean file. Stage 3 also excludes households flagged unusable.

| File | Amount | Raw | Exact repeats removed | Clean (stage 2) | Stage 3 | Change, raw to stage 3 |
|---|---|---:|---:|---:|---:|---:|
| S9A | `s9aq7` cash sent | 112.36 | 111.66 | 111.64 | 111.50 | −0.76% |
| S9A | `s9aq10` food sent | 76.60 | 75.77 | 75.77 | 75.68 | −1.21% |
| S9A | `s9aq12` in-kind sent | 37.40 | 37.18 | 37.17 | 37.13 | −0.73% |
| S9B | `s9bq8` cash received | 198.10 | 193.61 | 193.57 | 193.54 | −2.31% |
| S9C | `s9cq2` other expenditure | 490.03 | 486.36 | 486.20 | 486.01 | −0.82% |
| S9E | `s9eq3` other income, 4 weeks | 115.38 | 111.43 | 110.86 | 110.72 | −4.04% |
| S9E | `s9eq4` other income, 12 months | 1,279.15 | 1,266.52 | 1,265.07 | 1,264.09 | −1.18% |

- **By item.** Most items fall by 0–2%. The exception is S9E item 09, "allowance for dismissal or termination of employment", which falls by **32.7%**: two doubled households (amounts withheld) made up a large share of this rare item. Payments for medical treatment (item 02, −4.4%) and the FARG survivors' fund (item 04, −3.2%) are also above average.
- **Prevalence is unchanged.** The weighted share of households with a positive 12-month amount is the same before and after: S9A 88.90%, S9B 58.88%, S9C 96.30%, S9E 94.52%. A repeat never turns a zero into a positive amount.
- **Household level.** For every doubled household with a positive amount, raw total ÷ clean total = 2.00 in all four files. This is the error the household master table would have carried.

## 5. How to use the clean files

1. Read the clean files from `data/interim/`, never the raw section 9 files.
2. Before summing amounts to household level, keep rows with `use_in_totals == True`.
3. For households where `use_in_totals` is False, set that file's household total to **missing, not zero**. The household flags file has `{file}_use_in_totals` and `s9_version_conflict` for this join.
4. Use `s9eq4` (12 months) for annual other income. `s9eq3` is a 4-week amount.

## 6. Open points

- **Cause of the doubling.** The documentation does not explain it. It is worth asking NISR whether the 32 affected clusters, 14 of them in rural Rutsiro, were re-synced or re-entered. Other EICV7 files show no repeats for these households: notebook 04 found unique keys in the other 17 files.
- **Version-conflict households.** NISR could say which version is final for [ID withheld], [ID withheld], [ID withheld] and [ID withheld]. Until then they are missing for section 9 totals only. Their poverty, consumption and other modules are unaffected.
- **Not checked here.** Implausible amounts and don't-know codes inside kept rows. Deduplication does not alter values; extreme values will be flagged when the household master table is built.
