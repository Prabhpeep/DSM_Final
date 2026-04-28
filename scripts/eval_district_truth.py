"""
Evaluate the district classifier against the manually labeled ground truth.
"""
import csv
from pathlib import Path

TRUTH_CSV = Path("outputs/district_truth_filled.csv")

def main():
    if not TRUTH_CSV.exists():
        print(f"Truth CSV not found at {TRUTH_CSV}. Please create and fill it first.")
        return

    with TRUTH_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    valid_rows = [r for r in rows if r.get("true_district", "").strip()]
    
    if not valid_rows:
        print("No valid labels found in true_district column.")
        return

    proc_correct = 0
    
    exec_total = 0
    exec_correct = 0
    
    best_correct = 0
    
    unclass_total = 0
    unclass_correct = 0
    
    for r in valid_rows:
        truth = r["true_district"].strip()
        proc = r["district_procuring"].strip()
        exe = r["district_execution"].strip() if r["district_execution"] else None
        
        best = exe if exe else proc
        
        if proc == truth:
            proc_correct += 1
            
        if exe:
            exec_total += 1
            if exe == truth:
                exec_correct += 1
                
        if best == truth:
            best_correct += 1
            
        if proc == "Unclassified":
            unclass_total += 1
            if proc == truth:
                unclass_correct += 1

    total = len(valid_rows)
    print("=" * 60)
    print(f"DISTRICT CLASSIFIER EVALUATION (n={total})")
    print("=" * 60)
    print(f"Procuring Accuracy: {proc_correct}/{total} ({proc_correct/total*100:.1f}%)")
    
    if exec_total > 0:
        print(f"Execution Accuracy (when predicted): {exec_correct}/{exec_total} ({exec_correct/exec_total*100:.1f}%)")
    else:
        print("Execution Accuracy: N/A (no execution predictions)")
        
    print(f"Best District Accuracy (COALESCE): {best_correct}/{total} ({best_correct/total*100:.1f}%)")
    
    if unclass_total > 0:
        print(f"Unclassified Confusion (Correctly identified as Unclassified): {unclass_correct}/{unclass_total} ({unclass_correct/unclass_total*100:.1f}%)")

if __name__ == "__main__":
    main()
