# ============================================================
# US–CHINA TRADE FRAGMENTATION PROJECT
# Script: 04_descriptive_data_pull.R
#
# Purpose:
#   - Pull annual US import data from UN Comtrade
#   - Construct descriptive trade-fragmentation dataset
#   - Prepare product-country panel for:
#       * diversion
#       * concentration
#       * friendshoring
#       * network analysis
#       * transformation-stage analysis
#
# ============================================================
# KEY FINDINGS FROM API TESTING
# ============================================================
#
# 1. Monthly 2025 data proved inconsistent/incomplete.
#    Annual data is substantially more stable.
#
# 2. China export pulls for 2025 frequently returned:
#       - empty datasets
#       - inconsistent partner coverage
#       - unstable behaviour across API calls
#
# 3. US imports data is much more complete and stable.
#
# 4. Free API tier limitations:
#       - 100k row cap per request
#       - URL length limits
#       - no bulk API access
#
# 5. Solution:
#       - annual frequency only
#       - US imports instead of China exports
#       - all HS6 products
#       - split by partner-country batches
#
# 6. Main dataset structure:
#
#       US imports x origin country x HS6 x year
#
# ============================================================

rm(list = ls())

# ============================================================
# 0. Packages
# ============================================================

packages <- c(
  "tidyverse",
  "comtradr"
)

lapply(packages, library, character.only = TRUE)

# ============================================================
# 1. API Setup
# ============================================================

Sys.setenv(
  "COMTRADE_PRIMARY" =
    "0ca5ca6ac9a7420da8039828de48501c"
)

# ============================================================
# 2. Analysis Window
# ============================================================

analysis_years <- 2017:2025

# ============================================================
# 3. Selected Partner Sample
# ============================================================

# Strategy:
#
# Pull all HS6 products for a selected set of major
# US import partners rather than attempting:
#
# - all countries x all HS6
#
# which exceeds free API limits.
#
# Partner sample:
# top-60 trading partners in:
# - 2017
# - 2025
#
# Final sample:
# union of both years.

# ------------------------------------------------------------
# 3A. 2017 partner ranking
# ------------------------------------------------------------

us_2017_imports <- ct_get_data(
  
  reporter       = "USA",
  partner        = "all_countries",
  flow_direction = "Import",
  
  start_date     = 2017,
  end_date       = 2017
)

rank_2017 <- us_2017_imports %>%
  
  arrange(desc(primary_value)) %>%
  
  slice(1:60) %>%
  
  pull(partner_iso)

# ------------------------------------------------------------
# 3B. 2025 partner ranking
# ------------------------------------------------------------

us_2025_imports <- ct_get_data(
  
  reporter       = "USA",
  partner        = "all_countries",
  flow_direction = "Import",
  
  start_date     = 2025,
  end_date       = 2025,
  
  commodity_code = "TOTAL"
)

rank_2025 <- us_2025_imports %>%
  
  arrange(desc(primary_value)) %>%
  
  slice(1:60) %>%
  
  pull(partner_iso)

# ------------------------------------------------------------
# 3C. Final partner sample
# ------------------------------------------------------------

selected_partners <- union(
  rank_2017,
  rank_2025
)

length(selected_partners)

selected_partners

# ============================================================
# 4. Country Batches
# ============================================================

# API requests are split into batches to avoid:
#
# - 100k row cap
# - URL length limits
# - unstable large requests

partner_batches <- split(
  
  selected_partners,
  
  ceiling(
    seq_along(selected_partners) / 16
  )
)

length(partner_batches)

# ============================================================
# 5. Safe Pull Function
# ============================================================

# Pull:
#
# US imports x partner batch x HS6 x year

safe_trade_pull <- function(
    partner_batch,
    year
) {
  
  message(
    "Pulling year ",
    year,
    " | batch size = ",
    length(partner_batch)
  )
  
  tryCatch({
    
    Sys.sleep(0.5)
    
    ct_get_data(
      
      reporter       = "USA",
      partner        = partner_batch,
      flow_direction = "Import",
      
      start_date     = year,
      end_date       = year,
      
      commodity_classification = "HS",
      commodity_code           = "everything"
    )
    
  }, error = function(e) {
    
    message(
      "FAILED year ",
      year
    )
    
    NULL
  })
}

# ============================================================
# 6. Full Data Pull
# ============================================================

all_trade_data <- list()

counter <- 1

for(y in analysis_years){
  
  for(b in seq_along(partner_batches)){
    
    temp <- safe_trade_pull(
      
      partner_batch = partner_batches[[b]],
      year           = y
    )
    
    all_trade_data[[counter]] <- temp
    
    # --------------------------------------------------------
    # Save intermediate batch
    # --------------------------------------------------------
    
    write_csv(
      
      temp,
      
      paste0(
        "us_imports_",
        y,
        "_batch_",
        b,
        ".csv"
      )
    )
    
    counter <- counter + 1
  }
}



# ============================================================
# 7. Combine + Clean
# ============================================================

all_trade_data <- bind_rows(all_trade_data)

# ------------------------------------------------------------
# Keep HS6 observations only
# ------------------------------------------------------------

trade_panel <- all_trade_data %>%
  
  filter(aggr_level == 6)

# ============================================================
# 8. Basic Variables
# ============================================================

trade_panel <- trade_panel %>%
  
  mutate(
    
    hs6 = cmd_code,
    
    origin_iso = partner_iso,
    
    year = ref_year,
    
    imports = primary_value,
    
    hs2 = substr(hs6, 1, 2),
    
    hs4 = substr(hs6, 1, 4)
  )

# ============================================================
# 9. Basic Diagnostics
# ============================================================

dim(trade_panel)

n_distinct(trade_panel$hs6)

n_distinct(trade_panel$origin_iso)

range(trade_panel$year)

summary(trade_panel$imports)


head(trade_panel)

# ============================================================
# 10. Save Clean Panel
# ============================================================

write_csv(
  trade_panel,
  "us_imports_panel_2017_2025.csv"
)

# ============================================================
# 11. Placeholder Extensions
# ============================================================

# ------------------------------------------------------------
# A. Transformation-stage concordance
# ------------------------------------------------------------

# - HS concordance
# - stage classifications
# - GVC intensity measures

# ------------------------------------------------------------
# B. Trade diversion
# ------------------------------------------------------------

# - China share decline
# - third-country substitution
# - destination reallocation

# ------------------------------------------------------------
# C. Friendshoring measures
# ------------------------------------------------------------

# - allied-country import growth
# - geopolitical blocs
# - China+1 patterns

# ------------------------------------------------------------
# D. Concentration metrics
# ------------------------------------------------------------

# - HHI
# - top-5 supplier shares
# - supplier diversification

# ------------------------------------------------------------
# E. Network analysis
# ------------------------------------------------------------

# - hub structure
# - resilience
# - clustering
# - centrality

# ------------------------------------------------------------
# F. RoW residual construction
# ------------------------------------------------------------

# - total imports
# - selected-country imports
# - residual "rest of world"

# ------------------------------------------------------------
# G. Econometric panel construction
# ------------------------------------------------------------

# Potential future extension:
#
# US imports x origin x HS6 x year panel
# merged with:
# - tariff exposure
# - transformation stages
# - geopolitical measures
#