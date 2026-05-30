# ============================================================
# US–China Trade War Project
# Script: 01_data_build.R
#
# Purpose:
#   - Build clean analysis panels
#   - Harmonise HS classifications
#   - Merge tariffs + classifications
#   - Run diagnostics
# ============================================================

rm(list = ls())

# ============================================================
# 0. Packages
# ============================================================

packages <- c(
  "dplyr",
  "tidyr",
  "stringr",
  "readr",
  "purrr",
  "data.table",
  "fixest",
  "haven",
  "readxl",
  "concordance"
)

lapply(packages, library, character.only = TRUE)

# ============================================================
# 1. Paths
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"

data_path   <- file.path(root, "Data")
output_path <- file.path(root, "Output")

# BACI trade data
baci_hs12_path <- file.path(data_path, "BACI_HS12_V202601")
baci_hs92_path <- file.path(data_path, "BACI_HS92_V202601")

# Tariff data
tariff_path <- file.path(
  data_path,
  "Fajgelbaum-z_usch_w.dta"
)

# UNCTAD SOP
sop_path <- file.path(
  data_path,
  "UNCTAD-SOP.xlsx"
)

# BEC
bec_path <- file.path(
  data_path,
  "PLAID_v0.1_bec_H0.csv"
)

# Custom transformation stages
stage_path <- file.path(
  data_path,
  "gvc_hs17_classifications.csv"
)

# ============================================================
# 2. Tariff Data, from Fajgelbaum et al. dataset.
# Using dz_usch_w (tariff increase; weighted average for HS6)
# This is in HS17: I concord to HS12 and HS17 here too. 
# ============================================================

tariff_hs17 <- read_dta(tariff_path) %>%
  filter(t == 1) %>% #keep only the POST shock period; then use the change variable
  mutate(
    hs6 = str_pad(as.character(hs6), 6, pad = "0") #padding missing 0 if less than 6char
  ) %>%
  transmute(
    hs17 = hs6,
    tariff_rate = dz_usch_w #change in tariff rate; weighted
  )

summary(tariff_hs17$tariff_rate) 

## Concord HS17 tariffs to HS12

tariff_hs12 <- tariff_hs17 %>%
  mutate(
    hs6 = concord_hs(
      sourcevar   = hs17,
      origin      = "HS5", #HS2017
      destination = "HS4", #HS2012
      dest.digit  = 6,
      all         = FALSE
    )
  ) %>%
  filter(!is.na(hs6)) #81 unmatched of 5000+. These are dropped.  

#Note i checked for whether multiple HS17 concord to 1 HS12. 
#this issue does not come up using the concord_hs() function because it already deals with it:
#it “assign each HS17 tariff code to its most likely HS12 equivalent" depending on weight 

## Concord HS17 to HS92 (only for robustness checks)

tariff_hs92 <- tariff_hs17 %>%
  mutate(
    hs6 = concord_hs(
      sourcevar   = hs17,
      origin      = "HS5",
      destination = "HS0",
      dest.digit  = 6,
      all         = FALSE
    )
  ) %>%
  filter(!is.na(hs6)) #also 81 unmatched. These are dropped.

#Check: multiple HS17 codes mapping into the same HS92 code?
tariff_hs92 %>%
  count(hs6) %>%
  filter(n > 1) %>%
  arrange(desc(n))

# HS92 is substantially coarser than HS2017. 200+ with multi matches. 
# Multiple HS17 products can therefore map into the same HS92 category.
# Decision: take the maximum tariff change 

tariff_hs92 <- tariff_hs92 %>%
  group_by(hs6) %>%
  summarise(
    tariff_rate = max(tariff_rate, na.rm = TRUE), #take maximum 
    .groups = "drop"
  )

# ============================================================
# 3. BACI Panels (HS12 and HS92)
# ============================================================

## First set up the helper function:
# Builds:
# China exports x importer x HS6 x year panel

process_baci_year <- function(file, hs_version) {
  
  year_i <- str_extract( #extract file name
    basename(file),
    "(?<=_Y)\\d{4}"
  ) %>%
    as.integer()
  
  cat("Processing:", hs_version, "-", year_i, "\n")
  
  fread(file) %>% #keep only some variables. i = exporter; j = importer; k = HS6 product code; v = trade value
    
    transmute(
      exporter = i,
      importer = j,
      hs6      = str_pad(as.character(k), 6, pad = "0"),
      exports  = v
    ) %>%
    
    filter(exporter == 156) %>%     # Keep China exports only
    
    
    group_by(hs6, importer) %>% # Aggregate to: HS6 product × importer
    
    summarise(
      exports = sum(exports, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    
    mutate(
      year       = year_i,     # Add year and HS classification version
      hs_version = hs_version
    )
}

## Helper: find the yearly BACI files for a version and build the panel.
# Same logic for HS12 and HS92, only the directory + version string differ.
load_baci <- function(dir, version, yrs = 2012:2024) {
  
  files <- list.files( #find all .csvs but keep only certain years
    dir,
    pattern    = sprintf("^BACI_%s_Y\\d{4}_V\\d+\\.csv$", version),
    full.names = TRUE
  ) %>%
    
    keep(~ {
      
      yr <- str_extract(
        basename(.x),
        "(?<=_Y)\\d{4}"
      ) %>%
        as.integer()
      
      !is.na(yr) &&
        yr %in% yrs #2012-2024 only
    })
  
  cat(version, "files:", length(files), "\n")
  
  files %>%
    map_dfr(~ process_baci_year(.x, version)) # Process each yearly BACI file and combine into one panel
}

## HS2012 panel used for:
# - main regression analysis
# - tariff concordance from HS2017
# - compatibility with newer HS classifications

baci_hs12 <- load_baci(baci_hs12_path, "HS12")

cat("HS12 panel dimensions:", dim(baci_hs12), "\n")

# HS1992 panel used because:
# - UNCTAD SoP classifications are HS92-based
# - BEC classifications align more closely with HS92
# - some external concordances are only available in HS92

baci_hs92 <- load_baci(baci_hs92_path, "HS92")

cat("HS92 panel dimensions:", dim(baci_hs92), "\n")

## ============================================================
## BACI checks
## ============================================================

check_baci <- function(df, name){
  
  cat("\n=============================\n")
  cat("Checking:", name, "\n")
  cat("=============================\n")
  
  # Overall dimensions
  cat("Rows:", nrow(df), "\n")
  cat("Columns:", ncol(df), "\n")
  
  # Distinct counts
  cat("HS6 products:", n_distinct(df$hs6), "\n")
  cat("Importers:", n_distinct(df$importer), "\n")
  cat("Years:", n_distinct(df$year), "\n")
  
  # HS6 formatting
  cat("\nHS6 length check:\n")
  print(table(nchar(df$hs6)))
  
  # Duplicate check
  dupes <- df %>%
    count(hs6, importer, year) %>%
    filter(n > 1)
  
  cat("\nDuplicate rows:", nrow(dupes), "\n")
  
  # Missing values
  cat("\nMissing values:\n")
  print(colSums(is.na(df)))
  
  # Yearly diagnostics
  yearly <- df %>%
    group_by(year) %>%
    summarise(
      rows = n(),
      products = n_distinct(hs6),
      importers = n_distinct(importer),
      total_exports = sum(exports, na.rm = TRUE)
    )
  
  cat("\nYearly summary:\n")
  print(yearly)
}

check_baci(baci_hs12, "HS12")
check_baci(baci_hs92, "HS92")

# no duplicates; no missing values (ie no NAs; not no 0s); padding works; 
# good product counts; about 208-210 importers 
# ============================================================
# 4. Construct Base Panels (NO TARIFFS YET)
# ============================================================

# Keep:
# - China exports only (already imposed before)
# - create generic controls

df_hs12_base <- baci_hs12 %>%
  mutate(
    post2018 = as.integer(year >= 2018), #flag for post_2018
    log_exports = log(exports + 1), #log exports
    hs2 = str_sub(hs6, 1, 2),
    hs4 = str_sub(hs6, 1, 4)
  )

df_hs92_base <- baci_hs92 %>%
  mutate(
    post2018 = as.integer(year >= 2018),
    log_exports = log(exports + 1),
    hs2 = str_sub(hs6, 1, 2),
    hs4 = str_sub(hs6, 1, 4)
  )

head(df_hs12_base)

### Check: missing HS codes. Only 4700 in tariff data, but 5000 in BACI
## Missing codes account for about 3% of total Chinese trade over time. 
## Possible that these were truly not tariffed based on their chapter distribution.
## Decision: include them in panel with 0 TARIFF.

# missing_check -----------------------------------------------------------

missing_hs12 <- setdiff(
  unique(df_hs12_base$hs6),
  unique(tariff_hs12$hs6)
)

length(missing_hs12) #558 prev

missing_trade <- df_hs12_base %>%
  filter(hs6 %in% missing_hs12) %>%
  summarise(
    missing_exports = sum(exports, na.rm = TRUE)
  )

total_trade <- df_hs12_base %>%
  summarise(
    total_exports = sum(exports, na.rm = TRUE)
  )

missing_trade$missing_exports / #3%
  total_trade$total_exports

df_hs12_base %>%
  filter(hs6 %in% missing_hs12) %>%
  group_by(hs2) %>%
  summarise(
    products      = n_distinct(hs6),
    total_exports = sum(exports, na.rm = TRUE)
  ) %>%
  
  mutate(
    trade_share = total_exports / sum(total_exports)
  ) %>%
  arrange(desc(total_exports))

# ============================================================
# 5. Attach tariff data. This is ALREADY concorded. 
# ============================================================

# Full HS12 universe:
# unmatched tariff codes treated as zero tariff

## Helper: attach tariffs, flag imputed (unmatched) zeros, build bins.
# imputed_zero MUST be captured BEFORE replace_na, otherwise it gets
# conflated with genuine matched zeros (dz_usch_w == 0, real controls).
# Genuine zeros (~420k obs, 299 hs6) are legitimate "no change" controls;
# Imputed zeros (~189k obs, 2.7%, 558 hs6, 3.1% of value) are unmatched
# codes set to 0. The drop-imputed-zeros robustness run filters on this flag.
attach_tariffs <- function(df_base, tariffs) {
  df_base %>%
    left_join(
      tariffs, #already concorded
      by = "hs6"
    ) %>%
    
    mutate(
      imputed_zero = is.na(tariff_rate), #flag unmatched BEFORE imputing 0
      tariff_rate = replace_na(tariff_rate, 0), #0 for unmatched codes
      treated = as.integer(tariff_rate > 0), #binary 
      tariff_bin = case_when( #binned categories; based on distribution (median = 11%)
        tariff_rate == 0      ~ "0",
        tariff_rate <= 0.10   ~ "Low tariff (<=10%)",
        tariff_rate > 0.10    ~ "High tariff (>10%)"
      ),
      
      tariff_bin = factor( #rename with char names + order 
        tariff_bin,
        levels = c(
          "0",
          "Low tariff (<=10%)",
          "High tariff (>10%)"
        )
      )
    )
}

df_hs12 <- attach_tariffs(df_hs12_base, tariff_hs12)

print(df_hs12, width = Inf)

# Same for HS92
df_hs92 <- attach_tariffs(df_hs92_base, tariff_hs92)

# ============================================================
# 6. Merge UNCTAD SOP onto HS92 Base Panel
# ============================================================

sop_raw <- read_xlsx(sop_path)

sop_clean <- sop_raw %>%
  filter(
    ProductGroup != "Total",
    ProductDescription != "UN Special Code"
  ) %>%
  transmute(
    hs6 = str_pad(
      as.character(ProductCode),
      6,
      pad = "0"
    ),
    sop = ProductGroupDescription
  ) %>%
  
  distinct()

# Check, no duplicates
sop_clean %>%
  count(hs6) %>%
  filter(n > 1)

#Merge with df_hs92
df_sop <- df_hs92 %>%
  left_join(
    sop_clean,
    by = "hs6"
  ) %>%
  mutate(
    sop = factor(sop),
    sop = relevel(sop, ref = "Raw materials")
  )

nrow(df_sop)
nrow(df_hs92) #same row count

print(head(df_sop), width = Inf)
colSums(is.na(df_sop)) #38746 missing observations (ie unmatched to SoP). 
#Missing only 26 codes, 1% of total Chinese exports. Drop them later!

# ============================================================
# 7. BEC (HS92/H0)
# ============================================================

bec_raw <- read.csv(bec_path)

bec_clean <- bec_raw %>%
  transmute(
    hs6 = str_pad(
      as.character(hs6_code),
      6,
      pad = "0"
    ),
    bec
  )

#Merge onto 92 dataset
df_bec <- df_hs92 %>%
  left_join(
    bec_clean,
    by = "hs6"
  ) %>%
  
  mutate(
    bec = factor(
      ifelse(is.na(bec), "Missing", bec)
    )
  )

df_bec$bec <- relevel(
  df_bec$bec,
  ref = "consumption"
)

nrow(df_bec)
nrow(df_hs92)
colSums(is.na(df_bec)) #0 missing

# ============================================================
# 8. Custom Stage Diagnostics
# ============================================================

# Custom stage classification: now covers ALL DOMAINS but will likely be updated.

# 9A. Read HS17 stage classifications

class17 <- fread(stage_path) %>%
  mutate(
    hs17 = str_pad(
      as.character(code),
      6,
      pad = "0"
    ),
    
    stage_num = gvc_stage,
    
    stage_group = factor(
      paste0("S", stage_num),
      levels = c("S1", "S2", "S3", "S4", "S5"),
      ordered = TRUE
    )
  )

table(class17$stage_group, useNA = "ifany") #distribution; no NAs here

# 9B. Concord HS17 classifications to HS12
class12 <- class17 %>%
  mutate(
    hs6 = concord_hs(
      sourcevar   = hs17,
      origin      = "HS5", # HS2017
      destination = "HS4", # HS2012
      dest.digit  = 6,
      all         = FALSE #most weighted match
    )
  )

# Check unmatched concordances
sum(is.na(class12$hs6)) #missing only 1
mean(is.na(class12$hs6)) 

# 9C. Check many-to-one HS17 -> HS12 mappings
class12 %>%
  count(hs6) %>%
  filter(n > 1) %>%
  arrange(desc(n)) #Now 108 duplicates. range from 10 to 2

duplicated_hs12 <- class12 %>%
  count(hs6) %>%
  filter(n > 1) %>%
  pull(hs6)

#check only disagreements / distinct stages within 1 HS12. Only 16 yay!
class12 %>%
  group_by(hs6) %>%
  summarise(
    n_stage = n_distinct(stage_group)
  ) %>%
  filter(n_stage > 1)

#View disagreements
stage_conflicts <- class12 %>%
  group_by(hs6) %>%
  filter(
    n_distinct(stage_group) > 1
  ) %>%
  arrange(
    hs6,
    desc(confidence)
  ) %>%
  ungroup()

print(stage_conflicts, n = Inf) 

#The conflicts looked reasonable. Mostly at boundaries. 
#Rule: if same stage = use that stage. if not: if majority = stage, use that. if no majority, use highest certainty. 

# 9D. Resolve duplicate HS12 classifications
class12 <- class12 %>%
  group_by(hs6, stage_group) %>%
  summarise(
    n = n(),
    max_conf = max(confidence),
    .groups = "drop"
  ) %>%
  group_by(hs6) %>%
  arrange( #use arrange to implement rule; then slice 
    desc(n),
    desc(max_conf)
  ) %>%
  slice(1) %>%
  ungroup()

nrow(class12)

#View the final decision: 
# Pull final chosen classifications
final_stage <- class12 %>%
  select(hs6, final_stage = stage_group)

stage_conflicts <- stage_conflicts %>% #append so can see originals vs final
  left_join(
    final_stage,
    by = "hs6"
  ) %>%
  select(
    code,
    description,
    gvc_stage,
    domain,
    confidence,
    hs17,
    final_stage
  )

print(stage_conflicts, n = Inf) #looks reasonable

# ------------------------------------------------------------
# 9E. Merge classifications onto HS12 panel
# ------------------------------------------------------------

df_stage <- df_hs12 %>%
  left_join( #left join now that we have the full classification
    class12 %>%
      select(hs6, stage_group),
    by = "hs6"
  )

print(head(df_stage), width = Inf)
nrow(df_stage)

mean(is.na(df_stage$stage_group)) #0.1% na 
sum(is.na(df_stage$stage_group))

#check real traded codes
prop.table(table(df_stage$stage_group))

#check trade weighted stages
df_stage %>%
  group_by(stage_group) %>%
  summarise(
    exports = sum(exports, na.rm = TRUE)
  ) %>%
  mutate(
    share = exports / sum(exports)
  )

# ============================================================
# 9. Export Clean Datasets
# ============================================================

# These become the inputs for:
# 02_NEW_regressions.R

saveRDS(
  df_hs12,
  file.path(output_path, "df_hs12.rds")
)

saveRDS(
  df_hs92,
  file.path(output_path, "df_hs92.rds")
)

saveRDS(
  df_sop,
  file.path(output_path, "df_sop.rds")
)

saveRDS(
  df_bec,
  file.path(output_path, "df_bec.rds")
)

saveRDS(
  df_stage,
  file.path(output_path, "df_stage.rds")
)

saveRDS(
  class12,
  file.path(output_path, "class12.rds")
)

cat("\nAll clean datasets exported successfully.\n")
