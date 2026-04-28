import csv
from pathlib import Path

csv_path = Path("outputs/district_truth_filled.csv")

# Read the file
with csv_path.open("r", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

# The answers based on manual review
answers = [
    "Kamrup Metropolitan", # 2
    "Kamrup",              # 3
    "Hojai",               # 4
    "Kamrup Metropolitan", # 5
    "Kokrajhar",           # 6
    "Kokrajhar",           # 7
    "Udalguri",            # 8
    "Kokrajhar",           # 9
    "Jorhat",              # 10
    "Dibrugarh",           # 11
    "Dibrugarh",           # 12
    "Dibrugarh",           # 13
    "Cachar",              # 14
    "Hailakandi",          # 15
    "Cachar",              # 16
    "Cachar",              # 17
    "Biswanath",           # 18
    "Sonitpur",            # 19
    "Sonitpur",            # 20
    "Sonitpur",            # 21
    "Golaghat",            # 22
    "Jorhat",              # 23
    "Tinsukia",            # 24
    "Jorhat",              # 25
    "Lakhimpur",           # 26
    "Lakhimpur",           # 27
    "Lakhimpur",           # 28
    "Lakhimpur",           # 29
    "Tinsukia",            # 30
    "Tinsukia",            # 31
    "Tinsukia",            # 32
    "Tinsukia",            # 33
    "Dhemaji",             # 34
    "Dhemaji",             # 35
    "Dhemaji",             # 36
    "Dhemaji",             # 37
    "Nalbari",             # 38
    "Nalbari",             # 39
    "Bongaigaon",          # 40
    "Nalbari",             # 41
    "Sivasagar",           # 42
    "Kamrup Metropolitan", # 43
    "Nagaon",              # 44
    "Kokrajhar",           # 45
    "Baksa",               # 46
    "Kamrup Metropolitan", # 47
    "Kamrup",              # 48
    "Kamrup Metropolitan", # 49
    "Golaghat",            # 50
    "Kamrup",              # 51
]

for i, row in enumerate(rows):
    row[-1] = answers[i]

with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print("Filled the CSV!")
