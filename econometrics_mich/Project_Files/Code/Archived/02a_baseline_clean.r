# ============================================================
# US–China Trade War Project
# Final baseline regressions only
# ============================================================

rm(list = ls())

# ============================================================
# 0. Packages
# ============================================================

packages <- c(
  "dplyr",
  "fixest",
  "tidyr"
)

lapply(packages, library, character.only = TRUE)

# ============================================================
# 1. Paths + Load Data
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"

output_path <- file.path(root, "Output")

# ------------------------------------------------------------
# Main regression panel (exclude US destinations)

df_hs12 <- readRDS(
  file.path(output_path, "df_hs12.rds")
) %>%
  
  filter(importer != 842)

# ============================================================
# 2. Baseline regressions WITHOUT US exposure controls
# ============================================================

# ------------------------------------------------------------
# OLS: continuous tariff exposure

m_ols_cont <- feols(
  log_exports ~
    
    tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# ------------------------------------------------------------
# PPML: continuous tariff exposure

m_ppml_cont <- fixest::fepois(
  exports ~
    
    tariff_rate:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12,
  
  cluster = ~hs6 + importer
)

# ============================================================
# 3. Construct Pre-US exposure measure
# ============================================================

# Reload full dataset INCLUDING US

df_hs12_full <- readRDS(
  file.path(output_path, "df_hs12.rds")
)

# ------------------------------------------------------------
# Product-level pre-US exposure share (2015–2017 average)

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

# ------------------------------------------------------------
# Merge onto regression dataset

df_hs12_usexp <- df_hs12 %>%
  
  left_join(
    pre_us_share,
    by = "hs6"
  ) %>%
  
  mutate(
    pre_us_share = replace_na(pre_us_share, 0)
  )

# ============================================================
# 4. Create Pre-US exposure bins
# ============================================================

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
# 5. OLS WITH flexible US exposure controls (preferred)
# ============================================================

m_ols_preus_year <- feols(
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
# 6. OLS + PPML WITH simpler post-only US controls
# ============================================================

# ------------------------------------------------------------
# OLS

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

# ------------------------------------------------------------
# PPML

m_ppml_preus_post <- fixest::fepois(
  exports ~
    
    tariff_rate:post2018 +
    preus_bin:post2018 |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  data = df_hs12_usexp,
  
  cluster = ~hs6 + importer
)

# ============================================================
# 7. Results tables
# ============================================================

# ------------------------------------------------------------
# Main table

results_main <- etable(
  "OLS Continuous" = m_ols_cont,
  "PPML Continuous" = m_ppml_cont,
  "OLS + US exposure control (Year)" = m_ols_preus_year,
  
  drop = "preus_bin",
  
  digits = 3,
  se.below = TRUE
)

results_main

# ------------------------------------------------------------
# Post-only US controls robustness

results_post_controls <- etable(
  "OLS + US exposure control (Post)" = m_ols_preus_post,
  "PPML + US exposure control (Post)" = m_ppml_preus_post,
  
  drop = "preus_bin",
  
  digits = 3,
  se.below = TRUE
)

results_post_controls





### testing PPML with diff FEs

# Rung 1 — main
fepois(exports ~ tariff_rate:post2018 | hs6^importer + importer^year, data=df_hs12, cluster=~hs6+importer)
# Rung 0 — your current, as "saturated robustness"
fepois(exports ~ tariff_rate:post2018 | hs6^importer + importer^year + hs2^year,  data=df_hs12, cluster=~hs6+importer)
# Rung 2 — "parsimonious robustness"
fepois(exports ~ tariff_rate:post2018 | hs6^importer + year,  data=df_hs12, cluster=~hs6+importer)


## event study using PPML
m_es <- fepois(
  exports ~ i(year, tariff_rate, ref = 2017) | hs6^importer + importer^year,
  data    = df_hs12,
  cluster = ~ hs6 + importer
)

iplot(
  m_es,
  ref.line = TRUE,                    # vertical line at the reference year
  main     = "Effect of tariff exposure on exports, by year",
  xlab     = "Year",
  ylab     = "Coef. on tariff_rate × year (rel. to 2017)"
)
abline(h = 0, lty = 2, col = "grey50")