# NISR CPI data inventory: September 2026 release

Inspected 2026-10-15. The original workbook was opened read-only and not modified (SHA-256 unchanged after inspection).

## Source files

| File | Source | Size | SHA-256 |
|---|---|---|---|
| `data/external/prices/CPI_time_series_September_2026.xls` | [NISR CPI September 2026 page](https://statistics.gov.rw/statistical-publications/price-indices-cpi-ppi/consumer-price-index-cpi-september-2026) | 14.5 MB | `2e5ebfe1b867b81ae0ebb325cd6ffe19ab00a2373142b26d68ff26171a4d03a2` |
| `docs/source_documentation/prices/SEPTEMBER_2026_CPI_Report_English.pdf` | same page | 1.7 MB, 13 pages | `7d0c0c09c52c03728b6ac354654eed4e4cc402b0ede3e70e2e1fa09d699e7c50` |

- Publisher: National Institute of Statistics of Rwanda (NISR). Released 10 October 2026. Licensed CC BY 4.0.
- Format: legacy Excel 97-2003 (`.xls`, BIFF8). Reading it in Python needs `xlrd` (`openpyxl` cannot open `.xls`).

## Sheets

| # | Sheet | Visible | Size (rows × cols) | Contents |
|---|---|---|---|---|
| 0 | `Urban` | yes | 24 × 217 | **Table A: Urban CPI** (headline index for monetary policy) |
| 1 | `Other_Indices` | yes | 16 × 217 | **Table B: Other indices, Urban only** (local/imported, fresh, energy, core) |
| 2 | `Rural` | yes | 24 × 217 | **Table C: Rural CPI** |
| 3 | `All Rwanda` | yes | 25 × 217 | **Table D: Rwanda (national) CPI** |
| 4 | `Data` | hidden | 2,522 × 157 | Legacy back-end table, Feb 2009 – May 2014 only. Do not use. |
| 5 | `DataCore` | hidden | 952 × 163 | Legacy core/non-core back-end, Feb 2009 – May 2014 only. Do not use. |
| 6 | `DataLocImp` | hidden | 1,087 × 160 | Legacy local/imported back-end, Feb 2009 – May 2014 only. Do not use. |

### Which sheet holds what

| Need | Sheet | Row (Excel, 1-based) | Selector |
|---|---|---|---|
| Urban CPI (general) | `Urban` | 6 | `U_R = 1`, `COICOP = "00"` |
| Rural CPI (general) | `Rural` | 6 | `U_R = 2`, `COICOP = "00"` |
| Rwanda CPI (general) | `All Rwanda` | 6 | `U_R = 0`, `COICOP = "00"` |
| Category-level CPI, by area | `Urban` / `Rural` / `All Rwanda` | 7–23 | 12 COICOP divisions plus 5 food sub-groups |
| Local, imported, fresh, energy, core | `Other_Indices` | 5–15 | Urban only. Identify rows by label (see note below). |

## Layout of the visible sheets

The data is in wide format: one row per series and one column per month.

**`Urban`, `Rural`, `All Rwanda`**

| Excel row | Content |
|---|---|
| 1–3 | Titles in column D: table letter, series name, `Base: 2014; Reference: February 2014=100` |
| 4 | Header: `Weights` in E; month dates in F … HI |
| 5 | Key labels: `Province` (A), `U_R` (B), `COICOP` (C) |
| 6–23 | Data: 18 series |
| 24 | Footer: `Source: National Institute of Statistics of Rwanda` |

| Column | Field | Notes |
|---|---|---|
| A | `Province` | Always `0` (national level). No provincial breakdown is published. |
| B | `U_R` | `0` = All Rwanda, `1` = Urban, `2` = Rural |
| C | `COICOP` | Text code: `00`, `01`, `01.1.1`, … |
| D | Label | Sub-items are prefixed with `v` plus non-breaking spaces (`\xa0`). Strip these before use. |
| E | Weight | Parts per 10,000. The 12 divisions sum to exactly 10,000. |
| F–HI | Index values | 212 monthly columns |

**`Other_Indices`** has a different layout. Header labels are in A3:C4 (`Core_non Core`, `Local_Imp`, `UrbanRural`, `COICOP`), data is in rows 5–15, and there is no separate key-label row.

## Date format

- Header cells are **Excel date serials** (xlrd cell type `XL_CELL_DATE`), one per month.
- Coverage is **February 2009 to September 2026**: 212 consecutive months, with no gaps and no duplicates on any sheet.
- **The day part has no meaning.** It is the 1st up to March 2018 and the 10th from April 2018 onward. In the `Urban` sheet it also drifts (2nd, 3rd, 5th, … 29th) between August 2014 and March 2018. Convert each date to a monthly period (`YYYY-MM`) and discard the day.
- The hidden sheets use text `YYYYMM` codes instead (for example `"200902"`).

## Index base period

- **Base: 2014. Reference period: February 2014 = 100.**
- Verified: every series on all four visible sheets equals exactly 100.0 in February 2014.
- The 2014 annual average is **not** 100 (Urban 100.6, Rural 102.5, Rwanda 101.8). When deflating, rebase explicitly if you need a calendar-year base.
- Weights come from **EICV4 (2013/14)**, with 14,419 households. The index uses a modified Laspeyres formula (report, p. 8).
- Prices collected each month: more than 29,482 urban and 10,744 rural quotes, covering 1,622 products. The urban index covers 12 urban centres.

## Available categories

Weights are parts per 10,000. Year-on-year (YoY) changes compare September 2026 with September 2025 and were computed from the workbook.

| COICOP | Category | Urban wt | Rural wt | Rwanda wt | Urban YoY % | Rural YoY % | Rwanda YoY % |
|---|---|---:|---:|---:|---:|---:|---:|
| 00 | General index (CPI) | 10,000.0 | 10,000.0 | 10,000.0 | 17.2 | 22.0 | 20.0 |
| 01 | Food and non-alcoholic beverages | 2,737.9 | 4,804.2 | 3,903.5 | 20.9 | 27.0 | 25.2 |
| 01.1.1 | ↳ Bread and cereals | 539.4 | 757.2 | 662.3 | 6.4 | 4.1 | 4.8 |
| 01.1.2 | ↳ Meat | 197.4 | 155.5 | 173.8 | 33.6 | 26.4 | 29.7 |
| 01.1.4 | ↳ Milk, cheese and eggs | 132.1 | 98.2 | 113.0 | 11.6 | 13.0 | 12.3 |
| 01.1.7 | ↳ Vegetables | 885.6 | 2,582.5 | 1,842.9 | 35.1 | 38.5 | 37.8 |
| 01.2 | ↳ Non-alcoholic beverages | 132.1 | 101.1 | 114.6 | 8.8 | 10.5 | 9.6 |
| 02 | Alcoholic beverages and tobacco | 485.3 | 831.9 | 680.8 | 9.2 | 6.9 | 7.7 |
| 03 | Clothing and footwear | 530.8 | 531.2 | 531.0 | 5.3 | 5.2 | 5.3 |
| 04 | Housing, water, electricity, gas and other fuels | 2,075.5 | 1,636.4 | 1,827.8 | 18.3 | 19.7 | 19.1 |
| 05 | Furnishing, household equipment and routine maintenance | 375.5 | 323.1 | 345.9 | 7.7 | 13.4 | 10.8 |
| 06 | Health | 132.5 | 112.2 | 121.1 | 1.3 | 3.7 | 2.5 |
| 07 | Transport | 1,245.2 | 407.5 | 772.6 | 22.4 | 38.7 | 26.0 |
| 08 | Communication | 314.3 | 179.3 | 238.1 | 6.0 | 54.8 | 29.1 |
| 09 | Recreation and culture | 307.2 | 149.4 | 218.1 | 5.5 | 18.1 | 11.0 |
| 10 | Education | 274.9 | 143.9 | 201.0 | 8.6 | 28.5 | 18.0 |
| 11 | Restaurants and hotels | 882.1 | 460.0 | 644.0 | 18.9 | 12.4 | 16.0 |
| 12 | Miscellaneous goods and services | 638.9 | 421.0 | 516.0 | 18.3 | 7.9 | 13.4 |

The five food sub-groups are a **selection, not a full breakdown**. Together they make up 1,886.6 of the 2,737.9 urban food weight. Fish, oils and fats, fruit, sugar and other food groups are not published separately.

### `Other_Indices` (Urban only)

| Col A code | COICOP | Index | Weight | MoM % | YoY % |
|---|---|---|---:|---:|---:|
| 1 | 00 | Local goods index | 7,731.1 | 3.4 | 19.8 |
| 1 | 01 | ↳ Food and non-alcoholic beverages | 2,082.2 | 6.4 | 24.7 |
| 1 | 04 | ↳ Housing, water, electricity, gas and other fuels | 2,071.2 | 0.1 | 18.3 |
| 1 | 07 | ↳ Transport | 642.6 | 0.5 | 30.6 |
| 2 | 00 | Imported goods index | 2,268.9 | 0.5 | 9.7 |
| 2 | 01 | ↳ Food and non-alcoholic beverages | 655.7 | 1.2 | 8.5 |
| 2 | 04 | ↳ Furnishing, household equipment | 217.1 | 0.7 | 5.9 |
| 2 | 07 | ↳ Transport | 602.6 | −0.1 | 16.2 |
| 2 | 00 | Fresh products index (food with seasonal fluctuations) | 1,576.5 | 7.7 | 27.9 |
| 3 | 00 | Energy index | 676.0 | 0.2 | 45.0 |
| 1 | 00 | Core: general index excluding fresh products and energy | 7,747.5 | 1.3 | 11.4 |

MoM is the month-on-month change from August to September 2026.

## Validation against the PDF report

| Check | Workbook | PDF | Result |
|---|---|---|---|
| Urban, YoY / MoM | 17.2 / 2.7 | 17.2 / 2.7 (Table 1) | ✅ match |
| Rural, YoY / MoM | 22.0 / 6.5 | 22.0 / 6.5 (Table 1) | ✅ match |
| Rwanda, YoY / MoM | 20.0 / 5.0 | 20.0 / 5.0 (Table 1) | ✅ match |
| Urban divisions, YoY | see category table | Table 2 | ✅ all 18 rows match |
| `Other_Indices`, YoY / MoM | see table above | Table 4 | ✅ all 11 rows match |

## Caveats for analysis

1. **Do not use column A as a row key in `Other_Indices`.** The codes are reused: `1` marks local goods and also core, and `2` marks imported goods and also fresh products. Several rows share the same COICOP code (`00`). Select rows by label or by position.
2. **Label and code mismatch in `Other_Indices`.** The imported row with code `04` is labelled "Furnishing, household equipment", which is COICOP 05. The PDF uses the same label, so this is NISR's labelling and not a parsing error.
3. **There is no provincial CPI.** The hidden `Data` sheet has province codes 1–5, but those rows are empty or zero for every month.
4. **Hidden sheets are stale.** They only contain values for February 2009 to May 2014, and their weights differ from the published ones (for example, food is 44.1% there against 39.0% in `All Rwanda`). Ignore them.
5. **Rural communication jumped 54.8% in a single month (August 2026),** and Rwanda communication rose 25.3%. Rural education rose 27.6% in September 2026. These look like real price events (tariff or fee changes), not data errors, but check them before using these categories as deflators.
6. **The weights come from a different survey round.** CPI weights are from EICV4 (2013/14), while the project microdata is EICV7. Expenditure shares in EICV7 will differ from these weights. Keep this in mind when building group-specific deflators.
7. **Urban and rural are the only spatial split.** To deflate EICV7 household data, match on urban/rural status and survey month.

## Loading example

```python
import pandas as pd  # requires: pip install xlrd

path = "data/external/prices/CPI_time_series_September_2026.xls"

def load_cpi(sheet: str, area: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="xlrd")
    dates = pd.to_datetime(raw.iloc[3, 5:]).dt.to_period("M")  # discard the meaningless day
    body = raw.iloc[5:23, :].reset_index(drop=True)
    keys = pd.DataFrame({
        "area": area,
        "coicop": body[2].astype(str),
        "label": body[3].str.replace("\xa0", " ").str.replace(r"^v\s+", "", regex=True).str.strip(),
        "weight": body[4].astype(float),
    })
    values = body.iloc[:, 5:].astype(float).set_axis(dates, axis=1)
    out = pd.concat([keys, values], axis=1)
    return out.melt(id_vars=list(keys.columns), var_name="period", value_name="cpi")

cpi = pd.concat([load_cpi("Urban", "urban"), load_cpi("Rural", "rural"), load_cpi("All Rwanda", "rwanda")])
```
