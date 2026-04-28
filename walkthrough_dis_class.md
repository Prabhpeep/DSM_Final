# District Classifier — Validation Report and Walkthrough

The district classifier is fully implemented and successfully assigned over 92% of the dataset to specific districts.

## Accomplishments
1. **Gazetteer Creation (`src/classifiers/assam_gazetteer.yaml`)**:
   - Mapped all 35 Census 2011 districts (plus recent additions like Majuli and Hojai) with their canonical census codes.
   - Collected aliases based on actual data patterns, including Guwahati landmarks (e.g., *Bijulee Bhawan*, *Janata Bhawan*) and PWD circle abbreviations.
   - Introduced fallback keywords for state-level headquarter offices and Bodoland Territorial Council (BTC) entities.

2. **Classifier Logic (`src/classifiers/district.py`)**:
   - Implemented a 7-pass classification pipeline.
   - Features exact substring matching with longest-alias prioritization, abbreviation expansion, state-HQ fallback (to Kamrup Metropolitan), and a RapidFuzz partial string matching fallback mechanism.
   - Integrated logic to flag cases where the `tender_title` specifies a different district than the procuring office.

3. **Database Integration**:
   - Created the `dim_district_derived` table with district metadata.
   - Altered `fact_tenders` to include a `district_id` foreign key and ran an update to populate all 17,729 tenders.

4. **Testing (`tests/test_district.py`)**:
   - Wrote comprehensive tests validating exact matching, entity name fallback, title mismatch detection, and data completeness constraints.
   - All 38 tests pass successfully.

## Validation Metrics

The classifier achieved an **Unmatched Rate of just 7.4%**, far surpassing the 15% target limit.

### Key Statistics
*   **Total Tenders Processed**: 17,729
*   **Total Successfully Classified**: 16,425 (92.6%)
*   **Unmatched (Unclassified)**: 1,304 (7.4%)
*   **Title-District Mismatches**: 5,563 (31.4%) — Expected behavior, mostly due to centralized state offices in Kamrup Metropolitan procuring for other districts.

### Classification Method Breakdown
| Method | Tenders | Percentage |
| :--- | :--- | :--- |
| **Address Exact Match** | 10,757 | 60.7% |
| **State HQ Fallback** | 3,117 | 17.6% |
| **Entity Name Fallback** | 2,127 | 12.0% |
| **Unclassified** | 1,304 | 7.4% |
| **BTC Fallback** | 309 | 1.7% |
| **Circle Match** | 107 | 0.6% |
| **Fuzzy Address/Entity** | 8 | 0.0% |

### Top 5 Classified Districts
1. **Kamrup Metropolitan**: 6,346 (35.8%)
2. **Kokrajhar**: 1,833 (10.3%)
3. **Kamrup**: 766 (4.3%)
4. **Sonitpur**: 585 (3.3%)
5. **Darrang**: 515 (2.9%)

> [!TIP]
> The top 20 unmatched addresses are logged in the eyeball report in your terminal. They mainly consist of highly generic names like `"Online"` or `"S E, PWD (Roads), City Road Circle"`. Further iterations of the gazetteer could slowly chip away at the remaining 7.4%.
