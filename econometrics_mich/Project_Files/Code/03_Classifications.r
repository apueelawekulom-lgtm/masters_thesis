# ============================================================
# US–China Trade War Project
# Script: 03_ClassificationRegressions.R
#
# Question: does tariff-driven reallocation vary by the product's
# transformation stage (GVC position)?
#
# Inherits the locked baseline spec from 02B:
#   Estimator : PPML (fepois) baseline; OLS (feols) companion
#   Panel     : top-100 destinations + aggregated RoW
#   FE        : hs6^importer_grp + importer_grp^year + hs2^year
#   Cluster   : hs6 (treatment assigned at product level)
#   Control   : NONE (FEs absorb the confound)
#
# Stages: GVC stage S1-S5. S1+S2 COLLAPSED into "Early" (class imbalance:
#   S1 ~4% obs / 1.4% value, S2 ~7% / 2.5%). 4 groups: Early / S3 / S4 / S5,
#   Early = reference. Stage effects read as DEVIATION from early-stage.
#
# NOTE on imbalance: PPML weights by value, so Early/S3 are identified off
# little value and will be imprecise. Read stage ORDERING and SIGN, not stars.
# ============================================================

rm(list = ls()); gc()

# ------------------------------------------------------------
# 0. Packages + settings
# ------------------------------------------------------------
lapply(c("dplyr", "fixest", "tidyr"), library, character.only = TRUE)

setFixest_nthreads(0)
PPML_TOL <- 1e-6

root        <- "/Users/michelleshi/Documents/BSE/Term 3/Thesis/Project_Files"
output_path <- file.path(root, "Output")

# ============================================================
# 1. Data: df_stage -> RoW panel with collapsed stages (Route A)
# ============================================================
# df_stage.rds is already df_hs12 + stage_group. Drop US, attach pre-US share,
# collapse S1+S2 -> Early, aggregate to top-100 + RoW (same as 02B).

# pre-US-exposure share (2015-2017), built on the full panel incl. US
pre_us_share <- readRDS(file.path(output_path, "df_hs12.rds")) %>%
  filter(year >= 2015, year <= 2017) %>%
  group_by(hs6) %>%
  summarise(
    us_exports_pre    = sum(exports[importer == 842], na.rm = TRUE),
    world_exports_pre = sum(exports, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(pre_us_share = us_exports_pre / world_exports_pre) %>%
  select(hs6, pre_us_share)

df_stage_base <- readRDS(file.path(output_path, "df_stage.rds")) %>%
  filter(importer != 842) %>%
  filter(!is.na(stage_group)) %>%                 # drop 0.17% unmatched (decided in 01)
  left_join(pre_us_share, by = "hs6") %>%
  mutate(
    pre_us_share = replace_na(pre_us_share, 0),
    preus_bin = factor(                           # kept only for the optional split at end
      case_when(
        pre_us_share == 0    ~ "0",
        pre_us_share <= 0.10 ~ "Low US exposure",
        pre_us_share > 0.10  ~ "High US exposure"
      ),
      levels = c("0", "Low US exposure", "High US exposure")
    ),
    stage4 = factor(                              # COLLAPSE S1+S2 -> Early; Early = ref
      case_when(
        stage_group %in% c("S1", "S2") ~ "Early",
        TRUE                            ~ as.character(stage_group)
      ),
      levels = c("Early", "S3", "S4", "S5")
    )
  )

# rank destinations on pre-shock years; keep top-100, rest -> ROW
imp_rank <- df_stage_base %>%
  filter(year >= 2015, year <= 2017) %>%
  group_by(importer) %>%
  summarise(v = sum(exports), .groups = "drop") %>%
  mutate(share = v / sum(v)) %>%
  arrange(desc(share))

keep100 <- imp_rank %>% slice_max(share, n = 100) %>% pull(importer)
cat("top-100 cumulative share:",
    round(sum(imp_rank$share[imp_rank$importer %in% keep100]), 3), "\n")

# aggregate to top-100 + RoW, carrying stage4 through the key
df100_stage <- df_stage_base %>%
  mutate(importer_grp = ifelse(importer %in% keep100, as.character(importer), "ROW")) %>%
  group_by(hs6, hs2, importer_grp, year, post2018, tariff_rate,
           preus_bin, pre_us_share, stage4) %>%
  summarise(exports = sum(exports, na.rm = TRUE), .groups = "drop") %>%
  mutate(log_exports = log(exports + 1))

stopifnot(min(df100_stage$exports, na.rm = TRUE) > 0)
rm(pre_us_share, df_stage_base, imp_rank); gc()

# ------------------------------------------------------------
# Stage distribution checks (observation count vs trade value)
# ------------------------------------------------------------
table(df100_stage$stage4, useNA = "ifany")

df100_stage %>%            # distinct-hs6 composition, decent.
  distinct(hs6, stage4) %>%
  count(stage4) %>%
  mutate(share = n / sum(n))

df100_stage %>%      # trade-weighted composition, much worse. PPML may be much worse
  group_by(stage4) %>%
  summarise(exports = sum(exports), .groups = "drop") %>%
  mutate(value_share = exports / sum(exports))

# ============================================================
# 2. POOLED — stage interaction (PPML + OLS)
# ============================================================
# Standalone tariff_rate:post2018 = the Early (reference) effect.
# i(stage4, ..., ref = "Early") terms = each stage's effect RELATIVE to Early.
# So a positive S5 coefficient means late-stage goods diverted MORE than early.

m_ppml_stage <- fepois(
  exports ~ tariff_rate:post2018 +
    i(stage4, I(tariff_rate * post2018), ref = "Early") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100_stage, cluster = ~ hs6, fixef.tol = PPML_TOL
)
m_ols_stage <- feols(
  log_exports ~ tariff_rate:post2018 +
    i(stage4, I(tariff_rate * post2018), ref = "Early") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100_stage, cluster = ~ hs6
)

tab_stage <- etable(
  "PPML" = m_ppml_stage,
  "OLS"  = m_ols_stage,
  digits = 3, se.below = TRUE, fitstat = ~ n
)
print(tab_stage)

# stage terms only (cleaner view of the deviations)
etable(m_ppml_stage, m_ols_stage, keep = "stage4",
       digits = 3, se.below = TRUE)

# Absolute per-stage effects with SEs (no reference, drop standalone)
m_ppml_abs <- fepois(
  exports ~ i(stage4, I(tariff_rate * post2018)) |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df100_stage, cluster = ~ hs6, fixef.tol = PPML_TOL
)
etable(m_ppml_abs, keep = "stage4", digits = 3, se.below = TRUE)

# ============================================================
# 3. STAGE-SPECIFIC EVENT STUDIES (Early / S3 / S4 / S5)
# ============================================================
# Each event study isolates the tariff x year path for ONE stage by zeroing the
# treatment outside that stage. Reads: when did each stage's diversion happen,
# and is the pre-trend flat? Expect Early/S3 noisier (imbalance), S4/S5 cleaner.

run_stage_es <- function(stg) {
  d <- df100_stage %>% mutate(treat_stg = tariff_rate * (stage4 == stg))
  fepois(
    exports ~ i(year, treat_stg, ref = 2017) |
      hs6^importer_grp + importer_grp^year + hs2^year,
    data = d, cluster = ~ hs6, fixef.tol = PPML_TOL
  )
}

es_early <- run_stage_es("Early")
es_s3    <- run_stage_es("S3")
es_s4    <- run_stage_es("S4")
es_s5    <- run_stage_es("S5")

par(mfrow = c(2, 2))
iplot(es_early, ref.line = TRUE, main = "Early (S1+S2)", ylim = c(-2, 4)); abline(h = 0, lty = 2, col = "grey50")
iplot(es_s3,    ref.line = TRUE, main = "S3",            ylim = c(-2, 4)); abline(h = 0, lty = 2, col = "grey50")
iplot(es_s4,    ref.line = TRUE, main = "S4",            ylim = c(-2, 4)); abline(h = 0, lty = 2, col = "grey50")
iplot(es_s5,    ref.line = TRUE, main = "S5",            ylim = c(-2, 4)); abline(h = 0, lty = 2, col = "grey50")
par(mfrow = c(1, 1))

# ------------------------------------------------------------
# Objects retained:
#   tables : tab_stage
#   models : m_ppml_stage, m_ols_stage, es_early, es_s3, es_s4, es_s5
#   data   : df100_stage
# ------------------------------------------------------------

# ============================================================
# 5. ALTERNATIVE CLASSIFICATIONS (BEC, SoP) — robustness
# ============================================================
# Does the stage finding replicate under independent product taxonomies?
# BEC (capital/intermediate/consumption) and SoP (stages of processing) both
# proxy production-chain position. NOTE: both are HS92-based (df_bec/df_sop are
# built on df_hs92), so they run on an HS92 RoW panel, NOT df100_stage (HS12).
# Treat as replication: do alternative classifications show the same pattern?

# helper: drop US, attach pre-US share, aggregate to top-100 + RoW, on HS92
build_hs92_row <- function(df_in, class_var) {
  pus <- readRDS(file.path(output_path, "df_hs92.rds")) %>%
    filter(year >= 2015, year <= 2017) %>%
    group_by(hs6) %>%
    summarise(
      us_exports_pre    = sum(exports[importer == 842], na.rm = TRUE),
      world_exports_pre = sum(exports, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(pre_us_share = us_exports_pre / world_exports_pre) %>%
    select(hs6, pre_us_share)
  
  base <- df_in %>%
    filter(importer != 842) %>%
    left_join(pus, by = "hs6") %>%
    mutate(pre_us_share = replace_na(pre_us_share, 0))
  
  rank92 <- base %>%
    filter(year >= 2015, year <= 2017) %>%
    group_by(importer) %>%
    summarise(v = sum(exports), .groups = "drop") %>%
    slice_max(v, n = 100)
  
  base %>%
    mutate(importer_grp = ifelse(importer %in% rank92$importer,
                                 as.character(importer), "ROW")) %>%
    group_by(hs6, hs2, importer_grp, year, post2018, tariff_rate,
             .data[[class_var]]) %>%
    summarise(exports = sum(exports, na.rm = TRUE), .groups = "drop") %>%
    mutate(log_exports = log(exports + 1))
}

## 5a. BEC ----------------------------------------------------
# ref = "consumption" (set in build). NAs coded "Missing"; drop them here.
df_bec92 <- readRDS(file.path(output_path, "df_bec.rds")) %>%
  filter(bec != "Missing") %>%
  build_hs92_row("bec")

m_ppml_bec <- fepois(
  exports ~ tariff_rate:post2018 + i(bec, I(tariff_rate * post2018), ref = "consumption") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_bec92, cluster = ~ hs6, fixef.tol = PPML_TOL
)
m_ols_bec <- feols(
  log_exports ~ tariff_rate:post2018 + i(bec, I(tariff_rate * post2018), ref = "consumption") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_bec92, cluster = ~ hs6
)
etable("PPML BEC" = m_ppml_bec, "OLS BEC" = m_ols_bec,
       keep = "bec", digits = 3, se.below = TRUE, fitstat = ~ n)

## 5b. SoP ----------------------------------------------------
# ref = "Raw materials" (set in build). ~26 codes unmatched (~1% value); drop NAs.
df_sop92 <- readRDS(file.path(output_path, "df_sop.rds")) %>%
  filter(!is.na(sop)) %>%
  build_hs92_row("sop")

m_ppml_sop <- fepois(
  exports ~ tariff_rate:post2018 + i(sop, I(tariff_rate * post2018), ref = "Raw materials") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_sop92, cluster = ~ hs6, fixef.tol = PPML_TOL
)
m_ols_sop <- feols(
  log_exports ~ tariff_rate:post2018 + i(sop, I(tariff_rate * post2018), ref = "Raw materials") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_sop92, cluster = ~ hs6
)
etable("PPML SoP" = m_ppml_sop, "OLS SoP" = m_ols_sop,
       keep = "sop", digits = 3, se.below = TRUE, fitstat = ~ n)

# Replication read: if BEC intermediate/capital and SoP processed categories show
# the same positive concentration as GVC S4, the finding is robust across three
# independent classifications. Read PPML for high-value categories, OLS for sparse
# ones (same value-weighting caveat as the stage analysis).

# ============================================================
# OPTIONAL (end / later): stage x US-exposure split
# ============================================================
# CAUTION: this reintroduces the pre-US-exposure dimension that was sidelined in
# 02 (the exposure-as-treatment result was a COVID artifact). Splitting the stage
# analysis by exposure makes thin cells and leans on that channel. Park here as an
# exploratory check only; not a main result. hs6 clustering kept for consistency.

df_high_us <- df100_stage %>% 
  filter(preus_bin == "High US exposure")
df_low_us  <- df100_stage %>% 
  filter(preus_bin == "Low US exposure")

p_stage_high <- fepois(
  exports ~ tariff_rate:post2018 +
    i(stage4, I(tariff_rate * post2018), ref = "Early") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_high_us, cluster = ~ hs6, fixef.tol = PPML_TOL
)

p_stage_low <- fepois(
  exports ~ tariff_rate:post2018 +
    i(stage4, I(tariff_rate * post2018), ref = "Early") |
    hs6^importer_grp + importer_grp^year + hs2^year,
  data = df_low_us, cluster = ~ hs6, fixef.tol = PPML_TOL
)

 etable("PPML High US" = p_stage_high, "PPML Low US" = p_stage_low,
        keep = "stage4", digits = 3, se.below = TRUE)
 