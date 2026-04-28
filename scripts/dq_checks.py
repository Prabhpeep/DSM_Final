import pandas as pd
import numpy as np
import os, json

FPATH = 'data/raw/ocds_mapped_data_fiscal_year_2016_2022_v3.xlsx'
OUT   = 'outputs/dq'
os.makedirs(OUT, exist_ok=True)

xf = pd.ExcelFile(FPATH)
main    = xf.parse('main')
awards  = xf.parse('awards')
aw_supp = xf.parse('awards_suppliers')

results = {}  # store all output dicts for the report

# ── CHECK 1: Awards Join Integrity ──────────────────────────────────

print("=" * 70)
print("CHECK 1: AWARDS JOIN INTEGRITY")
print("=" * 70)

# 1a — Basic join stats
merged = main.merge(awards, left_on='_link', right_on='_link_main', how='left', suffixes=('', '_aw'))

awards_per_tender = awards.groupby('_link_main').size().reset_index(name='award_count')
main_with_counts  = main.merge(awards_per_tender, left_on='_link', right_on='_link_main', how='left')
main_with_counts['award_count'] = main_with_counts['award_count'].fillna(0).astype(int)

n_main   = len(main)
n_awards = len(awards)
n_with_award    = (main_with_counts['award_count'] > 0).sum()
n_without_award = (main_with_counts['award_count'] == 0).sum()
orphan_links    = set(awards['_link_main'].unique()) - set(main['_link'].unique())
n_orphans       = awards[awards['_link_main'].isin(orphan_links)].shape[0]

print(f"\n1a. Join statistics:")
print(f"  Total rows in main  : {n_main:,}")
print(f"  Total rows in awards: {n_awards:,}")
print(f"  Main tenders with ≥1 award : {n_with_award:,}")
print(f"  Main tenders with 0 awards : {n_without_award:,} ({n_without_award/n_main*100:.1f}%)")
print(f"  Orphan award rows          : {n_orphans:,} ({len(orphan_links)} unique _link_main values)")

# Award count distribution
dist = main_with_counts['award_count'].value_counts().sort_index()
print(f"\n  Award-count distribution:")
for k, v in dist.items():
    label = f"{int(k)}" if k < 5 else "5+"
    if k < 5:
        print(f"    {int(k):3d} awards: {v:6,} tenders")
    elif k == 5:
        n_5plus = main_with_counts[main_with_counts['award_count'] >= 5].shape[0]
        print(f"    5+ awards: {n_5plus:6,} tenders")
        break

# Save
dist_df = dist.reset_index()
dist_df.columns = ['award_count', 'n_tenders']
dist_df.to_csv(f'{OUT}/check1a_award_count_dist.csv', index=False)

# 1b — No-award breakdown by procurementMethod and fiscalYear
no_award = main_with_counts[main_with_counts['award_count'] == 0]

print(f"\n1b. No-award tenders by procurement method:")
pm = no_award['tender_procurementMethod'].value_counts()
pm_total = main['tender_procurementMethod'].value_counts()
pm_pct = (pm / pm_total * 100).round(1)
pm_df = pd.DataFrame({'no_award_count': pm, 'total_in_method': pm_total, 'pct_no_award': pm_pct}).sort_values('no_award_count', ascending=False)
print(pm_df.to_string())
pm_df.to_csv(f'{OUT}/check1b_noaward_by_method.csv')

print(f"\n    No-award tenders by fiscal year:")
fy = no_award['tender_fiscalYear'].value_counts().sort_index()
fy_total = main['tender_fiscalYear'].value_counts().sort_index()
fy_pct = (fy / fy_total * 100).round(1)
fy_df = pd.DataFrame({'no_award_count': fy, 'total_in_year': fy_total, 'pct_no_award': fy_pct})
print(fy_df.to_string())
fy_df.to_csv(f'{OUT}/check1b_noaward_by_fy.csv')

# 1c — 10 random multi-award tenders
multi = main_with_counts[main_with_counts['award_count'] > 1]
print(f"\n1c. Multi-award tenders: {len(multi):,} total")
if len(multi) > 0:
    sample_multi = multi.sample(min(10, len(multi)), random_state=42)
    print(f"    10 random examples:")
    for _, row in sample_multi.iterrows():
        link     = row['_link']
        ocid     = row['ocid']
        title    = str(row['tender_title'])[:80]
        n_aw     = row['award_count']
        aw_vals  = awards[awards['_link_main'] == link]['value_amount'].tolist()
        print(f"    ocid={ocid}  title='{title}'")
        print(f"      -> {n_aw} awards, values: {aw_vals}")
else:
    print("    No multi-award tenders found.")

# 1d — 5 random joined rows sanity check
print(f"\n1d. 5 random joined rows (sanity check):")
inner = main.merge(awards, left_on='_link', right_on='_link_main', how='inner', suffixes=('', '_aw'))
sample5 = inner.sample(5, random_state=99)
for _, row in sample5.iterrows():
    print(f"    ocid={row['ocid']}")
    print(f"      title        = {str(row['tender_title'])[:80]}")
    print(f"      tender_value = {row['tender_value_amount']}")
    print(f"      award_value  = {row['value_amount']}")
    print(f"      buyer        = {row['buyer_name']}")
    print()


# ── CHECK 2: Price Deviation Distribution ───────────────────────────

print("\n" + "=" * 70)
print("CHECK 2: PRICE DEVIATION DISTRIBUTION")
print("=" * 70)

inner = main.merge(awards, left_on='_link', right_on='_link_main', how='inner', suffixes=('', '_aw'))

# 2a — Sample size
both_nonnull = inner[
    inner['tender_value_amount'].notna() &
    inner['value_amount'].notna() &
    (inner['tender_value_amount'] > 0)
].copy()

n_sample = len(both_nonnull)
print(f"\n2a. Sample size:")
print(f"  Rows with both values non-null and tender_value > 0: {n_sample:,}")
print(f"  As % of all awards ({n_awards:,}): {n_sample/n_awards*100:.1f}%")
print(f"  As % of all main tenders ({n_main:,}): {n_sample/n_main*100:.1f}%")

# Count awards with value_amount <= 0 or null
aw_bad_val = inner[(inner['value_amount'].isna()) | (inner['value_amount'] <= 0)]
print(f"  Awards with value_amount <= 0 or null (excluded): {len(aw_bad_val):,}")

# 2b — Price deviation computation
both_nonnull['price_deviation'] = (both_nonnull['value_amount'] - both_nonnull['tender_value_amount']) / both_nonnull['tender_value_amount']

pd_col = both_nonnull['price_deviation']

percentiles = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
pct_vals = pd_col.quantile(percentiles)

print(f"\n2b. Price deviation statistics:")
print(f"  min   : {pd_col.min():.6f}")
for p, v in pct_vals.items():
    print(f"  P{int(p*100):02d}  : {v:.6f}")
print(f"  max   : {pd_col.max():.6f}")
print(f"  mean  : {pd_col.mean():.6f}")
print(f"  std   : {pd_col.std():.6f}")

n_exact_zero   = (pd_col == 0).sum()
n_negative     = (pd_col < 0).sum()
n_positive     = (pd_col > 0).sum()
n_abs_gt_50pct = (pd_col.abs() > 0.5).sum()
n_abs_gt_200pct= (pd_col.abs() > 2.0).sum()

print(f"\n  Deviation = 0 (exact match)  : {n_exact_zero:,} ({n_exact_zero/n_sample*100:.1f}%)")
print(f"  Deviation < 0 (below estimate): {n_negative:,} ({n_negative/n_sample*100:.1f}%)")
print(f"  Deviation > 0 (above estimate): {n_positive:,} ({n_positive/n_sample*100:.1f}%)")
print(f"  |deviation| > 50%             : {n_abs_gt_50pct:,} ({n_abs_gt_50pct/n_sample*100:.1f}%)")
print(f"  |deviation| > 200%            : {n_abs_gt_200pct:,} ({n_abs_gt_200pct/n_sample*100:.1f}%)")

# Save deviation stats
dev_stats = pd.DataFrame({
    'statistic': ['min'] + [f'P{int(p*100):02d}' for p in percentiles] + ['max', 'mean', 'std',
                  'exact_zero', 'negative', 'positive', 'abs_gt_50pct', 'abs_gt_200pct'],
    'value': [pd_col.min()] + list(pct_vals.values) + [pd_col.max(), pd_col.mean(), pd_col.std(),
              n_exact_zero, n_negative, n_positive, n_abs_gt_50pct, n_abs_gt_200pct]
})
dev_stats.to_csv(f'{OUT}/check2b_deviation_stats.csv', index=False)

# 2c — Sanity flags

# Median deviation by procurement method
print(f"\n2c. Median deviation by procurement method:")
dev_by_pm = both_nonnull.groupby('tender_procurementMethod')['price_deviation'].agg(['median', 'mean', 'count'])
dev_by_pm = dev_by_pm.sort_values('count', ascending=False)
print(dev_by_pm.to_string())
dev_by_pm.to_csv(f'{OUT}/check2c_deviation_by_method.csv')

# Extremes
print(f"\n  5 most negative deviations:")
bot5 = both_nonnull.nsmallest(5, 'price_deviation')
for _, row in bot5.iterrows():
    print(f"    ocid={row['ocid']}  dev={row['price_deviation']:.4f}")
    print(f"      title={str(row['tender_title'])[:80]}")
    print(f"      tender_val={row['tender_value_amount']:,.0f}  award_val={row['value_amount']:,.0f}  method={row['tender_procurementMethod']}")

print(f"\n  5 most positive deviations:")
top5 = both_nonnull.nlargest(5, 'price_deviation')
for _, row in top5.iterrows():
    print(f"    ocid={row['ocid']}  dev={row['price_deviation']:.4f}")
    print(f"      title={str(row['tender_title'])[:80]}")
    print(f"      tender_val={row['tender_value_amount']:,.0f}  award_val={row['value_amount']:,.0f}  method={row['tender_procurementMethod']}")

# Save full deviation dataset
both_nonnull[['ocid', 'tender_title', 'tender_value_amount', 'value_amount',
              'tender_procurementMethod', 'tender_fiscalYear', 'price_deviation']].to_csv(
    f'{OUT}/check2_full_deviations.csv', index=False)


# ── CHECK 9: Category Sanity ───────────────────────────────────────

print("\n" + "=" * 70)
print("CHECK 9: CATEGORY SANITY")
print("=" * 70)

# 9a — Category summary
cat_col = 'tender_mainProcurementCategory'
cat_agg = main.groupby(cat_col).agg(
    n_tenders          = ('_link', 'count'),
    total_value_inr    = ('tender_value_amount', 'sum'),
    median_value_inr   = ('tender_value_amount', 'median'),
    n_distinct_buyers  = ('buyer_name', 'nunique')
).sort_values('n_tenders', ascending=False)
cat_agg['total_value_cr'] = (cat_agg['total_value_inr'] / 1e7).round(1)      # INR crores
cat_agg['median_value_cr']= (cat_agg['median_value_inr'] / 1e7).round(2)

print(f"\n9a. Category summary ({main[cat_col].nunique()} unique values):")
print(cat_agg[['n_tenders', 'total_value_cr', 'median_value_cr', 'n_distinct_buyers']].to_string())
cat_agg.to_csv(f'{OUT}/check9a_category_summary.csv')

# 9b — 3 random example titles per category
print(f"\n9b. Example titles per category:")
for cat in cat_agg.index:
    subset = main[main[cat_col] == cat]
    samples = subset['tender_title'].dropna().sample(min(3, len(subset)), random_state=7)
    print(f"\n  [{cat}]")
    for t in samples.values:
        print(f"    - {str(t)[:100]}")

# 9c — Cross-tab: category × contract type
print(f"\n9c. Cross-tab: category × contract type:")
xtab = pd.crosstab(main[cat_col], main['tender_contractType'])
print(xtab.to_string())
xtab.to_csv(f'{OUT}/check9c_category_x_contracttype.csv')

# 9d — Keyword-based sector classification feasibility
keywords = ['road', 'bridge', 'building', 'hospital', 'health', 'school',
            'water', 'sanitation', 'electricity', 'IT', 'computer',
            'vehicle', 'medical', 'drug', 'equipment']

print(f"\n9d. Keyword presence in tender_title:")
title_lower = main['tender_title'].fillna('').str.lower()
kw_results = {}
for kw in keywords:
    if kw == 'IT':
        # case-sensitive to avoid matching 'it' in every title
        count = main['tender_title'].fillna('').str.contains(r'\bIT\b', regex=True).sum()
    else:
        count = title_lower.str.contains(kw.lower(), regex=False).sum()
    pct = count / n_main * 100
    kw_results[kw] = count
    print(f"  '{kw:>12s}' : {count:5,} tenders ({pct:.1f}%)")

kw_df = pd.DataFrame(list(kw_results.items()), columns=['keyword', 'n_matches'])
kw_df.to_csv(f'{OUT}/check9d_keyword_counts.csv', index=False)

print("\n" + "=" * 70)
print("ALL CHECKS COMPLETE — CSVs saved to", OUT)
print("=" * 70)
