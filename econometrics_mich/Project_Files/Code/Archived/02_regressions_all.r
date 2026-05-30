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

rm(list = ls())

# ============================================================
# 0. Packages
# ============================================================

packages <- c(
  "dplyr",
  "fixest",
  "ggplot2",
  "tidyr"
)

lapply(packages, library, character.only = TRUE)

# ============================================================
# 1. Paths + Load Data
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"

output_path <- file.path(root, "Output")

# ------------------------------------------------------------
# Main panels
# ------------------------------------------------------------

df_hs12 <- readRDS(
  file.path(output_path, "df_hs12.rds")
) %>%
  filter(importer != 842) #remove US here!!

df_hs92 <- readRDS(
  file.path(output_path, "df_hs92.rds")
) %>%
  filter(importer != 842) #remove US

#new bins; 4 vs 3
df_hs12 <- df_hs12 %>%
  mutate(
    new_bin = case_when(
      tariff_rate == 0 ~ "0",
      tariff_rate > 0    & tariff_rate <= 0.05 ~ "0-5%",
      tariff_rate > 0.05 & tariff_rate <= 0.10 ~ "5-10%",
      tariff_rate > 0.10 & tariff_rate <= 0.15 ~ "10-15%",
      tariff_rate > 0.15 & tariff_rate <= 0.20 ~ "15-20%",
      tariff_rate > 0.20 ~ "20%+"
    )
  )

# Order factor levels
df_hs12$new_bin <- factor(
  df_hs12$new_bin,
  levels = c(
    "0",
    "0-5%",
    "5-10%",
    "10-15%",
    "15-20%",
    "20%+"
  )
)

# ============================================================
# 2. Baseline Regressions: OLS vs PPML, continuous vs discrete
# ============================================================

# OLS: continuous treatment

summary(df_hs12$exports == 0)
mean(df_hs12$exports == 0) #no zeros

m_ols_cont <- feols(
  log_exports ~ tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# PPML: continuous treatment

m_ppml_cont <- fepois(
  exports ~ tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# ------------------------------------------------------------
# OLS: binned treatment

m_ols_bins <- feols(
  log_exports ~ i(new_bin, post2018, ref = "0") |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# PPML: binned treatment

m_ppml_bins <- fepois(
  exports ~ i(new_bin, post2018, ref = "0") |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# ------------------------------------------------------------
# Baseline results table

etable(
  "OLS Continuous"  = m_ols_cont,
  "PPML Continuous" = m_ppml_cont,
  #"OLS bins"      = m_ols_bins,
  #"PPML bins"     = m_ppml_bins,
  
  digits = 3,
  se.below = TRUE
)

# ============================================================
# 3. Baseline Regressions: weighted or not 
# ============================================================

#weight: base it on the product share of total chinese exports. not destination dependent 
product_weights <- df_hs12 %>%
  filter(year <= 2017) %>%
  
  group_by(hs6) %>%
  
  summarise(
    product_weight = mean(exports, na.rm = TRUE),
    .groups = "drop"
  )

df_hs12_w <- df_hs12 %>%
  left_join(product_weights, by = "hs6")

weights = ~product_weight

#OLS: continuous and weighted

m_ols_cont_w <- feols(
  log_exports ~ tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_w, #weight enters bc we use this df + weights
  
  cluster = ~hs6 + importer,
  
  weights = ~product_weight
)

# PPML: continuous tariff exposure (weighted)

m_ppml_cont_w <- fepois(
  exports ~ tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_w,
  
  cluster = ~hs6 + importer,
  
  weights = ~product_weight
)

# ------------------------------------------------------------
# OLS bins (weighted)

m_ols_bins_w <- feols(
  log_exports ~ i(new_bin, post2018, ref = "0") |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_w,
  
  cluster = ~hs6 + importer,
  
  weights = ~product_weight
)

# PPML bins (weighted)

m_ppml_bins_w <- fepois(
  exports ~ i(new_bin, post2018, ref = "0") |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_w,
  
  cluster = ~hs6 + importer,
  
  weights = ~product_weight
)

# ------------------------------------------------------------
# Results table

etable(
  "OLS Continuous"          = m_ols_cont,
  "OLS Continuous Weighted" = m_ols_cont_w,
  
  "PPML Continuous"         = m_ppml_cont,
  "PPML Continuous Weighted"= m_ppml_cont_w,
  
  digits = 3,
  se.below = TRUE
)

# Optional: bins comparison table

etable(
  "OLS Bins"           = m_ols_bins,
  "OLS Bins Weighted"  = m_ols_bins_w,
  
  "PPML Bins"          = m_ppml_bins,
  "PPML Bins Weighted" = m_ppml_bins_w,
  
  digits = 3,
  se.below = TRUE
)

# ============================================================
# 3. Baseline: add Pre-US exposure share
# ============================================================
# Reload full dataset INCLUDING US

df_hs12_full <- readRDS(
  file.path(output_path, "df_hs12.rds")
)

# ------------------------------------------------------------
# Construct product-level pre-US exposure share
# Average annual share over 2015-2017

pre_us_share <- df_hs12_full %>%
  
  filter(
    year >= 2015,
    year <= 2017
  ) %>%
  
  group_by(hs6) %>%
  
  summarise(
    
    us_exports_pre = sum(
      exports[importer == 842],
      na.rm = TRUE
    ),
    
    world_exports_pre = sum(
      exports,
      na.rm = TRUE
    ),
    
    .groups = "drop"
  ) %>%
  
  mutate(
    pre_us_share = us_exports_pre / world_exports_pre
  ) %>%
  
  select(
    hs6,
    pre_us_share
  )

summary(pre_us_share$pre_us_share)
head(pre_us_share)

mean(pre_us_share$pre_us_share == 0) #share 0 trade
sum(pre_us_share$pre_us_share == 0) #401 codes; about 8% of trade 

# ------------------------------------------------------------
# Merge onto regression dataset (US already excluded)

df_hs12_usexp <- df_hs12 %>%
  
  left_join(
    pre_us_share,
    by = "hs6"
  ) %>%
  
  mutate(
    pre_us_share = replace_na(pre_us_share, 0)
  )

# Diagnostics

summary(df_hs12_usexp$pre_us_share)

# -------------IN TREATMENT: Continuous tariff exposure + PreUSShare -----

m_ols_preus <- feols(
  log_exports ~
    
    tariff_rate:post2018 +
    tariff_rate:post2018:pre_us_share |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

#PPML version
m_ppml_preus <- fepois(
  exports ~
    
    tariff_rate:post2018 +
    tariff_rate:post2018:pre_us_share |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

# Results table

etable(
  "OLS" = m_ols_cont,
  "PPML" = m_ppml_cont,
  "OLS + PreUSShare"  = m_ols_preus,
  "PPML + PreUSShare" = m_ppml_preus,
  
  digits = 3,
  se.below = TRUE
)

# -------Binned tariff exposure + PreUSShare -------

m_ols_bins_preus <- feols(
  log_exports ~
    
    i(new_bin, post2018, ref = "0") +
    i(new_bin, post2018, ref = "0"):pre_us_share |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

# Results table

etable(
  "OLS Bins + PreUSShare" = m_ols_bins_preus,
  
  digits = 3,
  se.below = TRUE
)


# ============================================================
# Control instead: preUSexp x year
# year not post as there can be pre-shock divergences as suggested by event study 
# ------------------------------------------------------------

# ============================================================
# Pre-US exposure bins

df_hs12_usexp <- df_hs12_usexp %>%
  
  mutate(
    
    preus_bin = case_when(
      pre_us_share == 0    ~ "0",
      pre_us_share <= 0.05 ~ "Low US exposure",
      pre_us_share <= 0.20 ~ "Medium US exposure",
      TRUE                 ~ "High US exposure"
    ),
    
    preus_bin = factor(
      preus_bin,
      levels = c(
        "0",
        "Low US exposure",
        "Medium US exposure",
        "High US exposure"
      )
    )
  )

# ============================================================
# OLS: preferred baseline

m_ols_preus_control <- feols(
  log_exports ~
    
    tariff_rate:post2018 +
    i(year, preus_bin, ref = 2017) |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

# ============================================================
# PPML: other possible baseline

m_ppml_preus_control <- fixest::fepois(
  exports ~
    
    tariff_rate:post2018 +
    i(year, preus_bin, ref = 2017) |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

###above too large. lets just try post2018
m_ppml_preus_control <- fixest::fepois(
  exports ~
    
    tariff_rate:post2018 +
    preus_bin:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

## same OLS 
m_ols_preus_post <- feols(
  log_exports ~
    
    tariff_rate:post2018 +
    preus_bin:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

# ============================================================
# Results table

results1 <- etable(
  "OLS Continuous"  = m_ols_cont,
  "PPML Continuous" = m_ppml_cont,
  
  "OLS + US exposure control"  = m_ols_preus_control,
  #"PPML + US exposure control" = m_ppml_preus_control,
  
  drop = "preus_bin",
  
  digits = 3,
  se.below = TRUE
)

results1

# Results with post2018
results_post_controls <- etable(
  "OLS + Post2018 US controls"  = m_ols_preus_post,
  "PPML + Post2018 US controls" = m_ppml_preus_control,
  
  drop = "preus_bin",
  
  digits = 3,
  se.below = TRUE
)

results_post_controls
