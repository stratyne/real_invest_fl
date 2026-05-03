# download_gis.ps1
# Downloads all Florida county GIS parcel shapefiles from the DOR data portal,
# extracts each into the canonical gis/ folder, and saves the zip to source_zips/.
# Skips counties where a .shp file already exists in gis/.
#
# Run from: D:\Chris\Documents\Stratyne\real_invest_fl
# Usage:    .\download_gis.ps1

$ErrorActionPreference = "Stop"

$BASE_URL     = "https://floridarevenue.com/property/dataportal/Documents/PTO%20Data%20Portal/Map%20Data/2025F/2025F%20PAR"
$COUNTIES_DIR = "D:\Chris\Documents\Stratyne\real_invest_fl\data\raw\counties"

# Each entry: fips folder name, and one or more zip filenames to download.
# Filenames are exactly as they appear on the DOR portal.
$COUNTIES = @(
    @{ folder="12001_alachua";       zips=@("alachua_2025Ppar.zip") },
    @{ folder="12003_baker";         zips=@("baker_2025Ppar.zip") },
    @{ folder="12005_bay";           zips=@("bay_2025Ppar.zip") },
    @{ folder="12007_bradford";      zips=@("bradford_2025Ppar.zip") },
    @{ folder="12009_brevard";       zips=@("brevard_2025Ppar.zip") },
    @{ folder="12011_broward";       zips=@("broward_2025Ppar.zip") },
    @{ folder="12013_calhoun";       zips=@("calhoun_2025Ppar.zip") },
    @{ folder="12015_charlotte";     zips=@("charlotte_2025Ppar.zip") },
    @{ folder="12017_citrus";        zips=@("citrus_2025Ppar.zip") },
    @{ folder="12019_clay";          zips=@("clay_2025Ppar.zip") },
    @{ folder="12021_collier";       zips=@("collier_2025Ppar.zip") },
    @{ folder="12023_columbia";      zips=@("columbia_2025Ppar.zip") },
    @{ folder="12027_desoto";        zips=@("desoto_2025Ppar.zip") },
    @{ folder="12029_dixie";         zips=@("dixie_2025Ppar.zip") },
    @{ folder="12031_duval";         zips=@("duval_2025Ppar.zip") },
    @{ folder="12033_escambia";      zips=@() },
    @{ folder="12035_flagler";       zips=@("flagler_2025Ppar.zip") },
    @{ folder="12037_franklin";      zips=@("franklin_2025Ppar.zip") },
    @{ folder="12039_gadsden";       zips=@("gadsden_2025Ppar.zip") },
    @{ folder="12041_gilchrist";     zips=@("gilchrist_2025Ppar.zip") },
    @{ folder="12043_glades";        zips=@("glades_2025Ppar.zip") },
    @{ folder="12045_gulf";          zips=@("gulf_2025Ppar.zip") },
    @{ folder="12047_hamilton";      zips=@("hamilton_2025Ppar.zip") },
    @{ folder="12049_hardee";        zips=@("hardee_2025Ppar.zip") },
    @{ folder="12051_hendry";        zips=@("hendry_2025Ppar.zip") },
    @{ folder="12053_hernando";      zips=@("hernando_2025Ppar.zip") },
    @{ folder="12055_highlands";     zips=@("highlands_2025Ppar.zip") },
    @{ folder="12057_hillsborough";  zips=@("hillsborough_2025Ppar.zip") },
    @{ folder="12059_holmes";        zips=@("holmes_2025Ppar.zip") },
    @{ folder="12061_indian_river";  zips=@("indianriver_2025Ppar.zip") },
    @{ folder="12063_jackson";       zips=@("jackson_2025Ppar.zip") },
    @{ folder="12065_jefferson";     zips=@("jefferson_2025Ppar.zip") },
    @{ folder="12067_lafayette";     zips=@("lafayette_2025Ppar.zip") },
    @{ folder="12069_lake";          zips=@("lake_2025Ppar.zip") },
    @{ folder="12071_lee";           zips=@("lee_2025par.zip") },
    @{ folder="12073_leon";          zips=@("leon_2025par.shp.zip") },
    @{ folder="12075_levy";          zips=@("levy_2025par.zip") },
    @{ folder="12077_liberty";       zips=@("liberty_2025par.zip") },
    @{ folder="12079_madison";       zips=@("madison_2025par.zip") },
    @{ folder="12081_manatee";       zips=@("manatee_2025par.zip") },
    @{ folder="12083_marion";        zips=@("marion_2025par.zip") },
    @{ folder="12085_martin";        zips=@("martin_2025par.zip") },
    @{ folder="12086_miami_dade";    zips=@("miamidade_2025par.zip","miamidade_condos_2025par.zip") },
    @{ folder="12087_monroe";        zips=@("monroe_2025par.zip") },
    @{ folder="12089_nassau";        zips=@("nassau_2025par.zip") },
    @{ folder="12091_okaloosa";      zips=@("okaloosa_2025par.zip") },
    @{ folder="12093_okeechobee";    zips=@("okeechobee_2025par.zip") },
    @{ folder="12095_orange";        zips=@("orange_2025par.zip") },
    @{ folder="12097_osceola";       zips=@("osceola_2025par.zip") },
    @{ folder="12099_palm_beach";    zips=@("palmbeach_2025par.zip") },
    @{ folder="12101_pasco";         zips=@("pasco_2025par.zip") },
    @{ folder="12103_pinellas";      zips=@("pinellas_2025par.zip") },
    @{ folder="12105_polk";          zips=@("polk_2025par.zip") },
    @{ folder="12107_putnam";        zips=@("putnam_2025par.zip") },
    @{ folder="12109_saint_johns";   zips=@("stjohns_2025par.zip","stjohnscondos_2025.zip") },
    @{ folder="12111_saint_lucie";   zips=@("stlucie_2025par.zip") },
    @{ folder="12113_santa_rosa";    zips=@() },
    @{ folder="12115_sarasota";      zips=@("sarasota_2025par.zip") },
    @{ folder="12117_seminole";      zips=@("seminole_2025par.zip") },
    @{ folder="12119_sumter";        zips=@("sumter_2025par.zip") },
    @{ folder="12121_suwannee";      zips=@("suwannee_2025par.zip") },
    @{ folder="12123_taylor";        zips=@("taylor_2025par.zip") },
    @{ folder="12125_union";         zips=@("union_2025par.zip") },
    @{ folder="12127_volusia";       zips=@("volusia_2025par.zip") },
    @{ folder="12129_wakulla";       zips=@("wakulla_2025par.zip") },
    @{ folder="12131_walton";        zips=@("walton_2025par.zip") },
    @{ folder="12133_washington";    zips=@("washington_2025par.zip") }
)

$success  = @()
$skipped  = @()
$failed   = @()

foreach ($county in $COUNTIES) {
    $gis_dir    = "$COUNTIES_DIR\$($county.folder)\gis"
    $source_dir = "$COUNTIES_DIR\$($county.folder)\source_zips"

    # Skip counties with empty zip list (Escambia, Santa Rosa)
    if ($county.zips.Count -eq 0) {
        Write-Host "SKIP  $($county.folder) — already staged" -ForegroundColor Yellow
        $skipped += $($county.folder)
        continue
    }

    # Skip if any .shp already exists in gis/
    $existing_shp = Get-ChildItem -Path $gis_dir -Filter "*.shp" -ErrorAction SilentlyContinue
    if ($existing_shp) {
        Write-Host "SKIP  $($county.folder) — .shp already present" -ForegroundColor Yellow
        $skipped += $($county.folder)
        continue
    }

    # Ensure directories exist
    New-Item -ItemType Directory -Force -Path $gis_dir    | Out-Null
    New-Item -ItemType Directory -Force -Path $source_dir | Out-Null

    $county_ok = $true

    foreach ($zip_name in $county.zips) {
        $encoded  = $zip_name -replace " ", "%20"
        $url      = "$BASE_URL/$encoded"
        $zip_dest = "$source_dir\$zip_name"

        Write-Host "DL    $($county.folder) — $zip_name" -ForegroundColor Cyan

        try {
            Invoke-WebRequest -Uri $url -OutFile $zip_dest -UseBasicParsing
            Expand-Archive -Path $zip_dest -DestinationPath $gis_dir -Force
            Write-Host "OK    $($county.folder) — $zip_name" -ForegroundColor Green
        }
        catch {
            Write-Host "FAIL  $($county.folder) — $zip_name — $($_.Exception.Message)" -ForegroundColor Red
            $county_ok = $false
        }
    }

    if ($county_ok) {
        $success += $($county.folder)
    } else {
        $failed += $($county.folder)
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "GIS download complete"
Write-Host "  Success : $($success.Count)"
Write-Host "  Skipped : $($skipped.Count)"
Write-Host "  Failed  : $($failed.Count)"
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Failed counties:"
    $failed | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
}
