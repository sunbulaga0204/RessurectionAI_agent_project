#!/bin/bash

# Ensure virtual environment is used
PYTHON=".venv/bin/python"

BASE_URL="https://raw.githubusercontent.com/OpenITI/0525AH/master/data/0505Ghazali"

BOOKS=(
    "0505Ghazali.IhyaCulumDin/0505Ghazali.IhyaCulumDin.JK000001-ara1"
    "0505Ghazali.MinhajCabidin/0505Ghazali.MinhajCabidin.Kraken220414225509-ara1"
    "0505Ghazali.TibrMasbuk/0505Ghazali.TibrMasbuk.Shamela0004129-ara1"
    "0505Ghazali.MicyarCilm/0505Ghazali.MicyarCilm.JK010716-ara1"
    "0505Ghazali.Mustasfa/0505Ghazali.Mustasfa.JK000276-ara1"
)

echo "Starting Ghazali Corpus Ingestion..."

for BOOK in "${BOOKS[@]}"; do
    URL="${BASE_URL}/${BOOK}"
    echo "Ingesting: $URL"
    $PYTHON ingest.py --tenant ghazali --death-date 505 --openiti "$URL"
done

echo "Ghazali Corpus Ingestion Complete!"
