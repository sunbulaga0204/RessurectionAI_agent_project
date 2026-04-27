#!/bin/bash

# Ensure virtual environment is used
PYTHON=".venv/bin/python"

BOOKS=(
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.Munqidh/0505Ghazali.Munqidh.JK009330-ara1"
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.KimiyaSacada/0505Ghazali.KimiyaSacada.Shamela0009261-ara1"
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.MizanCamal/0505Ghazali.MizanCamal.JK009289-ara1"
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.Iqtisad/0505Ghazali.Iqtisad.JK009219-ara1"
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.Wasit/0505Ghazali.Wasit.JK000309-ara1"
    "https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali/0505Ghazali.BidayatHidaya/0505Ghazali.BidayatHidaya.Shamela0012718-ara1"
)

echo "🚀 Starting Expansion of Ghazali's Library..."

for URL in "${BOOKS[@]}"; do
    echo "------------------------------------------------------------"
    echo "📖 Processing: $URL"
    # We pipe 'c' to automatically choose [c]ontinue (append) in the ingestion prompt
    echo "c" | $PYTHON ingest.py --tenant ghazali --death-date 505 --openiti "$URL"
done

echo "============================================================"
echo "✨ Library Expansion Complete!"
echo "============================================================"
