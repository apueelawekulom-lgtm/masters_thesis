# ============================================================
# US–China Trade War Project
# Script: 02_regressions.R
#
# Purpose:
#   - Run baseline regressions
#   - Event studies
#   - Heterogeneity analysis
#   - Robustness specifications
#
# Clean datasets are loaded from:
# 01_data_build.R

#NOTE THAT THE RAW DATA CONTAINS THE US AS AN IMPORT DESTINATION
# ============================================================


# ============================================================
# 1. Paths + Load Data
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"

output_path <- file.path(root, "Output")


# ------------------------------------------------------------
# HS92 panels for benchmark classifications
# ------------------------------------------------------------

df_sop <- readRDS(
  file.path(output_path, "df_sop.rds")
)

df_bec <- readRDS(
  file.path(output_path, "df_bec.rds")
)


# ------------------------------------------------------------
# Custom transformation-stage panel
# ------------------------------------------------------------

df_stage <- readRDS(
  file.path(output_path, "df_stage.rds")
)



# ============================================================
# 4. UNCTAD SOP Heterogeneity
# ============================================================

# UNCTAD SOP:
# - raw materials
# - intermediate goods
# - capital goods
# etc.

# Main specification:
# HS2-specific trends

m_sop_hs2trend <- feols(
  log_exports ~ tariff_rate:post2018 * sop |
    
    hs6^importer +
    importer^year +
    hs2[year],
  
  data = df_sop,
  
  cluster = ~hs6 + importer
)

# Strict robustness:
# fully saturated HS2 x year FE

m_sop_hs2fe <- feols(
  log_exports ~ tariff_rate:post2018 * sop |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_sop,
  
  cluster = ~hs6 + importer
)

etable(
  "HS2 Trends" = m_sop_hs2trend,
  "HS2-Year FE" = m_sop_hs2fe,
  
  title = "UNCTAD SOP Heterogeneity",
  
  digits = 3,
  se.below = TRUE
)

# ============================================================
# 5. BEC Heterogeneity
# ============================================================

# BEC:
# - consumption
# - intermediate
# - capital goods

m_bec_hs2trend <- feols(
  log_exports ~ tariff_rate:post2018 * bec |
    
    hs6^importer +
    importer^year +
    hs2[year],
  
  data = df_bec,
  
  cluster = ~hs6 + importer
)

m_bec_hs2fe <- feols(
  log_exports ~ tariff_rate:post2018 * bec |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_bec,
  
  cluster = ~hs6 + importer
)

etable(
  "HS2 Trends" = m_bec_hs2trend,
  "HS2-Year FE" = m_bec_hs2fe,
  
  title = "BEC Heterogeneity",
  
  drop = "Missing",
  
  digits = 3,
  se.below = TRUE
)

# ============================================================
# 6. Custom Transformation Stages
# ============================================================

# Main classification:
#
# S1_3 = lower transformation
# S4   = medium-high transformation
# S5   = highest transformation
#
# Reference category:
# S1_3

# ------------------------------------------------------------
# Preferred specification:
# HS2-specific trends
# ------------------------------------------------------------

reg_stage_hs2trend <- feols(
  log_exports ~
    
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs2[year],
  
  data = df_stage,
  
  cluster = ~hs6 + importer
)

summary(reg_stage_hs2trend)

# ------------------------------------------------------------
# Strict robustness:
# HS2 x year FE
# ------------------------------------------------------------

reg_stage_hs2fe <- feols(
  log_exports ~
    
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_stage,
  
  cluster = ~hs6 + importer
)

summary(reg_stage_hs2fe)

# ------------------------------------------------------------
# Granular robustness:
# HS4-specific trends
# ------------------------------------------------------------

# Important robustness:
#
# Results weaken substantially under HS4-specific
# trends, likely because transformation-stage
# variation becomes much more homogeneous within
# narrowly defined HS4 product groups.

reg_stage_hs4trend <- feols(
  log_exports ~
    
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs4[year],
  
  data = df_stage,
  
  cluster = ~hs6 + importer
)

summary(reg_stage_hs4trend)

# ============================================================
# 7. Confidence-Weighted Robustness
# ============================================================

# Weight observations by classifier confidence score.

reg_stage_weighted <- feols(
  log_exports ~
    
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_stage,
  
  cluster = ~hs6 + importer,
  
  weights = ~setfit_confidence
)

summary(reg_stage_weighted)

# ============================================================
# 8. Main Stage Results Table
# ============================================================

etable(
  "HS2 Trends"      = reg_stage_hs2trend,
  "HS2-Year FE"     = reg_stage_hs2fe,
  "HS4 Trends"      = reg_stage_hs4trend,
  "Confidence Wgt." = reg_stage_weighted,
  
  dict = c(
    
    "tariff_rate:post2018"
    = "Tariff Exposure × Post-2018 (S1-3)",
    
    "post2018:stage_groupS4"
    = "Post-2018 × S4",
    
    "post2018:stage_groupS5"
    = "Post-2018 × S5",
    
    "tariff_rate:post2018:stage_groupS4"
    = "Tariff Exposure × Post-2018 × S4",
    
    "tariff_rate:post2018:stage_groupS5"
    = "Tariff Exposure × Post-2018 × S5"
  ),
  
  fitstat = ~ n + r2,
  
  digits = 3,
  se.below = TRUE
)

# ============================================================
# 9. Key Interpretation Notes
# ============================================================

# Broad findings:
#
# 1. UNCTAD SOP and BEC effects attenuate
#    substantially once industry-level trends
#    are controlled for.
#
# 2. Custom transformation-stage results remain
#    more stable under HS2 trends / HS2-year FE.
#
# 3. Results weaken under HS4-specific trends,
#    likely because transformation-stage
#    variation becomes limited within narrowly
#    defined HS4 manufacturing groups.
#
# 4. This suggests the custom stage measure
#    captures economically meaningful variation
#    primarily across broader manufacturing
#    product groups.



# ============================================================
# Preliminary heterogeneity regression
# OLS, continuous tariff exposure, no US controls
# ============================================================

# Remove US import destination if still present

df_stage_usexp <- df_stage %>%
  filter(importer != 842)

# ------------------------------------------------------------
# Heterogeneity: transformation stages

m_ols_stage <- feols(
  log_exports ~
    
    tariff_rate:post2018 +
    i(stage_group, I(tariff_rate * post2018), ref = "S1") |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_stage_usexp,
  
  cluster = ~hs6 + importer
)

etable(
  "OLS: Transformation Heterogeneity" = m_ols_stage,
  
  digits = 3,
  se.below = TRUE
)

# ------------------------------------------------------------
# Results

etable(
  "OLS: Transformation Heterogeneity" = m_ols_stage,
  
  digits = 3,
  se.below = TRUE
)
