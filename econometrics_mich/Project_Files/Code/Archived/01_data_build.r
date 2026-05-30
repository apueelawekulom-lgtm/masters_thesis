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
  "readxl"
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
  "gvc_setfit_hs17_classifications.csv"
)

# HS17 -> HS12 concordance
conc_path <- file.path(
  data_path,
  "HS2017toHS2012.xlsx"
)

# ============================================================
# 2. Tariff Data, from Fajgelbaum et al. dataset.
# Using dz_usch_w (tariff increase; weighted average for HS6)
# ============================================================

tariff_hs6 <- read_dta(tariff_path) %>%
  
  mutate(
    hs6 = str_pad(as.character(hs6), 6, pad = "0")
  ) %>%
  
  group_by(hs6) %>%
  
  summarise(
    tariff_rate = max(dz_usch_w, na.rm = TRUE),
    .groups = "drop"
  )

summary(tariff_hs6$tariff_rate)

# ============================================================
# 3. Helper Function: BACI Processing
# ============================================================

# Builds:
# China exports x importer x HS6 x year panel

process_baci_year <- function(file, hs_version) {
  
  year_i <- str_extract(
    basename(file),
    "(?<=_Y)\\d{4}"
  ) %>%
    as.integer()
  
  cat("Processing:", hs_version, "-", year_i, "\n")
  
  fread(file) %>%
    
    filter(i == 156) %>%   # China exports only
    
    group_by(k, j) %>%
    
    summarise(
      exports = sum(v, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    
    mutate(
      hs6        = str_pad(as.character(k), 6, pad = "0"),
      importer   = j,
      year       = year_i,
      hs_version = hs_version
    ) %>%
    
    select(
      hs6,
      importer,
      year,
      exports,
      hs_version
    )
}

# ============================================================
# 4. BACI HS12 Panel
# ============================================================

# Main econometric panel.
# Used for:
# - baseline regressions
# - custom transformation-stage analysis

files_hs12 <- list.files(
  baci_hs12_path,
  pattern = "^BACI_HS12_Y\\d{4}_V\\d+\\.csv$",
  full.names = TRUE
) %>%
  
  keep(~ {
    
    yr <- str_extract(
      basename(.x),
      "(?<=_Y)\\d{4}"
    ) %>%
      as.integer()
    
    !is.na(yr) &&
      between(yr, 2012, 2024)
  })

cat("HS12 files:", length(files_hs12), "\n")

baci_hs12 <- files_hs12 %>%
  map_dfr(~ process_baci_year(.x, "HS12"))

cat("HS12 panel dimensions:", dim(baci_hs12), "\n")

# ============================================================
# 5. BACI HS92 Panel
# ============================================================

# Separate HS92 panel used because:
# - UNCTAD SOP classifications are HS92-based
# - BEC H0 is also closer to HS92 structure

files_hs92 <- list.files(
  baci_hs92_path,
  pattern = "^BACI_HS92_Y\\d{4}_V\\d+\\.csv$",
  full.names = TRUE
) %>%
  
  keep(~ {
    
    yr <- str_extract(
      basename(.x),
      "(?<=_Y)\\d{4}"
    ) %>%
      as.integer()
    
    !is.na(yr) &&
      between(yr, 2012, 2024)
  })

cat("HS92 files:", length(files_hs92), "\n")

baci_hs92 <- files_hs92 %>%
  map_dfr(~ process_baci_year(.x, "HS92"))

cat("HS92 panel dimensions:", dim(baci_hs92), "\n")

# ============================================================
# 6. Construct Master Panels
# ============================================================

# Core transformations:
# - remove US destination
# - create post-2018 treatment period
# - create log exports
# - create HS2 / HS4 controls

df_hs12 <- baci_hs12 %>%
  
  inner_join(
    tariff_hs6,
    by = "hs6"
  ) %>%
  
  filter(importer != 842) %>%   # remove US
  
  mutate(
    post2018  = as.integer(year >= 2018),
    treated   = as.integer(tariff_rate > 0),
    log_exports = log(exports + 1),
    
    hs2 = str_sub(hs6, 1, 2),
    hs4 = str_sub(hs6, 1, 4)
  )

df_hs92 <- baci_hs92 %>%
  
  inner_join(
    tariff_hs6,
    by = "hs6"
  ) %>%
  
  filter(importer != 842) %>%
  
  mutate(
    post2018  = as.integer(year >= 2018),
    treated   = as.integer(tariff_rate > 0),
    log_exports = log(exports + 1),
    
    hs2 = str_sub(hs6, 1, 2),
    hs4 = str_sub(hs6, 1, 4)
  )

head(df_hs12)

# ============================================================
# 7. UNCTAD SOP (HS92)
# ============================================================

# UNCTAD SOP = Stage of Processing classification.
# This is one benchmark heterogeneity system.

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

# Check for duplicate HS6 mappings
sop_clean %>%
  count(hs6) %>%
  filter(n > 1) #none

# Merge onto HS92 panel
df_sop <- df_hs92 %>%
  
  left_join(
    sop_clean,
    by = "hs6"
  ) %>%
  
  mutate(
    sop = factor(sop),
    sop = relevel(sop, ref = "Raw materials")
  )

# Match quality
mean(is.na(df_sop$sop))

table(df_sop$sop, useNA = "ifany") #good match quality

# ============================================================
# 8. BEC (HS92/H0)
# ============================================================

# BEC = Broad Economic Categories.
# Categories reflect economic use:
# - consumption
# - intermediate
# - capital goods

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

table(df_bec$bec, useNA = "ifany")

# ============================================================
# 9. Custom Transformation Stages
# ============================================================

# Custom transformation-stage measure:
#
# S1-3 = lower transformation
# S4   = medium-high transformation
# S5   = highest transformation
#
# Original classifications are in HS17.

# ------------------------------------------------------------
# 9A. Read HS17 classifications
# ------------------------------------------------------------

class17 <- fread(stage_path)

class17 <- class17 %>%
  
  mutate(
    hs17 = str_pad(
      as.character(code),
      6,
      pad = "0"
    ),
    
    stage_group = case_when(
      
      setfit_class %in% c(1,2,3) ~ "S1_3",
      setfit_class == 4 ~ "S4",
      setfit_class == 5 ~ "S5",
      
      TRUE ~ NA_character_
    )
  )

table(class17$stage_group, useNA = "ifany")

# ------------------------------------------------------------
# 9B. HS17 -> HS12 concordance
# ------------------------------------------------------------

# Needed because:
# - main regression panel is HS12
# - classifications originate in HS17

conc <- read_excel(conc_path)

names(conc) <- c("hs17", "hs12")

conc <- conc %>%
  
  mutate(
    hs17 = str_pad(as.character(hs17), 6, pad = "0"),
    hs12 = str_pad(as.character(hs12), 6, pad = "0")
  )

# ------------------------------------------------------------
# 9C. Concordance diagnostics
# ------------------------------------------------------------

# Check many-to-one and one-to-many mappings

conc %>%
  count(hs17) %>%
  filter(n > 1)

conc %>%
  count(hs12) %>%
  filter(n > 1)

# ------------------------------------------------------------
# 9D. Convert HS17 classifications -> HS12
# ------------------------------------------------------------

# If multiple HS17 products map into one HS12 code,
# keep the classification with highest confidence score.

class12 <- class17 %>%
  
  left_join(
    conc,
    by = "hs17"
  ) %>%
  
  group_by(hs12) %>%
  
  slice_max(
    order_by = setfit_confidence,
    n = 1,
    with_ties = FALSE
  ) %>%
  
  ungroup()

# ============================================================
# 10. Merge Custom Stages onto HS12 Panel
# ============================================================

classified_hs <- unique(class12$hs12)

df_stage <- df_hs12 %>%
  
  filter(hs6 %in% classified_hs) %>%
  
  left_join(
    class12 %>%
      select(
        hs12,
        stage_group,
        setfit_confidence
      ),
    
    by = c("hs6" = "hs12")
  ) %>%
  
  mutate(
    stage_group = factor(
      stage_group,
      levels = c("S1_3", "S4", "S5")
    )
  )

# ============================================================
# 11. Custom Stage Diagnostics
# ============================================================

table(df_stage$stage_group)

# Check tariff exposure distribution across stages

df_stage %>%
  
  group_by(stage_group) %>%
  
  summarise(
    mean_tariff = mean(tariff_rate, na.rm = TRUE),
    sd_tariff   = sd(tariff_rate, na.rm = TRUE),
    
    p25 = quantile(
      tariff_rate,
      0.25,
      na.rm = TRUE
    ),
    
    p50 = quantile(
      tariff_rate,
      0.50,
      na.rm = TRUE
    ),
    
    p75 = quantile(
      tariff_rate,
      0.75,
      na.rm = TRUE
    )
  )

# ============================================================
# 12. Export Clean Datasets
# ============================================================

# These become the inputs for:
# 02_regressions.R

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

cat("\nAll clean datasets exported successfully.\n")
