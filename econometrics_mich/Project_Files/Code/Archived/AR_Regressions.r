# ============================================================
# US–China Trade War
# Author: Michelle Shi | Updated: May 2026
# ============================================================

rm(list = ls())

packages <- c("dplyr","tidyr","stringr","readr","purrr",
              "data.table","fixest","haven","readxl")
lapply(packages, library, character.only = TRUE)

# ============================================================
# 1. Paths
# ============================================================

root <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
data_path <- file.path(root, "Data")
output_path <- file.path(root, "Output")

baci_path   <- file.path(data_path, "BACI_HS12_V202601")
tariff_path <- file.path(data_path, "Fajgelbaum-z_usch_w.dta")

BEC_path <- file.path(data_path, "PLAID_v0.1_bec_H0.csv")
GVC_path <- file.path(data_path, "NaiveGVC1.csv")

# ============================================================
# 2. Tariffs (continuous intensity)
# ============================================================

tariff_hs6 <- read_dta(tariff_path) %>%
  mutate(hs6 = str_pad(as.character(hs6), 6, pad = "0")) %>%
  group_by(hs6) %>%
  summarise(
    tariff_rate = max(dz_usch_w, na.rm = TRUE),
    .groups = "drop"
  )

#which tariff column to use?
# tariff_compare <- read_dta(tariff_path) %>%
#   mutate(hs6 = str_pad(as.character(hs6), 6, pad = "0")) %>%
#   filter(t == 1) %>%
#   group_by(hs6) %>%
#   summarise(
#     z_mean       = max(z_usch, na.rm = TRUE),
#     z_weighted   = max(z_usch_w, na.rm = TRUE),
#     dz_mean      = max(dz_usch, na.rm = TRUE),
#     dz_weighted  = max(dz_usch_w, na.rm = TRUE),
#     z_max        = max(z_usch_max, na.rm = TRUE),
#     dz_max       = max(dz_usch_max, na.rm = TRUE),
#     .groups = "drop"
#   )
# 
# summary(tariff_compare)
# 
# sapply(tariff_compare[-1], function(x) mean(x == 0, na.rm = TRUE))
# 
# cor(
#   tariff_compare[-1],
#   use = "pairwise.complete.obs"
# )

# ============================================================
# 3. BACI panel (China exports; HS12 classification)
# ============================================================
files <- list.files(
  baci_path,
  pattern = "^BACI_HS12_Y\\d{4}_V\\d+\\.csv$",
  full.names = TRUE
) %>%
  keep(~ {
    yr <- str_extract(basename(.x), "(?<=_Y)\\d{4}") %>% as.integer()
    !is.na(yr) && between(yr, 2012, 2024)
  })

cat("Files found:", length(files), "\n")

process_baci_year <- function(file) {
  
  year_i <- str_extract(basename(file), "(?<=_Y)\\d{4}") %>% as.integer()
  cat("Processing:", year_i, "\n")
  
  fread(file) %>%
    filter(i == 156) %>%   # China exports only
    group_by(k, j) %>%
    summarise(
      exports = sum(v, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(
      hs6 = str_pad(as.character(k), 6, pad = "0"),
      importer = j,
      year = year_i,
      hs_version = "HS12"
    ) %>%
    select(hs6, importer, year, exports, hs_version)
}

baci_panel <- files %>%
  map_dfr(process_baci_year)

cat("Final panel dimensions:", dim(baci_panel), "\n")


##Read in HS92 for checks
files1 <- list.files(
  file.path(data_path, "BACI_HS92_V202601"),
  pattern = "^BACI_HS92_Y\\d{4}_V\\d+\\.csv$",
  full.names = TRUE
) %>%
  keep(~ {
    yr <- str_extract(basename(.x), "(?<=_Y)\\d{4}") %>% as.integer()
    !is.na(yr) && between(yr, 2012, 2024)
  })

cat("Files found:", length(files1), "\n")

process_baci_year1 <- function(file) {

  year_i <- str_extract(basename(file), "(?<=_Y)\\d{4}") %>% as.integer()
  cat("Processing:", year_i, "\n")

  fread(file) %>%   # <- file, not file1
    filter(i == 156) %>%   # China exports only
    group_by(k, j) %>%
    summarise(
      exports = sum(v, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(
      hs6 = str_pad(as.character(k), 6, pad = "0"),
      importer = j,
      year = year_i,
      hs_version = "HS92"
    ) %>%
    select(hs6, importer, year, exports, hs_version)
}

baci_panel_92 <- files1 %>%
  map_dfr(process_baci_year1)

cat("Final panel dimensions:", dim(baci_panel_92), "\n")

# ============================================================
# 4. Merge + variables
# ============================================================

df <- baci_panel %>%
  inner_join(tariff_hs6, by = "hs6") %>%   # Keep only HS6 codes in tariff data
  mutate(
    post2018 = as.integer(year >= 2018),
    log_exports = log(exports + 1),
    hs2 = str_sub(hs6, 1, 2),
    hs4 = str_sub(hs6, 1, 4),
  ) %>%
  filter(importer != 842) %>%   # Remove US destination
  mutate(
    treated = as.integer(tariff_rate > 0)
  )

# Sanity: Check the range of the continuous tariff rate
summary(df$tariff_rate)

#HS92 version
df92 <- baci_panel_92 %>%
  inner_join(tariff_hs6, by="hs6") %>%  
  mutate(
    post2018 = as.integer(year >= 2018),
    log_exports = log(exports + 1),
    hs2 = str_sub(hs6, 1, 2)
  ) %>%
  filter(importer != 842)  

# ============================================================
# 5. Initial event study 
# ============================================================

reg_es <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer + importer^year + hs2^year,
  data = df,
  cluster = ~hs6
)

par(mfrow = c(1,1))
iplot(reg_es,
      main = "Event Study (2017 as baseline; HS12)",
      xlab = "Year",
      ylab = "Coefficient")

wald(reg_es, keep = "year::2012|year::2013|year::2014|year::2015|year::2016")

#92 version
reg_es1 <- feols(
  log_exports ~ i(year, tariff_rate, ref = 2017) |
    hs6^importer + importer^year + hs2^year,
  data = df92,
  cluster = ~hs6
)

par(mfrow = c(1,1))

iplot(
  reg_es1,
  main = "HS92 Event Study: Tariff Exposure and Chinese Export Diversion",
  xlab = "Year",
  ylab = "Coefficient"
)

# ============================================================
# 6. Baseline regressions
# ============================================================

# ------------------------------------------------------------
# Spec 1: OLS (continuous treatment)
# ------------------------------------------------------------

m_ols_cont <- feols(
  log_exports ~ tariff_rate:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df,
  cluster = ~hs6
)

# ------------------------------------------------------------
# Spec 2: PPML (continuous treatment)
# ------------------------------------------------------------

m_ppml_cont <- fepois(
  exports ~ tariff_rate:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df,
  cluster = ~hs6
)

# ------------------------------------------------------------
# Spec 3: OLS (binary treatment)
# ------------------------------------------------------------

m_ols_bin <- feols(
  log_exports ~ treated:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df,
  cluster = ~hs6
)

# ------------------------------------------------------------
# Spec 4: PPML (binary treatment)
# ------------------------------------------------------------

m_ppml_bin <- fepois(
  exports ~ treated:post2018 |
    hs6^importer + importer^year + hs2^year,
  data = df,
  cluster = ~hs6
)

# ------------------------------------------------------------
# Results table
# ------------------------------------------------------------

etable(
  "OLS Continuous"  = m_ols_cont,
  "PPML Continuous" = m_ppml_cont,
  "OLS Binary"      = m_ols_bin,
  "PPML Binary"     = m_ppml_bin,
  digits = 3
)

# ============================================================
# UNCTAD Stages of Processing (SoP)
# ============================================================

sop <- readxl::read_xlsx(file.path(data_path, "UNCTAD-SOP.xlsx"))

# Clean concordance
sop_clean <- sop %>%
  filter(
    ProductGroup != "Total",
    ProductDescription != "UN Special Code"
  ) %>%
  transmute(
    hs6 = str_pad(as.character(ProductCode), 6, pad = "0"),
    sop = ProductGroupDescription
  ) %>%
  distinct()


# ------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------

# Number of unique HS6 codes
n_distinct(sop_clean$hs6)

# Check duplicates
sop_clean %>%
  count(hs6) %>%
  filter(n > 1)

# ------------------------------------------------------------
# Merge onto main dataframe WITH HS92 DATA 
# ------------------------------------------------------------

df_sop <- df92 %>%
  left_join(sop_clean, by = "hs6")

# ------------------------------------------------------------
# Match diagnostics
# ------------------------------------------------------------

# Share unmatched
mean(is.na(df_sop$sop))

# Counts by category
table(df_sop$sop, useNA = "ifany")

df_sop %>%
  distinct(hs6, sop) %>%
  summarise(
    total_hs6 = n(),
    missing_hs6 = sum(is.na(sop)),
    missing_share = mean(is.na(sop))
  )

#export mass on missing
df_sop %>%
  mutate(missing_sop = is.na(sop)) %>%
  group_by(missing_sop) %>%
  summarise(
    total_exports = sum(exports, na.rm = TRUE)
  ) %>%
  mutate(
    export_share = total_exports / sum(total_exports)
  )


##### Regression with UNCTAD SOP

df_sop <- df_sop %>%
  mutate(
    sop = factor(sop),
    sop = relevel(sop, ref = "Raw materials")
  )

m_sop <- feols(
  log_exports ~ tariff_rate:post2018 * sop |
    hs6^importer + importer^year + hs2[year],
  data = df_sop,
  cluster = ~hs6 + importer
)

etable(
  m_sop,
  title = "Heterogeneity by UNCTAD Stage of Processing",
  
  dict = c(
    "tariff_rate:post2018"
    = "Tariff Exposure × Post-2018",
    
    "tariff_rate:post2018:sopCapital goods"
    = "× Capital Goods",
    
    "tariff_rate:post2018:sopIntermediate goods"
    = "× Intermediate Goods",
    
    "tariff_rate:post2018:sopRaw materials"
    = "× Raw Materials"
  ),
  
  fitstat = ~ n + r2,
  digits = 3,
  se.below = TRUE
)



# ============================================================
# 7. Heterogeneity (BEC) using
# ============================================================

BEC <- read.csv(BEC_path)

BEC_clean <- BEC %>% select(hs6_code, bec) %>% rename(hs6 = hs6_code) %>%
  mutate(hs6 = as.character(hs6))

#New df which adds both BEC and GVC_clean. unmatched df rows get "MISSING"
df2 <- df %>%
  left_join(BEC_clean, by="hs6") %>%
  mutate(
    bec = factor(ifelse(is.na(bec), "Missing", bec))
  )

df2$bec <- relevel(df2$bec, ref="consumption")

# ============================================================
# 8. Heterogeneity regressions
# ============================================================

#Run with BEC
m_bec <- feols(
  log_exports ~ tariff_rate:post2018 * bec |
    hs6^importer + importer^year + hs2[year],
  data = df2,
  cluster = ~hs6 + importer
)

etable(
  "BEC"=m_bec,
  drop="Missing",
  se.below=TRUE,
  digits=3
)


# =========================================================
# NEW WITH GVC TRANSFORMATION MEASURE
# =========================================================

class_path <- file.path(
  data_path,
  "gvc_setfit_hs17_classifications.csv"
)

conc_path <- file.path(
  data_path,
  "HS2017toHS2012.xlsx"
)

# =========================================================
# 2. Read HS17 classification file
# =========================================================

class17 <- fread(class_path)

class17 <- class17 %>%
  mutate(
    
    hs17 = str_pad(as.character(code), 6, pad = "0"),
    
    stage_group = case_when(
      
      setfit_class %in% c(1, 2, 3) ~ "S1_3",
      
      setfit_class == 4 ~ "S4",
      
      setfit_class == 5 ~ "S5",
      
      TRUE ~ NA_character_
    )
  )

head(class17)
unique(class17$stage_group)

table(class17$stage_group, useNA = "ifany")

# =========================================================
# 3. Read concordance
# =========================================================

conc <- read_excel(conc_path)

names(conc) <- c("hs17", "hs12")

conc <- conc %>%
  mutate(
    hs17 = str_pad(as.character(hs17), 6, pad = "0"),
    hs12 = str_pad(as.character(hs12), 6, pad = "0")
  )

# =========================================================
# 4. Diagnostics: check concordance structure
# =========================================================

# HS17 mapping to multiple HS12?
conc %>%
  count(hs17) %>%
  filter(n > 1)

# Multiple HS17 mapping into same HS12?
conc %>%
  count(hs12) %>%
  filter(n > 1)

class12_check <- class17 %>%
  left_join(conc, by = "hs17") %>%
  group_by(hs12) %>%
  summarise(
    n_classes = n_distinct(stage_group),
    classes = paste(unique(stage_group), collapse = ", "),
    n = n()
  ) %>%
  filter(n > 1)

class12_check %>%
  filter(n_classes > 1)

#manual category for the 2-1 mapping
class17 %>%
  left_join(conc, by = "hs17") %>%
  filter(hs12 %in% c("842481", "854370")) %>%
  select(
    hs17,
    hs12,
    setfit_class,
    stage_group,
    setfit_confidence
  )

# =========================================================
# 5. Convert classifications HS17 -> HS12
# =========================================================

class12 <- class17 %>%
  left_join(conc, by = "hs17") %>%
  group_by(hs12) %>%
  slice_max(
    order_by = setfit_confidence,
    n = 1,
    with_ties = FALSE
  ) %>%
  ungroup()

# Check unmatched
class12 %>%
  filter(is.na(hs12)) #none

# =========================================================
# Keep only classified HS12 products
# =========================================================

classified_hs <- unique(class12$hs12)

# =========================================================
# Merge classifications onto existing df
# =========================================================

df_stage <- df %>%
  filter(hs6 %in% classified_hs) %>%
  left_join(
    class12 %>%
      select(
        hs12,
        stage_group,
        setfit_confidence
      ),
    by = c("hs6" = "hs12")
  )

# =========================================================
# Factor ordering
# =========================================================

df_stage <- df_stage %>%
  mutate(
    stage_group = factor(
      stage_group,
      levels = c("S1_3", "S4", "S5")
    )
  )

# =========================================================
# Diagnostics
# =========================================================

table(df_stage$stage_group)

df_stage %>%
  group_by(stage_group) %>%
  summarise(
    mean_tariff = mean(tariff_rate, na.rm = TRUE),
    sd_tariff   = sd(tariff_rate, na.rm = TRUE),
    p25         = quantile(tariff_rate, 0.25, na.rm = TRUE),
    p50         = quantile(tariff_rate, 0.50, na.rm = TRUE),
    p75         = quantile(tariff_rate, 0.75, na.rm = TRUE)
  )

# =========================================================
# Main heterogeneity regression
# =========================================================

reg_stage <- feols(
  log_exports ~
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs4[year],
  
  cluster = ~hs6 + importer,
  
  data = df_stage
)

summary(reg_stage)

# =========================================================
# Robustness: weighted
# =========================================================

weights = ~setfit_confidence

reg_stage_weighted <- feols(
  log_exports ~
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +
    importer^year +
    hs2^year,
  
  cluster = ~hs6 + importer,
  
  weights = ~setfit_confidence,
  
  data = df_stage
)

summary(reg_stage_weighted)


etable(
  reg_stage,
  reg_stage_weighted,
  
  headers = c(
    "Baseline",
    "Confidence Weighted"
  ),
  
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


df_stage1 <- df_stage %>%
  mutate(hs4 = substr(hs6, 1, 4))
    

reg_stage_hs4trends <- feols(
      log_exports ~
        tariff_rate * post2018 * stage_group |
        
        hs6^importer +
        importer^year +
        hs2^year +
        hs4[year],
      
      cluster = ~hs6 + importer,
      
      data = df_stage1
    )
    
summary(reg_stage_hs4trends)


# ============================================================
# Another Specification:
# HS4-specific trends as middle-ground specification
# ============================================================

reg_stage_final <- feols(
  log_exports ~
    tariff_rate * post2018 * stage_group |
    
    hs6^importer +     # bilateral product-importer FE
    importer^year +    # importer-year FE 
    hs4[year],        # HS4-specific linear trends
  
  cluster = ~hs6 + importer,
  
  data = df_stage1
)

summary(reg_stage_final)
